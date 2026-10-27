import importlib.util
import json
import subprocess

import pytest

from worklife.workspace import Workspace


def career(tmp_path):
    assert importlib.util.find_spec("worklife.career") is not None, "Career toolkit is not implemented"
    from worklife.career import Career

    workspace = Workspace(tmp_path / "private")
    return workspace, Career(workspace)


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def repository(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Example")
    git(root, "config", "user.email", "example@example.org")
    (root / "README.md").write_text("# Local service\nA small async service with verified checks.\n")
    (root / "service.py").write_text("async def fetch_record():\n    return {'status': 'ready'}\n")
    (root / "test_service.py").write_text("def test_status():\n    assert 1 + 1 == 2\n")
    (root / ".env").write_text("PRIVATE_TEST_SECRET=must-never-appear\n")
    (root / "malicious.py").write_text(
        f"from pathlib import Path\nPath({str(tmp_path / 'executed')!r}).touch()\n"
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "Add async service and checks")
    return root


def test_repository_analysis_uses_actual_local_evidence_without_executing_code(tmp_path):
    workspace, toolkit = career(tmp_path)
    root = repository(tmp_path)
    # No remote access or repository-configured pager should be needed.
    git(root, "remote", "add", "origin", "https://user:remote-secret@example.invalid/private.git")
    git(root, "config", "core.pager", f"touch {tmp_path / 'pager-executed'}")
    value = toolkit.repository_analyze(str(root))
    assert value["path"] == str(root.resolve())
    assert value["branch"] == "main"
    assert value["commit"] == git(root, "rev-parse", "HEAD")
    assert value["file_count"] == 5
    assert value["languages"]["Python"] == 3
    assert "Local service" in value["readme_excerpt"]
    assert value["recent_commits"][0]["subject"] == "Add async service and checks"
    assert value["strength_suggestions"]
    assert all(s["status"] == "proposed" and s["evidence"] for s in value["strength_suggestions"])
    assert any(e["path"] == "service.py" for e in value["evidence"])
    assert ".env" not in [e["path"] for e in value["evidence"]]
    assert "must-never-appear" not in json.dumps(value)
    assert "remote-secret" not in json.dumps(value)
    assert not (tmp_path / "executed").exists()
    assert not (tmp_path / "pager-executed").exists()
    assert workspace.store.get("repository", value["id"]) == value
    assert workspace.ledger.export() == []


def test_repository_analysis_bounds_files_and_does_not_infer_skill_from_extension(tmp_path):
    _, toolkit = career(tmp_path)
    root = tmp_path / "empty-code"
    root.mkdir()
    git(root, "init", "-b", "main")
    (root / "empty.py").write_text("# placeholder\n")
    git(root, "add", ".")
    value = toolkit.repository_analyze(root, max_files=1)
    assert value["languages"] == {"Python": 1}
    assert value["strength_suggestions"] == []
    assert value["commit"] is None
    assert value["recent_commits"] == []
    with pytest.raises(ValueError, match="Git"):
        toolkit.repository_analyze(tmp_path)
    with pytest.raises(ValueError, match="max_files"):
        toolkit.repository_analyze(root, max_files=0)


def test_repository_monitor_ignores_refresh_times_but_detects_source_changes(tmp_path):
    from worklife.operations import Operations

    workspace, toolkit = career(tmp_path)
    root = repository(tmp_path)
    ops = Operations(workspace, lambda tool, arguments: toolkit.repository_analyze(**arguments))
    schedule = ops.schedule_save("Repository", "repository_analyze", {"path": str(root)})
    assert ops.schedule_run(schedule["id"])["changed"] is True
    assert ops.schedule_run(schedule["id"])["changed"] is False
    assert len(workspace.store.list("repository")) == 1
    (root / "service.py").write_text("async def fetch_record():\n    return {'status': 'changed'}\n")
    assert ops.schedule_run(schedule["id"])["changed"] is True


def test_repository_analysis_does_not_execute_repository_configured_signature_program(tmp_path):
    _, toolkit = career(tmp_path)
    root = repository(tmp_path)
    program = tmp_path / "signature-program"
    marker = tmp_path / "signature-executed"
    program.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
    program.chmod(0o700)
    git(root, "config", "gpg.program", str(program))
    git(root, "config", "log.showSignature", "true")
    original = git(root, "cat-file", "commit", "HEAD")
    signed = original.replace(
        "\n\n", "\ngpgsig -----BEGIN PGP SIGNATURE-----\n fake\n -----END PGP SIGNATURE-----\n\n", 1
    )
    commit = subprocess.run(
        ["git", "-C", str(root), "hash-object", "-t", "commit", "-w", "--stdin"],
        input=signed,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    git(root, "update-ref", "HEAD", commit)
    toolkit.repository_analyze(root)
    assert not marker.exists()


def test_strength_and_tactics_have_evidence_and_explicit_status(tmp_path):
    workspace, toolkit = career(tmp_path)
    with pytest.raises(ValueError, match="evidence"):
        toolkit.strengths_save("Python", "Built a service", [])
    with pytest.raises(ValueError, match="source"):
        toolkit.strengths_save("Python", "Built a service", [{"text": "Trust me"}])
    strength = toolkit.strengths_save(
        "Python", "Built an async service", [{"source": "portfolio", "path": "service.py"}]
    )
    assert strength["status"] == "proposed"
    confirmed = toolkit.strengths_save(
        "Python", "Built an async service", strength["evidence"], "confirmed", strength["id"]
    )
    assert confirmed["id"] == strength["id"]
    assert confirmed["status"] == "confirmed"
    tactic = toolkit.tactic_save(
        "Focused applications",
        "Specific evidence earns replies",
        ["Select five matching roles"],
        "reply rate",
    )
    assert tactic["status"] == "planned"
    assert "results" not in tactic
    assert (
        toolkit.tactic_save(
            tactic["name"],
            tactic["hypothesis"],
            tactic["actions"],
            tactic["success_metric"],
            "active",
            tactic["id"],
        )["status"]
        == "active"
    )
    with pytest.raises(ValueError, match="status"):
        toolkit.tactic_save("Bad", "A hypothesis", ["Apply"], "Replies", "successful")
    assert workspace.store.list("strength") == [confirmed]
    assert workspace.ledger.export() == []


def test_platform_and_account_are_private_metadata_not_registration(tmp_path):
    workspace, toolkit = career(tmp_path)
    platform = toolkit.platform_save(
        "Community board", "https://jobs.example.org", ["search", "profile"], "Discovered by the agent"
    )
    assert platform["capabilities"] == ["search", "profile"]
    account = toolkit.account_save(
        platform["id"],
        "candidate",
        email="candidate@example.org",
        notes="Credential reference: env:BOARD_TOKEN",
    )
    assert account["status"] == "planned"
    assert account["platform_id"] == platform["id"]
    assert "password" not in account and "token" not in account
    assert (
        toolkit.account_save(platform["id"], "candidate", "verification_required", account_id=account["id"])[
            "status"
        ]
        == "verification_required"
    )
    with pytest.raises(ValueError):
        toolkit.account_save("missing", "candidate")
    with pytest.raises(ValueError, match="status"):
        toolkit.account_save(platform["id"], "candidate", "created")
    with pytest.raises(ValueError, match="secret|credential"):
        toolkit.account_save(platform["id"], "candidate", notes="password=do-not-store")
    with pytest.raises(ValueError, match="URL|credential"):
        toolkit.platform_save("Bad", "https://user:password@example.org", ["search"])
    assert len(workspace.store.list("account")) == 1
    assert workspace.ledger.export() == []


def test_cv_localization_preserves_fact_ids_sources_and_original_text(tmp_path):
    workspace, toolkit = career(tmp_path)
    workspace.save_profile(
        {
            "name": "Alex",
            "facts": [
                {"id": "api", "text": "Built Python APIs", "source": {"path": "service.py", "commit": "abc"}},
                {"id": "team", "text": "Led a team of three", "source": "project report"},
            ],
        }
    )
    original = workspace.create_cv("Backend", ["api", "team"], "Developer", "Original summary")
    translated = toolkit.cv_localize(
        original["id"],
        "ja-JP",
        {"api": "Python API を開発", "team": "3 人のチームを指揮"},
        headline="開発者",
        summary="経験の概要",
        name="日本語 CV",
    )
    assert translated["id"] != original["id"]
    assert translated["source_cv_id"] == original["id"]
    assert translated["language"] == "ja-JP"
    assert translated["fact_ids"] == original["fact_ids"]
    assert translated["original_facts"] == original["facts"]
    assert translated["facts"][0]["id"] == "api"
    assert translated["facts"][0]["source"] == original["facts"][0]["source"]
    assert translated["facts"][0]["original_text"] == "Built Python APIs"
    assert translated["facts"][0]["text"] == "Python API を開発"
    assert translated["review_required"] is True
    assert "Python API を開発" in translated["markdown"]
    assert workspace.store.get("cv", original["id"]) == original
    assert workspace.store.get("cv", translated["id"]) == translated
    # A snapshot remains usable after the live profile changes.
    workspace.save_profile({"name": "Alex", "facts": []})
    german = toolkit.cv_localize(
        original["id"], "de", {"api": "Python-APIs entwickelt", "team": "Ein Dreierteam geleitet"}
    )
    assert german["facts"][0]["source"] == original["facts"][0]["source"]
    assert workspace.ledger.export() == []


def test_cv_localization_requires_supplied_translations_for_every_fact(tmp_path):
    workspace, toolkit = career(tmp_path)
    workspace.save_profile({"name": "Alex", "facts": [{"id": "api", "text": "Built APIs", "source": "repo"}]})
    cv = workspace.create_cv("Original", ["api"], "Developer")
    for translations in ({}, {"api": " "}, {"invented": "Nouvelle expérience"}):
        with pytest.raises(ValueError, match="translation"):
            toolkit.cv_localize(cv["id"], "fr", translations)
    for language in ("", "English please", "../../en", "en_US"):
        with pytest.raises(ValueError, match="language"):
            toolkit.cv_localize(cv["id"], language, {"api": "API développées"})
    assert len(workspace.store.list("cv")) == 1
