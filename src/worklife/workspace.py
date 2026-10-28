import hashlib
import json
import math
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .languages import language_tag, search_languages
from .ledger import Ledger, employer_domain
from .storage import Store, canonical, now


def uid():
    return uuid4().hex


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp requires a timezone")
    return result.astimezone(UTC)


class Workspace:
    def __init__(self, home):
        self.store = Store(home)
        self.home = self.store.home
        self.ledger = Ledger(self.store)
        self._blockchain = None

    @property
    def blockchain(self):
        if self._blockchain is None:
            from .blockchain import Blockchain

            self._blockchain = Blockchain(self.store, self.ledger)
        return self._blockchain

    def save_profile(self, profile):
        facts = profile.get("facts", [])
        if len({f["id"] for f in facts}) != len(facts) or any(
            not f.get("text") or not f.get("source") for f in facts
        ):
            raise ValueError("Facts require unique IDs, text, and a source")
        profile = dict(profile)
        if "search_languages" in profile:
            profile["search_languages"] = search_languages(profile["search_languages"])
        if "interface_language" in profile:
            profile["interface_language"] = language_tag(profile["interface_language"])
        return self.store.put("profile", "me", profile)

    def get_profile(self):
        return self.store.get("profile", "me")

    def record_source(self, name, url, capability):
        """Remember an agent-used service automatically, without credentials/search queries."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        origin = f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "")
        existing = next((p for p in self.store.list("platform") if p.get("url") == origin), None)
        key = existing["id"] if existing else hashlib.sha256(origin.encode()).hexdigest()[:24]
        previous = existing or {}
        value = {
            **previous,
            "id": key,
            "name": (name or host)[:200],
            "url": origin,
            "capabilities": sorted(set(previous.get("capabilities", []) + [capability])),
            "notes": previous.get("notes", "Обнаружено агентом во время работы"),
            "created_at": previous.get("created_at", now()),
            "updated_at": now(),
            "discovered_by": "agent",
        }
        self.store.put("platform", key, value)
        try:
            resource = self.store.get("resource", key)
        except ValueError:
            resource = {
                "id": key,
                "kind": "source",
                "notes": "Обнаружено агентом",
                "budget": None,
                "created_at": now(),
            }
        self.store.put("resource", key, {**resource, "name": value["name"], "url": origin})
        return value

    def create_cv(self, name, fact_ids, headline, summary=""):
        profile = self.get_profile()
        facts = {f["id"]: f for f in profile.get("facts", [])}
        if not fact_ids or set(fact_ids) - facts.keys():
            raise ValueError("CV must use existing profile fact IDs")
        selected = [facts[i] for i in dict.fromkeys(fact_ids)]
        markdown = f"# {profile.get('name', '')}\n\n## {headline}\n\n"
        if summary:
            markdown += summary + "\n\n"
        markdown += "\n".join(f"- {f['text']}" for f in selected) + "\n"
        value = {
            "id": uid(),
            "name": name,
            "headline": headline,
            "summary": summary,
            "fact_ids": fact_ids,
            "facts": selected,
            "markdown": markdown,
            "created_at": now(),
            "review_required": True,
        }
        return self.store.put("cv", value["id"], value)

    def save_job(self, job):
        if not all(job.get(k) for k in ("id", "platform", "title", "employer", "url")):
            raise ValueError("Job requires id, platform, title, employer, url")
        if not isinstance(job["id"], str) or not isinstance(job["platform"], str):
            raise ValueError("Job id and platform must be strings")
        # Platform-qualified identity keeps unrelated providers' numeric IDs apart.
        key = job["id"] if job["id"].startswith(job["platform"] + ":") else f"{job['platform']}:{job['id']}"
        try:
            previous = self.store.get("job", key)
        except ValueError:
            previous = {}
        at = now()
        value = {
            **job,
            "id": key,
            "fetched_at": at,
            "last_seen_at": at,
            "first_seen_at": previous.get("first_seen_at") or previous.get("fetched_at") or at,
        }
        if "search_languages" in job or "search_languages" in previous:
            value["search_languages"] = search_languages(
                previous.get("search_languages", []) + job.get("search_languages", [])
            )
        observation = {"id": uid(), "job_id": key, "observed_at": at, "job": value}
        with self.store.connect() as db:
            for bucket, identifier, document in (
                ("job_observation", observation["id"], observation),
                ("job", key, value),
            ):
                db.execute(
                    "INSERT INTO objects VALUES (?,?,?) ON CONFLICT(bucket,id) DO UPDATE SET data=excluded.data",
                    (bucket, identifier, canonical(document).decode()),
                )
        return value

    def assess_job(self, job_id):
        job, profile = self.store.get("job", job_id), self.get_profile()
        rules = profile.get("constraints", {})
        reject, clarify = [], []
        domain = self.job_domain(job)
        if domain and self.employer_blocked(domain):
            reject.append("Employer is blocked in your local blocklist")
        if rules.get("remote") is True:
            if job.get("remote") is False:
                reject.append("Requires office attendance")
            elif job.get("remote") is not True:
                clarify.append("Confirm fully remote work")
        if rules.get("min_salary") is not None:
            if "salary_gross" in rules and job.get("salary_gross") is not rules["salary_gross"]:
                clarify.append("Confirm comparable gross/net salary basis")
            elif job.get("currency") != rules.get("currency") or job.get("salary_period") != rules.get(
                "salary_period"
            ):
                clarify.append("Confirm comparable salary currency and period")
            elif job.get("salary_max") is not None and job["salary_max"] < rules["min_salary"]:
                reject.append("Salary ceiling below your minimum")
            elif job.get("salary_min") is None or job["salary_min"] < rules["min_salary"]:
                clarify.append("Confirm salary at or above your minimum")
        for field, constraint, question in (
            ("hours", "max_hours", "weekly work hours"),
            ("hiring_stages", "max_hiring_stages", "number of hiring stages"),
            ("test_hours", "max_test_hours", "time required for the test task"),
        ):
            if rules.get(constraint) is not None:
                if job.get(field) is None:
                    clarify.append(f"Confirm {question}")
                elif job[field] > rules[constraint]:
                    reject.append(f"Exceeds your limit for {question}")
        return {
            "job_id": job_id,
            "decision": "reject" if reject else "clarify" if clarify else "consider",
            "reasons": reject,
            "questions": clarify,
            "basis": "advertised; confirm before accepting",
            "life_preferences": profile.get("life_preferences", []),
            "note": "Unstructured preferences need agent judgment; this is not a skills or employer rating",
        }

    def application(self, job_id, cv_id, stage, note=""):
        if stage not in {
            "saved",
            "applied",
            "reply",
            "interview",
            "offer",
            "accepted",
            "rejected",
            "withdrawn",
        }:
            raise ValueError("Unknown application stage")
        self.store.get("job", job_id)
        if cv_id:
            self.store.get("cv", cv_id)
        key = hashlib.sha256(job_id.encode()).hexdigest()[:24]
        try:
            previous = self.store.get("application", key)
        except ValueError:
            previous = {"id": key, "job_id": job_id, "history": [], "created_at": now()}
        value = {
            **previous,
            "cv_id": cv_id or previous.get("cv_id"),
            "stage": stage,
            "updated_at": now(),
            "history": previous["history"] + [{"stage": stage, "note": note, "at": now()}],
        }
        return self.store.put("application", key, value)

    def create_experiment(self, hypothesis, variant_ids, metric="reply", horizon_hours=168, min_samples=20):
        if not hypothesis or metric not in {"reply", "interview", "offer"}:
            raise ValueError("Hypothesis and supported metric required")
        if len(set(variant_ids)) < 2 or horizon_hours <= 0 or min_samples < 2:
            raise ValueError("At least two variants, positive horizon, and min_samples >= 2 required")
        for variant in variant_ids:
            self.store.get("cv", variant)
        value = {
            "id": uid(),
            "hypothesis": hypothesis,
            "variant_ids": list(dict.fromkeys(variant_ids)),
            "metric": metric,
            "horizon_hours": horizon_hours,
            "min_samples": min_samples,
            "created_at": now(),
            "status": "active",
        }
        return self.store.put("experiment", value["id"], value)

    def assign_experiment(self, experiment_id, job_id, variant_id=None):
        experiment = self.store.get("experiment", experiment_id)
        self.store.get("job", job_id)
        key = experiment_id + ":" + job_id
        try:
            previous = self.store.get("assignment", key)
        except ValueError:
            previous = None
        if variant_id and variant_id not in experiment["variant_ids"]:
            raise ValueError("Variant is not part of this experiment")
        if previous:
            if variant_id and previous["variant_id"] != variant_id:
                raise ValueError("Assignment is immutable; do not contaminate the experiment")
            return previous
        # Stable pseudorandom assignment, independent of job attributes/outcome.
        index = int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(experiment["variant_ids"])
        value = {
            "id": key,
            "experiment_id": experiment_id,
            "job_id": job_id,
            "variant_id": variant_id or experiment["variant_ids"][index],
            "assigned_at": now(),
            "manual_assignment": variant_id is not None,
            "exposed_at": None,
            "outcomes": [],
        }
        return self.store.put("assignment", key, value)

    def record_outcome(self, experiment_id, job_id, outcome, at=None):
        if outcome not in {"applied", "reply", "interview", "offer", "rejected", "no_reply"}:
            raise ValueError("Unknown outcome")
        at = at or now()
        timestamp(at)
        key = experiment_id + ":" + job_id
        value = self.store.get("assignment", key)
        if outcome == "applied" and not value["exposed_at"]:
            value["exposed_at"] = at
        if not any(o["outcome"] == outcome for o in value["outcomes"]):
            value["outcomes"].append({"outcome": outcome, "at": at})
        return self.store.put("assignment", key, value)

    def experiment_report(self, experiment_id, as_of=None):
        experiment = self.store.get("experiment", experiment_id)
        at = timestamp(as_of or now())
        assignments = [a for a in self.store.list("assignment") if a["experiment_id"] == experiment_id]
        variants = []
        levels = {
            "reply": {"reply", "interview", "offer"},
            "interview": {"interview", "offer"},
            "offer": {"offer"},
        }
        for variant_id in experiment["variant_ids"]:
            rows = [a for a in assignments if a["variant_id"] == variant_id]
            mature = [
                a
                for a in rows
                if a["exposed_at"]
                and (at - timestamp(a["exposed_at"])).total_seconds() >= experiment["horizon_hours"] * 3600
            ]

            def success(a):
                if not a["exposed_at"]:
                    return False
                return any(
                    o["outcome"] in levels[experiment["metric"]]
                    and 0
                    <= (timestamp(o["at"]) - timestamp(a["exposed_at"])).total_seconds()
                    <= experiment["horizon_hours"] * 3600
                    for o in a["outcomes"]
                )

            n, wins = len(mature), sum(success(a) for a in mature)
            interval = None
            if n:
                p, z = wins / n, 1.96
                center = (p + z * z / (2 * n)) / (1 + z * z / n)
                half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
                interval = [max(0, center - half), min(1, center + half)]
            variants.append(
                {
                    "variant_id": variant_id,
                    "assigned": len(rows),
                    "exposed": sum(bool(a["exposed_at"]) for a in rows),
                    "mature": n,
                    "successes": wins,
                    "rate": wins / n if n else None,
                    "wilson_95": interval,
                    "replies": sum(any(o["outcome"] in levels["reply"] for o in a["outcomes"]) for a in rows),
                }
            )
        sufficient = all(v["mature"] >= experiment["min_samples"] for v in variants)
        return {
            "experiment": experiment,
            "variants": variants,
            "conclusion": "descriptive_only" if sufficient else "insufficient_data",
            "limitations": [
                "No causal claim: job/company mix can differ",
                "Rates use only submitted applications with a complete observation window",
                "Replies after the prespecified window do not count toward the metric",
            ],
        }

    def add_task(self, title, job_id=None, due_at=None):
        if due_at:
            timestamp(due_at)
        if job_id:
            self.store.get("job", job_id)
        value = {
            "id": uid(),
            "title": title,
            "job_id": job_id,
            "due_at": due_at,
            "status": "open",
            "created_at": now(),
        }
        return self.store.put("task", value["id"], value)

    def due_tasks(self, as_of=None):
        at = timestamp(as_of or now())
        return [
            t
            for t in self.store.list("task")
            if t["status"] == "open" and (t["due_at"] is None or timestamp(t["due_at"]) <= at)
        ]

    def complete_task(self, task_id):
        value = self.store.get("task", task_id)
        return self.store.put("task", task_id, {**value, "status": "done", "completed_at": now()})

    def draft_action(self, connector, operation, payload, idempotency_key):
        if not idempotency_key or not connector or not operation:
            raise ValueError("Connector, operation, and idempotency key required")
        self.guard_employer_contact(payload)
        with self.store.connect() as db:
            row = db.execute(
                "SELECT document FROM actions WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row:
                old = json.loads(row[0])
                if (old["connector"], old["operation"], old["payload"]) != (connector, operation, payload):
                    raise ValueError("Idempotency key already used for different content")
                return old
            value = {
                "id": uid(),
                "connector": connector,
                "operation": operation,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "status": "draft",
                "created_at": now(),
            }
            db.execute(
                "INSERT INTO actions VALUES (?,?,?)",
                (value["id"], idempotency_key, canonical(value).decode()),
            )
        return value

    def actions(self):
        with self.store.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT document FROM actions ORDER BY rowid")]

    def _change_action(self, action_id, allowed, **changes):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM actions WHERE id=?", (action_id,)).fetchone()
            if not row:
                raise ValueError("Unknown action")
            value = json.loads(row[0])
            if value["status"] not in allowed:
                raise ValueError(f"Action status {value['status']}; approve a draft before execution")
            value.update(changes, updated_at=now())
            db.execute("UPDATE actions SET document=? WHERE id=?", (canonical(value).decode(), action_id))
        return value

    def approve_action(self, action_id):
        return self._change_action(action_id, {"draft"}, status="approved")

    def cancel_action(self, action_id):
        return self._change_action(action_id, {"draft", "approved"}, status="cancelled")

    def execute_action(self, action_id, executor):
        old = next((a for a in self.actions() if a["id"] == action_id), None)
        if old and old["status"] == "sent":
            return old
        if old:
            self.guard_employer_contact(old["payload"])
        action = self._change_action(action_id, {"approved"}, status="sending")
        try:
            result = executor(action["connector"], action["operation"], action["payload"])
        except Exception as exc:
            # Transport failure may happen after delivery. Do not automatically resend.
            return self._change_action(
                action_id,
                {"sending"},
                status="uncertain",
                error=f"{type(exc).__name__}; inspect the provider before reconciling",
            )
        return self._change_action(action_id, {"sending"}, status="sent", result=result)

    def employer_blocked(self, domain):
        try:
            return self.store.get("employer_block", employer_domain(domain)).get("blocked", False)
        except ValueError:
            return False

    @staticmethod
    def job_domain(job):
        value = job.get("employer_domain")
        if not value:
            url = job.get("employer_url") or (
                job.get("url") if job.get("platform") in {"manual", "browser"} else None
            )
            value = urlparse(url).hostname if url else None
        return employer_domain(value) if value else None

    def guard_employer_contact(self, payload):
        """Honor company blocks before queuing or sending, including already approved drafts."""
        from email.utils import getaddresses

        domains = [payload.get("_employer_domain")]
        if payload.get("_job_id"):
            domains.append(self.job_domain(self.store.get("job", payload["_job_id"])))
        if payload.get("vacancy_id"):
            domains += [
                self.job_domain(j)
                for j in self.store.list("job")
                if j["id"].endswith(":" + str(payload["vacancy_id"]))
            ]
        if payload.get("expected_url"):
            domains.append(urlparse(payload["expected_url"]).hostname)
        recipients = []
        for field in ("to", "cc", "bcc"):
            addresses = payload.get(field, [])
            recipients.extend([addresses] if isinstance(addresses, str) else addresses)
        domains += [address.rsplit("@", 1)[1] for _, address in getaddresses(recipients) if "@" in address]
        if any(self.employer_blocked(domain) for domain in domains if domain):
            raise ValueError("Contact prevented: employer is blocked in your local blocklist")

    def reconcile_action(self, action_id, delivered, evidence):
        if not evidence.strip():
            raise ValueError("Provider evidence is required to reconcile uncertain delivery")
        return self._change_action(
            action_id,
            {"sending", "uncertain"},
            status="sent" if delivered else "failed",
            reconciliation=evidence,
        )

    def trust_author(self, author, level, note=""):
        if level not in {"trusted", "unknown", "blocked"} or len(author) != 64:
            raise ValueError("Invalid author or trust level")
        return self.store.put("trust", author, {"id": author, "level": level, "note": note})

    def shared_records(self, kind=None, subject=None, include_blocked=False, confirmed_only=False):
        from .blockchain import CONFIRMATIONS

        trust = {t["id"]: t["level"] for t in self.store.list("trust")}
        if subject is not None:
            subject = employer_domain(subject)
        events = self.blockchain.active_events() if confirmed_only else self.ledger.query(kind, subject)
        path = self.blockchain.canonical_blocks()
        confirmations = {
            event["event_id"]: {
                "status": "confirmed" if len(path) - block["height"] + 1 >= CONFIRMATIONS else "included",
                "depth": len(path) - block["height"] + 1,
                "block_id": block["block_id"],
                "height": block["height"],
                "scope": "protocol_validity",
            }
            for block in path
            for event in block["events"]
        }
        return [
            {
                **e,
                "trust": trust.get(
                    e["author"], "self" if e["author"] == self.ledger.author_id else "unknown"
                ),
                "confirmation": confirmations.get(
                    e["event_id"], {"status": "pending", "depth": 0, "scope": "protocol_validity"}
                ),
            }
            for e in events
            if (include_blocked or trust.get(e["author"]) != "blocked")
            and (kind is None or e["kind"] == kind)
            and (subject is None or e["subject"] == subject)
        ]

    def backup(self, destination):
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        with self.store.connect() as source:
            with sqlite3.connect(destination / "worklife.sqlite3") as target:
                source.backup(target)
        shutil.copy2(self.home / "identity.key", destination / "identity.key")
        for p in destination.iterdir():
            p.chmod(0o600)
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir()}
        (destination / "manifest.json").write_bytes(canonical(manifest))
        return str(destination)

    def pending_records(self):
        """The whole unconfirmed author chain, including corrections and retractions."""
        records = []
        for event in self.ledger.all():
            confirmation = self.blockchain.confirmation(event["event_id"])
            if confirmation["status"] != "confirmed":
                records.append({**event, "confirmation": confirmation})
        return records

    @classmethod
    def restore(cls, source, destination):
        source, destination = Path(source), Path(destination)
        manifest = json.loads((source / "manifest.json").read_text())
        if set(manifest) != {"worklife.sqlite3", "identity.key"}:
            raise ValueError("Invalid backup manifest")
        for filename, digest in manifest.items():
            if hashlib.sha256((source / filename).read_bytes()).hexdigest() != digest:
                raise ValueError("Backup checksum mismatch")
        if destination.exists():
            raise ValueError("Restore destination must not exist")
        shutil.copytree(source, destination)
        result = cls(destination)
        result.ledger.verify()
        with result.store.connect() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Invalid backup database")
        return result
