import json

import pytest
from starlette.testclient import TestClient

from worklife.config import Config
from worklife.operations import Operations
from worklife.workspace import Workspace


def test_local_app_uses_real_private_state_and_tools(tmp_path):
    from worklife.app import create_app

    w = Workspace(tmp_path)
    w.save_profile({"name": "Private person", "facts": []})
    app = create_app(Config(tmp_path), scheduler=False)
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert state["profile"]["name"] == "Private person"
        assert state["release"]["status"] == "offline"
        assert state["release"]["update_available"] is False
        assert state["statistics"]["jobs"] == 0
        assert state["network"]["events"] == 0
        assert (
            client.post("/api/tools/resource_save", json={"name": "Source", "kind": "source"}).status_code
            == 403
        )
        response = client.post(
            "/api/tools/resource_save",
            json={"name": "Source", "kind": "source"},
            headers={"X-Worklife-Client": "local"},
        )
        assert response.json()["ok"], response.text
        assert client.get("/api/state").json()["resources"][0]["name"] == "Source"
        assert client.get("/api/state", headers={"Origin": "https://other.example"}).status_code == 403


def test_employer_proposals_track_real_confirmation_without_private_data(tmp_path):
    from worklife.app import create_app

    app = create_app(Config(tmp_path, network_auto=False), scheduler=False)
    server = app.state.worklife
    w = server.worklife_workspace
    w.save_profile({"name": "PRIVATE_PROFILE_SENTINEL", "facts": []})
    w.save_job(
        {
            "id": "private-job",
            "platform": "manual",
            "title": "PRIVATE_JOB_SENTINEL",
            "employer": "Acme",
            "url": "https://acme.example/private-job",
        }
    )
    server.worklife_agency.conversation_record(channel="email", text="PRIVATE_MESSAGE_SENTINEL")
    event = w.ledger.publish(
        "employer",
        "acme.example",
        {
            "name": "Acme",
            "claim": "Advertises remote roles",
            "evidence_kind": "advertised",
            "source_url": "https://acme.example/jobs",
            "observed_at": "2026-10-15T10:00:00Z",
        },
    )
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert state["employers"] == []
        assert state["employer_proposals"] == [
            {**event, "confirmation": w.blockchain.confirmation(event["event_id"])}
        ]
        assert state["employer_proposals"][0]["confirmation"]["status"] == "pending"
        assert state["employer_proposals"][0]["confirmation"]["depth"] == 0
        assert state["network"]["proposals"] == 1
        assert state["network"]["summary"]["auto"] is False
        assert state["profile"]["name"] == "PRIVATE_PROFILE_SENTINEL"
        assert state["jobs"][0]["title"] == "PRIVATE_JOB_SENTINEL"
        assert state["messages"][0]["text"] == "PRIVATE_MESSAGE_SENTINEL"
        assert "PRIVATE_" not in json.dumps(state["employer_proposals"])

        w.blockchain.qualify(at="2026-10-15T10:00:00Z")
        assert w.blockchain.mine(at="2026-10-15T10:00:00Z")["mined"]
        state = client.get("/api/state").json()
        assert state["employers"] == []
        assert state["employer_proposals"] == [
            {**event, "confirmation": w.blockchain.confirmation(event["event_id"])}
        ]
        assert state["employer_proposals"][0]["confirmation"]["status"] == "included"
        assert state["employer_proposals"][0]["confirmation"]["depth"] == 1
        assert state["network"]["chain"]["confirmations"] == 3
        assert state["network"]["proposals"] == 1

        for second in (1, 2):
            assert w.blockchain.mine([], at=f"2026-10-15T10:00:{second:02d}Z")["mined"]
        state = client.get("/api/state").json()
        assert [record["event_id"] for record in state["employers"]] == [event["event_id"]]
        assert state["employers"][0]["confirmation"]["status"] == "confirmed"
        assert state["employers"][0]["confirmation"]["depth"] == 3
        assert state["employer_proposals"] == []
        assert state["network"]["proposals"] == 0


@pytest.mark.parametrize("corrupt", ["ledger", "chain"])
def test_employer_proposals_are_empty_during_recovery_with_auto_disabled(tmp_path, corrupt):
    from worklife.app import create_app

    app = create_app(Config(tmp_path, network_auto=False), scheduler=False)
    w = app.state.worklife.worklife_workspace
    event = w.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Advertises remote roles",
            "evidence_kind": "advertised",
            "source_url": "https://acme.example/jobs",
            "observed_at": "2026-10-15T10:00:00Z",
        },
    )
    if corrupt == "ledger":
        changed = {**event, "payload": {**event["payload"], "claim": "Unsigned change"}}
        with w.store.connect() as db:
            db.execute("UPDATE events SET document=?", (json.dumps(changed),))
    else:
        w.blockchain.qualify(at="2026-10-15T10:00:00Z")
        mined = w.blockchain.mine(at="2026-10-15T10:00:00Z")
        assert mined["mined"]
        block = mined["block"]
        w.store.put("chain_blocks", block["block_id"], {**block, "nonce": block["nonce"] + 1})
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert state["network"]["valid"] is False
        assert state["network"]["chain"]["valid"] is False
        assert state["employers"] == []
        assert state["employer_proposals"] == []
        assert state["network"]["proposals"] == 0
        assert state["network"]["summary"]["status"] == "recovering"
        assert state["network"]["summary"]["auto"] is False


def test_blocking_employer_stops_saved_jobs_and_prepared_contact(tmp_path):
    w = Workspace(tmp_path)
    w.save_profile({"facts": []})
    job = w.save_job(
        {
            "id": "1",
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "employer_domain": "acme.example",
            "url": "https://acme.example/jobs/1",
        }
    )
    action = w.draft_action(
        "mail",
        "send",
        {"to": "hr@acme.example", "body": "hello", "_employer_domain": "acme.example"},
        "contact",
    )
    w.approve_action(action["id"])
    Operations(w).block_employer("acme.example", "Does not honor stated conditions")
    assert w.assess_job(job["id"])["decision"] == "reject"
    called = []
    import pytest

    with pytest.raises(ValueError, match="blocked"):
        w.execute_action(action["id"], lambda *args: called.append(args))
    assert called == []


@pytest.mark.parametrize("recipient_field", ["cc", "bcc"])
def test_company_blocks_apply_to_all_mail_recipients(tmp_path, recipient_field):
    w = Workspace(tmp_path)
    Operations(w).block_employer("acme.example", "Do not contact")
    with pytest.raises(ValueError, match="blocked"):
        w.draft_action(
            "mail",
            "send",
            {"to": "me@other.example", recipient_field: "hr@acme.example", "body": "Hello"},
            recipient_field,
        )


def test_scheduler_endpoint_persists_real_runs(tmp_path):
    from worklife.app import create_app

    with TestClient(create_app(Config(tmp_path), scheduler=False)) as client:
        headers = {"X-Worklife-Client": "local"}
        schedule = client.post(
            "/api/tools/schedule_save",
            json={
                "name": "Review search",
                "tool": "reminder",
                "arguments": {"title": "Check results"},
                "interval_minutes": 30,
            },
            headers=headers,
        ).json()["result"]
        run = client.post(
            "/api/tools/schedule_run", json={"schedule_id": schedule["id"]}, headers=headers
        ).json()
        assert run["result"]["status"] == "success", run
        state = client.get("/api/state").json()
        assert state["tasks"][0]["title"] == "Check results"
        assert len(state["schedule_runs"]) == 1
