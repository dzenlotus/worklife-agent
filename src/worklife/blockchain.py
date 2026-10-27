"""Experimental tokenless proof-of-work ordering of signed employer proposals.

Fixed 12-bit work is deliberately easy for a reference implementation, not a
production security setting. Safety assumes honest-work majority, network
connectivity and trustworthy bootstrap discovery. Monthly qualification grants
only temporary protocol rights; neither it nor confirmations prove claim truth.
There are no coins, fees, balances, reputation weights or per-key votes.
"""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import qualification
from .chain_profile import BLOCK_BITS, CONFIRMATIONS, PROFILE
from .ledger import GENESIS as EVENT_GENESIS
from .ledger import Ledger
from .storage import canonical

NETWORK = qualification.NETWORK
VERSION = 1
MAX_EVENTS = 100
MAX_BODY_BYTES = 512 * 1024
PROTOCOL = {
    "network": NETWORK,
    "version": VERSION,
    "block_bits": BLOCK_BITS,
    "confirmations": CONFIRMATIONS,
    "qualification_version": qualification.QUALIFICATION_VERSION,
    "qualification_bits": qualification.QUALIFICATION_BITS,
    "max_events": MAX_EVENTS,
    "max_body_bytes": MAX_BODY_BYTES,
    "max_future_seconds": 120,
}
GENESIS = hashlib.sha256(b"worklife:genesis\0" + canonical(PROTOCOL)).hexdigest()
FIELDS = {
    "version",
    "network",
    "parent",
    "height",
    "created_at",
    "author",
    "public_key",
    "qualification",
    "events",
    "nonce",
    "block_id",
    "signature",
}


def pow_digest(body_digest, nonce):
    """Real mining hash: SHA256(domain || SHA256(canonical body) || uint64 nonce)."""
    if not isinstance(body_digest, bytes) or len(body_digest) != 32:
        raise ValueError("Body digest must contain 32 bytes")
    if type(nonce) is not int or not 0 <= nonce < 2**64:
        raise ValueError("Invalid proof nonce")
    return hashlib.sha256(b"worklife-chain-v1:block-pow\0" + body_digest + nonce.to_bytes(8, "big")).digest()


def meets_work(digest, bits=BLOCK_BITS):
    """Leading-zero check; validation always supplies the fixed protocol bits."""
    if not isinstance(digest, bytes) or len(digest) != 32 or type(bits) is not int or not 0 <= bits <= 256:
        raise ValueError("Invalid proof digest or bit count")
    return int.from_bytes(digest, "big") < 2 ** (256 - bits)


def _time(value=None):
    moment = datetime.now(UTC) if value is None else value
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return moment.astimezone(UTC)


def _stamp(value=None):
    return _time(value).isoformat().replace("+00:00", "Z")


def _body(block):
    return {key: value for key, value in block.items() if key not in {"nonce", "block_id", "signature"}}


class Blockchain:
    def __init__(self, store, ledger):
        self.store, self.ledger = store, ledger

    @staticmethod
    def _head(blocks):
        # Equal verified work converges on the lexicographically smaller hash.
        return min(blocks, key=lambda key: (-blocks[key]["height"], key)) if blocks else GENESIS

    @staticmethod
    def _path(blocks, head):
        result = []
        while head != GENESIS:
            result.append(blocks[head])
            head = blocks[head]["parent"]
        return list(reversed(result))

    @staticmethod
    def _event_state(path):
        """Ancestors have already been fully verified in the topological read/import."""
        known, heads = {}, {}
        for ancestor in path:
            for event in ancestor["events"]:
                known[event["event_id"]] = event
                heads[event["author"]] = event
        return known, heads

    @staticmethod
    def _append_events(events, known, heads):
        for event in events:
            Ledger.check_event(event)
            if event["event_id"] in known:
                raise ValueError("Duplicate or replayed event in block ancestry")
            previous = heads.get(event["author"])
            if event["seq"] != (previous["seq"] + 1 if previous else 1) or event["prev"] != (
                previous["event_id"] if previous else EVENT_GENESIS
            ):
                raise ValueError("Broken or incomplete author chain in blocks")
            Ledger._check_correction(event, known)
            known[event["event_id"]] = event
            heads[event["author"]] = event

    def _validate(self, block, blocks):
        try:
            if not isinstance(block, dict) or set(block) != FIELDS:
                raise ValueError("Unsupported block schema")
            if (
                type(block["version"]) is not int
                or block["version"] != VERSION
                or block["network"] != NETWORK
            ):
                raise ValueError("Unsupported block protocol/network")
            if type(block["height"]) is not int or block["height"] < 1:
                raise ValueError("Invalid block height")
            parent = block["parent"]
            if parent != GENESIS and parent not in blocks:
                raise ValueError("Unknown block parent; import predecessors first")
            path = self._path(blocks, parent)
            if block["height"] != len(path) + 1:
                raise ValueError("Block height differs from parent height")
            moment = _time(block["created_at"])
            previous = _time(path[-1]["created_at"]) if path else datetime(1970, 1, 1, tzinfo=UTC)
            if moment <= previous or moment > datetime.now(UTC) + timedelta(
                seconds=PROTOCOL["max_future_seconds"]
            ):
                raise ValueError("Invalid ancestral or future block timestamp")
            if block["created_at"] != _stamp(moment):
                raise ValueError("Block timestamp must be canonical UTC")
            if not isinstance(block["events"], list) or len(block["events"]) > MAX_EVENTS:
                raise ValueError("Block requires at most 100 events")
            body = _body(block)
            encoded = canonical(body)
            if len(encoded) > MAX_BODY_BYTES:
                raise ValueError("Block body exceeds 512 KiB")
            digest = pow_digest(hashlib.sha256(encoded).digest(), block["nonce"])
            if block["block_id"] != digest.hex() or not meets_work(digest, BLOCK_BITS):
                raise ValueError("Invalid fixed-difficulty block proof")
            if type(block["signature"]) is not str or not re.fullmatch(r"[0-9a-f]{128}", block["signature"]):
                raise ValueError("Block signature must be canonical lowercase hexadecimal")
            public = bytes.fromhex(block["public_key"])
            if hashlib.sha256(public).hexdigest() != block["author"]:
                raise ValueError("Block author fingerprint mismatch")
            Ed25519PublicKey.from_public_bytes(public).verify(bytes.fromhex(block["signature"]), digest)
            rights = qualification.verify(block["qualification"], at=block["created_at"])
            if rights["author"] != block["author"]:
                raise ValueError("Qualification belongs to another block author")
            if rights["anchor"] not in {GENESIS, *(ancestor["block_id"] for ancestor in path)}:
                raise ValueError("Qualification anchor is not a block ancestor")
            known, heads = self._event_state(path)
            self._append_events(block["events"], known, heads)
        except (KeyError, TypeError, AttributeError, InvalidSignature, OverflowError) as exc:
            raise ValueError("Invalid signed block") from exc

    def _read(self, db):
        rows = db.execute("SELECT id,data FROM objects WHERE bucket='chain_blocks'").fetchall()
        try:
            documents = [(row["id"], json.loads(row["data"])) for row in rows]
            documents.sort(key=lambda row: (row[1]["height"], row[0]))
            blocks = {}
            # ponytail: full DAG validation on every read; add validated checkpoints only at measured scale.
            for identity, block in documents:
                self._validate(block, blocks)
                if identity != block["block_id"]:
                    raise ValueError("Block index differs from signed document")
                blocks[identity] = block
            return blocks
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            raise ValueError("Corrupt persisted block DAG") from exc

    def _load(self):
        with self.store.connect() as db:
            return self._read(db)

    def all(self):
        """Entire verified DAG in deterministic topological order."""
        return sorted(self._load().values(), key=lambda block: (block["height"], block["block_id"]))

    def canonical_blocks(self):
        blocks = self._load()
        return self._path(blocks, self._head(blocks))

    def page(self, after=0, limit=100):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid block cursor or limit")
        documents = self.all()[after : after + limit]
        return {"blocks": documents, "next_cursor": after + len(documents)}

    def challenge(self, at=None):
        blocks = self._load()
        return qualification.challenge(self.ledger.public_key, self._head(blocks), at=at)

    def qualify(self, at=None, max_attempts=100000):
        blocks = self._load()
        month = qualification.period(at)
        ancestors = {GENESIS, *(block["block_id"] for block in self._path(blocks, self._head(blocks)))}
        try:
            progress = self.store.get("chain_qualification_progress", self.ledger.author_id)
        except ValueError:
            progress = {}
        if (
            progress.get("network") != NETWORK
            or progress.get("month") != month
            or progress.get("anchor") not in ancestors
            or progress.get("complete")
        ):
            progress = {"network": NETWORK, "month": month, "anchor": self._head(blocks), "next_nonce": 0}
        start_nonce = progress["next_nonce"]
        try:
            certificate = qualification.qualify(
                self.ledger.key, progress["anchor"], at=at, max_attempts=max_attempts, start_nonce=start_nonce
            )
        except ValueError as exc:
            if str(exc).startswith("Qualification proof exhausted"):
                self.store.put(
                    "chain_qualification_progress",
                    self.ledger.author_id,
                    {
                        **progress,
                        "next_nonce": start_nonce + max_attempts,
                        "last_attempts": max_attempts,
                        "complete": False,
                    },
                )
            raise
        self.store.put(
            "chain_qualification_progress",
            self.ledger.author_id,
            {
                **progress,
                "next_nonce": certificate["nonce"] + 1,
                "last_attempts": certificate["nonce"] - start_nonce + 1,
                "complete": True,
            },
        )
        self.store.put("chain_qualification", self.ledger.author_id, certificate)
        return certificate

    def _rights(self, blocks, at=None):
        try:
            certificate = self.store.get("chain_qualification", self.ledger.author_id)
            rights = qualification.verify(certificate, at=at)
            if rights["author"] != self.ledger.author_id:
                raise ValueError("Foreign qualification")
            ancestors = {GENESIS, *(block["block_id"] for block in self._path(blocks, self._head(blocks)))}
            if rights["anchor"] not in ancestors:
                raise ValueError("Qualification anchor left canonical ancestry")
            return certificate, rights
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Current monthly qualification required; qualify first") from exc

    def status(self):
        blocks = self._load()
        head = self._head(blocks)
        try:
            _, rights = self._rights(blocks)
        except ValueError:
            rights = None
        return {
            "protocol": VERSION,
            "network": NETWORK,
            "profile": PROFILE,
            "rules": dict(PROTOCOL),
            "genesis": GENESIS,
            "height": blocks[head]["height"] if blocks else 0,
            "head": head,
            "cumulative_work": (blocks[head]["height"] if blocks else 0) * 2**BLOCK_BITS,
            "qualified": rights is not None,
            "qualification": rights,
            "blocks": len(blocks),
            "block_bits": BLOCK_BITS,
            "confirmations": CONFIRMATIONS,
        }

    def mine(self, events=None, max_attempts=100000, at=None):
        if type(max_attempts) is not int or not 0 <= max_attempts <= 1_000_000:
            raise ValueError("Invalid mining attempt budget")
        blocks = self._load()
        parent = self._head(blocks)
        created_at = _stamp(at)
        certificate, _ = self._rights(blocks, at=created_at)
        path = self._path(blocks, parent)
        known, heads = self._event_state(path)
        automatic = events is None
        if automatic:
            events = [event for event in self.ledger.all() if event["event_id"] not in known][:MAX_EVENTS]
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            raise ValueError("Block requires at most 100 events")
        self._append_events(events, known, heads)
        body = {
            "version": VERSION,
            "network": NETWORK,
            "parent": parent,
            "height": len(path) + 1,
            "created_at": created_at,
            "author": self.ledger.author_id,
            "public_key": self.ledger.public_key,
            "qualification": certificate,
            "events": events,
        }
        encoded = canonical(body)
        while automatic and len(encoded) > MAX_BODY_BYTES and events:
            events.pop()
            encoded = canonical(body)
        if len(encoded) > MAX_BODY_BYTES:
            raise ValueError("Block body exceeds 512 KiB")
        previous = _time(path[-1]["created_at"]) if path else datetime(1970, 1, 1, tzinfo=UTC)
        if _time(created_at) <= previous or _time(created_at) > datetime.now(UTC) + timedelta(seconds=120):
            raise ValueError("Invalid ancestral or future block timestamp")
        body_digest = hashlib.sha256(encoded).digest()
        for nonce in range(max_attempts):
            proof = pow_digest(body_digest, nonce)
            if meets_work(proof, BLOCK_BITS):
                block = {
                    **body,
                    "nonce": nonce,
                    "block_id": proof.hex(),
                    "signature": self.ledger.key.sign(proof).hex(),
                }
                imported = self.import_blocks([block])
                return {"mined": True, "attempts": nonce + 1, "block": block, "head": imported["head"]}
        return {"mined": False, "attempts": max_attempts, "block": None, "head": parent}

    def import_blocks(self, incoming):
        if not isinstance(incoming, list) or len(incoming) > 100:
            raise ValueError("Import requires at most 100 blocks per batch")
        try:
            ordered = sorted(incoming, key=lambda block: (block["height"], block["block_id"]))
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid block batch") from exc
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            blocks = self._read(db)
            previous = self._head(blocks)
            added = []
            for block in ordered:
                identity = block["block_id"]
                if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
                    raise ValueError("Invalid block identifier")
                if identity in blocks:
                    if block != blocks[identity]:
                        raise ValueError("Conflicting duplicate block")
                    continue
                self._validate(block, blocks)
                blocks[identity] = block
                added.append(block)
            head = self._head(blocks)
            for block in added:
                db.execute(
                    "INSERT INTO objects VALUES ('chain_blocks',?,?)",
                    (block["block_id"], canonical(block).decode()),
                )
            ancestors = {GENESIS, *(block["block_id"] for block in self._path(blocks, head))}
            return {
                "imported": len(added),
                "head": head,
                "height": blocks[head]["height"] if blocks else 0,
                "reorganized": previous not in ancestors,
            }

    def confirmation(self, event_id):
        path = self.canonical_blocks()
        for block in path:
            if any(event["event_id"] == event_id for event in block["events"]):
                depth = len(path) - block["height"] + 1
                return {
                    "status": "confirmed" if depth >= CONFIRMATIONS else "included",
                    "depth": depth,
                    "block_id": block["block_id"],
                    "height": block["height"],
                    "scope": "protocol_validity",
                }
        return {
            "status": "pending",
            "depth": 0,
            "block_id": None,
            "height": None,
            "scope": "protocol_validity",
        }

    def active_events(self, confirmed_only=True):
        path = self.canonical_blocks()
        eligible = path[: max(0, len(path) - CONFIRMATIONS + 1)] if confirmed_only else path
        events = [event for block in eligible for event in block["events"]]
        superseded = {
            event["payload"]["supersedes"] for event in events if event["payload"].get("supersedes")
        }
        return [
            event for event in events if event["event_id"] not in superseded and event["kind"] != "retraction"
        ]
