import shlex
import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import httpx
import pytest

from worklife.storage import Store


@pytest.fixture
def release_check(tmp_path, monkeypatch):
    from worklife import releases

    monkeypatch.delenv("WORKLIFE_NETWORK_OFFLINE", raising=False)
    monkeypatch.setattr(releases, "version", lambda name: "0.4.9")
    clock = SimpleNamespace(now=1_800_000_000.0)
    monkeypatch.setattr(releases.time, "time", lambda: clock.now)
    state = SimpleNamespace(payload={"info": {"version": "0.4.10", "yanked": False}}, error=None)
    requests, options = [], []

    def handle(request):
        requests.append(request)
        if state.error:
            raise state.error
        return httpx.Response(200, json=state.payload)

    original_client = httpx.Client

    def client(**kwargs):
        options.append(kwargs)
        return original_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(releases.httpx, "Client", client)
    return releases, Store(tmp_path), clock, state, requests, options


def test_new_stable_release_is_compared_numerically_with_safe_upgrade_command(release_check):
    releases, store, _, _, requests, options = release_check
    result = releases.ReleaseUpdates(store).status()
    assert result["status"] == "checked"
    assert result["installed_version"] == "0.4.9"
    assert result["latest_version"] == "0.4.10"
    assert result["update_available"] is True
    assert result["release_url"] == "https://pypi.org/project/worklife-agent/0.4.10/"
    assert result["checked_at"].endswith("Z")
    assert shlex.split(result["update_command"]) == [
        "uv",
        "pip",
        "install",
        "--python",
        sys.executable,
        "--upgrade",
        "worklife-agent",
    ]
    assert str(requests[0].url) == "https://pypi.org/pypi/worklife-agent/json"
    assert not requests[0].content
    assert options == [{"timeout": 2, "follow_redirects": False}]


@pytest.mark.parametrize("installed", ["0.4.10", "0.5.0", "0.4.10.dev1", "0.5.0rc1"])
def test_current_newer_or_nonstable_installed_version_has_no_notice(release_check, monkeypatch, installed):
    releases, store, *_ = release_check
    monkeypatch.setattr(releases, "version", lambda name: installed)
    assert releases.ReleaseUpdates(store).status()["update_available"] is False


def test_daily_cache_survives_new_checker_and_recomputes_after_upgrade(release_check, monkeypatch):
    releases, store, clock, _, requests, _ = release_check
    assert releases.ReleaseUpdates(store).status()["update_available"]
    clock.now += 3600
    monkeypatch.setattr(releases, "version", lambda name: "0.4.10")
    assert not releases.ReleaseUpdates(Store(store.home)).status()["update_available"]
    assert len(requests) == 1
    clock.now += 86400
    releases.ReleaseUpdates(store).status()
    assert len(requests) == 2


def test_failed_check_is_unavailable_and_throttled_for_a_day(release_check):
    releases, store, clock, state, requests, _ = release_check
    state.error = httpx.ConnectError("network unavailable")
    first = releases.ReleaseUpdates(store).status()
    assert first["status"] == "unavailable"
    assert first["latest_version"] is None
    assert first["update_available"] is False
    assert first["checked_at"]
    clock.now += 10
    assert releases.ReleaseUpdates(Store(store.home)).status() == first
    assert len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"info": {"version": "0.5.0rc1"}},
        {"info": {"version": "0.5.0", "yanked": True}},
        {"info": {"version": "not-a-version"}},
        {"info": {"version": 5}},
        {"info": []},
        [],
    ],
)
def test_invalid_prerelease_or_yanked_response_never_announces_update(release_check, payload):
    releases, store, _, state, _, _ = release_check
    state.payload = payload
    result = releases.ReleaseUpdates(store).status()
    assert result["status"] == "unavailable"
    assert result["update_available"] is False


def test_offline_does_not_contact_provider_or_claim_latest(release_check, monkeypatch):
    releases, store, _, _, requests, _ = release_check
    monkeypatch.setenv("WORKLIFE_NETWORK_OFFLINE", "1")
    result = releases.ReleaseUpdates(store).status()
    assert result["status"] == "offline"
    assert result["latest_version"] is None
    assert result["checked_at"] is None
    assert not result["update_available"]
    assert not requests


def test_outage_preserves_previous_result_but_marks_it_unavailable(release_check):
    releases, store, clock, state, _, _ = release_check
    releases.ReleaseUpdates(store).status()
    clock.now += 86401
    state.error = httpx.ReadTimeout("timeout")
    result = releases.ReleaseUpdates(store).status()
    assert result["status"] == "unavailable"
    assert result["latest_version"] == "0.4.10"
    assert result["update_available"] is False


def test_unknown_distribution_does_not_fail(release_check, monkeypatch):
    releases, store, *_ = release_check

    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(releases, "version", missing)
    result = releases.ReleaseUpdates(store).status()
    assert result["installed_version"] == "unknown"
    assert result["update_available"] is False
