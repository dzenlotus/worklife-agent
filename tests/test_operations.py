import json

import pytest

from worklife.workspace import Workspace


def operations(tmp_path, runner=None):
    from worklife.operations import Operations

    return Operations(Workspace(tmp_path), runner)


def test_resources_and_activity_are_private_and_persist(tmp_path):
    ops = operations(tmp_path)
    resource = ops.resource_save("HH account", "job_board", "https://hh.ru", "PRIVATE", 25)
    updated = ops.resource_save("HH account updated", "job_board", resource_id=resource["id"])
    assert updated["id"] == resource["id"]
    assert updated["created_at"] == resource["created_at"]
    event = ops.activity_record(
        "research",
        "PRIVATE research",
        resource["id"],
        {
            "cost_usd": 0.25,
            "duration_seconds": 12,
            "input_tokens": 100,
        },
    )
    restarted = operations(tmp_path)
    assert restarted.store.get("resource", resource["id"])["name"] == "HH account updated"
    assert restarted.store.get("activity", event["id"])["metrics"]["cost_usd"] == 0.25
    assert restarted.workspace.ledger.export() == []


@pytest.mark.parametrize("metrics", [{"cost": "2"}, {"tokens": True}, {"cost": float("nan")}])
def test_activity_rejects_non_numeric_metrics(tmp_path, metrics):
    with pytest.raises(ValueError, match="metrics"):
        operations(tmp_path).activity_record("research", "Checked", metrics=metrics)


def test_statistics_uses_real_pipeline_stages_and_actions(tmp_path):
    ops = operations(tmp_path)
    w = ops.workspace
    w.save_profile({"facts": [{"id": "python", "text": "Built Python", "source": "repo"}]})
    cvs = [w.create_cv(str(i), ["python"], "Developer")["id"] for i in range(2)]
    for number, stage in enumerate(("saved", "applied", "interview")):
        job = w.save_job(
            {
                "id": str(number),
                "platform": "manual",
                "title": "Engineer",
                "employer": "Acme",
                "url": "https://acme.example/jobs",
            }
        )
        w.application(job["id"], cvs[0], stage)
    w.draft_action("email", "send", {"body": "Draft only"}, "draft")
    w.create_experiment("Different headline", cvs)
    ops.resource_save("Tokens", "model", budget=5)
    ops.activity_record("analysis", "Read repository", metrics={"cost_usd": 1, "input_tokens": 80})
    ops.activity_record("analysis", "Read another", metrics={"cost_usd": 0.5, "input_tokens": 20})
    stats = ops.statistics()
    assert stats["jobs"] == 3
    assert stats["applications"] == 3
    assert stats["stage_counts"] == {"saved": 1, "applied": 1, "interview": 1}
    assert stats["actions_by_status"] == {"draft": 1}
    assert stats["cv_variants"] == 2
    assert stats["experiments"] == stats["resources"] == 1
    assert stats["activity_count"] == 2
    assert stats["metrics_totals"] == {"cost_usd": 1.5, "input_tokens": 100}


def test_schedule_persists_and_due_run_does_not_catch_up(tmp_path):
    calls = []

    def run(tool, arguments):
        calls.append((tool, arguments))
        return {"items": [{"id": "one", "title": "Engineer"}]}

    ops = operations(tmp_path, run)
    schedule = ops.schedule_save("Search", "jobs_search", {"connector": "hh"}, 30)
    restarted = operations(tmp_path, run)
    assert restarted.store.get("schedule", schedule["id"])["enabled"] is True
    due = restarted.run_due("2099-01-01T12:00:00Z")
    assert len(due) == 1
    assert due[0]["status"] == "success"
    assert due[0]["changed"] is True
    assert calls == [("jobs_search", {"connector": "hh"})]
    saved = restarted.store.get("schedule", schedule["id"])
    assert saved["next_run_at"] == "2099-01-01T12:30:00Z"
    assert saved["last_run_at"] == "2099-01-01T12:00:00Z"
    assert restarted.run_due("2099-01-01T12:00:00Z") == []
    restarted.schedule_toggle(schedule["id"], False)
    assert restarted.run_due("2099-01-01T13:00:00Z") == []
    assert restarted.schedule_toggle(schedule["id"], True)["enabled"] is True


def test_monitor_records_all_runs_but_only_changed_activity(tmp_path):
    results = [
        [{"id": "one", "title": "Engineer", "fetched_at": "2026-01-01T00:00:00Z"}],
        [{"id": "one", "title": "Engineer", "fetched_at": "2026-01-02T00:00:00Z"}],
        [{"id": "one", "title": "Senior Engineer", "fetched_at": "2026-01-03T00:00:00Z"}],
    ]
    ops = operations(tmp_path, lambda tool, arguments: results.pop(0))
    schedule = ops.schedule_save("Monitor", "jobs_search", {})
    assert ops.schedule_run(schedule["id"])["changed"] is True
    assert ops.schedule_run(schedule["id"])["changed"] is False
    assert ops.schedule_run(schedule["id"])["changed"] is True
    assert len(ops.store.list("schedule_run")) == 3
    assert len(ops.store.list("activity")) == 2
    assert ops.statistics()["metrics_totals"]["duration_seconds"] >= 0


def test_scheduler_records_failure_missing_runner_and_recovery(tmp_path):
    ops = operations(tmp_path)
    schedule = ops.schedule_save("Inbox", "connector_read", {"connector": "mail"})
    failed = ops.schedule_run(schedule["id"])
    assert failed["status"] == "failed"
    assert "runner" in failed["error"].lower()
    assert failed["result"] is None
    assert ops.schedule_run(schedule["id"])["changed"] is False
    assert len(ops.store.list("activity")) == 1
    ops.runner = lambda tool, arguments: {"messages": []}
    assert ops.schedule_run(schedule["id"])["changed"] is True
    saved = ops.store.get("schedule", schedule["id"])
    assert saved["last_status"] == "success"
    assert saved["last_error"] is None


def test_scheduler_error_is_failure_and_output_is_bounded(tmp_path):
    def fail(tool, arguments):
        raise ConnectionError("Provider offline")

    ops = operations(tmp_path, fail)
    schedule = ops.schedule_save("Search", "jobs_search", {})
    assert ops.schedule_run(schedule["id"])["error"] == "ConnectionError: Provider offline"
    ops.runner = lambda tool, arguments: {"data": "x" * 100_000}
    result = ops.schedule_run(schedule["id"])
    assert result["status"] == "success"
    assert result["result"]["truncated"] is True
    assert len(json.dumps(result["result"]).encode()) <= 32_768


@pytest.mark.parametrize(
    "tool,interval,arguments",
    [
        ("shell", 60, {}),
        ("jobs_search", 0, {}),
        ("jobs_search", 60, "shell command"),
    ],
)
def test_schedule_allowlist_and_arguments(tmp_path, tool, interval, arguments):
    with pytest.raises(ValueError):
        operations(tmp_path).schedule_save("Unsupported", tool, arguments, interval)


def test_blocklist_is_local_canonical_and_survives_restart(tmp_path):
    ops = operations(tmp_path)
    blocked = ops.block_employer(" Acme.Example. ", "PRIVATE reason", "https://acme.example/evidence")
    assert blocked["domain"] == "acme.example"
    assert blocked["blocked"] is True
    assert blocked["at"]
    restarted = operations(tmp_path)
    assert restarted.employer_block_status("ACME.EXAMPLE")["reason"] == "PRIVATE reason"
    assert restarted.employer_block_status("other.example")["blocked"] is False
    assert restarted.workspace.ledger.export() == []
    assert restarted.block_employer("acme.example", "Cleared", blocked=False)["blocked"] is False
    with pytest.raises(ValueError, match="domain"):
        restarted.block_employer("worker-name", "Not an employer")
