"""Automatic, employer-only relay sync; author signatures are not proof of factual truth."""

import hashlib
import os
import sqlite3
import subprocess
import time
from uuid import uuid4

import httpx

from .ledger import GENESIS, Ledger
from .storage import canonical, now

DEFAULT_RELAY_URL = "https://raw.githubusercontent.com/dzenlotus/worklife-employers/main/snapshot.json"
DEFAULT_RELAY_REPO = "dzenlotus/worklife-employers"
INTAKE_MARKER = "<!-- worklife-employers:v1 -->\n"


def merge_events(existing, incoming):
    """Keep accepted history; isolate invalid events/forks and defer missing predecessors.

    Returns {events: verified contiguous author chains, rejected: int, pending: int,
    conflicts: ["author:sequence", ...]}. Existing history wins a conflicting fork.
    """
    accepted, known, heads = [], {}, {}
    rejected, pending, conflicts = 0, 0, []
    for batch in (existing, incoming):
        valid = []
        for event in batch:
            try:
                Ledger.check_event(event)
                valid.append(event)
            except (ValueError, TypeError):
                rejected += 1
        for event in sorted(valid, key=lambda item: (item["author"], item["seq"])):
            if event["event_id"] in known:
                continue
            head = heads.get(event["author"])
            expected = head["seq"] + 1 if head else 1
            if event["seq"] > expected:
                pending += 1
                continue
            if event["seq"] < expected or event["prev"] != (head["event_id"] if head else GENESIS):
                rejected += 1
                conflicts.append(f"{event['author']}:{event['seq']}")
                continue
            try:
                Ledger._check_correction(event, known)
            except (ValueError, TypeError):
                rejected += 1
                continue
            accepted.append(event)
            known[event["event_id"]] = event
            heads[event["author"]] = event
    return {"events": accepted, "rejected": rejected, "pending": pending, "conflicts": conflicts}


def github_token():
    """Use the user's own login; never persist or include credentials in status/errors."""
    token = os.getenv("WORKLIFE_NETWORK_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if token:
        return token.strip()
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


class NetworkManager:
    """One public read relay and an authenticated intake queue, without peer configuration."""

    LABELS = {
        "healthy": "Сеть подключена",
        "offline": "Нет связи с сетью",
        "recovering": "Данные распространяются",
        "local_only": "Данные на этом устройстве",
        "attention": "Нужна проверка данных",
    }

    def __init__(
        self,
        workspace,
        relay_url=DEFAULT_RELAY_URL,
        relay_repo=DEFAULT_RELAY_REPO,
        interval_seconds=300,
        client=None,
        token_provider=None,
    ):
        self.workspace = workspace
        self.relay_url, self.relay_repo = relay_url, relay_repo
        self.interval_seconds = interval_seconds
        self.client = client
        self.token_provider = token_provider or github_token
        self._last_attempt = None
        try:
            self.meta = workspace.store.get("network_state", "meta")
        except ValueError:
            self.meta = {}
        # A different relay cannot inherit another relay's confirmation or submission receipts.
        if self.meta.get("relay_url", relay_url) != relay_url:
            self.meta = {}
        self.meta["relay_url"] = relay_url
        self._summary = self.meta.get("summary") or {
            "status": "local_only",
            "label": self.LABELS["local_only"],
            "detail": "Синхронизация начнётся автоматически.",
            "employers": 0,
            "protected_copies": 1,
            "last_sync": None,
            "auto": True,
            "pending": 0,
        }

    def status(self):
        """Return cached state; rendering the interface never initiates network requests."""
        return dict(self._summary)

    def mark_dirty(self):
        """Invalidate an old remote confirmation immediately after a local public write."""
        self._last_attempt = None
        events = self.workspace.ledger.all()
        pending = len({event["event_id"] for event in events} - set(self.meta.get("last_remote_ids", [])))
        return self._save(
            "local_only",
            "Новые записи сохранены. Синхронизация начнётся автоматически.",
            events,
            pending=pending,
        )

    def _save(self, state, detail, events, *, local_valid=True, **extra):
        local_ids = {e["event_id"] for e in events}
        remote_ids = set(self.meta.get("last_remote_ids", []))
        confirmed = self.meta.get("last_sync") is not None and local_ids.issubset(remote_ids)
        self._summary = {
            "status": state,
            "label": self.LABELS[state],
            "detail": detail,
            "employers": len({e["subject"] for e in events if e["kind"] == "employer"}),
            "protected_copies": int(local_valid) + int(confirmed),
            "last_sync": self.meta.get("last_sync"),
            "auto": True,
            "pending": 0,
            **extra,
        }
        self.meta["summary"] = self._summary
        self.workspace.store.put("network_state", "meta", self.meta)
        return self.status()

    def tick(self, force=False):
        current = time.monotonic()
        if (
            not force
            and self._last_attempt is not None
            and current - self._last_attempt < self.interval_seconds
        ):
            return self.status()
        self._last_attempt = current
        try:
            if self.client is None:
                with httpx.Client(timeout=15, follow_redirects=True) as client:
                    return self._sync(client)
            return self._sync(self.client)
        except (ValueError, TypeError, OSError, sqlite3.DatabaseError):
            # Storage may itself be unavailable, so keep this retry status in memory.
            self._summary = {
                **self._summary,
                "status": "attention",
                "label": self.LABELS["attention"],
                "detail": "Не удалось завершить проверку общей базы. Повторим автоматически.",
            }
            return self.status()

    def _sync(self, client):
        ledger = self.workspace.ledger
        events, repaired, local_valid = [], 0, True
        try:
            events = ledger.all()
            ledger._archive_current()
        except (ValueError, TypeError, sqlite3.DatabaseError):
            try:
                repaired = ledger.repair(self.meta.get("remote_events", []))["recovered"]
                events = ledger.all()
            except (ValueError, TypeError, OSError, sqlite3.DatabaseError):
                local_valid = False
        try:
            response = client.get(self.relay_url, headers={"Accept": "application/json"})
            response.raise_for_status()
            snapshot = response.json()
            if (
                not isinstance(snapshot, dict)
                or snapshot.get("protocol") != 1
                or not isinstance(snapshot.get("events"), list)
            ):
                raise ValueError("Invalid employer relay snapshot")
        except httpx.HTTPError:
            return self._save(
                "offline" if local_valid else "attention",
                "Локальные записи доступны. Повторим соединение автоматически."
                if local_valid
                else "Повреждение обнаружено; для восстановления нужна проверенная копия.",
                events,
                local_valid=local_valid,
                repaired=repaired,
                pending=len(set(e["event_id"] for e in events) - set(self.meta.get("last_remote_ids", []))),
            )
        except (ValueError, TypeError):
            return self._save(
                "attention",
                "Сеть вернула неподходящие данные; локальная история сохранена.",
                events,
                local_valid=local_valid,
                repaired=repaired,
            )

        remote = merge_events([], snapshot["events"])
        if not local_valid:
            try:
                repaired = ledger.repair(remote["events"])["recovered"]
                events, local_valid = ledger.all(), True
            except (ValueError, TypeError, OSError, sqlite3.DatabaseError):
                return self._save(
                    "attention",
                    "Проверенной копии недостаточно для восстановления истории.",
                    [],
                    local_valid=False,
                    invalid=remote["rejected"],
                    repaired=repaired,
                )

        merged = merge_events(events, remote["events"])
        existing_ids = {event["event_id"] for event in events}
        new = [event for event in merged["events"] if event["event_id"] not in existing_ids]
        for start in range(0, len(new), 1000):
            ledger.import_events(new[start : start + 1000])
        events = ledger.all()
        accepted_ids = {e["event_id"] for e in events}
        remote_events = [e for e in remote["events"] if e["event_id"] in accepted_ids]
        remote_positions = {(e["author"], e["seq"]): e["event_id"] for e in remote_events}
        rollback = any(
            remote_positions.get((author, head["seq"])) != head["event_id"]
            for author, head in self.meta.get("remote_heads", {}).items()
        )
        remembered = merge_events(self.meta.get("remote_events", []), remote_events)["events"]
        self.meta["remote_events"] = remembered
        self.meta["remote_heads"] = {
            e["author"]: {"seq": e["seq"], "event_id": e["event_id"]}
            for e in sorted(remembered, key=lambda item: item["seq"])
        }
        self.meta["last_remote_ids"] = [e["event_id"] for e in remote_events]
        self.meta["last_sync"] = now()
        self.meta.setdefault("remote_seen_at", {}).update(
            {e["event_id"]: self.meta["last_sync"] for e in remote_events}
        )
        remote_ids = set(self.meta["last_remote_ids"])
        missing = [e for e in events if e["event_id"] not in remote_ids]
        queued, failed = self._submit(client, missing)
        invalid = remote["rejected"] + merged["rejected"]
        incomplete = remote["pending"]
        if invalid or incomplete or rollback:
            state, detail = (
                "attention",
                "Подмена или неполная история отклонена; проверенные записи сохранены.",
            )
        elif missing:
            state = "recovering" if queued and not failed else "local_only"
            detail = (
                "Записи отправлены. Ожидаем подтверждения общей копии."
                if queued and not failed
                else (
                    "Записи сохранены локально. Для отправки нужен доступ к GitHub; чтение сети уже работает."
                )
            )
        else:
            state, detail = "healthy", "Подписи проверены. Локальная и общая копии совпадают."
        return self._save(
            state,
            detail,
            events,
            pending=len(missing),
            invalid=invalid,
            incomplete=incomplete,
            rollback=rollback,
            repaired=repaired,
        )

    def _submit(self, client, events):
        # An old intake receipt must not block restoring a previously confirmed relay copy.
        submitted = {
            event_id
            for item in self.workspace.store.list("network_submission")
            if item.get("relay_repo") == self.relay_repo
            for event_id in item.get("event_ids", [])
            if item.get("submitted_at", "") >= self.meta.get("remote_seen_at", {}).get(event_id, "")
        }
        waiting = [event for event in events if event["event_id"] not in submitted]
        if not waiting:
            return len(events), False
        token = self.token_provider()
        if not token:
            return len(events) - len(waiting), True
        submissions, batch, failed = [], [], False
        for event in waiting:
            candidate = batch + [event]
            if len(self._intake_body(candidate)) >= 60000:
                if batch:
                    submissions.append((batch, [self._intake_body(batch)]))
                batch = [event]
                if len(self._intake_body(batch)) >= 60000:
                    submissions.append((batch, self._fragment_bodies(event)))
                    batch = []
            else:
                batch = candidate
        if batch:
            submissions.append((batch, [self._intake_body(batch)]))
        queued = len(events) - len(waiting)
        for batch, bodies in submissions:
            try:
                issue_numbers = []
                for body in bodies:
                    response = client.post(
                        f"https://api.github.com/repos/{self.relay_repo}/issues",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                        json={"title": f"Employer records {batch[0]['event_id'][:12]}", "body": body},
                    )
                    response.raise_for_status()
                    issue = response.json()
                    if not isinstance(issue.get("number"), int):
                        raise ValueError("Missing intake receipt")
                    issue_numbers.append(issue["number"])
                event_ids = [event["event_id"] for event in batch]
                submission_id = hashlib.sha256(canonical([self.relay_repo, event_ids])).hexdigest()
                self.workspace.store.put(
                    "network_submission",
                    submission_id,
                    {
                        "id": submission_id,
                        "relay_repo": self.relay_repo,
                        "event_ids": event_ids,
                        "issue": issue_numbers[-1],
                        "issues": issue_numbers,
                        "submitted_at": now(),
                    },
                )
                queued += len(batch)
            except (httpx.HTTPError, ValueError, TypeError):
                failed = True
        return queued, failed

    @staticmethod
    def _intake_body(events):
        return INTAKE_MARKER + canonical({"protocol": 1, "events": events}).decode()

    @staticmethod
    def _fragment_bodies(event):
        encoded, group = canonical(event).decode(), uuid4().hex
        # JSON escaping can double a chunk's length when it is put inside another JSON string.
        chunks = [encoded[start : start + 20000] for start in range(0, len(encoded), 20000)]
        return [
            INTAKE_MARKER
            + canonical(
                {
                    "protocol": 1,
                    "fragment": {
                        "event_id": event["event_id"],
                        "group": group,
                        "index": index,
                        "total": len(chunks),
                        "data": chunk,
                    },
                }
            ).decode()
            for index, chunk in enumerate(chunks)
        ]
