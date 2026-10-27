import pytest


@pytest.fixture(autouse=True)
def no_live_shared_network(monkeypatch):
    """Product networking is automatic; tests use explicit local/injected transports."""
    monkeypatch.setenv("WORKLIFE_NETWORK_OFFLINE", "1")
