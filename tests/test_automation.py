from contextlib import contextmanager

import pytest

from worklife.config import Config
from worklife.server import create_server


@contextmanager
def server_at(tmp_path, connectors=None, profile=None):
    server = create_server(Config(tmp_path, connectors or {}, network_auto=False), profile=profile)
    try:
        yield server
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_automatic_checks_persist_update_and_pause_only_their_schedules(tmp_path):
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as server:
        operations = server.worklife_operations
        manual = operations.schedule_save(
            "My search",
            "jobs_search",
            {"connector": "hh", "query": "Python", "language": "en", "parameters": {"area": "1"}},
            240,
            enabled=False,
        )
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        configured = automation.configure(True, 30, check_inbox=False)
        assert configured["ready"] is True
        assert len(configured["schedules"]) == 3
        search = next(row for row in configured["schedules"] if row["tool"] == "jobs_search")
        assert search["arguments"] == manual["arguments"]
        assert all(row["interval_minutes"] == 30 and row["enabled"] for row in configured["schedules"])
        again = automation.configure(True, 30, check_inbox=False)
        assert again["schedules"] == configured["schedules"]
        paused = automation.configure(False, 30, check_inbox=False)
        assert all(not row["enabled"] for row in paused["schedules"])
        assert operations.store.get("schedule", manual["id"]) == manual
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as restarted:
        status = restarted.worklife_automation.status()
        assert status["config"]["enabled"] is False
        assert status["config"]["interval_minutes"] == 30
        assert len(status["schedules"]) == 3
        assert status["executor_required"] is True


@pytest.mark.parametrize("tool", ["jobs_search", "market_collect"])
@pytest.mark.parametrize("nullable", [False, True])
def test_active_manual_checks_are_not_run_twice_and_keep_their_controls(tmp_path, tool, nullable):
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as server:
        search = {
            "connector": "hh",
            "query": "Python",
            "parameters": None if nullable else {},
            "language": None,
        }
        manual = server.worklife_operations.schedule_save(
            "Existing search",
            tool,
            search if tool == "jobs_search" else {"name": "Existing sample", "searches": [search]},
        )
        result = server.worklife_automation.configure(True, check_inbox=False, review=False)
        assert not result["schedules"][0]["enabled"]
        assert result["schedules"][0]["covered_by"] == manual["id"]
        assert result["warnings"]
        assert server.worklife_operations.store.get("schedule", manual["id"]) == manual


def test_search_reuses_only_latest_explicit_collected_snapshot_sources(tmp_path):
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as server:
        store = server.worklife_workspace.store
        store.put(
            "market_snapshot",
            "old",
            {
                "id": "old",
                "created_at": "2026-01-01T00:00:00Z",
                "sources": [{"connector": "hh", "query": "Old", "status": "collected", "parameters": {}}],
            },
        )
        store.put(
            "market_snapshot",
            "latest",
            {
                "id": "latest",
                "created_at": "2026-02-01T00:00:00Z",
                "sources": [
                    {
                        "connector": "hh",
                        "query": "Engineer",
                        "language": "en",
                        "status": "collected",
                        "parameters": {"area": "2"},
                    },
                    {
                        "connector": "hh",
                        "query": "Hidden",
                        "status": "collected",
                        "parameters": {"key": "[СКРЫТО]"},
                        "parameters_redacted": True,
                    },
                    {"connector": "hh", "query": "No parameters", "status": "collected"},
                ],
            },
        )
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        status = automation.configure(True, check_inbox=False, review=False)
        assert len(status["schedules"]) == 1
        assert status["schedules"][0]["arguments"] == {
            "connector": "hh",
            "query": "Engineer",
            "language": "en",
            "parameters": {"area": "2"},
        }
        assert status["warnings"]


def test_run_now_uses_real_inbox_bridge_and_preserves_cursor_while_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MAIL_USER", "me@example.org")
    monkeypatch.setenv("AUTO_MAIL_PASSWORD", "fixture-password")
    config = {
        "mail": {
            "type": "email",
            "imap_host": "fixture",
            "username_env": "AUTO_MAIL_USER",
            "password_env": "AUTO_MAIL_PASSWORD",
        }
    }
    with server_at(tmp_path, config) as server:
        seen = []

        def read(name, operation, parameters):
            seen.append(dict(parameters))
            return {"messages": [], "next_after_uid": 17, "uidvalidity": "99", "errors": []}

        monkeypatch.setattr(server.worklife_connectors, "read", read)
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        automation.configure(False, check_inbox=True, refresh_search=False, review=False)
        result = automation.run()
        assert result["status"] == "success"
        assert len(result["runs"]) == 1 and result["runs"][0]["status"] == "success"
        assert len(server.worklife_workspace.store.list("schedule_run")) == 1
        assert not result["schedules"][0]["enabled"]
        again = automation.configure(False, check_inbox=True, refresh_search=False, review=False)
        assert again["schedules"][0]["arguments"]["parameters"]["after_uid"] == 17
        automation.run()
        assert seen[1]["after_uid"] == 17
        assert seen[1]["uidvalidity"] == "99"


def test_missing_mail_access_is_warning_and_run_is_not_a_success(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTO_MAIL_PASSWORD", raising=False)
    with server_at(
        tmp_path,
        {
            "mail": {
                "type": "email",
                "imap_host": "fixture",
                "username_env": "AUTO_MAIL_USER",
                "password_env": "AUTO_MAIL_PASSWORD",
            }
        },
    ) as server:
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        configured = automation.configure(True, refresh_search=False, review=False)
        assert configured["ready"] is False and configured["warnings"]
        assert configured["schedules"] == []
        assert automation.run()["status"] == "needs_setup"
        assert server.worklife_workspace.store.list("schedule_run") == []


def test_explicit_inbox_arguments_are_reused_without_guessing_http_parameters(tmp_path):
    with server_at(
        tmp_path,
        {
            "messages": {
                "type": "http",
                "operations": {"history": {"method": "GET", "path": "/history/{inbox_id}", "effect": "read"}},
            }
        },
    ) as server:
        explicit = server.worklife_operations.schedule_save(
            "My messages",
            "inbox_sync",
            {
                "connector": "messages",
                "operation": "history",
                "parameters": {"inbox_id": "explicit-id", "cursor": "page-2"},
            },
        )
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        status = automation.configure(True, refresh_search=False, review=False)
        assert len(status["schedules"]) == 1
        assert status["schedules"][0]["arguments"] == explicit["arguments"]


@pytest.mark.parametrize("profile", [None, "recruiter"])
def test_agent_goal_requires_configured_runtime_and_recruiter_cannot_schedule_it(tmp_path, profile):
    with server_at(tmp_path, profile=profile) as server:
        automation = getattr(server, "worklife_automation", None)
        assert automation is not None, "Automatic check setup is not implemented"
        with pytest.raises(ValueError):
            automation.configure(True, agent_goal="Review my search")
        assert server.worklife_workspace.store.list("schedule") == []


def test_saved_agent_goal_can_be_paused_after_model_disconnects(tmp_path, monkeypatch):
    with server_at(tmp_path) as server:
        monkeypatch.setattr(server.worklife_runtime, "status", lambda: {"configured": True})
        server.worklife_automation.configure(
            True, check_inbox=False, refresh_search=False, review=False, agent_goal="Review my search"
        )
        monkeypatch.setattr(server.worklife_runtime, "status", lambda: {"configured": False})
        paused = server.worklife_automation.configure(
            False, check_inbox=False, refresh_search=False, review=False, agent_goal="Review my search"
        )
        assert all(not row["enabled"] for row in paused["schedules"])


def test_run_now_executes_saved_search_through_connector_and_retains_result(tmp_path, monkeypatch):
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as server:
        server.worklife_operations.schedule_save(
            "Existing search",
            "jobs_search",
            {"connector": "hh", "query": "Python", "parameters": {}},
            enabled=False,
        )
        monkeypatch.setattr(
            server.worklife_connectors,
            "_request",
            lambda *args, **kwargs: {
                "items": [
                    {
                        "id": "1",
                        "name": "Python engineer",
                        "employer": {"name": "Fixture"},
                        "alternate_url": "https://example.org/jobs/1",
                    }
                ]
            },
        )
        server.worklife_automation.configure(False, check_inbox=False, review=False)
        result = server.worklife_automation.run()
        assert result["status"] == "success"
        assert result["runs"][0]["result"][0]["title"] == "Python engineer"
        assert len(server.worklife_workspace.store.list("job")) == 1


def test_invalid_saved_search_does_not_break_automatic_check_status(tmp_path):
    with server_at(tmp_path, {"hh": {"type": "hh"}}) as server:
        server.worklife_operations.schedule_save(
            "Invalid", "jobs_search", {"connector": "hh", "query": "Python", "parameters": "invalid"}
        )
        server.worklife_operations.schedule_save(
            "Valid", "jobs_search", {"connector": "hh", "query": "Python", "parameters": {}}, enabled=False
        )
        status = server.worklife_automation.status()
        assert status["sources"]["search"] == 1
        assert status["warnings"]


def test_local_api_exposes_saved_automation_and_executor_state(tmp_path):
    from starlette.testclient import TestClient

    from worklife.app import create_app

    with TestClient(create_app(Config(tmp_path, network_auto=False), scheduler=False)) as client:
        response = client.post(
            "/api/tools/automation_configure",
            json={"enabled": False, "check_inbox": False, "refresh_search": False},
            headers={"X-Worklife-Client": "local"},
        )
        assert response.json()["ok"] is True
        state = client.get("/api/state").json()
        assert state["scheduler"]["running"] is False
        assert state["automation"]["config"]["enabled"] is False
        assert len(state["automation"]["schedules"]) == 2
        run = client.post(
            "/api/tools/automation_run", json={}, headers={"X-Worklife-Client": "local"}
        ).json()["result"]
        assert run["status"] == "success" and len(run["runs"]) == 2


def test_optional_null_inbox_parameters_are_normalized_and_cursor_survives_update(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_MAIL_USER", "me@example.org")
    monkeypatch.setenv("AUTO_MAIL_PASSWORD", "fixture-password")
    with server_at(
        tmp_path,
        {
            "mail": {
                "type": "email",
                "imap_host": "fixture",
                "username_env": "AUTO_MAIL_USER",
                "password_env": "AUTO_MAIL_PASSWORD",
            }
        },
    ) as server:
        server.worklife_operations.schedule_save(
            "Mail", "inbox_sync", {"connector": "mail", "parameters": None}, enabled=False
        )
        result = server.worklife_automation.configure(True, refresh_search=False, review=False)
        assert result["ready"] is True
        server.worklife_automation.configure(True, 30, refresh_search=False, review=False)
        assert len(server.worklife_automation.status()["schedules"]) == 1


def test_worker_refreshes_enabled_checks_when_a_search_is_collected_later(tmp_path, monkeypatch):
    from worklife.cli import worker_cycle

    config = Config(tmp_path, {"hh": {"type": "hh"}}, network_auto=False)
    with server_at(tmp_path, config.connectors) as server:
        initial = server.worklife_automation.configure(True, check_inbox=False, review=False)
        assert initial["ready"] is False and not initial["schedules"]
        server.worklife_workspace.store.put(
            "market_snapshot",
            "late",
            {
                "id": "late",
                "created_at": "2026-10-28T00:00:00Z",
                "sources": [{"connector": "hh", "query": "Python", "parameters": {}, "status": "collected"}],
            },
        )
        monkeypatch.setattr(server.worklife_connectors, "_request", lambda *args, **kwargs: {"items": []})
        packet = worker_cycle(
            config,
            server.worklife_workspace,
            server.worklife_operations,
            server.worklife_network,
            server.worklife_automation,
        )
        assert len(packet["scheduled_runs"]) == 1
        assert packet["scheduled_runs"][0]["status"] == "success"
        saved = server.worklife_automation.status()["schedules"][0]
        worker_cycle(
            config,
            server.worklife_workspace,
            server.worklife_operations,
            server.worklife_network,
            server.worklife_automation,
        )
        assert server.worklife_automation.status()["schedules"][0] == saved


def test_app_dispatches_enabled_checks_from_later_saved_sources(tmp_path, monkeypatch):
    import time

    from starlette.testclient import TestClient

    from worklife.app import create_app
    from worklife.connectors import Connectors
    from worklife.workspace import Workspace

    config = Config(tmp_path, {"hh": {"type": "hh"}}, network_auto=False)
    with server_at(tmp_path, config.connectors) as server:
        server.worklife_automation.configure(True, check_inbox=False, review=False)
    from worklife.market import Market

    Market(Workspace(tmp_path)).snapshot(
        "Late", [], sources=[{"connector": "hh", "query": "Python", "parameters": {}, "status": "collected"}]
    )
    monkeypatch.setattr(Connectors, "_request", lambda *args, **kwargs: {"items": []})
    with TestClient(create_app(config)) as client:
        deadline = time.monotonic() + 2
        while True:
            state = client.get("/api/state").json()
            if state["schedule_runs"] or time.monotonic() > deadline:
                break
            time.sleep(0.01)
        assert state["scheduler"]["running"] is True
        assert len(state["schedule_runs"]) == 1
        assert state["schedule_runs"][0]["status"] == "success"
