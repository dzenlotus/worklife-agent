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
