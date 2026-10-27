"""Per-author signed chains. No global order, consensus, or claim of factual truth."""

import hashlib
import json
import re
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .storage import canonical, now

GENESIS = "0" * 64
KINDS = {"employer", "experience", "lesson", "retraction"}
EVIDENCE = {"advertised", "confirmed", "observed", "hypothesis"}
FIELDS = {"name", "claim", "source_url", "observed_at", "evidence_kind", "tags", "metrics", "supersedes"}


def validate_payload(kind, payload):
    if kind not in KINDS or not isinstance(payload, dict) or set(payload) - FIELDS:
        raise ValueError("Unknown shared kind/fields; private documents must stay local")
    if len(canonical(payload)) > 65536:
        raise ValueError("Shared record exceeds 64 KiB")
    if payload.get("evidence_kind") not in EVIDENCE:
        raise ValueError("evidence_kind must be advertised, confirmed, observed, or hypothesis")
    for field in ("claim", "source_url", "observed_at"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"Missing shared field: {field}")
    if urlparse(payload["source_url"]).scheme not in {"http", "https"}:
        raise ValueError("source_url must be an HTTP(S) source, never a private attachment")
    if "metrics" in payload and (
        not isinstance(payload["metrics"], dict)
        or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in payload["metrics"].values())
    ):
        raise ValueError("Shared metrics must contain numeric aggregate values only")
    if kind == "retraction" and not payload.get("supersedes"):
        raise ValueError("Retraction requires supersedes")


class Ledger:
    def __init__(self, store):
        self.store = store
        path = store.home / "identity.key"
        if not path.exists():
            key = Ed25519PrivateKey.generate()
            with path.open("xb") as f:
                path.chmod(0o600)
                f.write(key.private_bytes_raw())
        self.key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
        self.public_key = self.key.public_key().public_bytes_raw().hex()
        self.author_id = hashlib.sha256(bytes.fromhex(self.public_key)).hexdigest()

    @staticmethod
    def check_event(event):
        try:
            expected = {
                "version",
                "author",
                "public_key",
                "seq",
                "prev",
                "kind",
                "subject",
                "payload",
                "created_at",
                "event_id",
                "signature",
            }
            if set(event) != expected or event["version"] != 1:
                raise ValueError("Unsupported event schema")
            if type(event["seq"]) is not int or event["seq"] < 1:
                raise ValueError("Invalid sequence")
            if not isinstance(event["subject"], str) or not 1 <= len(event["subject"]) <= 300:
                raise ValueError("Invalid subject")
            if not re.fullmatch(r"[0-9a-f]{64}", event["prev"]):
                raise ValueError("Invalid previous event hash")
            public = bytes.fromhex(event["public_key"])
            if hashlib.sha256(public).hexdigest() != event["author"]:
                raise ValueError("Author fingerprint mismatch")
            validate_payload(event["kind"], event["payload"])
            body = {k: v for k, v in event.items() if k not in {"event_id", "signature"}}
            digest = hashlib.sha256(canonical(body)).hexdigest()
            if digest != event["event_id"]:
                raise ValueError("Event hash mismatch")
            Ed25519PublicKey.from_public_bytes(public).verify(
                bytes.fromhex(event["signature"]), bytes.fromhex(digest)
            )
        except (KeyError, TypeError, InvalidSignature, OverflowError) as exc:
            raise ValueError("Invalid signed event") from exc

    def publish(self, kind, subject, payload):
        validate_payload(kind, payload)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT event_id,seq FROM events WHERE author=? ORDER BY seq DESC LIMIT 1", (self.author_id,)
            ).fetchone()
            body = {
                "version": 1,
                "author": self.author_id,
                "public_key": self.public_key,
                "seq": row["seq"] + 1 if row else 1,
                "prev": row["event_id"] if row else GENESIS,
                "kind": kind,
                "subject": subject,
                "payload": payload,
                "created_at": now(),
            }
            digest = hashlib.sha256(canonical(body)).hexdigest()
            event = {**body, "event_id": digest, "signature": self.key.sign(bytes.fromhex(digest)).hex()}
            self._insert(db, event)
        return event

    def _insert(self, db, event):
        self.check_event(event)
        existing = db.execute(
            "SELECT event_id FROM events WHERE author=? AND seq=?", (event["author"], event["seq"])
        ).fetchone()
        if existing:
            if existing[0] != event["event_id"]:
                raise ValueError(f"Author fork detected at {event['author']}:{event['seq']}")
            return False
        head = db.execute(
            "SELECT seq,event_id FROM events WHERE author=? ORDER BY seq DESC LIMIT 1", (event["author"],)
        ).fetchone()
        if event["seq"] != (head[0] + 1 if head else 1) or event["prev"] != (head[1] if head else GENESIS):
            raise ValueError("Broken or incomplete author chain; import predecessors first")
        target = event["payload"].get("supersedes")
        if target:
            original = db.execute("SELECT author,subject FROM events WHERE event_id=?", (target,)).fetchone()
            if not original or original[0] != event["author"] or original[1] != event["subject"]:
                raise ValueError("Only the author may correct/retract their own record for this subject")
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?)",
            (
                event["event_id"],
                event["author"],
                event["seq"],
                event["kind"],
                event["subject"],
                canonical(event).decode(),
            ),
        )
        return True

    def import_events(self, events):
        if not isinstance(events, list) or len(events) > 1000:
            raise ValueError("Import requires at most 1000 events per batch")
        for event in events:
            self.check_event(event)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = sum(self._insert(db, e) for e in sorted(events, key=lambda e: (e["author"], e["seq"])))
        return {"imported": count}

    def export(self, after=0, limit=1000):
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid export cursor or limit")
        with self.store.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT document FROM events WHERE rowid>? ORDER BY rowid LIMIT ?", (after, limit)
                )
            ]

    def page(self, after=0, limit=200):
        # Cursor belongs to this replica. It is never an author sequence or a peer cursor.
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid export cursor or limit")
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT rowid,document FROM events WHERE rowid>? ORDER BY rowid LIMIT ?", (after, limit)
            ).fetchall()
        return {"events": [json.loads(r[1]) for r in rows], "next_cursor": rows[-1][0] if rows else after}

    def all(self):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT document FROM events ORDER BY rowid")]

    def query(self, kind=None, subject=None):
        self.verify()
        events = self.all()
        superseded = {e["payload"]["supersedes"] for e in events if e["payload"].get("supersedes")}
        return [
            e
            for e in events
            if e["event_id"] not in superseded
            and e["kind"] != "retraction"
            and (kind is None or e["kind"] == kind)
            and (subject is None or e["subject"] == subject)
        ]

    def verify(self):
        heads = {}
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM events ORDER BY rowid").fetchall()
        for row in rows:
            event = json.loads(row["document"])
            self.check_event(event)
            if any(row[field] != event[field] for field in ("event_id", "author", "seq", "kind", "subject")):
                raise ValueError("Event index differs from signed document")
            previous = heads.get(event["author"])
            if event["seq"] != (previous["seq"] + 1 if previous else 1) or event["prev"] != (
                previous["event_id"] if previous else GENESIS
            ):
                raise ValueError("Broken author chain in local storage")
            heads[event["author"]] = event
        return {
            "valid": True,
            "events": len(rows),
            "heads": {author: {"seq": e["seq"], "event_id": e["event_id"]} for author, e in heads.items()},
        }
