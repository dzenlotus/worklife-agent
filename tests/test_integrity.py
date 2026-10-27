import json

import pytest


def payload(claim="Advertised terms"):
    return {
        "claim": claim,
        "evidence_kind": "advertised",
        "source_url": "https://example.org/jobs",
        "observed_at": "2026-10-27T10:00:00Z",
    }


def test_fork_and_corrections(tmp_path):
    from worklife.workspace import Workspace

    original = Workspace(tmp_path / "original")
    first = original.ledger.publish("employer", "acme", payload())
    original.backup(tmp_path / "snapshot")
    fork = Workspace.restore(tmp_path / "snapshot", tmp_path / "fork")
    second = original.ledger.publish(
        "employer", "acme", {**payload("Corrected"), "supersedes": first["event_id"]}
    )
    forked = fork.ledger.publish("employer", "acme", payload("Different history"))
    with pytest.raises(ValueError, match="fork"):
        original.ledger.import_events([forked])
    assert [e["event_id"] for e in original.ledger.query()] == [second["event_id"]]
    other = Workspace(tmp_path / "other")
    other.ledger.import_events(original.ledger.export())
    with pytest.raises(ValueError, match="author"):
        other.ledger.publish("retraction", "acme", {**payload(), "supersedes": second["event_id"]})
    original.ledger.publish("retraction", "acme", {**payload("Retracted"), "supersedes": second["event_id"]})
    assert original.ledger.query() == []
    assert original.ledger.verify()["events"] == 3


def test_local_index_tampering_is_detected(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    w.ledger.publish("employer", "acme", payload())
    with w.store.connect() as db:
        db.execute("UPDATE events SET subject='different-company'")
    with pytest.raises(ValueError, match="index"):
        w.ledger.verify()


def test_query_never_returns_locally_forged_claims(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    event = w.ledger.publish("employer", "acme", payload())
    event["payload"]["claim"] = "Forged in local database"
    with w.store.connect() as db:
        db.execute("UPDATE events SET document=?", (json.dumps(event),))
    with pytest.raises(ValueError):
        w.shared_records("employer", "acme")


def test_import_batch_is_atomic(tmp_path):
    from worklife.workspace import Workspace

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    first = a.ledger.publish("employer", "a", payload())
    second = a.ledger.publish("employer", "b", payload())
    altered = json.loads(json.dumps(second))
    altered["payload"]["claim"] = "forged"
    with pytest.raises(ValueError):
        b.ledger.import_events([first, altered])
    assert b.ledger.verify()["events"] == 0


def test_experiment_uses_submission_and_fixed_window(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    w.save_profile({"name": "A", "facts": [{"id": "f", "text": "A fact", "source": "source"}]})
    variants = [w.create_cv(str(i), ["f"], "Developer")["id"] for i in range(2)]
    experiment = w.create_experiment("Hypothesis", variants, "reply", 24)
    jobs = [
        w.save_job(
            {
                "id": str(i),
                "platform": "test",
                "title": "Engineer",
                "employer": "Acme",
                "url": "https://example.org",
            }
        )["id"]
        for i in range(3)
    ]
    for job in jobs:
        w.assign_experiment(experiment["id"], job, variants[0])
    w.record_outcome(experiment["id"], jobs[0], "applied", "2026-10-25T10:00:00Z")
    w.record_outcome(experiment["id"], jobs[0], "reply", "2026-10-25T12:00:00Z")
    w.record_outcome(experiment["id"], jobs[1], "applied", "2026-10-25T10:00:00Z")
    w.record_outcome(experiment["id"], jobs[1], "reply", "2026-10-26T12:00:00Z")
    row = w.experiment_report(experiment["id"], "2026-10-27T10:00:00Z")["variants"][0]
    assert row["assigned"] == 3 and row["mature"] == 2 and row["successes"] == 1 and row["rate"] == 0.5


def test_salary_basis_is_not_silently_compared(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    w.save_profile(
        {
            "facts": [],
            "constraints": {
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "month",
                "salary_gross": False,
            },
        }
    )
    job = w.save_job(
        {
            "id": "1",
            "platform": "test",
            "title": "Engineer",
            "employer": "Acme",
            "url": "https://example.org",
            "salary_min": 120,
            "salary_max": 150,
            "currency": "EUR",
            "salary_period": "month",
            "salary_gross": True,
        }
    )
    assert w.assess_job(job["id"])["decision"] == "clarify"
