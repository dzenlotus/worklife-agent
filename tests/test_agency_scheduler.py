from worklife.config import Config
from worklife.server import create_server


def test_market_monitor_preserves_snapshots_but_is_quiet_without_new_information(tmp_path, monkeypatch):
    server = create_server(Config(tmp_path))
    w = server.worklife_workspace
    salary = [100]

    def search(*args, **kwargs):
        return [
            w.save_job(
                {
                    "id": "1",
                    "platform": "fixture",
                    "title": "Python",
                    "employer": "Example",
                    "url": "https://example.org/job/1",
                    "salary_min": salary[0],
                    "salary_max": salary[0] + 100,
                    "currency": "RUB",
                    "salary_period": "month",
                    "salary_gross": True,
                }
            )
        ]

    monkeypatch.setattr(server.worklife_connectors, "search", search)
    try:
        schedule = server.worklife_operations.schedule_save(
            "Market",
            "market_collect",
            {
                "name": "Python",
                "searches": [{"connector": "fixture", "query": "Python"}],
                "scope": {"role": "Python"},
            },
        )
        first = server.worklife_operations.schedule_run(schedule["id"])
        second = server.worklife_operations.schedule_run(schedule["id"])
        assert first["status"] == second["status"] == "success"
        assert first["changed"] is True and second["changed"] is False
        assert len(server.worklife_market.snapshots()) == 2
        salary[0] = 200
        assert server.worklife_operations.schedule_run(schedule["id"])["changed"] is True
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_scheduled_inbox_retains_cursor_before_truncation_and_stays_quiet_on_empty(tmp_path, monkeypatch):
    server = create_server(Config(tmp_path))
    seen = []

    def sync(connector, parameters=None, **kwargs):
        seen.append(parameters)
        if len(seen) == 1:
            return {
                "status": "ready",
                "imported": 1,
                "errors": [],
                "messages": [{"id": "m1", "text": "x" * 40000}],
                "next_parameters": {"folder": "INBOX", "after_uid": 10, "uidvalidity": "77"},
            }
        return {"status": "empty", "imported": 0, "errors": [], "messages": [], "next_parameters": parameters}

    monkeypatch.setattr(server.worklife_inbox, "sync", sync)
    try:
        schedule = server.worklife_operations.schedule_save(
            "Inbox", "inbox_sync", {"connector": "fixture", "parameters": {"folder": "INBOX"}}
        )
        first = server.worklife_operations.schedule_run(schedule["id"])
        assert first["result"]["truncated"] is True
        stored = server.worklife_workspace.store.get("schedule", schedule["id"])
        assert stored["arguments"]["parameters"]["after_uid"] == 10
        second = server.worklife_operations.schedule_run(schedule["id"])
        assert seen[1]["uidvalidity"] == "77"
        assert second["changed"] is False
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()
