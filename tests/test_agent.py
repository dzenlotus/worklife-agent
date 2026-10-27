import json
import os
from pathlib import Path

import pytest


async def test_mcp_stdio_is_usable_by_a_real_client(tmp_path):
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "worklife", "mcp"],
        env={**os.environ, "WORKLIFE_HOME": str(tmp_path)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            listing = await client.list_tools()
            names = {t.name for t in listing.tools}
            assert {
                "profile_save",
                "jobs_search",
                "action_draft",
                "browser_inspect",
                "knowledge_publish",
                "peer_sync",
                "experiment_report",
                "cv_export",
                "agent_brief",
            } <= names
            result = await client.call_tool("profile_save", {"profile": {"name": "Test", "facts": []}})
            assert not result.isError
            brief = await client.call_tool("agent_brief", {})
            assert "Test" in str(brief)
            result = await client.call_tool(
                "knowledge_publish",
                {
                    "kind": "employer",
                    "subject": "acme.example",
                    "payload": {
                        "claim": "Employer advertises remote work",
                        "evidence_kind": "advertised",
                        "source_url": "https://example.org",
                        "observed_at": "2026-10-27T10:00:00Z",
                    },
                },
            )
            assert not result.isError


def test_browser_forms_upload_and_pdf_are_real(tmp_path):
    from worklife.browser import Browser

    pytest.importorskip("playwright")
    page = tmp_path / "page.html"
    page.write_text("""<html><title>Apply</title><body><form>
        <label>Name<input id="name"></label><input id="cv" type="file">
        <button type="button" id="send" onclick="document.querySelector('#result').textContent=document.querySelector('#name').value">Send</button>
        <p id="result"></p></form></body></html>""")
    cv = tmp_path / "cv.md"
    cv.write_text("Real CV")
    browser = Browser(tmp_path / "browser")
    try:
        browser.open(page.as_uri())
        browser.prepare("fill", {"selector": "#name", "value": "Alex"})
        browser.prepare("upload", {"selector": "#cv", "paths": [str(cv)]})
        state = browser.inspect()
        assert state["title"] == "Apply"
        assert any(c.get("value") == "Alex" for c in state["controls"])
        browser.execute("click", {"selector": "#send", "expected_url": page.as_uri()})
        assert "Alex" in browser.inspect()["text"]
        pdf = browser.pdf("# Alex\n\nBuilt Python APIs", tmp_path / "cv.pdf")
        assert Path(pdf).read_bytes().startswith(b"%PDF")
    finally:
        browser.close()


def test_cli_demo_and_json_tool_call(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "worklife", "--home", str(tmp_path / "demo"), "demo"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["replication"]["valid"] is True
    assert output["tampering_rejected"] is True
    status = subprocess.run(
        [sys.executable, "-m", "worklife", "--home", str(tmp_path / "demo"), "call", "agent_brief", "{}"],
        capture_output=True,
        text=True,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["profile"]["name"] == "Demo candidate"
