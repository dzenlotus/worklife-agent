import asyncio
import json
import subprocess
import sys

from starlette.testclient import TestClient

from worklife.app import create_app, normalize_result
from worklife.config import Config
from worklife.server import create_server
from worklife.workspace import Workspace


def proposal(w):
    return w.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Employer advertises remote work",
            "evidence_kind": "advertised",
            "source_url": "https://acme.example/jobs",
            "observed_at": "2026-10-27T10:00:00Z",
        },
    )


def test_agent_tools_require_chain_confirmation_before_shared_query(tmp_path):
    server = create_server(Config(tmp_path, network_auto=False))
    w = server.worklife_workspace

    def call(name, arguments=None):
        return normalize_result(asyncio.run(server.call_tool(name, arguments or {})))

    try:
        event = proposal(w)
        assert "chain" in call("agent_brief")
        assert call("knowledge_query") == []
        pending = call("knowledge_proposals")
        assert pending[0]["event_id"] == event["event_id"]
        assert pending[0]["confirmation"]["status"] == "pending"
        challenge = call("blockchain_challenge")
        assert challenge["month"] and challenge["tasks"]
        call("blockchain_qualify")
        for _ in range(3):
            assert call("blockchain_mine")["mined"]
        accepted = call("knowledge_query")
        assert accepted[0]["event_id"] == event["event_id"]
        assert accepted[0]["confirmation"]["scope"] == "protocol_validity"
        assert accepted[0]["confirmation"]["status"] == "confirmed"
        assert call("blockchain_status")["qualified"]
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_local_app_keeps_unsigned_in_chain_proposals_out_of_confirmed_view(tmp_path):
    w = Workspace(tmp_path)
    event = proposal(w)
    with TestClient(create_app(Config(tmp_path, network_auto=False), scheduler=False)) as client:
        state = client.get("/api/state").json()
        assert state["employers"] == []
        assert state["network"]["chain"]["height"] == 0
        assert state["network"]["proposals"] == 1
        w.blockchain.qualify()
        for _ in range(3):
            assert w.blockchain.mine()["mined"]
        state = client.get("/api/state").json()
        assert state["employers"][0]["event_id"] == event["event_id"]
        assert state["network"]["chain"]["height"] == 3


def test_cli_runs_qualification_mining_and_reproducible_simulation(tmp_path):
    def command(*args):
        result = subprocess.run(
            [sys.executable, "-m", "worklife", "--home", str(tmp_path), "chain", *args],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert command("status")["height"] == 0
    assert command("qualify")["month"]
    assert command("mine")["mined"]
    assert command("status")["height"] == 1
    experiment = command("simulate", "--trials", "1000", "--keys", "1,1000")
    assert experiment["total_attempts_executed"] == 2000


def test_pending_queue_keeps_unconfirmed_retractions_and_their_predecessors(tmp_path):
    server = create_server(Config(tmp_path, network_auto=False))
    w = server.worklife_workspace
    try:
        event = proposal(w)
        retraction = w.ledger.publish(
            "retraction", event["subject"], {**event["payload"], "supersedes": event["event_id"]}
        )
        result = normalize_result(asyncio.run(server.call_tool("knowledge_proposals", {})))
        assert [item["event_id"] for item in result] == [event["event_id"], retraction["event_id"]]
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()
