"""Employer-only signed chains. No global order, consensus, or claim of factual truth."""

import hashlib
import json
import re
import sqlite3
from urllib.parse import urlparse
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .storage import canonical, now

GENESIS = "0" * 64
KINDS = {"employer", "retraction"}
EVIDENCE = {"advertised", "confirmed", "observed", "hypothesis"}
FIELDS = {"name", "claim", "source_url", "observed_at", "evidence_kind", "tags", "metrics", "supersedes"}
EMPLOYER_METRICS = {"response_days", "hiring_stages", "test_hours", "weekly_hours", "salary_delay_days"}
EMPLOYER_TAGS = {
    "organization",
    "vacancy",
    "salary",
    "remote",
    "schedule",
    "hiring_process",
    "test_task",
    "communication",
    "payment",
    "working_conditions",
    "benefits",
}


def employer_domain(value):
    if not isinstance(value, str):
        raise ValueError("Shared subject must be an employer domain")
    domain = value.strip().rstrip(".").lower().encode("idna").decode("ascii")
    if len(domain) > 253 or not re.fullmatch(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", domain
    ):
        raise ValueError("Shared subject must be an employer domain, e.g. acme.example")
    return domain


def validate_payload(kind, payload):
    if kind not in KINDS or not isinstance(payload, dict) or set(payload) - FIELDS:
        raise ValueError(
            "Shared records are employer/retraction only; worker data and general lessons stay local"
        )
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
        or set(payload["metrics"]) - EMPLOYER_METRICS
        or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in payload["metrics"].values())
    ):
        raise ValueError(
            "Shared metrics may describe only employer response, hiring, test/work hours, pay delays"
        )
    if "tags" in payload and (
        not isinstance(payload["tags"], list)
        or any(not isinstance(tag, str) or tag not in EMPLOYER_TAGS for tag in payload["tags"])
    ):
        raise ValueError("Shared tags must describe employer topics only")
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
        self.archive_path = store.home / "employer_archive"
        self.checkpoint_path = store.home / "employer-checkpoint.json"
        # Opening a damaged workspace must leave recovery available, not bless its current rows.
        try:
            self._archive_current()
        except (ValueError, OSError, sqlite3.DatabaseError):
            pass

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
            if employer_domain(event["subject"]) != event["subject"]:
                raise ValueError("Shared subject must be a canonical employer domain")
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
        except (KeyError, TypeError, InvalidSignature, OverflowError, AttributeError) as exc:
            raise ValueError("Invalid signed event") from exc

    def publish(self, kind, subject, payload):
        self.verify()
        validate_payload(kind, payload)
        subject = employer_domain(subject)
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
        self._archive_current()
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
        self.verify()
        if not isinstance(events, list) or len(events) > 1000:
            raise ValueError("Import requires at most 1000 events per batch")
        for event in events:
            self.check_event(event)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = sum(self._insert(db, e) for e in sorted(events, key=lambda e: (e["author"], e["seq"])))
        self._archive_current()
        return {"imported": count}

    def export(self, after=0, limit=1000):
        return self.page(after, limit)["events"]

    def page(self, after=0, limit=200):
        self.verify()
        # Cursor belongs to this replica. It is never an author sequence or a peer cursor.
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid export cursor or limit")
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT rowid,document FROM events WHERE rowid>? ORDER BY rowid LIMIT ?", (after, limit)
            ).fetchall()
        return {"events": [json.loads(r[1]) for r in rows], "next_cursor": rows[-1][0] if rows else after}

    def all(self):
        self.verify()
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT document FROM events ORDER BY rowid")]

    def query(self, kind=None, subject=None):
        if subject is not None:
            subject = employer_domain(subject)
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
        known = {}
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
            self._check_correction(event, known)
            heads[event["author"]] = event
            known[event["event_id"]] = event
        self._require_checkpoint(list(known.values()))
        return {
            "valid": True,
            "events": len(rows),
            "heads": {author: {"seq": e["seq"], "event_id": e["event_id"]} for author, e in heads.items()},
        }

    @staticmethod
    def _check_correction(event, known):
        target = event["payload"].get("supersedes")
        if target:
            original = known.get(target)
            if not original or any(original[k] != event[k] for k in ("author", "subject")):
                raise ValueError("Only the author may correct/retract their own record for this subject")

    def _checkpoint(self):
        if not self.checkpoint_path.exists():
            return None
        try:
            checkpoint = json.loads(self.checkpoint_path.read_text())
            body = {k: v for k, v in checkpoint.items() if k != "signature"}
            if set(body) != {"version", "author", "public_key", "heads"} or (
                body["version"] != 1
                or body["author"] != self.author_id
                or body["public_key"] != self.public_key
                or not isinstance(body["heads"], dict)
            ):
                raise ValueError("Invalid checkpoint identity")
            self.key.public_key().verify(bytes.fromhex(checkpoint["signature"]), canonical(body))
            return body
        except (ValueError, KeyError, TypeError, AttributeError, InvalidSignature) as exc:
            raise ValueError("Invalid signed employer checkpoint") from exc

    def _require_checkpoint(self, events, archive_fallback=True):
        checkpoint = self._checkpoint()
        if checkpoint is None:
            if archive_fallback:
                from .automatic_network import merge_events

                archived, bad_paths = self._read_archive()
                verified = merge_events([], archived)
                if bad_paths or verified["rejected"] or verified["pending"]:
                    raise ValueError("Invalid or incomplete employer archive")
                positions = {(e["author"], e["seq"]): e["event_id"] for e in events}
                if any(positions.get((e["author"], e["seq"])) != e["event_id"] for e in archived):
                    raise ValueError("Employer archive detects missing or changed author history")
            return
        by_position = {(e["author"], e["seq"]): e["event_id"] for e in events}
        for author, head in checkpoint["heads"].items():
            if by_position.get((author, head["seq"])) != head["event_id"]:
                raise ValueError("Employer checkpoint detects missing or changed author history")

    def _archive_current(self):
        integrity = self.verify()
        with self.store.connect() as db:
            events = [json.loads(row[0]) for row in db.execute("SELECT document FROM events ORDER BY rowid")]
        self.archive_path.mkdir(exist_ok=True, mode=0o700)
        for event in events:
            path = self.archive_path / f"{event['event_id']}.json"
            encoded = canonical(event)
            if path.exists():
                previous = path.read_bytes()
                if previous != encoded:
                    quarantine = self.store.home / "employer_quarantine"
                    quarantine.mkdir(exist_ok=True, mode=0o700)
                    self._write_private(quarantine / f"{uuid4().hex}.archive.json", previous)
                    self._write_private(path, encoded)
            else:
                self._write_private(path, encoded)
        body = {
            "version": 1,
            "author": self.author_id,
            "public_key": self.public_key,
            "heads": integrity["heads"],
        }
        self._write_private(
            self.checkpoint_path,
            canonical(
                {
                    **body,
                    "signature": self.key.sign(canonical(body)).hex(),
                }
            ),
        )

    @staticmethod
    def _write_private(path, data):
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                temporary.chmod(0o600)
                handle.write(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def repair(self, extra_events=None):
        """Restore only employer rows, preserving identity and every private table/object."""
        from .automatic_network import merge_events

        checkpoint = self._checkpoint()
        archived, bad_paths = self._read_archive()
        if bad_paths and (not extra_events or not checkpoint):
            raise ValueError("Invalid employer archive; refusing recovery without a complete remote copy")
        merged = merge_events([], archived + (extra_events or []))
        events = merged["events"]
        # The signed checkpoint prevents a valid but older snapshot becoming a silent reset.
        self._require_checkpoint(events, archive_fallback=False)
        if (not checkpoint and not archived) or (not events and self._raw_rows()):
            raise ValueError("No complete employer checkpoint/archive available for recovery")
        if merged["rejected"] or merged["pending"]:
            archive_ids = {e["event_id"] for e in archived}
            if not archive_ids.issubset({e["event_id"] for e in events}):
                raise ValueError("Incomplete or conflicting employer archive; refusing recovery")
        quarantine = self.store.home / "employer_quarantine"
        quarantine.mkdir(exist_ok=True, mode=0o700)
        self._write_private(quarantine / f"{uuid4().hex}.json", canonical(self._raw_rows()))
        for path in bad_paths:
            self._write_private(quarantine / f"{uuid4().hex}.archive.json", path.read_bytes())
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM events")
            for event in events:
                self._insert(db, event)
        for path in bad_paths:
            path.unlink()
        self._archive_current()
        return {"recovered": len(events), "valid": True}

    def _read_archive(self):
        archived, bad_paths = [], []
        for path in sorted(self.archive_path.glob("*.json")):
            try:
                event = json.loads(path.read_text())
                self.check_event(event)
                if path.stem != event["event_id"]:
                    raise ValueError("Archive filename differs from event")
                archived.append(event)
            except (ValueError, TypeError, KeyError):
                bad_paths.append(path)
        return archived, bad_paths

    def _raw_rows(self):
        with self.store.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM events ORDER BY rowid")]
