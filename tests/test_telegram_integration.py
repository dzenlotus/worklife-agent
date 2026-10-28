import asyncio
import sqlite3

import pytest

from worklife.chain_network import BlockchainNetwork
from worklife.config import Config, load_config
from worklife.workspace import Workspace


def test_telegram_configuration_uses_environment_references(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[network.telegram]\nchat = "@worklife_test"\n'
        'api_id_env = "MY_TG_ID"\napi_hash_env = "MY_TG_HASH"\n'
        'session_env = "MY_TG_SESSION"\n'
    )
    config = load_config(path)
    assert getattr(config, "telegram_sync", None) == {
        "chat": "@worklife_test",
        "api_id_env": "MY_TG_ID",
        "api_hash_env": "MY_TG_HASH",
        "session_env": "MY_TG_SESSION",
    }, "Telegram sync settings are not loaded"


def test_connecting_a_service_chat_persists_without_contacting_telegram(tmp_path):
    workspace = Workspace(tmp_path)
    network = BlockchainNetwork(workspace, lambda: [])
    assert hasattr(network, "connect_telegram"), "Telegram chat connection is not implemented"
    result = network.connect_telegram("-1001234567890")
    assert result["chat"] == "-1001234567890"
    reopened = BlockchainNetwork(Workspace(tmp_path), lambda: [])
    assert reopened.telegram["chat"] == "-1001234567890"
    assert reopened.status()["telegram"]["status"] == "configured"
    assert reopened.status()["status"] == "local_only"


def test_recruiter_can_connect_and_synchronize_the_public_database(tmp_path):
    from worklife.server import create_server

    server = create_server(Config(tmp_path), profile="recruiter")
    try:
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        assert {"blockchain_status", "blockchain_sync", "blockchain_telegram_connect"} <= names
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


@pytest.mark.parametrize("chat", ["", "   ", "https://other.example/path", "@", "0"])
def test_service_chat_requires_a_telegram_identifier(tmp_path, chat):
    network = BlockchainNetwork(Workspace(tmp_path), lambda: [])
    assert hasattr(network, "connect_telegram"), "Telegram chat connection is not implemented"
    with pytest.raises(ValueError, match="Telegram"):
        network.connect_telegram(chat)


def test_network_uses_telegram_without_an_http_peer_and_reports_rejections(tmp_path, monkeypatch):
    network = BlockchainNetwork(Workspace(tmp_path), lambda: [])
    network.connect_telegram("@worklife_test")

    async def sync():
        return {"status": "healthy", "pulled": 3, "pushed": 1, "rejected": 0, "pending": 0}

    monkeypatch.setattr(network, "_sync_telegram", sync)
    result = network.tick(force=True)
    assert result["status"] == "healthy"
    assert result["telegram"]["pulled"] == 3
    assert result["protected_copies"] == 1  # Telegram upload is not proof of another independent node.

    async def rejected():
        return {"status": "attention", "pulled": 1, "pushed": 0, "rejected": 1, "pending": 0}

    monkeypatch.setattr(network, "_sync_telegram", rejected)
    assert network.tick(force=True)["status"] == "attention"


def test_mcp_sync_runs_telegram_outside_the_tool_event_loop(tmp_path, monkeypatch):
    from worklife.server import create_server

    server = create_server(Config(tmp_path), profile="recruiter")
    server.worklife_network.connect_telegram("@worklife_test")

    async def sync():
        await asyncio.sleep(0)
        return {"status": "healthy", "pulled": 0, "pushed": 0, "rejected": 0, "pending": 0}

    monkeypatch.setattr(server.worklife_network, "_sync_telegram", sync)
    try:
        result = asyncio.run(server.call_tool("blockchain_sync", {}))
        assert result is not None
        assert server.worklife_network.status()["status"] == "healthy"
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_configured_telegram_starts_in_the_existing_server_network(tmp_path):
    from worklife.server import create_server

    server = create_server(Config(tmp_path, telegram_sync={"chat": "@worklife_test"}))
    try:
        assert server.worklife_network.telegram["chat"] == "@worklife_test"
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_running_network_picks_up_chat_selected_by_another_process(tmp_path, monkeypatch):
    running = BlockchainNetwork(Workspace(tmp_path), lambda: [])
    assert running.tick(force=True)["status"] == "local_only"
    BlockchainNetwork(Workspace(tmp_path), lambda: []).connect_telegram("-1001234567890")

    async def sync():
        assert running.telegram["chat"] == "-1001234567890"
        return {"status": "healthy", "pulled": 0, "pushed": 0, "rejected": 0, "pending": 0}

    monkeypatch.setattr(running, "_sync_telegram", sync)
    assert running.tick()["status"] == "healthy"


def test_chat_selection_read_failure_keeps_background_network_retryable(tmp_path, monkeypatch):
    network = BlockchainNetwork(Workspace(tmp_path), lambda: [])
    original = network.workspace.store.get

    def unavailable(bucket, key):
        if bucket == "telegram_sync_config":
            raise sqlite3.OperationalError("database temporarily unavailable")
        return original(bucket, key)

    monkeypatch.setattr(network.workspace.store, "get", unavailable)
    assert network.tick(force=True)["status"] == "attention"
    monkeypatch.setattr(network.workspace.store, "get", original)
    assert network.tick(force=True)["status"] == "local_only"
