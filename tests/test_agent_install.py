import json
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from json5.loader import loads as json5_loads
from ruamel.yaml import YAML

from worklife.agent_install import AGENT_NAME, SERVER_NAME, doctor, install_agent, load_catalog, merge_config
from worklife.agent_profile import BUNDLE_DIR, load_agent_profile
from worklife.recruiter_cli import main


def catalog_target(name):
    return next(item for item in load_catalog()["harnesses"] if item["id"] == name)


def test_all_project_adapters_bundle_and_idempotence_without_home_writes(tmp_path):
    destination = tmp_path / "My career agent"
    user_root = tmp_path / "untouched-user"
    ids = [item["id"] for item in load_catalog()["harnesses"]]
    result = install_agent(destination, ids, user_root=user_root, environment={})
    configured = {item["target"] for item in result["targets"] if item["status"] == "configured"}
    exported = {item["target"] for item in result["targets"] if item["status"] == "exported"}
    assert {
        "codex",
        "claude-code",
        "cursor",
        "gemini",
        "opencode",
        "vscode",
        "roo",
        "kiro",
        "mistral-vibe",
        "pi",
    } <= configured
    assert {
        "claude-desktop",
        "goose",
        "openclaw",
        "zed",
        "openhands",
        "trae",
        "generic",
        "kilo-legacy",
    } <= exported
    assert not user_root.exists()
    assert len(result["targets"]) == len(ids)
    assert (destination / ".agents/skills/worklife-market/SKILL.md").exists()
    assert (destination / ".claude/skills/worklife-market/SKILL.md").exists()
    helper = "worklife-onboarding/scripts/telegram_login.py"
    assert (destination / ".agents/skills" / helper).is_file()
    assert (destination / ".claude/skills" / helper).is_file()
    codex = tomllib.loads((destination / ".codex/config.toml").read_text())
    assert codex["mcp_servers"][SERVER_NAME]["command"] == sys.executable
    native = tomllib.loads((destination / ".codex/agents/worklife-recruiter.toml").read_text())
    assert native["name"] == AGENT_NAME
    assert "recruiter_start" in native["developer_instructions"]
    assert not {"model", "sandbox_mode", "approval_policy"} & native.keys()
    for skill in load_agent_profile()["skills"]:
        assert (destination / ".worklife/recruiter" / skill["path"]).exists()
    second = install_agent(destination, ids, user_root=user_root, environment={})
    assert all(item["action"] == "unchanged" for item in second["files"])
    assert not list(destination.rglob("*.worklife-backup-*"))
    assert all(item["config_exists"] for item in doctor(destination)["checks"])
    # A venv interpreter must keep its symlink path, and work outside the source cwd.
    completed = subprocess.run(
        [result["launch"]["command"], *result["launch"]["args"], "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_skill_install_ignores_python_bytecode(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE_DIR, bundle)
    cache = bundle / "skills/worklife-onboarding/scripts/__pycache__/telegram_login.cpython-312.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"\xff\x00compiled code")
    monkeypatch.setattr("worklife.agent_install.BUNDLE_DIR", bundle)
    destination = tmp_path / "agent"
    install_agent(destination, ["codex"], environment={})
    assert not list(destination.rglob("*.pyc"))
    assert all(
        item["action"] == "unchanged"
        for item in install_agent(destination, ["codex"], environment={})["files"]
    )


def test_dry_run_writes_nothing_and_reports_export(tmp_path):
    destination = tmp_path / "agent"
    result = install_agent(destination, ["codex", "claude-desktop"], dry_run=True, environment={})
    assert not destination.exists()
    assert [item["status"] for item in result["targets"]] == ["configured", "exported"]
    assert result["dry_run"]
    assert result["files"]


def test_json_update_preserves_unrelated_server_settings_and_backup(tmp_path):
    destination = tmp_path / "agent"
    destination.mkdir()
    path = destination / ".mcp.json"
    old = {
        "mcpServers": {
            "other": {"command": "other", "env": {"TEST_SECRET": "sample-secret-not-printed"}},
            SERVER_NAME: {"command": "old"},
        },
        "permissions": {"default": "ask"},
    }
    original = json.dumps(old).encode()
    path.write_bytes(original)
    path.chmod(0o640)
    result = install_agent(destination, ["claude-code"], environment={})
    actual = json.loads(path.read_text())
    assert actual["mcpServers"]["other"] == old["mcpServers"]["other"]
    assert actual["permissions"] == old["permissions"]
    change = next(item for item in result["files"] if item["path"] == str(path))
    assert Path(change["backup"]).read_bytes() == original
    assert stat.S_IMODE(Path(change["backup"]).stat().st_mode) == 0o600
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert "sample-secret-not-printed" not in json.dumps(result)


@pytest.mark.parametrize(
    "target,source,expected_key",
    [
        (
            "opencode",
            '{\n // model choice\n "model": "mine", /* keep block */\n "permissions":{"edit":"ask"},\n "mcp":{"existing":{"type":"local","command":["something"]}},\n}\n',
            "mcp",
        ),
        (
            "amp",
            '{"amp.model":"mine", /* keep block */ "amp.mcpServers":{"existing":{"command":"x"}},}\n',
            "amp.mcpServers",
        ),
        (
            "vscode",
            '{\n // profile\n "servers":{"existing":{"type":"stdio","command":"x"}},\n "inputs":[{"id":"token","type":"promptString","password":true}],\n}\n',
            "servers",
        ),
    ],
)
def test_jsonc_preserves_comments_literals_and_existing_variant(tmp_path, target, source, expected_key):
    destination = tmp_path / target
    spec = catalog_target(target)["mcp"]["project"]
    path = destination / spec["path"]
    if target == "opencode":
        path = path.with_suffix(".jsonc")
    path.parent.mkdir(parents=True)
    path.write_text(source)
    before = json5_loads(source)
    result = install_agent(destination, [target], environment={})
    after_text = path.read_text()
    after = json5_loads(after_text)
    assert result["targets"][0]["config"] == str(path)
    assert after[expected_key]["existing"] == before[expected_key]["existing"]
    del after[expected_key][SERVER_NAME]
    assert after == before
    if "/* keep block */" in source:
        assert "/* keep block */" in after_text
    if "// model choice" in source:
        assert "// model choice" in after_text
    assert all(
        item["action"] == "unchanged"
        for item in install_agent(destination, [target], environment={})["files"]
    )


def test_openclaw_explicit_json5_and_user_path_override(tmp_path):
    path = tmp_path / "profile" / "openclaw.json"
    path.parent.mkdir()
    source = "{ // custom profile\n model: 'my-model', control: -1.5e2, mcp: {servers: {existing: {command: 'other'}}}, }\n"
    path.write_text(source)
    result = install_agent(
        tmp_path / "agent",
        ["openclaw"],
        scope="user",
        user_root=tmp_path / "user",
        environment={"OPENCLAW_CONFIG_PATH": str(path)},
    )
    assert result["targets"][0]["config"] == str(path)
    actual = json5_loads(path.read_text())
    assert actual["model"] == "my-model"
    assert actual["control"] == -150
    assert actual["mcp"]["servers"]["existing"]["command"] == "other"
    assert "// custom profile" in path.read_text()
    assert "'my-model'" in path.read_text()
    assert SERVER_NAME in actual["mcp"]["servers"]


def test_toml_map_and_native_preserve_model_and_comments(tmp_path):
    destination = tmp_path / "agent"
    path = destination / ".codex/config.toml"
    agent = destination / ".codex/agents/worklife-recruiter.toml"
    agent.parent.mkdir(parents=True)
    path.write_text(
        '# my setup\nmodel = "my-model"\napproval_policy = "on-request"\n[mcp_servers.existing]\ncommand = "other"\nargs = ["one"]\n'
    )
    agent.write_text(
        'name = "worklife-recruiter"\nmodel = "selected-by-user" # keep choice\ndeveloper_instructions = "old"\n'
    )
    install_agent(destination, ["codex"], environment={})
    actual = tomllib.loads(path.read_text())
    assert actual["model"] == "my-model"
    assert actual["approval_policy"] == "on-request"
    assert actual["mcp_servers"]["existing"] == {"command": "other", "args": ["one"]}
    assert "# my setup" in path.read_text()
    assert tomllib.loads(agent.read_text())["model"] == "selected-by-user"
    assert "# keep choice" in agent.read_text()


def test_toml_array_of_tables_and_roo_mode_merge(tmp_path):
    destination = tmp_path / "agent"
    path = destination / ".vibe/config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        'active_model = "my-model"\n# existing extension\n[[mcp_servers]]\nname = "other"\ncommand = "other"\ntransport = "stdio"\n'
    )
    modes = destination / ".roomodes"
    modes.write_text(
        "customModes:\n  - slug: designer\n    name: Designer # retain\n    roleDefinition: Design\n    groups: [read]\n"
    )
    install_agent(destination, ["mistral-vibe", "roo"], environment={})
    actual = tomllib.loads(path.read_text())
    assert actual["active_model"] == "my-model"
    assert len(actual["mcp_servers"]) == 2
    assert {item["name"] for item in actual["mcp_servers"]} == {"other", SERVER_NAME}
    assert "# existing extension" in path.read_text()
    actual_modes = YAML(typ="safe").load(modes.read_text())
    assert [item["slug"] for item in actual_modes["customModes"]] == ["designer", AGENT_NAME]
    assert "# retain" in modes.read_text()
    assert all(
        item["action"] == "unchanged"
        for item in install_agent(destination, ["mistral-vibe", "roo"], environment={})["files"]
    )


def test_goose_yaml_user_install_preserves_other_provider(tmp_path):
    user_root = tmp_path / "user"
    path = user_root / ".config/goose/config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "GOOSE_PROVIDER: custom # user choice\nGOOSE_MODEL: chosen\nextensions:\n  existing:\n    type: stdio\n    cmd: other\n    enabled: true\n"
    )
    result = install_agent(
        tmp_path / "agent", ["goose"], scope="user", user_root=user_root, environment={}, platform="linux"
    )
    actual = YAML(typ="safe").load(path.read_text())
    assert actual["GOOSE_PROVIDER"] == "custom"
    assert actual["GOOSE_MODEL"] == "chosen"
    assert actual["extensions"]["existing"]["cmd"] == "other"
    assert actual["extensions"][SERVER_NAME]["cmd"] == sys.executable
    assert "# user choice" in path.read_text()
    assert result["targets"][0]["status"] == "configured"


def test_explicit_zed_path_and_unsupported_adapter_refusal(tmp_path):
    path = tmp_path / "profile.json"
    result = install_agent(tmp_path / "agent", ["zed"], config_path=path, environment={})
    assert result["targets"][0]["status"] == "configured"
    assert SERVER_NAME in json5_loads(path.read_text())["context_servers"]
    with pytest.raises(ValueError, match="No verified"):
        install_agent(tmp_path / "unwritten", ["trae"], config_path=tmp_path / "trae.json", environment={})
    assert not (tmp_path / "unwritten").exists()


def test_invalid_config_stops_all_planned_writes(tmp_path):
    destination = tmp_path / "agent"
    path = destination / ".cursor/mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"mcpServers":broken}')
    before = {
        str(file.relative_to(destination)): file.read_bytes()
        for file in destination.rglob("*")
        if file.is_file()
    }
    with pytest.raises(ValueError):
        install_agent(destination, ["codex", "cursor"], environment={})
    assert {
        str(file.relative_to(destination)): file.read_bytes()
        for file in destination.rglob("*")
        if file.is_file()
    } == before


def test_duplicate_identity_and_wrong_type_are_not_replaced(tmp_path):
    with pytest.raises(ValueError, match="mapping"):
        merge_config('{"mcpServers": []}', catalog_target("cursor")["mcp"]["project"], {"command": "python"})
    with pytest.raises(ValueError, match="Duplicate"):
        merge_config(
            '{"mcpServers":{},"mcpServers":{}}',
            catalog_target("cursor")["mcp"]["project"],
            {"command": "python"},
        )
    with pytest.raises(ValueError, match="Duplicate"):
        merge_config(
            '{"servers":{},"servers":{}}', catalog_target("vscode")["mcp"]["project"], {"command": "python"}
        )


def test_existing_json_and_jsonc_requires_explicit_choice(tmp_path):
    (tmp_path / "opencode.json").write_text("{}")
    (tmp_path / "opencode.jsonc").write_text("{}")
    with pytest.raises(ValueError, match="Multiple configurations"):
        install_agent(tmp_path, ["opencode"], environment={})
    assert not (tmp_path / ".worklife").exists()


def test_user_home_override_is_read_without_mutating_environment(tmp_path):
    environment = {"CODEX_HOME": str(tmp_path / "alternate-codex")}
    original = environment.copy()
    result = install_agent(
        tmp_path / "agent", ["codex"], scope="user", user_root=tmp_path / "user", environment=environment
    )
    assert result["targets"][0]["config"] == str(tmp_path / "alternate-codex/config.toml")
    assert (tmp_path / "alternate-codex/agents/worklife-recruiter.toml").exists()
    assert environment == original
    assert not (tmp_path / "user/.codex").exists()


def test_native_markdown_preserves_user_model(tmp_path):
    path = tmp_path / ".claude/agents/worklife-recruiter.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: worklife-recruiter\ndescription: Old\nmodel: my-choice # preserve\n---\nOld body"
    )
    install_agent(tmp_path, ["claude-code"], environment={})
    assert "model: my-choice # preserve" in path.read_text()
    assert "recruiter_start" in path.read_text()
    assert "Old body" not in path.read_text()


def test_cli_target_listing_dryrun_and_errors(tmp_path, capsys):
    assert main(["targets"]) == 0
    assert "codex" in {item["id"] for item in json.loads(capsys.readouterr().out)}
    assert main(["install", "--target", "codex", "--destination", str(tmp_path / "agent"), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"]
    assert not (tmp_path / "agent").exists()
    assert main(["install", "--target", "missing", "--destination", str(tmp_path / "agent")]) == 2
    assert "Choose supported" in capsys.readouterr().err


def test_config_home_env_paths_are_explicit_and_secrets_are_not_exported(tmp_path):
    config = tmp_path / "worklife config.toml"
    config.write_text('[worklife]\nhome = "private-data"\n[network]\nauto = false\n')
    env_file = tmp_path / "secret environment.env"
    env_file.write_text("EXAMPLE_API_KEY=do-not-copy-this-value\n")
    data_root = tmp_path / "personal data"
    result = install_agent(
        tmp_path / "agent", ["codex"], config=config, home=data_root, env_file=env_file, environment={}
    )
    assert result["launch"]["args"] == [
        "-m",
        "worklife.recruiter_cli",
        "mcp",
        "--config",
        str(config),
        "--home",
        str(data_root),
        "--env-file",
        str(env_file),
    ]
    for item in result["files"]:
        assert "do-not-copy-this-value" not in Path(item["path"]).read_text()
    assert not data_root.exists()


@pytest.mark.parametrize("platform", ["macos", "linux", "windows"])
def test_user_adapters_all_platforms_use_supplied_root(tmp_path, platform):
    user_root = tmp_path / platform
    appdata = user_root / "AppData/Roaming"
    environment = {"APPDATA": str(appdata)}
    ids = [item["id"] for item in load_catalog()["harnesses"]]
    result = install_agent(
        tmp_path / "agent", ids, scope="user", user_root=user_root, environment=environment, platform=platform
    )
    for target in result["targets"]:
        path = Path(target["config"])
        assert path.is_relative_to(tmp_path)
        assert path.exists()
        if target["status"] == "configured":
            assert path.is_relative_to(user_root)
    second = install_agent(
        tmp_path / "agent", ids, scope="user", user_root=user_root, environment=environment, platform=platform
    )
    assert all(item["action"] == "unchanged" for item in second["files"])


def test_cli_invalid_yaml_reports_error_without_printing_config(tmp_path, capsys):
    path = tmp_path / "goose.yaml"
    path.write_text("secret: sample-secret-not-printed\nextensions: [broken")
    assert (
        main(
            [
                "install",
                "--target",
                "goose",
                "--config-path",
                str(path),
                "--destination",
                str(tmp_path / "agent"),
            ]
        )
        == 2
    )
    error = capsys.readouterr().err
    assert "Invalid YAML" in error
    assert "sample-secret-not-printed" not in error
    assert not (tmp_path / "agent").exists()
