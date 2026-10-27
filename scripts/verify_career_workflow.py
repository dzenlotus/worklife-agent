#!/usr/bin/env python3
"""Exercise actual MCP and worker processes against a loopback-only synthetic provider.

Run with the project's Python: uv run --no-env-file python scripts/verify_career_workflow.py.
No personal workspace, external provider, model, account, or credential is used.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from worklife.storage import Store
from worklife.workspace import Workspace


class FixtureProvider(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/send":
            return self.respond({"error": "unknown fixture operation"}, 404)
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.sent.append(payload)
        self.respond({"id": "fixture-outbound-1", "delivery": "accepted_by_fixture"})

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/messages":
            return self.respond({"error": "unknown fixture operation"}, 404)
        cursor = parse_qs(parsed.query).get("cursor", [""])[0]
        self.server.reads.append(cursor)
        messages = []
        if self.server.sent and cursor != "after-reply-1":
            messages = [
                {
                    "id": "fixture-reply-1",
                    "text": "Synthetic employer reply: let us arrange an interview.",
                    "direction": "inbound",
                    "in_reply_to": "fixture-outbound-1",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ]
        self.respond({"messages": messages, "next_cursor": "after-reply-1"})


def isolated_environment(config, data_home):
    # Explicit provider-free environment: do not inherit model/mail/API variables or a user's .env.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT") if key in os.environ}
    env.update(
        WORKLIFE_CONFIG=str(config),
        WORKLIFE_HOME=str(data_home),
        WORKLIFE_NETWORK_OFFLINE="1",
    )
    return env


@asynccontextmanager
async def mcp_session(config, data_home, profile):
    module = "worklife" if profile == "full" else "worklife.recruiter_cli"
    options = ["--config", str(config), "--home", str(data_home)]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", module, *([*options, "mcp"] if profile == "full" else ["mcp", *options])],
        env=isolated_environment(config, data_home),
        cwd=str(config.parent),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
            initialized = await session.initialize()
            yield session, initialized


async def call(session, name, arguments=None):
    result = await session.call_tool(name, arguments or {})
    if result.isError:
        raise AssertionError(f"MCP {name} failed: {result.content}")
    value = result.structuredContent
    if value is None:
        value = json.loads("\n".join(part.text for part in result.content if part.type == "text"))
    return value["result"] if isinstance(value, dict) and set(value) == {"result"} else value


def run_worker(config, data_home):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "worklife",
            "--config",
            str(config),
            "--home",
            str(data_home),
            "worker",
            "--once",
        ],
        env=isolated_environment(config, data_home),
        cwd=config.parent,
        text=True,
        capture_output=True,
        timeout=45,
        check=True,
    )
    return json.loads(completed.stdout)


async def verify(root, provider, profile):
    config, data_home = root / "config.toml", root / "data"
    config.write_text('[worklife]\nhome = "data"\n[network]\nauto = false\n', encoding="utf-8")
    evidence = {"profile": profile, "synthetic_only": True, "checks": {}}
    base_url = f"http://127.0.0.1:{provider.server_address[1]}"
    async with mcp_session(config, data_home, profile) as (session, initialized):
        evidence["server_name"] = initialized.serverInfo.name
        tool_names = {tool.name for tool in (await session.list_tools()).tools}
        evidence["tool_count"] = len(tool_names)
        if profile == "recruiter":
            from worklife.agent_profile import load_agent_profile

            assert tool_names == set(load_agent_profile()["allowed_tools"])
            start = await call(session, "recruiter_start")
            assert start["agent"]["instructions"] and start["agent"]["skills"]
            assert "profile" in start and "actions" in start
            instructions = await session.read_resource("worklife://recruiter/instructions")
            assert instructions.contents[0].text == start["agent"]["instructions"]
            skill_name = "worklife-pipeline"
            skill = await call(session, "recruiter_skill", {"name": skill_name})
            resource = await session.read_resource(f"worklife://recruiter/skills/{skill_name}")
            assert skill == resource.contents[0].text and "conversation_update" in skill
            denied = await session.call_tool("blockchain_status", {})
            assert denied.isError
            denied_schedule = await session.call_tool(
                "schedule_save",
                {"name": "Forbidden admin schedule", "tool": "peer_sync", "arguments": {"name": "any"}},
            )
            assert denied_schedule.isError
            assert await call(session, "records_list", {"bucket": "schedule"}) == []
            evidence["checks"]["recruiter_instructions_and_toolset"] = True
            evidence["checks"]["skills_resources_and_admin_schedule_exclusion"] = True
        await call(
            session,
            "connector_configure",
            {
                "name": "fixture",
                "config": {
                    "type": "http",
                    "base_url": base_url,
                    "operations": {
                        "inbox": {"path": "/messages", "method": "GET", "effect": "read"},
                        "send": {"path": "/send", "method": "POST", "effect": "write"},
                    },
                },
            },
        )
        imported = await call(
            session,
            "resume_import",
            {"name": "Fixture CV", "text": "Built Python APIs.\n\nDesigned SQL databases.", "language": "en"},
        )
        cv = imported["cv"]
        profile_data = (await call(session, "recruiter_start"))["profile"]
        await call(
            session,
            "profile_save",
            {
                "profile": {
                    **profile_data,
                    "target_roles": ["Python developer"],
                    "constraints": {"remote": True},
                }
            },
        )
        job = await call(
            session,
            "job_save",
            {
                "job": {
                    "id": "fixture-1",
                    "platform": "fixture",
                    "title": "Python developer",
                    "employer": "Synthetic Example",
                    "url": f"{base_url}/job/1",
                    "remote": True,
                    "salary_min": 100000,
                    "salary_max": 200000,
                    "currency": "RUB",
                    "salary_period": "month",
                    "salary_gross": True,
                    "requirements": ["Python", "SQL"],
                    "cv_language": "en",
                }
            },
        )
        market = await call(
            session,
            "market_snapshot",
            {
                "name": "Synthetic Python sample",
                "job_ids": [job["id"]],
                "scope": {"role": "Python developer", "region": "remote"},
                "sources": [{"name": "Loopback fixture", "query": "Python"}],
            },
        )
        report = await call(session, "market_report", {"snapshot_id": market["id"]})
        assert report["salary_groups"][0]["lower"]["median"] == 100000
        assert report["status"] == "insufficient_data"
        await call(
            session,
            "recommendation_save",
            {
                "job_id": job["id"],
                "verdict": "consider",
                "reasons": ["Synthetic source evidence matches the stated requirements."],
                "evidence": [{"fact_id": cv["fact_ids"][0]}],
                "cv_id": cv["id"],
                "priority": 1,
            },
        )
        recommendations = await call(session, "recommendations_report")
        assert recommendations["recommendations"][0]["assessment_status"] == "fresh"
        evidence["checks"]["market_and_evidence_backed_recommendation"] = True
        await call(
            session,
            "pipeline_update",
            {
                "job_id": job["id"],
                "stage": "saved",
                "cv_id": cv["id"],
                "next_action": "Review the synthetic contact",
            },
        )
        draft = await call(
            session,
            "action_draft",
            {
                "connector": "fixture",
                "operation": "send",
                "payload": {"_job_id": job["id"], "body": "Synthetic acceptance message"},
                "idempotency_key": "fixture-contact-1",
            },
        )
        assert provider.sent == []
        await call(session, "action_approve", {"action_id": draft["id"]})
        sent = await call(session, "action_execute", {"action_id": draft["id"]})
        assert sent["status"] == "sent" and sent["result"]["id"] == "fixture-outbound-1"
        assert provider.sent == [{"body": "Synthetic acceptance message"}]
        await call(session, "action_execute", {"action_id": draft["id"]})
        assert len(provider.sent) == 1
        assert await call(session, "conversation_list") == []
        await call(
            session,
            "pipeline_update",
            {"job_id": job["id"], "stage": "applied", "next_action": "Wait for an actual reply"},
        )
        before = await call(session, "records_list", {"bucket": "application"})
        assert before[0]["stage"] == "applied"
        evidence["checks"]["contact_idempotent_receipt_not_response"] = True
        schedule = await call(
            session,
            "schedule_save",
            {
                "name": "Synthetic inbox",
                "tool": "inbox_sync",
                "arguments": {"connector": "fixture", "parameters": {}},
                "interval_minutes": 0.001,
            },
        )
        assert provider.reads == []
    # The MCP connection and its server process are closed before any scheduled read.
    first = await asyncio.to_thread(run_worker, config, data_home)
    assert first["network"] is None and first["peers"] == {}
    assert len(first["scheduled_runs"]) == 1
    first_run = first["scheduled_runs"][0]
    assert first_run["status"] == "success" and first_run["result"]["imported"] == 1
    store = Store(data_home)
    message = store.list("message")[0]
    assert message["job_id"] == job["id"] and message["source"]["link_basis"] == "exact_reply"
    assert message["in_reply_to"] == "fixture-outbound-1"
    assert store.list("application")[0]["stage"] == "reply"
    assert store.get("schedule", schedule["id"])["arguments"]["parameters"]["cursor"] == "after-reply-1"
    evidence["checks"]["worker_after_mcp_close_imports_exact_reply"] = True
    second = await asyncio.to_thread(run_worker, config, data_home)
    assert len(second["scheduled_runs"]) == 1
    second_run = second["scheduled_runs"][0]
    assert second_run["status"] == "success" and second_run["result"]["imported"] == 0
    assert second_run["changed"] is False
    assert len(store.list("message")) == 1 and len(provider.sent) == 1
    assert provider.reads == ["", "after-reply-1"]
    evidence["checks"]["persistent_cursor_duplicate_free_quiet_second_worker"] = True
    async with mcp_session(config, data_home, profile) as (session, _):
        brief = await call(session, "agency_brief")
        messages = await call(session, "conversation_list")
        assert len(messages) == 1 and messages[0]["job_id"] == job["id"]
        applications = await call(session, "records_list", {"bucket": "application"})
        assert applications[0]["stage"] == "reply"
        assert brief["unread_messages"][0]["external_id"] == "fixture-reply-1"
        updated = await call(session, "conversation_update", {"message_id": message["id"], "read": True})
        assert updated["unread"] is False and updated["read_at"]
        assert updated["source"] == message["source"] and updated["text"] == message["text"]
        assert (
            await call(session, "conversation_update", {"message_id": message["id"], "read": True}) == updated
        )
        unlinked = await call(session, "conversation_update", {"message_id": message["id"], "unlink": True})
        assert unlinked["job_id"] is None
        relinked = await call(
            session, "conversation_update", {"message_id": message["id"], "job_id": job["id"], "read": False}
        )
        assert relinked["job_id"] == job["id"] and relinked["unread"] is True
        assert relinked["metadata_link_basis"] == "explicit" and relinked["source"] == message["source"]
        evidence["checks"]["explicit_message_assignment_and_local_read_state"] = True
    assert Workspace(data_home).ledger.export() == []
    evidence["checks"]["restart_persistence_and_private_ledger_separation"] = True
    evidence["worker_runs"] = [
        {"status": r["status"], "imported": r["result"]["imported"], "changed": r["changed"]}
        for r in (first_run, second_run)
    ]
    evidence["provider"] = {
        "binding": "127.0.0.1",
        "posts": len(provider.sent),
        "read_cursors": provider.reads,
    }
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON evidence path")
    parser.add_argument("--profile", choices=["full", "recruiter"], default="full")
    args = parser.parse_args()
    provider = ThreadingHTTPServer(("127.0.0.1", 0), FixtureProvider)
    provider.sent, provider.reads = [], []
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="worklife-career-acceptance-") as directory:
            evidence = asyncio.run(verify(Path(directory), provider, args.profile))
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)
    evidence.update(status="passed", completed_at=datetime.now(UTC).isoformat())
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
