import json
import re

import pytest

from worklife.agent_profile import BUNDLE_DIR, load_agent_profile, read_agent_skill
from worklife.app import normalize_result
from worklife.config import Config
from worklife.server import create_server


def test_profile_loads_complete_portable_bundle():
    profile = load_agent_profile()
    assert profile["id"] == "recruiter"
    assert profile["name"] == "Worklife Recruiter"
    assert profile["instructions"] == (BUNDLE_DIR / "AGENTS.md").read_text(encoding="utf-8")
    assert len(profile["skills"]) == len({skill["name"] for skill in profile["skills"]}) == 7
    assert len(profile["allowed_tools"]) == len(set(profile["allowed_tools"]))
    assert {"recruiter_start", "recruiter_skill", "recommendation_save", "inbox_sync"} <= set(
        profile["allowed_tools"]
    )
    # The startup's file links must remain usable by both the installer and local readers.
    links = re.findall(r"\]\((skills/[^)]+/SKILL\.md)\)", profile["instructions"])
    assert set(links) == {skill["path"] for skill in profile["skills"]}
    for skill in profile["skills"]:
        path = BUNDLE_DIR / skill["path"]
        assert not path.relative_to(BUNDLE_DIR).is_absolute()
        content = read_agent_skill(skill["name"])
        assert content == path.read_text(encoding="utf-8")
        frontmatter = content.split("---", 2)[1].splitlines()
        values = dict(line.split(": ", 1) for line in frontmatter if ": " in line)
        assert values["name"] == skill["name"]
        assert json.loads(values["description"]) == skill["description"]
        metadata = (path.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert f"${skill['name']}" in metadata
        assert 'value: "worklife_recruiter"' in metadata
        assert "allow_implicit_invocation: true" in metadata


@pytest.mark.parametrize("name", ["missing", "../AGENTS.md", "skills/worklife-intake/SKILL.md"])
def test_skill_lookup_rejects_unregistered_names(name):
    with pytest.raises(ValueError, match="Unknown recruiter skill"):
        read_agent_skill(name)


def test_profile_lookup_rejects_unknown_profile():
    with pytest.raises(ValueError, match="Unknown agent profile"):
        load_agent_profile("../recruiter")


def test_profile_results_are_not_shared_mutable_state():
    first = load_agent_profile()
    first["allowed_tools"].clear()
    first["skills"][0]["name"] = "changed"
    second = load_agent_profile()
    assert second["allowed_tools"]
    assert second["skills"][0]["name"] != "changed"


def test_documented_tool_calls_are_available_in_profile():
    profile = load_agent_profile()
    texts = [profile["instructions"], *(read_agent_skill(skill["name"]) for skill in profile["skills"])]
    referenced = set(re.findall(r"`([a-z][a-z0-9_]*)\(", "\n".join(texts)))
    assert referenced <= set(profile["allowed_tools"])


@pytest.mark.asyncio
async def test_recruiter_toolset_matches_registered_tools(tmp_path):
    server = create_server(Config(tmp_path), profile="recruiter")
    try:
        names = {tool.name for tool in await server.list_tools()}
        assert names == set(load_agent_profile()["allowed_tools"])
        assert not any(name.startswith(("blockchain_", "peer_")) for name in names)
        assert not names & {
            "agent_run",
            "agent_cancel",
            "backup_create",
            "knowledge_import",
            "knowledge_export",
            "knowledge_verify",
            "author_trust",
        }
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


@pytest.mark.asyncio
async def test_default_mcp_keeps_full_toolset(tmp_path):
    server = create_server(Config(tmp_path))
    try:
        names = {tool.name for tool in await server.list_tools()}
        assert {"blockchain_mine", "peer_sync", "backup_create", "agent_run"} <= names
        career_tools = set(load_agent_profile()["allowed_tools"]) - {"recruiter_start", "recruiter_skill"}
        assert career_tools <= names
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


@pytest.mark.asyncio
async def test_recruiter_bootstrap_and_skill_resources_supply_current_context(tmp_path):
    server = create_server(Config(tmp_path), profile="recruiter")
    try:
        w = server.worklife_workspace
        w.save_profile({"name": "Fixture", "facts": [], "target_roles": ["Analyst"]})
        draft = w.draft_action("fixture", "send", {"text": "Draft only"}, "draft-1")
        start = normalize_result(await server.call_tool("recruiter_start", {}))
        assert start["profile"]["name"] == "Fixture"
        assert start["actions"][0]["id"] == draft["id"]
        assert {"agency", "market", "advisor", "connectors"} <= start.keys()
        assert start["agent"]["id"] == "recruiter"
        assert "blockchain_mine" not in server.instructions
        instructions = await server.read_resource("worklife://recruiter/instructions")
        assert list(instructions)[0].content == load_agent_profile()["instructions"]
        skill = await server.read_resource("worklife://recruiter/skills/worklife-market")
        assert list(skill)[0].content == read_agent_skill("worklife-market")
        with pytest.raises(Exception, match="Unknown tool"):
            await server.call_tool("agent_run", {"goal": "Do not run"})
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()


@pytest.mark.asyncio
async def test_recruiter_schedules_cannot_run_or_enable_administrative_operations(tmp_path):
    server = create_server(Config(tmp_path), profile="recruiter")
    try:
        operations = server.worklife_operations
        for forbidden in ("agent_cycle", "peer_sync"):
            arguments = {"goal": "Do not run"} if forbidden == "agent_cycle" else {"name": "missing"}
            with pytest.raises(Exception, match="not available in the recruiter profile"):
                await server.call_tool(
                    "schedule_save", {"name": "Admin", "tool": forbidden, "arguments": arguments}
                )
            # An existing schedule created through the full operator MCP is still out of scope.
            saved = operations.schedule_save("Admin", forbidden, arguments, enabled=False)
            for tool, kwargs in (("schedule_run", {}), ("schedule_toggle", {"enabled": True})):
                with pytest.raises(Exception, match="not available in the recruiter profile"):
                    await server.call_tool(tool, {"schedule_id": saved["id"], **kwargs})
            assert operations.schedule_toggle(saved["id"], False)["enabled"] is False
        saved = normalize_result(
            await server.call_tool(
                "schedule_save", {"name": "Review", "tool": "search_review", "arguments": {}}
            )
        )
        result = normalize_result(await server.call_tool("schedule_run", {"schedule_id": saved["id"]}))
        assert result["status"] == "success"
        assert not server.worklife_workspace.store.list("agent_run")
    finally:
        server.worklife_runtime.close()
        server.worklife_browser.close()
