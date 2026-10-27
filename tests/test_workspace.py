import json

import pytest


def test_personal_workflow(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    w.save_profile(
        {
            "name": "Alex",
            "constraints": {
                "remote": True,
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "year",
                "max_hours": 32,
            },
            "facts": [{"id": "python", "text": "Built Python APIs", "source": "portfolio"}],
        }
    )
    cv = w.create_cv("Backend", ["python"], "Python developer")
    assert "Built Python APIs" in cv["markdown"]
    with pytest.raises(ValueError):
        w.create_cv("Fake", ["invented"], "CEO")
    job = w.save_job(
        {
            "id": "remote",
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "url": "https://example.org/jobs/1",
            "remote": True,
            "salary_min": 120,
            "salary_max": 150,
            "currency": "EUR",
            "salary_period": "year",
            "hours": 30,
        }
    )
    assert w.assess_job(job["id"])["decision"] == "consider"
    bad = w.save_job({**job, "id": "office", "remote": False})
    assert w.assess_job(bad["id"])["decision"] == "reject"
    unknown = w.save_job({**job, "id": "unknown", "remote": None})
    assert w.assess_job(unknown["id"])["decision"] == "clarify"
    app = w.application(job["id"], cv["id"], "saved")
    assert w.application(job["id"], cv["id"], "interview")["id"] == app["id"]
    experiment = w.create_experiment(
        "Clear headline improves replies",
        [cv["id"], w.create_cv("Second", ["python"], "Backend engineer")["id"]],
        "reply",
        24,
    )
    assignment = w.assign_experiment(experiment["id"], job["id"])
    assert w.assign_experiment(experiment["id"], job["id"]) == assignment
    with pytest.raises(ValueError):
        w.assign_experiment(experiment["id"], job["id"], assignment["variant_id"] + "bad")
    w.record_outcome(experiment["id"], job["id"], "reply")
    report = w.experiment_report(experiment["id"])
    assert sum(r["replies"] for r in report["variants"]) == 1
    assert report["conclusion"] == "insufficient_data"
    task = w.add_task("Ask salary", job["id"], "2026-11-01T10:00:00Z")
    assert task["id"] in [t["id"] for t in w.due_tasks("2026-11-02T00:00:00Z")]
    assert "facts" not in json.dumps(w.ledger.export())


def test_actions_are_explicit_and_do_not_resend(tmp_path):
    from worklife.workspace import Workspace

    w = Workspace(tmp_path)
    action = w.draft_action("email", "send", {"to": "a@example.org", "body": "Hello"}, "one")
    assert w.draft_action("email", "send", action["payload"], "one")["id"] == action["id"]
    with pytest.raises(ValueError):
        w.draft_action("email", "send", {"body": "changed"}, "one")
    calls = []

    def execute(connector, operation, payload):
        calls.append(payload)
        return {"message_id": "123"}

    with pytest.raises(ValueError, match="approve"):
        w.execute_action(action["id"], execute)
    w.approve_action(action["id"])
    assert w.execute_action(action["id"], execute)["status"] == "sent"
    assert w.execute_action(action["id"], execute)["status"] == "sent"
    assert len(calls) == 1
    second = w.draft_action("email", "send", {"body": "second"}, "two")
    w.approve_action(second["id"])

    def timeout(*args):
        raise TimeoutError("Connection lost after submission")

    assert w.execute_action(second["id"], timeout)["status"] == "uncertain"
    with pytest.raises(ValueError):
        w.execute_action(second["id"], execute)


def test_signed_network_replicates_and_rejects_tampering(tmp_path):
    from worklife.workspace import Workspace

    a, b, c = [Workspace(tmp_path / name) for name in "abc"]
    event = a.ledger.publish(
        "employer",
        "acme.example",
        {
            "name": "Acme",
            "claim": "Remote work advertised",
            "source_url": "https://acme.example/jobs",
            "evidence_kind": "advertised",
            "observed_at": "2026-10-27T10:00:00Z",
        },
    )
    b.ledger.import_events(a.ledger.export())
    c.ledger.import_events(b.ledger.export())
    assert c.ledger.verify()["events"] == 1
    assert c.ledger.query("employer", "acme.example")[0]["event_id"] == event["event_id"]
    changed = json.loads(json.dumps(event))
    changed["payload"]["claim"] = "Forged!"
    with pytest.raises(ValueError):
        b.ledger.import_events([changed])
    assert b.ledger.verify()["events"] == 1
    a.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Replied within 2 days",
            "evidence_kind": "observed",
            "observed_at": "2026-10-27T10:00:00Z",
            "source_url": "https://acme.example",
        },
    )
    with pytest.raises(ValueError, match="chain"):
        Workspace(tmp_path / "empty").ledger.import_events(a.ledger.export()[1:])
    c.ledger.import_events(a.ledger.export())
    assert c.ledger.verify()["events"] == 2
    b.trust_author(a.ledger.author_id, "trusted", "Known participant")
    assert b.shared_records("employer", "acme.example")[0]["trust"] == "trusted"
    assert c.shared_records("employer", "acme.example")[0]["trust"] == "unknown"


def test_backup_restores_identity_private_state_and_public_log(tmp_path):
    from worklife.workspace import Workspace

    a = Workspace(tmp_path / "a")
    a.save_profile({"name": "Alex", "facts": []})
    a.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Employer may offer flexible working hours; hypothesis only",
            "evidence_kind": "hypothesis",
            "observed_at": "2026-10-27T10:00:00Z",
            "source_url": "https://example.org",
        },
    )
    backup = a.backup(tmp_path / "backup")
    b = Workspace.restore(backup, tmp_path / "restored")
    assert b.ledger.author_id == a.ledger.author_id
    assert b.get_profile()["name"] == "Alex"
    assert b.ledger.verify()["events"] == 1
