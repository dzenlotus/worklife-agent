"""Explicit public-node worker with bounded proof batches and a measured CPU duty policy."""

import math
import time

from .chain_network import BlockchainNetwork
from .storage import now


def cpu_pause(cpu_seconds, wall_seconds, fraction):
    if (
        not isinstance(fraction, (int, float))
        or not math.isfinite(fraction)
        or not 0 < fraction <= 1
        or cpu_seconds < 0
        or wall_seconds < 0
    ):
        raise ValueError("CPU fraction must be finite and in (0, 1]")
    return max(0.0, cpu_seconds / fraction - wall_seconds)


def run_cycle(workspace, network, batch_attempts=250000):
    if type(batch_attempts) is not int or not 1 <= batch_attempts <= 1_000_000:
        raise ValueError("Worker batch must be between 1 and 1000000 attempts")
    sync = network.tick()
    chain = workspace.blockchain
    rights = {"status": "valid", "attempts": 0}
    mining = {"mined": False, "attempts": 0, "block_id": None}
    if not chain.status()["qualified"]:
        try:
            chain.qualify(max_attempts=batch_attempts)
            progress = workspace.store.get("chain_qualification_progress", workspace.ledger.author_id)
            rights = {"status": "earned", "attempts": progress["last_attempts"]}
        except ValueError as exc:
            if not str(exc).startswith("Qualification proof exhausted"):
                raise
            rights = {"status": "pending", "attempts": batch_attempts}
    if rights["status"] != "pending":
        result = chain.mine(max_attempts=batch_attempts)
        mining = {
            "mined": result["mined"],
            "attempts": result["attempts"],
            "block_id": result["block"]["block_id"] if result["block"] else None,
        }
        if result["mined"]:
            network.mark_dirty()
    return {"at": now(), "qualification": rights, "mining": mining, "chain": chain.status(), "network": sync}


def worker_cycles(
    workspace,
    peers_callable,
    *,
    cpu_fraction=0.25,
    batch_attempts=250000,
    sync_seconds=30,
    once=False,
    telegram=None,
):
    cpu_pause(0, 0, cpu_fraction)
    if not isinstance(sync_seconds, (int, float)) or not math.isfinite(sync_seconds) or sync_seconds < 1:
        raise ValueError("Sync interval must be at least one second")
    network = BlockchainNetwork(workspace, peers_callable, interval_seconds=sync_seconds, telegram=telegram)
    while True:
        started, cpu_started = time.monotonic(), time.process_time()
        packet = run_cycle(workspace, network, batch_attempts)
        elapsed, cpu = time.monotonic() - started, time.process_time() - cpu_started
        pause = cpu_pause(cpu, elapsed, cpu_fraction)
        packet["worker"] = {
            "cpu_seconds": cpu,
            "elapsed_seconds": elapsed,
            "pause_seconds": pause,
            "cpu_fraction": cpu_fraction,
        }
        yield packet
        if once:
            return
        time.sleep(max(0.01, pause))
