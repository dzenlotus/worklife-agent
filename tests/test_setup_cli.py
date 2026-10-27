"""Verify the uvx installer contract without downloads or writes outside a temporary home."""

import json
import os
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

from worklife import setup_cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "events.jsonl"
    shim = (
        f"#!{sys.executable}\n"
        + r"""
import json
import os
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["INSTALL_EVENTS"], "a") as output:
    output.write(json.dumps([name, *args]) + "\n")
if " ".join([name, *args]).startswith(os.environ.get("INSTALL_FAIL") or "never match"):
    sys.exit(7)
if name == "uv" and args[0] == "venv":
    binary = Path(args[-1]) / "bin"
    binary.mkdir(parents=True)
    python = binary / "python"
    python.write_text(Path(sys.argv[0]).read_text())
    python.chmod(0o755)
if name == "python" and args[:2] == ["-m", "worklife"]:
    home = Path(args[args.index("--home") + 1])
    home.mkdir(parents=True, exist_ok=True)
    (home / "initialized").touch()
    print(json.dumps({"home": str(home)}))
if name == "python" and args[:2] == ["-m", "worklife.recruiter_cli"]:
    print(json.dumps({"targets": [{"target": args[args.index("--target") + 1]}]}))
"""
    )
    uv = commands / "uv"
    uv.write_text(shim)
    uv.chmod(0o755)
    home = tmp_path / "user home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(commands) + os.pathsep + os.defpath)
    monkeypatch.setenv("INSTALL_EVENTS", str(log))
    monkeypatch.delenv("WORKLIFE_HOME", raising=False)

    def run(*args, fail=None, platform="darwin"):
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setenv("INSTALL_FAIL", fail or "")
        status = setup_cli.main(list(args))
        events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return status, events

    return run, home, uv


def test_package_exposes_uvx_entrypoint():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["scripts"]["worklife-agent"] == "worklife.setup_cli:main"


def test_setup_installs_exact_release_to_durable_runtime_and_initializes_private_home(setup):
    run, home, _ = setup
    status, events = run("--no-browser")
    assert status == 0
    installation = home / ".local/share/worklife"
    python = installation / "venv/bin/python"
    assert events[0] == ["uv", "venv", "--python", "3.12", str(installation / "venv")]
    pip = next(event for event in events if event[:3] == ["uv", "pip", "install"])
    assert pip[pip.index("--python") + 1] == str(python)
    assert f"worklife-agent=={version('worklife-agent')}" in pip
    assert not any("[browser]" in argument for argument in pip)
    assert ["python", "-m", "worklife", "--home", str(home / ".worklife"), "init"] in events
    recruiter = next(event for event in events if event[:3] == ["python", "-m", "worklife.recruiter_cli"])
    assert recruiter[3:] == [
        "install",
        "--target",
        "generic",
        "--destination",
        str(home / "worklife-career"),
        "--home",
        str(home / ".worklife"),
    ]
    assert json.loads((installation / "state.json").read_text())["home"] == str(home / ".worklife")
    assert json.loads((installation / "installation.json").read_text())["targets"] == [{"target": "generic"}]
    assert not any(event[:3] == ["python", "-m", "playwright"] for event in events)


@pytest.mark.parametrize("platform, options", [("darwin", []), ("linux", ["--with-deps"])])
def test_setup_installs_chromium_with_same_runtime(setup, platform, options):
    run, _, _ = setup
    status, events = run("--target", "codex", platform=platform)
    assert status == 0
    pip = next(event for event in events if event[:3] == ["uv", "pip", "install"])
    assert f"worklife-agent[browser]=={version('worklife-agent')}" in pip
    assert ["python", "-m", "playwright", "install", *options, "chromium"] in events
    assert next(event for event in events if "worklife.recruiter_cli" in event)[5] == "codex"


def test_setup_preserves_existing_runtime_and_data_with_explicit_paths(setup, tmp_path):
    run, _, _ = setup
    installation = tmp_path / "installation path"
    data = tmp_path / "private data"
    destination = tmp_path / "career workspace"
    args = (
        "--target",
        "cursor",
        "--install-dir",
        str(installation),
        "--home",
        str(data),
        "--destination",
        str(destination),
        "--no-browser",
    )
    assert run(*args)[0] == 0
    marker = installation / "venv/retained"
    marker.write_text("keep environment")
    (data / "retained").write_text("keep private data")
    status, events = run(*args)
    assert status == 0
    assert sum(event[:2] == ["uv", "venv"] for event in events) == 1
    assert marker.read_text() == "keep environment"
    assert (data / "retained").read_text() == "keep private data"
    recruiter = next(event for event in events if "worklife.recruiter_cli" in event)
    assert recruiter[recruiter.index("--destination") + 1] == str(destination)
    assert recruiter[recruiter.index("--home") + 1] == str(data)


def test_setup_accepts_local_wheel_for_smoke_test(setup, tmp_path):
    run, _, _ = setup
    wheel = tmp_path / "local package.whl"
    wheel.touch()
    status, events = run("--package-source", str(wheel))
    assert status == 0
    pip = next(event for event in events if event[:3] == ["uv", "pip", "install"])
    assert f"worklife-agent[browser] @ {wheel.as_uri()}" in pip


def test_setup_honors_worklife_home(setup, tmp_path, monkeypatch):
    run, _, _ = setup
    data = tmp_path / "environment private data"
    monkeypatch.setenv("WORKLIFE_HOME", str(data))
    status, events = run("--no-browser")
    assert status == 0
    assert ["python", "-m", "worklife", "--home", str(data), "init"] in events


@pytest.mark.parametrize("fail", ["uv pip install", "python -m playwright", "python -m worklife --home"])
def test_setup_stops_before_adapter_on_failed_step(setup, fail, capsys):
    run, _, _ = setup
    status, events = run(fail=fail)
    assert status == 1
    assert not any("worklife.recruiter_cli" in event for event in events)
    assert "Worklife:" in capsys.readouterr().err


@pytest.mark.parametrize("args", [("--target", "claude-desktop"), ("--target", "unknown"), ("--unknown",)])
def test_setup_rejects_invalid_or_user_only_target_before_installing(setup, args):
    run, _, uv = setup
    with pytest.raises(SystemExit) as exc:
        run(*args)
    assert exc.value.code == 2
    assert not (uv.parent.parent / "events.jsonl").exists()


def test_setup_reports_missing_uv_before_writing(setup, monkeypatch, capsys):
    run, home, uv = setup
    uv.unlink()
    monkeypatch.setattr(setup_cli.shutil, "which", lambda _: None)
    status, events = run()
    assert status == 1
    assert not events
    assert not (home / ".local").exists()
    assert "uv" in capsys.readouterr().err
