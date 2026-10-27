import importlib.util
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from worklife.workspace import Workspace


def runtime(tmp_path, monkeypatch, base=None, server=None):
    assert importlib.util.find_spec("worklife.agent_runtime") is not None, "Agent runtime is not implemented"
    from worklife.agent_runtime import AgentRuntime

    for key in ("BASE_URL", "MODEL", "API_KEY"):
        monkeypatch.delenv(f"WORKLIFE_AGENT_{key}", raising=False)
    if base:
        monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", base)
        monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "local-test-model")
    workspace = Workspace(tmp_path)
    return workspace, AgentRuntime(workspace, server or ToolServer(workspace))


class ToolServer:
    instructions = "Use actual tools and preserve evidence."

    def __init__(self, workspace):
        self.workspace = workspace
        self.calls = []

    async def list_tools(self):
        return [
            SimpleNamespace(
                name="save_note",
                description="Save a private note",
                inputSchema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
            SimpleNamespace(name="agent_run", description="Recursive run", inputSchema={"type": "object"}),
        ]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name != "save_note":
            raise ValueError("Unknown tool")
        value = self.workspace.store.put("research", "actual-note", {"id": "actual-note", **arguments})
        return (
            [
                SimpleNamespace(
                    text=json.dumps(value), model_dump=lambda **_: {"type": "text", "text": json.dumps(value)}
                )
            ],
            value,
        )


@contextmanager
def endpoint(responder):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(
                {"path": self.path, "payload": payload, "authorization": self.headers.get("Authorization")}
            )
            status, result = responder(payload, len(requests))
            encoded = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}/v1", requests
    finally:
        http.shutdown()
        http.server_close()
        worker.join(timeout=2)


def response(content=None, calls=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {
        "choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def tool_call(name="save_note", arguments=None):
    return {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments or {"text": "Evidence gathered"}),
        },
    }


def finished(agent, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = next(r for r in agent.status()["runs"] if r["id"] == run_id)
        if run["status"] in {"completed", "failed", "step_limit", "cancelled"}:
            return run
        time.sleep(0.01)
    pytest.fail("Agent run did not finish")


def test_runtime_calls_real_tool_and_finishes_with_observations(tmp_path, monkeypatch):
    def responder(payload, number):
        if number == 1:
            return 200, response(calls=[tool_call()])
        assert payload["messages"][-1]["role"] == "tool"
        assert "Evidence gathered" in payload["messages"][-1]["content"]
        return 200, response("Saved the actual note.")

    with endpoint(responder) as (base, requests):
        workspace, agent = runtime(tmp_path, monkeypatch, base)
        try:
            run = agent.start("Gather evidence and save a note", 4)
            assert run["status"] in {"queued", "running"}
            result = finished(agent, run["id"])
            assert result["status"] == "completed"
            assert result["final_answer"] == "Saved the actual note."
            assert len(result["steps"]) == 2
            assert result["usage"]["total_tokens"] == 30
            assert workspace.store.get("research", "actual-note")["text"] == "Evidence gathered"
            assert workspace.store.list("activity")
            assert workspace.ledger.export() == []
            assert requests[0]["path"] == "/v1/chat/completions"
            assert requests[0]["authorization"] is None
            names = {t["function"]["name"] for t in requests[0]["payload"]["tools"]}
            assert names == {"save_note"}
            assert "Use actual tools" in requests[0]["payload"]["messages"][0]["content"]
        finally:
            agent.close()


def test_runtime_requires_explicit_provider_and_model(tmp_path, monkeypatch):
    _, agent = runtime(tmp_path, monkeypatch)
    try:
        assert agent.status() == {"configured": False, "runs": []}
        with pytest.raises(ValueError, match="configur|BASE_URL"):
            agent.start("Do work")
        with pytest.raises(ValueError, match="max_steps"):
            agent.start("Do work", 31)
    finally:
        agent.close()


def test_cli_agent_run_waits_for_the_requested_work(tmp_path, monkeypatch):
    from worklife.cli import call
    from worklife.config import Config

    with endpoint(lambda *_: (200, response("Finished the requested local work"))) as (base, requests):
        monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", base)
        monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "local-test-model")
        monkeypatch.delenv("WORKLIFE_AGENT_API_KEY", raising=False)
        result = call(Config(tmp_path), "agent_run", {"goal": "Review my search", "max_steps": 2})
        assert result["status"] == "completed"
        assert len(requests) == 1


def test_worker_once_finishes_an_agent_cycle_before_exit(tmp_path, monkeypatch, capsys):
    from worklife.cli import main
    from worklife.operations import Operations

    with endpoint(lambda *_: (200, response("Reviewed the search"))) as (base, requests):
        monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", base)
        monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "local-test-model")
        monkeypatch.delenv("WORKLIFE_AGENT_API_KEY", raising=False)
        monkeypatch.delenv("WORKLIFE_CONFIG", raising=False)
        w = Workspace(tmp_path)
        Operations(w).schedule_save("Agent", "agent_cycle", {"goal": "Review my search", "max_steps": 2})
        monkeypatch.setattr("sys.argv", ["worklife", "--home", str(tmp_path), "worker", "--once"])
        main()
        assert w.store.list("agent_run")[0]["status"] == "completed"
        assert len(requests) == 1
        assert json.loads(capsys.readouterr().out)["scheduled_runs"][0]["status"] == "success"


def test_runtime_records_http_failure_without_claiming_success(tmp_path, monkeypatch):
    with endpoint(lambda *_: (503, {"error": "Temporarily unavailable"})) as (base, _):
        _, agent = runtime(tmp_path, monkeypatch, base)
        try:
            run = finished(agent, agent.start("Gather evidence")["id"])
            assert run["status"] == "failed"
            assert run["error"]
            assert run["final_answer"] is None
            assert run["finished_at"]
            assert run["steps"][0]["finished_at"]
        finally:
            agent.close()


def test_runtime_keeps_configured_api_key_out_of_private_trace_and_status(tmp_path, monkeypatch):
    secret = "test-private-key-do-not-persist"
    with endpoint(lambda *_: (200, response(f"Echoed by endpoint: {secret}"))) as (base, requests):
        monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", base)
        monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "local-test-model")
        monkeypatch.setenv("WORKLIFE_AGENT_API_KEY", secret)
        from worklife.agent_runtime import AgentRuntime

        workspace = Workspace(tmp_path)
        agent = AgentRuntime(workspace, ToolServer(workspace))
        try:
            result = finished(agent, agent.start("Save evidence")["id"])
            assert result["status"] == "completed"
            assert requests[0]["authorization"] == f"Bearer {secret}"
            assert secret not in json.dumps(agent.status())
            assert secret not in json.dumps(workspace.store.list("agent_run"))
            assert "[redacted]" in result["final_answer"]
        finally:
            agent.close()


def test_runtime_honors_cancellation_before_executing_requested_tool(tmp_path, monkeypatch):
    requested, release = threading.Event(), threading.Event()

    def responder(*_):
        requested.set()
        release.wait(3)
        return 200, response(calls=[tool_call()])

    with endpoint(responder) as (base, _):
        workspace, agent = runtime(tmp_path, monkeypatch, base)
        try:
            run = agent.start("Gather evidence")
            assert requested.wait(3)
            assert agent.cancel(run["id"])["cancel_requested"] is True
            release.set()
            assert finished(agent, run["id"])["status"] == "cancelled"
            assert workspace.store.list("research") == []
        finally:
            release.set()
            agent.close()


def test_runtime_enforces_step_cap_and_does_not_execute_hidden_tools(tmp_path, monkeypatch):
    with endpoint(lambda *_: (200, response(calls=[tool_call("agent_run")]))) as (base, requests):
        _, agent = runtime(tmp_path, monkeypatch, base)
        try:
            run = finished(agent, agent.start("Gather evidence", 2)["id"])
            assert run["status"] == "step_limit"
            assert len(requests) == 2
            assert agent.tool_server.calls == []
            assert run["steps"][0]["tool_results"][0]["error"]
        finally:
            agent.close()
