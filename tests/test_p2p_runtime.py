import asyncio
import base64
import json
import os
import subprocess
import sys

import pytest


def test_transport_environment_does_not_inherit_model_credentials(tmp_path, monkeypatch):
    from worklife.p2p import transport_environment

    monkeypatch.setenv("OPENAI_API_KEY", "private-test-value")
    monkeypatch.setenv("GITHUB_TOKEN", "private-test-value")
    env = transport_environment(tmp_path)
    assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env
    assert env["WORKLIFE_P2P_HOME"] == str(tmp_path)
    assert "HOME" not in env
    assert "PATH" in env


def test_invite_binds_network_topic_and_transport_key():
    from worklife.p2p import make_invite, parse_invite

    genesis, topic, peer = "a" * 64, "b" * 64, "c" * 64
    uri = make_invite(genesis, topic, peer)
    assert parse_invite(uri, genesis, topic) == peer
    with pytest.raises(ValueError):
        parse_invite(uri, "d" * 64, topic)
    with pytest.raises(ValueError):
        parse_invite(uri + "&peer=" + peer, genesis, topic)


def test_setup_respects_prebundled_transport_and_does_not_write_it(tmp_path, monkeypatch):
    from worklife.p2p import prepare_transport

    bundled = tmp_path / "image-transport"
    (bundled / "node_modules/hyperswarm").mkdir(parents=True)
    (bundled / "swarm.mjs").write_text("// prebuilt image\n")
    monkeypatch.setenv("WORKLIFE_P2P_TRANSPORT_DIR", str(bundled))
    assert prepare_transport(tmp_path / "home") == bundled
    assert not (tmp_path / "home").exists()


def test_cli_p2p_status_defaults_to_public_network_without_installing_packages(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in {"WORKLIFE_CHAIN_PROFILE", "WORKLIFE_CONFIG"}}
    result = subprocess.run(
        [sys.executable, "-m", "worklife", "--home", str(tmp_path), "p2p", "status"],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    assert state["chain"]["profile"] == "public-testnet-v1"
    assert state["running"] is False
    assert not (tmp_path / "p2p-transport").exists()


def test_runtime_preserves_large_consensus_integers_in_transport_payload(tmp_path):
    from worklife.p2p import P2PNode
    from worklife.workspace import Workspace

    node = P2PNode(Workspace(tmp_path))
    message = {"nonce": 2**60 + 1}
    node._send("a" * 64, message)
    command = node.outgoing.get_nowait()
    assert command["type"] == "send_raw"
    assert json.loads(base64.b64decode(command["payload"])) == message


def test_unexpected_sidecar_exit_does_not_leave_running_status(tmp_path, monkeypatch):
    from worklife.p2p import P2PNode
    from worklife.workspace import Workspace

    folder = tmp_path / "transport"
    (folder / "node_modules/hyperswarm").mkdir(parents=True)
    (folder / "swarm.mjs").write_text(
        "import fs from 'node:fs'; fs.closeSync(2); setTimeout(() => process.exit(3), 300)\n"
    )
    monkeypatch.setenv("WORKLIFE_P2P_TRANSPORT_DIR", str(folder))
    node = P2PNode(Workspace(tmp_path / "home"))
    with pytest.raises(ValueError, match="stopped unexpectedly"):
        asyncio.run(node.run())
    assert json.loads(node.path.read_text())["running"] is False


@pytest.mark.asyncio
async def test_only_a_completed_verified_protocol_round_marks_neighbor_useful(tmp_path):
    from types import SimpleNamespace

    from worklife.p2p import P2PNode
    from worklife.storage import canonical
    from worklife.workspace import Workspace

    node = P2PNode(Workspace(tmp_path))
    stream = asyncio.StreamReader()
    node.process = SimpleNamespace(stdout=stream)
    peer = "a" * 64
    node.protocol.connected(peer)
    first = node.outgoing.get_nowait()
    hello = json.loads(base64.b64decode(first["payload"]))

    def receive(message):
        stream.feed_data(
            canonical(
                {"type": "message", "peer": peer, "payload": base64.b64encode(canonical(message)).decode()}
            )
            + b"\n"
        )

    receive(hello)
    receive({"type": "page", "after": 0, "blocks": [], "next_cursor": 0})
    reader = asyncio.create_task(node._reader())
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        commands = [node.outgoing.get_nowait() for _ in range(node.outgoing.qsize())]
        assert [c for c in commands if c["type"] == "peer_verified"] == [
            {"type": "peer_verified", "peer": peer}
        ]
        receive({"type": "peer_verified", "peer": "b" * 64})
        for _ in range(10):
            await asyncio.sleep(0)
        assert node.outgoing.get_nowait() == {"type": "disconnect", "peer": peer}
        assert node.outgoing.empty() and not node.stop.is_set()
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
