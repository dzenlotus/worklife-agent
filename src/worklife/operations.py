"""Private resources, activity, scheduled operations, and employer exclusions."""

import hashlib
import json
import math
import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .ledger import employer_domain
from .storage import canonical, now

SCHEDULE_TOOLS = {
    "jobs_search",
    "connector_read",
    "peer_sync",
    "repository_analyze",
    "reminder",
    "agent_cycle",
}
MAX_OUTPUT_BYTES = 32_768


def _timestamp(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp requires a timezone")
    return result.astimezone(UTC)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _meaningful(value):
    if isinstance(value, dict):
        return {
            key: _meaningful(item)
            for key, item in value.items()
            if key
            not in {
                "fetched_at",
                "checked_at",
                "last_checked_at",
                "duration_seconds",
                "elapsed_seconds",
                "analyzed_at",
            }
        }
    if isinstance(value, list):
        return [_meaningful(item) for item in value]
    return value


class Operations:
    def __init__(self, workspace, runner=None):
        self.workspace, self.store, self.runner = workspace, workspace.store, runner
        # ponytail: one process-local lock; the local app owns its scheduler worker.
        self._lock = threading.RLock()

    def resource_save(self, name, kind, url="", notes="", budget=None, resource_id=None):
        if budget is not None and not _number(budget):
            raise ValueError("Resource budget must be a finite nonnegative number")
        previous = self.store.get("resource", resource_id) if resource_id else {}
        value = {
            "id": resource_id or uuid4().hex,
            "name": _text(name, "Resource name"),
            "kind": _text(kind, "Resource kind"),
            "url": url,
            "notes": notes,
            "budget": budget,
            "created_at": previous.get("created_at", now()),
        }
        return self.store.put("resource", value["id"], value)

    def activity_record(self, kind, summary, related_id=None, metrics=None):
        metrics = {} if metrics is None else metrics
        if not isinstance(metrics, dict) or any(
            not isinstance(key, str) or not key or not _number(value) for key, value in metrics.items()
        ):
            raise ValueError("Activity metrics must contain finite nonnegative numeric values")
        value = {
            "id": uuid4().hex,
            "kind": _text(kind, "Activity kind"),
            "summary": _text(summary, "Activity summary")[:4000],
            "related_id": related_id,
            "metrics": metrics,
            "at": now(),
        }
        return self.store.put("activity", value["id"], value)

    def statistics(self):
        applications, activity = self.store.list("application"), self.store.list("activity")
        runs = self.store.list("schedule_run")
        totals = Counter()
        for event in activity:
            totals.update(event.get("metrics", {}))
        for run in runs:
            totals["duration_seconds"] += run["duration_seconds"]
        return {
            "jobs": len(self.store.list("job")),
            "applications": len(applications),
            "stage_counts": dict(Counter(row["stage"] for row in applications)),
            "actions_by_status": dict(Counter(row["status"] for row in self.workspace.actions())),
            "cv_variants": len(self.store.list("cv")),
            "experiments": len(self.store.list("experiment")),
            "resources": len(self.store.list("resource")),
            "activity_count": len(activity),
            "metrics_totals": dict(totals),
        }

    def schedule_save(self, name, tool, arguments, interval_minutes=60, enabled=True, schedule_id=None):
        if tool not in SCHEDULE_TOOLS:
            raise ValueError(f"Supported scheduled tools: {', '.join(sorted(SCHEDULE_TOOLS))}")
        if not isinstance(arguments, dict):
            raise ValueError("Scheduled arguments must be a JSON object")
        if not _number(interval_minutes) or interval_minutes <= 0:
            raise ValueError("Schedule interval_minutes must be positive and finite")
        if not isinstance(enabled, bool):
            raise ValueError("Schedule enabled must be boolean")
        arguments = json.loads(canonical(arguments))
        with self._lock:
            previous = self.store.get("schedule", schedule_id) if schedule_id else {}
            value = {
                **previous,
                "id": schedule_id or uuid4().hex,
                "name": _text(name, "Schedule name"),
                "tool": tool,
                "arguments": arguments,
                "interval_minutes": interval_minutes,
                "enabled": enabled,
                "next_run_at": now(),
                "last_run_at": previous.get("last_run_at"),
                "last_status": previous.get("last_status"),
                "last_error": previous.get("last_error"),
            }
            if (tool, arguments) != (previous.get("tool"), previous.get("arguments")):
                value.pop("last_result_digest", None)
            return self.store.put("schedule", value["id"], value)

    def schedule_toggle(self, schedule_id, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Schedule enabled must be boolean")
        with self._lock:
            value = self.store.get("schedule", schedule_id)
            if enabled and not value["enabled"]:
                value["next_run_at"] = now()
            value["enabled"] = enabled
            return self.store.put("schedule", schedule_id, value)

    def schedule_run(self, schedule_id, at=None):
        with self._lock:
            schedule = self.store.get("schedule", schedule_id)
            started_at = _timestamp(at or now())
            started = time.monotonic()
            result, error = None, None
            try:
                if schedule["tool"] not in SCHEDULE_TOOLS:
                    raise ValueError("Unsupported scheduled tool")
                if self.runner is None:
                    raise RuntimeError("Scheduler runner is not configured")
                result = self.runner(schedule["tool"], json.loads(canonical(schedule["arguments"])))
                encoded = canonical(result)
                meaningful = result
                if schedule["tool"] == "peer_sync" and isinstance(result, dict):
                    meaningful = {
                        key: item for key, item in result.items() if key not in {"pulled", "pushed"}
                    }
                digest = hashlib.sha256(canonical({"status": "success", "result": _meaningful(meaningful)}))
                if len(encoded) > MAX_OUTPUT_BYTES:
                    result = {"truncated": True, "bytes": len(encoded), "preview": encoded.decode()[:4096]}
                status = "success"
            except Exception as exc:
                result, status = None, "failed"
                error = f"{type(exc).__name__}: {exc}"[:2000]
                digest = hashlib.sha256(canonical({"status": status, "error": error}))
            duration = time.monotonic() - started
            changed = digest.hexdigest() != schedule.get("last_result_digest")
            run = {
                "id": uuid4().hex,
                "schedule_id": schedule_id,
                "tool": schedule["tool"],
                "started_at": _iso(started_at),
                "finished_at": _iso(started_at + timedelta(seconds=duration)),
                "status": status,
                "changed": changed,
                "result": result,
                "error": error,
                "duration_seconds": duration,
            }
            self.store.put("schedule_run", run["id"], run)
            schedule.update(
                last_run_at=_iso(started_at),
                next_run_at=_iso(started_at + timedelta(minutes=schedule["interval_minutes"])),
                last_status=status,
                last_error=error,
                last_result_digest=digest.hexdigest(),
            )
            self.store.put("schedule", schedule_id, schedule)
            if changed:
                self.activity_record(
                    "schedule_failed" if error else "schedule_changed",
                    f"{schedule['name']}: {error or 'result changed'}",
                    schedule_id,
                )
            return run

    def run_due(self, at=None):
        at = _timestamp(at or now())
        with self._lock:
            return [
                self.schedule_run(schedule["id"], at)
                for schedule in self.store.list("schedule")
                if schedule["enabled"] and _timestamp(schedule["next_run_at"]) <= at
            ]

    def block_employer(self, domain, reason, evidence_url="", blocked=True):
        domain = employer_domain(domain)
        if not isinstance(blocked, bool):
            raise ValueError("Employer blocked must be boolean")
        value = {
            "id": domain,
            "domain": domain,
            "blocked": blocked,
            "reason": _text(reason, "Blocklist reason"),
            "evidence_url": evidence_url,
            "at": now(),
        }
        return self.store.put("employer_block", domain, value)

    def employer_block_status(self, domain):
        domain = employer_domain(domain)
        try:
            return self.store.get("employer_block", domain)
        except ValueError:
            return {
                "id": domain,
                "domain": domain,
                "blocked": False,
                "reason": "",
                "evidence_url": "",
                "at": None,
            }
