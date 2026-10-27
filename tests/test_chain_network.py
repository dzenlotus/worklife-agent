import copy
import importlib.util
import json
import socket
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
import uvicorn
from starlette.testclient import TestClient

from worklife.blockchain import BLOCK_BITS, GENESIS
from worklife.federation import create_app
from worklife.workspace import Workspace

AT = "2026-10-15T10:00:00Z"


def test_public_chain_transport_is_available():
    from worklife import federation

    assert hasattr(federation, "sync_chain_peer"), "Public blockchain transport is not implemented"
    assert importlib.util.find_spec("worklife.chain_network") is not None


def publish(workspace):
    return workspace.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Employer advertises remote work",
            "evidence_kind": "advertised",
            "source_url": "https://acme.example/jobs",
            "observed_at": AT,
        },
    )


def prepare(workspace):
    event = publish(workspace)
    workspace.blockchain.qualify(at=AT)
    for second in range(3):
        assert workspace.blockchain.mine(at=f"2026-10-15T10:00:{second:02d}Z")["mined"]
    return event, workspace.blockchain.all()


@contextmanager
def serving(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def test_tokenless_localhost_sync_confirmations_restart_idempotence_and_private_scope(tmp_path):
    from worklife.federation import sync_chain_peer, sync_peer

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    event, blocks = prepare(a)
    pending = publish(b)
    a.save_profile({"name": "Private person", "facts": []})
    with serving(create_app(a)) as url:
        result = sync_chain_peer(b, url)
        assert result["pulled"] == 3
        assert result["pushed"] == 0
        assert result["chain"]["height"] == 3
        assert b.blockchain.confirmation(event["event_id"])["status"] == "confirmed"
        assert b.blockchain.active_events() == [event]
        assert b.ledger.all() == [pending]
        assert a.ledger.all() == [event]
        assert sync_peer(b, {"protocol": 2, "url": url})["pulled"] == 0
        assert sync_chain_peer(b, url)["pushed"] == 0
        restarted = Workspace(tmp_path / "b")
        assert restarted.blockchain.all() == blocks
        assert restarted.blockchain.active_events() == [event]
        assert restarted.store.list("profile") == []


def test_public_routes_have_no_signing_or_proposal_access_and_v1_empty_token_is_denied(tmp_path):
    workspace = Workspace(tmp_path)
    _, blocks = prepare(workspace)
    for token in ("", "legacy-secret"):
        with TestClient(create_app(workspace, token)) as client:
            state = client.get("/v2/state")
            assert state.status_code == 200
            assert state.json()["transport_protocol"] == 2
            assert state.json()["genesis"] == GENESIS
            assert state.json()["block_bits"] == BLOCK_BITS
            assert client.get("/v2/blocks?after=0&limit=2").json() == {
                "blocks": blocks[:2],
                "next_cursor": 2,
            }
            assert client.post("/v2/blocks", json={"blocks": blocks}).json()["imported"] == 0
            assert client.get("/v1/events").status_code == 401
            assert client.get("/v2/profile").status_code == 404
            assert client.post("/v2/qualify").status_code == 404
            assert client.post("/v2/mine").status_code == 404
            assert client.post("/v2/events", json={"events": []}).status_code == 404
            if not token:
                assert client.get("/v1/events", headers={"Authorization": "Bearer "}).status_code == 401


def test_invalid_block_batch_is_atomic_and_bad_requests_are_bounded(tmp_path):
    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    _, blocks = prepare(a)
    forged = copy.deepcopy(blocks[1])
    forged["signature"] = "0" * 128
    with TestClient(create_app(b)) as client:
        assert client.post("/v2/blocks", json={"blocks": [blocks[0], forged]}).status_code == 400
        assert b.blockchain.all() == []
        for body in (b"not json", b"[" * 1100 + b"0" + b"]" * 1100):
            assert client.post("/v2/blocks", content=body).status_code == 400
        assert client.post("/v2/blocks", json={"blocks": [blocks[0]] * 101}).status_code == 400
        assert client.post("/v2/blocks", content=b"x" * (8 * 1024 * 1024 + 1)).status_code == 413
        assert client.get("/v2/blocks?after=-1").status_code == 400
        assert client.get("/v2/blocks?limit=101").status_code == 400
        assert client.post("/v2/blocks", json={"events": []}).status_code == 400


@pytest.mark.parametrize("field,value", [("network", "foreign"), ("genesis", "0" * 64), ("block_bits", 0)])
def test_sync_rejects_chain_identity_mismatch_before_writing(tmp_path, field, value):
    from worklife.federation import sync_chain_peer

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    app = create_app(a)
    original = a.blockchain.status
    a.blockchain.status = lambda: {**original(), field: value}
    with serving(app) as url:
        with pytest.raises(ValueError, match="identity|protocol"):
            sync_chain_peer(b, url)
    assert b.blockchain.all() == []


def test_nonadvancing_cursor_and_large_response_are_rejected(tmp_path, monkeypatch):
    from worklife import federation

    workspace = Workspace(tmp_path)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/v2/state":
            return httpx.Response(200, json={**workspace.blockchain.status(), "transport_protocol": 2})
        return httpx.Response(200, json={"blocks": [{}], "next_cursor": 0})

    real_client = httpx.Client
    monkeypatch.setattr(
        federation.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ValueError, match="cursor"):
        federation.sync_chain_peer(workspace, "https://peer.example")
    assert len(calls) == 2

    def oversized(request):
        return httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1))

    monkeypatch.setattr(
        federation.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(oversized)),
    )
    with pytest.raises(ValueError, match="8 MiB"):
        federation.sync_chain_peer(workspace, "https://peer.example")


def test_manager_only_syncs_explicit_v2_peers_and_keeps_cached_status(tmp_path, monkeypatch):
    from worklife import chain_network

    workspace = Workspace(tmp_path)
    calls = []

    def sync(workspace, peer):
        calls.append(peer)
        return {"peer": peer["url"], "pulled": 0, "pushed": 0, "chain": workspace.blockchain.status()}

    monkeypatch.setattr(chain_network, "sync_chain_peer", sync)
    peers = {"old": {"url": "https://legacy.example"}, "new": {"url": "https://chain.example", "protocol": 2}}
    manager = chain_network.BlockchainNetwork(workspace, lambda: peers)
    assert manager.status()["auto"] is True
    assert calls == []
    assert manager.tick()["status"] == "healthy"
    assert manager.tick()["status"] == "healthy"
    assert len(calls) == 1
    assert manager.status()["protected_copies"] == 1
    publish(workspace)
    assert manager.mark_dirty()["pending"] == 1
    assert manager.status()["status"] == "local_only"
    assert manager.status()["qualified"] is False
    manager.tick()
    assert len(calls) == 2
    assert workspace.blockchain.all() == []
    assert workspace.store.list("chain_qualification") == []


def test_manager_local_only_offline_attention_and_restart(tmp_path, monkeypatch):
    from worklife import chain_network

    workspace = Workspace(tmp_path)
    manager = chain_network.BlockchainNetwork(workspace, lambda: [])
    status = manager.tick()
    assert status["status"] == "local_only"
    assert "уз" in status["detail"]
    assert status["last_sync"] is None
    peers = [{"url": "https://offline.example", "protocol": 2}]

    def fail(*args):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(chain_network, "sync_chain_peer", fail)
    manager = chain_network.BlockchainNetwork(workspace, lambda: peers)
    assert manager.tick()["status"] == "offline"

    def invalid(*args):
        raise ValueError("invalid chain")

    monkeypatch.setattr(chain_network, "sync_chain_peer", invalid)
    assert manager.tick(force=True)["status"] == "attention"
    monkeypatch.setattr(chain_network, "sync_chain_peer", lambda *args: {})
    success = manager.tick(force=True)
    assert success["status"] == "healthy"
    assert success["last_sync"]
    reopened = chain_network.BlockchainNetwork(Workspace(tmp_path), lambda: peers)
    assert reopened.status()["last_sync"] == success["last_sync"]
    assert json.loads(json.dumps(reopened.status()))["auto"] is True


def test_two_way_sync_preserves_all_verified_forks(tmp_path):
    from worklife.federation import sync_chain_peer

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    prepare(a)
    prepare(b)
    with serving(create_app(a)) as url:
        result = sync_chain_peer(b, url)
        assert result["pulled"] == result["pushed"] == 3
        assert len(a.blockchain.all()) == len(b.blockchain.all()) == 6
        assert a.blockchain.all() == b.blockchain.all()
        assert a.blockchain.status()["head"] == b.blockchain.status()["head"]
        assert sync_chain_peer(b, url)["pushed"] == 0


def test_transport_reduces_pages_and_push_batches_to_eight_mib(tmp_path, monkeypatch):
    from worklife import federation

    workspace = Workspace(tmp_path)
    blocks = [{"data": "x" * 600_000, "number": number} for number in range(20)]
    monkeypatch.setattr(
        workspace.blockchain,
        "page",
        lambda after, limit: {
            "blocks": blocks[after : after + limit],
            "next_cursor": min(after + limit, len(blocks)),
        },
    )
    with TestClient(create_app(workspace)) as client:
        response = client.get("/v2/blocks")
        assert response.status_code == 200
        assert len(response.content) <= 8 * 1024 * 1024
        assert 0 < len(response.json()["blocks"]) < len(blocks)
        assert response.json()["next_cursor"] == len(response.json()["blocks"])

    requests = []

    def handler(request):
        requests.append(request)
        assert "authorization" not in request.headers
        if request.url.path == "/v2/state":
            return httpx.Response(200, json={**workspace.blockchain.status(), "transport_protocol": 2})
        if request.method == "GET":
            return httpx.Response(200, json={"blocks": [], "next_cursor": 0})
        assert len(request.content) <= 8 * 1024 * 1024
        batch = json.loads(request.content)["blocks"]
        assert 0 < len(batch) <= 100
        return httpx.Response(200, json={"imported": len(batch)})

    monkeypatch.setattr(workspace.blockchain, "all", lambda: blocks)
    real_client = httpx.Client
    monkeypatch.setattr(
        federation.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    assert federation.sync_chain_peer(workspace, "https://peer.example")["pushed"] == 20
    assert len([request for request in requests if request.method == "POST"]) == 2
