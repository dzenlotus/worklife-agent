import json
import os
import subprocess
import sys
from collections import Counter

import pytest

from worklife import qualification
from worklife.blockchain import GENESIS
from worklife.ledger import Ledger
from worklife.workspace import Workspace

AT = "2026-10-15T10:00:00Z"


def test_qualification_batches_resume_instead_of_repeating_failed_hashes(tmp_path, monkeypatch):
    w = Workspace(tmp_path)
    nonces = []

    def miss(body):
        nonces.append(body["nonce"])
        return False

    monkeypatch.setattr(qualification, "_work", miss)
    for _ in range(2):
        w = Workspace(tmp_path)
        with pytest.raises(ValueError, match="exhausted"):
            w.blockchain.qualify(at=AT, max_attempts=3)
    assert nonces == list(range(6))
    progress = w.store.get("chain_qualification_progress", w.ledger.author_id)
    assert progress["next_nonce"] == 6
    assert progress["anchor"] == GENESIS


def test_a_read_verifies_each_event_once_without_trusting_unverified_ancestors(tmp_path, monkeypatch):
    w = Workspace(tmp_path)
    w.blockchain.qualify(at=AT)
    events = []
    for second in range(3):
        event = w.ledger.publish(
            "employer",
            f"company{second}.example",
            {
                "claim": "Employer advertises remote work",
                "source_url": "https://company.example/jobs",
                "evidence_kind": "advertised",
                "observed_at": AT,
            },
        )
        events.append(event)
        assert w.blockchain.mine(at=f"2026-10-15T10:00:{second:02d}Z")["mined"]
    counts = Counter()
    original = Ledger.check_event

    def checked(event):
        counts[event["event_id"]] += 1
        return original(event)

    monkeypatch.setattr(Ledger, "check_event", staticmethod(checked))
    assert w.blockchain.status()["height"] == 3
    assert counts == Counter({event["event_id"]: 1 for event in events})


def test_cpu_pause_accounts_for_cpu_already_spent_and_elapsed_wall_time():
    from worklife.chain_worker import cpu_pause

    assert cpu_pause(0.25, 0.5, 0.25) == pytest.approx(0.5)
    assert cpu_pause(0.25, 2, 0.25) == 0
    assert cpu_pause(1, 1, 1) == 0
    for invalid in (0, -1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            cpu_pause(1, 1, invalid)


def test_worker_once_earns_rights_and_uses_a_bounded_mining_batch(tmp_path):
    from worklife.chain_network import BlockchainNetwork
    from worklife.chain_worker import run_cycle

    w = Workspace(tmp_path)
    result = run_cycle(w, BlockchainNetwork(w, lambda: []), batch_attempts=100000)
    assert result["qualification"]["status"] == "earned"
    assert result["chain"]["qualified"]
    assert result["mining"]["attempts"] <= 100000
    assert "events" not in result["mining"]


def test_public_profile_worker_once_is_usable_from_the_operator_command(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "worklife",
            "--home",
            str(tmp_path),
            "chain",
            "worker",
            "--once",
            "--batch-attempts",
            "1",
            "--cpu-fraction",
            "0.25",
        ],
        env={**os.environ, "WORKLIFE_CHAIN_PROFILE": "public-testnet-v1", "WORKLIFE_CONFIG": ""},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["chain"]["profile"] == "public-testnet-v1"
    assert packet["chain"]["rules"]["block_bits"] == 25
    assert packet["qualification"]["attempts"] <= 1
    assert packet["mining"]["attempts"] <= 1


def test_slow_peer_sync_waits_a_full_interval_before_retrying(tmp_path, monkeypatch):
    from worklife import chain_network

    clock, calls = [0.0], []

    def slow_sync(*args):
        calls.append(clock[0])
        clock[0] += 31
        return {}

    monkeypatch.setattr(chain_network.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(chain_network, "sync_chain_peer", slow_sync)
    manager = chain_network.BlockchainNetwork(
        Workspace(tmp_path), lambda: [{"url": "https://peer.example", "protocol": 2}], interval_seconds=30
    )
    manager.tick()
    clock[0] += 1
    manager.tick()
    assert len(calls) == 1
