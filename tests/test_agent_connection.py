import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from worklife.agent_runtime import AgentRuntime
from worklife.config import Config
from worklife.credentials import Credentials
from worklife.workspace import Workspace


class MemoryBackend:
    def __init__(self):
        self.values = {}

    def set_password(self, service, name, secret):
        self.values[service, name] = secret

    def get_password(self, service, name):
        return self.values.get((service, name))


@pytest.fixture
def connection(tmp_path, monkeypatch):
    for name in ("BASE_URL", "MODEL", "API_KEY"):
        monkeypatch.delenv("WORKLIFE_AGENT_" + name, raising=False)
    backend = MemoryBackend()
    monkeypatch.setattr(
        "worklife.agent_runtime.Credentials", lambda w: Credentials(w, backend), raising=False
    )
    w = Workspace(tmp_path)
    agent = AgentRuntime(w, SimpleNamespace())
    try:
        yield w, agent, backend
    finally:
        agent.close()


def test_connection_reports_no_secret_or_implicit_provider(connection):
    _, agent, _ = connection
    assert agent.connection() == {
        "base_url": "",
        "model": "",
        "has_key": False,
        "configured": False,
        "source": "none",
    }
    assert agent.status() == {"configured": False, "runs": []}


def test_local_connection_persists_and_blank_environment_uses_saved(connection, monkeypatch):
    w, agent, backend = connection
    assert agent.configure("http://localhost:1234/v1/", "local-model")["configured"]
    path = w.home / "agent-model.json"
    assert json.loads(path.read_text())["base_url"] == "http://localhost:1234/v1"
    assert path.stat().st_mode & 0o777 == 0o600
    assert backend.values == {}
    for name in ("BASE_URL", "MODEL", "API_KEY"):
        monkeypatch.setenv("WORKLIFE_AGENT_" + name, " ")
    restarted = AgentRuntime(w, SimpleNamespace())
    try:
        assert restarted.connection() == {
            "base_url": "http://localhost:1234/v1",
            "model": "local-model",
            "has_key": False,
            "configured": True,
            "source": "saved",
        }
    finally:
        restarted.close()


def test_remote_secret_only_enters_os_backend_and_is_reused(connection, monkeypatch):
    w, agent, backend = connection
    secret = "private-api-key-never-in-json"
    info = agent.configure("https://models.example/v1", "model-one", secret)
    assert info["has_key"] and info["configured"]
    assert list(backend.values.values()) == [secret]
    assert secret not in json.dumps(info)
    assert secret not in (w.home / "agent-model.json").read_text()
    assert secret.encode() not in w.store.path.read_bytes()
    assert agent.configure("https://models.example/v1", "model-two")["has_key"]
    restarted = AgentRuntime(w, SimpleNamespace())
    try:
        assert restarted.connection()["model"] == "model-two"
        assert restarted.connection()["configured"]
        monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "environment-model")
        override = AgentRuntime(w, SimpleNamespace())
        try:
            assert override.connection()["model"] == "environment-model"
            assert override.connection()["source"] == "environment"
        finally:
            override.close()
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "base",
    [
        "file:///tmp/model",
        "https://user:password@models.example/v1",
        "https://models.example/v1?api_key=secret",
        "https://models.example/v1#key",
        "https://",
    ],
)
def test_connection_rejects_invalid_or_secret_bearing_urls(connection, base):
    _, agent, _ = connection
    with pytest.raises(ValueError):
        agent.configure(base, "model", "secret")
    assert not agent.connection()["configured"]


def test_remote_key_required_and_session_config_does_not_write(connection):
    w, agent, backend = connection
    with pytest.raises(ValueError, match="key"):
        agent.configure("https://models.example/v1", "model")
    assert (
        agent.configure("https://models.example/v1", "model", "session-secret", persist=False)["source"]
        == "session"
    )
    assert not (w.home / "agent-model.json").exists()
    assert backend.values == {}


def test_active_run_refuses_provider_change(connection, monkeypatch):
    w, agent, _ = connection
    agent.configure("http://localhost:1234/v1", "model", persist=False)
    entered, release = threading.Event(), threading.Event()

    async def loop(run_id):
        entered.set()
        await asyncio.to_thread(release.wait, 3)
        agent._finish(run_id, "completed", final_answer="done")

    monkeypatch.setattr(agent, "_loop", loop)
    run = agent.start("Do the requested work")
    try:
        assert entered.wait(2)
        with pytest.raises(ValueError, match="running|active|finish"):
            agent.configure("http://localhost:5678/v1", "other", persist=False)
        assert agent.connection()["model"] == "model"
        assert w.store.get("agent_run", run["id"])["status"] == "running"
    finally:
        release.set()


def test_models_uses_only_get_and_sanitizes_provider_errors(connection, monkeypatch):
    _, agent, _ = connection
    calls = []
    status = [200]

    def respond(request):
        calls.append(request)
        if status[0] != 200:
            return httpx.Response(status[0], json={"error": "private-api-key"})
        return httpx.Response(200, json={"data": [{"id": "beta"}, {"id": "alpha"}, {"id": "alpha"}]})

    native = httpx.Client
    monkeypatch.setattr(
        "worklife.agent_runtime.httpx.Client",
        lambda **kw: native(transport=httpx.MockTransport(respond), **kw),
    )
    assert agent.list_models("https://models.example/v1", "private-api-key") == ["alpha", "beta"]
    assert calls[0].method == "GET" and str(calls[0].url) == "https://models.example/v1/models"
    assert calls[0].headers["authorization"] == "Bearer private-api-key"
    assert calls[0].extensions["timeout"]["read"] == 10
    status[0] = 401
    with pytest.raises(ValueError) as error:
        agent.list_models("https://models.example/v1", "private-api-key")
    assert "401" in str(error.value) and "private-api-key" not in str(error.value)


def test_saved_key_only_follows_the_same_provider_origin(connection, monkeypatch):
    w, agent, _ = connection
    agent.configure("https://models.example/v1", "model", "old-provider-key")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": "model"}]})

    native = httpx.Client
    monkeypatch.setattr(
        "worklife.agent_runtime.httpx.Client",
        lambda **kw: native(transport=httpx.MockTransport(respond), **kw),
    )
    with pytest.raises(ValueError, match="key"):
        agent.list_models("https://other.example/v1")
    assert calls == []
    with pytest.raises(ValueError, match="key"):
        agent.configure("https://other.example/v1", "other-model")
    assert agent.list_models("https://models.example:443/other-path") == ["model"]
    assert calls[-1].headers["authorization"] == "Bearer old-provider-key"
    assert agent.list_models("http://localhost:1234/v1") == ["model"]
    assert "authorization" not in calls[-1].headers
    monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", "https://other.example/v1")
    restarted = AgentRuntime(w, SimpleNamespace())
    try:
        assert not restarted.connection()["has_key"]
        assert not restarted.connection()["configured"]
    finally:
        restarted.close()


def test_invalid_environment_url_does_not_disclose_url_credentials(connection, monkeypatch):
    w, _, _ = connection
    monkeypatch.setenv("WORKLIFE_AGENT_BASE_URL", "https://user:private-url-key@models.example/v1")
    monkeypatch.setenv("WORKLIFE_AGENT_MODEL", "model")
    restarted = AgentRuntime(w, SimpleNamespace())
    try:
        assert "private-url-key" not in json.dumps(restarted.connection())
        assert not restarted.connection()["configured"]
    finally:
        restarted.close()


def test_model_endpoints_keep_local_guard_and_extend_snapshot(connection, tmp_path, monkeypatch):
    from worklife.app import create_app

    monkeypatch.setattr(AgentRuntime, "list_models", lambda self, base_url, api_key=None: ["local-model"])
    headers = {"X-Worklife-Client": "local"}
    with TestClient(create_app(Config(tmp_path), scheduler=False)) as client:
        assert not client.get("/api/model").json()["configured"]
        args = {"base_url": "http://localhost:1234/v1", "model": "local-model"}
        assert client.post("/api/model", json=args).status_code == 403
        result = client.post("/api/model", json=args, headers=headers).json()
        assert result["ok"] and result["result"]["configured"]
        state = client.get("/api/state").json()["agent"]
        assert state["configured"] and state["runs"] == []
        assert state["connection"] == result["result"]
        assert client.post(
            "/api/model/models", json={"base_url": args["base_url"]}, headers=headers
        ).json() == {"ok": True, "result": ["local-model"]}
        assert client.get("/api/model", headers={"Origin": "https://other.example"}).status_code == 403
