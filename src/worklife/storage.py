import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


class Store:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.home / "worklife.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS objects (
                    bucket TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(bucket,id));
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, author TEXT NOT NULL, seq INTEGER NOT NULL,
                    kind TEXT NOT NULL, subject TEXT NOT NULL, document TEXT NOT NULL,
                    UNIQUE(author,seq));
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, document TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def put(self, bucket, key, value):
        with self.connect() as db:
            db.execute(
                "INSERT INTO objects VALUES (?,?,?) ON CONFLICT(bucket,id) DO UPDATE SET data=excluded.data",
                (bucket, key, canonical(value).decode()),
            )
        return value

    def get(self, bucket, key):
        with self.connect() as db:
            row = db.execute("SELECT data FROM objects WHERE bucket=? AND id=?", (bucket, key)).fetchone()
        if row is None:
            raise ValueError(f"Unknown {bucket}: {key}")
        return json.loads(row[0])

    def list(self, bucket):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT data FROM objects WHERE bucket=? ORDER BY id", (bucket,))
            ]
