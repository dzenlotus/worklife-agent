import threading

import pytest
import uvicorn
from starlette.testclient import TestClient


def record():
    return {
        "claim": "Employer advertises two interview stages",
        "evidence_kind": "advertised",
        "source_url": "https://example.org/jobs",
        "observed_at": "2026-10-27T10:00:00Z",
    }


def test_peer_protocol_auth_and_pinning(tmp_path):
    from worklife.federation import create_app
    from worklife.workspace import Workspace

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    event = a.ledger.publish("employer", "acme.example", record())
    app = create_app(b, "test-token")
    with TestClient(app) as client:
        assert client.get("/v1/events").status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        assert client.get("/v1/identity", headers=headers).json()["author"] == b.ledger.author_id
        assert client.post("/v1/events", headers=headers, json={"events": [event]}).json()["imported"] == 1
        page = client.get("/v1/events?after=0&limit=1", headers=headers).json()
        assert page["events"][0]["event_id"] == event["event_id"]
        assert client.get("/v1/events?after=-1", headers=headers).status_code == 400
        assert client.get("/v1/heads", headers=headers).json()["events"] == 1
        assert client.post("/v1/events", headers=headers, json={"events": [{"bad": True}]}).status_code == 400
        assert client.get("/v1/profile", headers=headers).status_code == 404


def test_real_network_two_way_replication_and_restart(tmp_path):
    import socket
    import time

    from worklife.federation import create_app, sync_peer
    from worklife.workspace import Workspace

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    a.ledger.publish("employer", "a.example", record())
    b.ledger.publish("employer", "b.example", record())
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(b, "secret"), log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        peer = {"url": f"http://127.0.0.1:{port}", "token": "secret", "author": b.ledger.author_id}
        assert sync_peer(a, peer)["pulled"] == 1
        assert a.ledger.verify()["events"] == b.ledger.verify()["events"] == 2
        assert sync_peer(a, peer)["pulled"] == 0
        with pytest.raises(ValueError, match="identity"):
            sync_peer(a, {**peer, "author": "0" * 64})
        restarted = Workspace(tmp_path / "b")
        assert restarted.ledger.verify()["events"] == 2
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
