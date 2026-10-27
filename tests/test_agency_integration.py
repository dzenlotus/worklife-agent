import base64

import pytest
from starlette.testclient import TestClient

from worklife.app import create_app, normalize_result, snapshot
from worklife.config import Config
from worklife.server import create_server


@pytest.mark.asyncio
async def test_mcp_market_resume_recommendation_and_pipeline_flow(tmp_path):
    server = create_server(Config(tmp_path))

    async def call(name, arguments):
        return normalize_result(await server.call_tool(name, arguments))

    try:
        imported = await call(
            "resume_import", {"name": "Backend", "text": "Python services\n\nSQL databases", "language": "en"}
        )
        cv = imported["cv"]
        profile = server.worklife_workspace.get_profile()
        await call(
            "profile_save",
            {
                "profile": {
                    **profile,
                    "target_roles": ["Python"],
                    "constraints": {
                        "remote": True,
                        "min_salary": 100,
                        "currency": "RUB",
                        "salary_period": "month",
                        "salary_gross": True,
                    },
                }
            },
        )
        job = await call(
            "job_save",
            {
                "job": {
                    "id": "1",
                    "platform": "fixture",
                    "title": "Python developer",
                    "employer": "Example",
                    "url": "https://example.org/1",
                    "remote": True,
                    "salary_min": 150,
                    "salary_max": 250,
                    "currency": "RUB",
                    "salary_period": "month",
                    "salary_gross": True,
                    "requirements": ["Python", "SQL"],
                    "cv_language": "en",
                }
            },
        )
        market = await call(
            "market_snapshot",
            {
                "name": "Python remote",
                "job_ids": [job["id"]],
                "scope": {"role": "Python", "region": "remote"},
                "sources": [{"name": "Fixture", "query": "Python"}],
            },
        )
        report = await call("market_report", {"snapshot_id": market["id"]})
        assert report["salary_groups"][0]["lower"]["median"] == 150
        recommendation = await call("recommendations_report", {})
        assert recommendation["recommendations"][0]["job_id"] == job["id"]
        await call(
            "recommendation_save",
            {
                "job_id": job["id"],
                "verdict": "consider",
                "reasons": ["Опыт подтверждён импортированным резюме"],
                "evidence": [{"fact_id": cv["fact_ids"][0]}],
                "cv_id": cv["id"],
                "priority": 1,
            },
        )
        semantic = await call("recommendations_report", {})
        assert semantic["recommendations"][0]["assessment_status"] == "fresh"
        await call("pipeline_update", {"job_id": job["id"], "stage": "saved", "next_action": "Review"})
        await call(
            "conversation_record",
            {
                "job_id": job["id"],
                "direction": "inbound",
                "channel": "fixture",
                "text": "Interview invitation",
                "external_id": "message-1",
            },
        )
        await call("interview_save", {"job_id": job["id"], "scheduled_at": "2026-11-03T12:00:00+03:00"})
        await call(
            "offer_save",
            {
                "job_id": job["id"],
                "terms": {
                    "salary_min": 200,
                    "currency": "RUB",
                    "salary_period": "month",
                    "salary_gross": True,
                    "remote": True,
                },
            },
        )
        state = snapshot(server)
        assert state["market"]["report"]["snapshot"]["id"] == market["id"]
        assert state["cvs"][0]["id"] == cv["id"]
        assert state["messages"][0]["external_id"] == "message-1"
        assert len(state["interviews"]) == len(state["offers"]) == 1
        assert server.worklife_workspace.ledger.export() == []
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


def test_resume_upload_imports_text_and_rejects_invalid_data(tmp_path):
    app = create_app(Config(tmp_path), scheduler=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        result = client.post(
            "/api/resume",
            headers={"X-Worklife-Client": "local"},
            json={
                "name": "My CV",
                "filename": "resume.txt",
                "language": "en",
                "file_base64": base64.b64encode(b"Python services\n\nSQL databases").decode(),
            },
        )
        assert result.status_code == 200
        assert result.json()["result"]["cv"]["name"] == "My CV"
        cv_id = result.json()["result"]["cv"]["id"]
        assert result.json()["result"]["cv"]["original_filename"] == "resume.txt"
        original = client.get(f"/api/cv/{cv_id}/download?format=original")
        assert original.status_code == 200
        assert original.content == b"Python services\n\nSQL databases"
        state = client.get("/api/state").json()
        assert state["cvs"] and state["profile"]["facts"]
        invalid = client.post(
            "/api/resume",
            headers={"X-Worklife-Client": "local"},
            json={"filename": "resume.pdf", "file_base64": "not base64"},
        )
        assert invalid.status_code == 400
        for invalid_fields in ({"language": "invalid!!"}, {"language": 123}, {"name": "   "}):
            bad = client.post(
                "/api/resume",
                headers={"X-Worklife-Client": "local"},
                json={
                    "name": "CV",
                    "filename": "resume.txt",
                    "file_base64": base64.b64encode(b"Python services").decode(),
                    **invalid_fields,
                },
            )
            assert bad.status_code == 400
            assert bad.json()["ok"] is False
        assert len(client.get("/api/state").json()["cvs"]) == 1
