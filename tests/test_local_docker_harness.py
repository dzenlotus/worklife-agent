import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_local_docker_network.py"
SPEC = importlib.util.spec_from_file_location("local_docker_harness", SCRIPT)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def mounts(config):
    return [
        {
            "Type": "volume",
            "Name": "check_data-a",
            "Source": "/var/lib/docker/volumes/check_data-a/_data",
            "Destination": "/data",
            "RW": True,
        },
        {
            "Type": "bind",
            "Name": None,
            "Source": str(config),
            "Destination": "/etc/worklife/config.toml",
            "RW": False,
        },
    ]


def test_mount_order_and_macos_host_alias_do_not_change_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(harness.sys, "platform", "darwin")
    before = mounts(tmp_path / "node-a.toml")
    original = deepcopy(before)
    after = list(reversed(deepcopy(before)))
    after[0]["Source"] = "/host_mnt" + before[1]["Source"]
    assert harness.normalized_mounts(before) == harness.normalized_mounts(after)
    assert before == original


def test_macos_bind_source_resolves_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(harness.sys, "platform", "darwin")
    config = tmp_path / "node-a.toml"
    config.write_text("[worklife]\n")
    alias = tmp_path / "alias.toml"
    alias.symlink_to(config)
    assert harness.normalized_mounts(mounts(config)) == harness.normalized_mounts(mounts(alias))


@pytest.mark.parametrize("field,value", [("Name", "other_data-a"), ("RW", False), ("Source", "/other")])
def test_different_volume_or_permissions_remain_different(tmp_path, field, value):
    before = mounts(tmp_path / "node-a.toml")
    after = deepcopy(before)
    after[0][field] = value
    assert harness.normalized_mounts(before) != harness.normalized_mounts(after)


def test_linux_bind_sources_do_not_assume_a_desktop_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(harness.sys, "platform", "linux")
    before = mounts(tmp_path / "node-a.toml")
    after = deepcopy(before)
    after[1]["Source"] = "/host_mnt" + before[1]["Source"]
    assert harness.normalized_mounts(before) != harness.normalized_mounts(after)
