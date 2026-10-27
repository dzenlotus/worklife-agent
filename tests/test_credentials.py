import importlib.util
import json
import sys
from types import SimpleNamespace

import pytest

from worklife.workspace import Workspace


class MemoryBackend:
    def __init__(self):
        self.values, self.writes = {}, 0

    def set_password(self, service, username, password):
        self.values[service, username] = password
        self.writes += 1

    def get_password(self, service, username):
        return self.values.get((service, username))


def credentials(tmp_path, backend=None):
    assert importlib.util.find_spec("worklife.credentials") is not None, (
        "Credential helper is not implemented"
    )
    from worklife.credentials import Credentials

    workspace = Workspace(tmp_path)
    return workspace, Credentials(workspace, backend or MemoryBackend())


def test_generated_credential_is_only_in_backend_and_retry_does_not_rotate(tmp_path):
    backend = MemoryBackend()
    workspace, vault = credentials(tmp_path, backend)
    metadata = vault.create("community-board", "candidate@example.org")
    password = backend.get_password(metadata["service"], metadata["name"])
    assert isinstance(password, str) and len(password) >= 32
    assert set(metadata) == {"id", "name", "username", "service", "created_at"}
    assert password not in json.dumps(metadata)
    assert password not in json.dumps(workspace.store.list("credential"))
    assert password.encode() not in workspace.store.path.read_bytes()
    assert workspace.ledger.export() == []
    assert vault.create("community-board") == metadata
    assert backend.writes == 1
    assert backend.get_password(metadata["service"], metadata["name"]) == password


def test_explicit_secret_updates_stable_id_and_workspace_isolation(tmp_path):
    backend = MemoryBackend()
    _, first = credentials(tmp_path / "first", backend)
    _, second = credentials(tmp_path / "second", backend)
    original = first.create("board", "candidate", "supplied-test-password")
    updated = first.create("board", "candidate", "updated-test-password")
    isolated = second.create("board", "other-candidate", "other-password")
    assert updated["id"] == original["id"]
    assert updated["created_at"] == original["created_at"]
    assert isolated["service"] != original["service"]
    assert backend.get_password(original["service"], "board") == "updated-test-password"
    assert backend.get_password(isolated["service"], "board") == "other-password"


def test_fill_uses_stored_secret_and_discards_browser_inspection(tmp_path):
    backend = MemoryBackend()
    _, vault = credentials(tmp_path, backend)
    vault.create("board", "candidate", "secret-never-returned")

    class Browser:
        def __init__(self):
            self.calls = []

        def prepare(self, operation, payload):
            self.calls.append((operation, payload))
            return {"controls": [{"type": "text", "value": payload["value"]}]}

    browser = Browser()
    result = vault.fill(browser, "#password", "board")
    assert result == {"filled": True, "name": "board", "field": "password"}
    assert browser.calls[-1] == ("fill", {"selector": "#password", "value": "secret-never-returned"})
    assert "secret-never-returned" not in json.dumps(result)
    assert vault.fill(browser, "#username", "board", "username")["field"] == "username"
    assert browser.calls[-1][1]["value"] == "candidate"
    with pytest.raises(ValueError, match="field"):
        vault.fill(browser, "#other", "board", "token")


def test_backend_and_browser_failures_do_not_disclose_secret_or_fallback(tmp_path):
    class Unavailable:
        def set_password(self, *_):
            raise RuntimeError("backend error accidentally includes supplied-test-password")

        def get_password(self, *_):
            raise RuntimeError("backend error accidentally includes supplied-test-password")

    workspace, vault = credentials(tmp_path, Unavailable())
    with pytest.raises(ValueError, match="OS credential store unavailable") as error:
        vault.create("board", secret="supplied-test-password")
    assert "supplied-test-password" not in str(error.value)
    assert workspace.store.list("credential") == []

    good = MemoryBackend()
    _, vault = credentials(tmp_path, good)
    vault.create("board", secret="supplied-test-password")

    class FailingBrowser:
        def prepare(self, *_):
            raise RuntimeError("fill failed with supplied-test-password")

    with pytest.raises(ValueError) as error:
        vault.fill(FailingBrowser(), "#password", "board")
    assert "supplied-test-password" not in str(error.value)

    _, unavailable = credentials(tmp_path, Unavailable())
    with pytest.raises(ValueError, match="OS credential store unavailable"):
        unavailable.fill(FailingBrowser(), "#password", "board")


def test_default_backend_rejects_non_os_storage_without_writing(tmp_path, monkeypatch):
    from worklife.credentials import Credentials

    writes = []
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(
            get_keyring=lambda: SimpleNamespace(), set_password=lambda *args: writes.append(args)
        ),
    )
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError, match="OS credential store unavailable"):
        Credentials(workspace).create("board")
    assert writes == []
    assert workspace.store.list("credential") == []
