import asyncio
import inspect
import json
import threading

import pytest
from mcp.server.fastmcp import FastMCP

from worklife.app import normalize_result, snapshot
from worklife.config import Config
from worklife.server import create_server
from worklife.workspace import Workspace


@pytest.fixture
def server(tmp_path):
    value = create_server(Config(tmp_path))
    try:
        yield value
    finally:
        value.worklife_runtime.close()
        value.worklife_browser.close()


async def test_external_mcp_call_records_private_outcome_without_raw_profile(server):
    secret = "private-profile-value-must-not-be-in-metadata"
    result = normalize_result(
        await server.call_tool("profile_save", {"profile": {"name": secret, "facts": []}})
    )
    assert result["name"] == secret
    calls = server.worklife_workspace.store.list("tool_call")
    assert len(calls) == 1
    call = calls[0]
    assert call["tool"] == "profile_save" and call["status"] == "completed"
    assert call["started_at"] <= call["finished_at"]
    assert call["duration_seconds"] >= 0
    assert call["summary"] == "Профиль обновлён" and call["error"] is None
    assert secret not in json.dumps(call)
    assert not {"arguments", "result", "payload"} & call.keys()
    assert server.worklife_workspace.ledger.export() == []


async def test_failed_tool_records_sanitized_exception_without_argument_echo(server):
    secret = "secret-task-id"
    with pytest.raises(Exception):
        await server.call_tool("task_complete", {"task_id": secret})
    call = server.worklife_workspace.store.list("tool_call")[0]
    assert call["status"] == "failed" and call["finished_at"]
    assert call["error"].startswith("ValueError:")
    assert secret not in json.dumps(call)


async def test_saved_result_is_linked_without_copying_its_content(server):
    secret = "private-resource-name-and-notes"
    result = normalize_result(
        await server.call_tool("resource_save", {"name": secret, "kind": "source", "notes": secret})
    )
    call = server.worklife_workspace.store.list("tool_call")[0]
    assert call["related_id"] == result["id"]
    assert secret not in json.dumps(call)
    assert server.worklife_workspace.ledger.export() == []


async def test_noisy_queries_and_manual_activity_do_not_duplicate_tool_feed(server):
    for name, args in [
        ("agent_brief", {}),
        ("agent_status", {}),
        ("statistics_report", {}),
        ("records_list", {"bucket": "activity"}),
        ("knowledge_query", {}),
        ("knowledge_verify", {}),
        ("knowledge_export", {}),
        ("employer_block_status", {"domain": "example.org"}),
        ("activity_record", {"kind": "note", "summary": "An actual private observation"}),
    ]:
        await server.call_tool(name, args)
    assert server.worklife_workspace.store.list("tool_call") == []


async def test_running_external_read_is_visible_to_observer_and_finishes_with_actual_count(
    server, monkeypatch
):
    entered, release = threading.Event(), threading.Event()

    def search(*args, **kwargs):
        entered.set()
        release.wait(3)
        return [{"title": "private-title", "url": "https://example.org/?token=private-query"}]

    monkeypatch.setattr(server.worklife_connectors, "search", search)
    running = asyncio.create_task(
        asyncio.to_thread(
            asyncio.run, server.call_tool("jobs_search", {"connector": "hh", "query": "private-search"})
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        state = snapshot(server)
        assert state["mcp"]["active_calls"] == 1 and state["mcp"]["tool_calls"] == 1
        assert state["mcp"]["last_activity"]
        assert state["tool_calls"][0]["status"] == "running"
        assert state["tool_calls"][0]["finished_at"] is None
        assert "connected" not in state["mcp"]
    finally:
        release.set()
        await running
    state = snapshot(server)
    assert state["mcp"]["active_calls"] == 0
    assert state["tool_calls"][0]["summary"] == "Поиск завершён: вакансий — 1"
    assert "private-" not in json.dumps(state["tool_calls"])


async def test_uncertain_action_does_not_claim_delivery_in_tool_feed(server, monkeypatch):
    action = normalize_result(
        await server.call_tool(
            "action_draft",
            {
                "connector": "email",
                "operation": "send",
                "payload": {"to": "private@example.org", "body": "private-mail"},
                "idempotency_key": "test-action",
            },
        )
    )
    await server.call_tool("action_approve", {"action_id": action["id"]})

    def transport(*args):
        raise RuntimeError("private-provider-error-with-secret")

    monkeypatch.setattr(server.worklife_connectors, "execute", transport)
    result = normalize_result(await server.call_tool("action_execute", {"action_id": action["id"]}))
    assert result["status"] == "uncertain"
    call = next(
        row for row in server.worklife_workspace.store.list("tool_call") if row["tool"] == "action_execute"
    )
    assert "не подтвержд" in call["summary"]
    assert "отправлено" not in call["summary"].lower()
    assert "private-" not in json.dumps(call)


async def test_observed_public_decorator_preserves_tool_schema_and_signature(tmp_path, server):
    from worklife.observability import ObservedMCP

    plain = FastMCP("Plain")
    observed = ObservedMCP(Workspace(tmp_path / "decorator"), "Observed")

    def sample(name: str, enabled: bool = True, count: int = 3) -> dict:
        """An unchanged public tool description."""
        return {"name": name, "enabled": enabled, "count": count}

    plain.tool()(sample)
    wrapped = observed.tool()(sample)
    assert inspect.signature(wrapped) == inspect.signature(sample)
    assert [tool.model_dump() for tool in await observed.list_tools()] == [
        tool.model_dump() for tool in await plain.list_tools()
    ]
    assert normalize_result(await observed.call_tool("sample", {"name": "actual"}))["name"] == "actual"
    assert len(await server.list_tools()) == 65
