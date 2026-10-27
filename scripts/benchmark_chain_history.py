#!/usr/bin/env python3
"""Measure verified local history reads, using real development-profile proofs.

Run: WORKLIFE_CHAIN_PROFILE=development python scripts/benchmark_chain_history.py
This small synthetic benchmark makes no network capacity or security claim.
"""

import argparse
import hashlib
import json
import platform
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from worklife import blockchain, qualification  # noqa: E402
from worklife.storage import canonical  # noqa: E402
from worklife.workspace import Workspace  # noqa: E402


def measure(function):
    runs = []
    for _ in range(3):
        started = perf_counter()
        result = function()
        runs.append(perf_counter() - started)
    return result, {"runs_seconds": runs, "median_seconds": statistics.median(runs), "max_seconds": max(runs)}


def run_benchmark(cases):
    if blockchain.PROFILE != "development":
        raise ValueError(
            "Set WORKLIFE_CHAIN_PROFILE=development; public-profile mining is intentionally refused"
        )
    if not cases or any(type(n) is not int or not 1 <= n <= 1000 for n in cases):
        raise ValueError("Block counts must be integers from 1 to 1000")
    cases = sorted(set(cases))
    # Public synthetic seed, never an operator's signing key or real employer data.
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public = key.public_key().public_bytes_raw().hex()
    author = hashlib.sha256(bytes.fromhex(public)).hexdigest()
    base = datetime(2026, 10, 15, tzinfo=UTC)
    certificate = qualification.qualify(key, blockchain.GENESIS, at=base, max_attempts=1_000_000)
    blocks, measurements, parent, previous = [], [], blockchain.GENESIS, "0" * 64
    attempts = 0
    for height in range(1, max(cases) + 1):
        stamp = (base + timedelta(seconds=height)).isoformat().replace("+00:00", "Z")
        event = {
            "version": 1,
            "author": author,
            "public_key": public,
            "seq": height,
            "prev": previous,
            "kind": "employer",
            "subject": "bench.example",
            "created_at": stamp,
            "payload": {
                "claim": "Synthetic benchmark only",
                "evidence_kind": "hypothesis",
                "source_url": "https://bench.example",
                "observed_at": stamp,
            },
        }
        digest = hashlib.sha256(canonical(event)).digest()
        event.update(event_id=digest.hex(), signature=key.sign(digest).hex())
        previous = event["event_id"]
        body = {
            "version": blockchain.VERSION,
            "network": blockchain.NETWORK,
            "parent": parent,
            "height": height,
            "created_at": stamp,
            "author": author,
            "public_key": public,
            "qualification": certificate,
            "events": [event],
        }
        body_digest = hashlib.sha256(canonical(body)).digest()
        for nonce in range(1_000_000):
            proof = blockchain.pow_digest(body_digest, nonce)
            if blockchain.meets_work(proof, blockchain.BLOCK_BITS):
                break
        else:
            raise ValueError("Synthetic block exhausted 1000000 real proof attempts")
        attempts += nonce + 1
        blocks.append({**body, "nonce": nonce, "block_id": proof.hex(), "signature": key.sign(proof).hex()})
        parent = proof.hex()
    with TemporaryDirectory(prefix="worklife-history-benchmark-") as home:
        chain, imported = Workspace(home).blockchain, 0
        for count in cases:
            for offset in range(imported, count, 100):
                batch = blocks[offset : min(offset + 100, count)]
                result = chain.import_blocks(batch)
                assert result["imported"] == len(batch)
            imported = count
            status, status_time = measure(chain.status)
            page, page_time = measure(lambda: chain.page(after=count, limit=100))
            assert status["height"] == status["blocks"] == count
            assert page == {"blocks": [], "next_cursor": count}
            measurements.append(
                {"blocks": count, "events": count, "status": status_time, "empty_terminal_page": page_time}
            )
    return {
        "benchmark": "verified-history-reads-v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "chain_profile": blockchain.PROFILE,
        "rules": blockchain.PROTOCOL,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "parameters": {
            "block_cases": cases,
            "events_per_block": 1,
            "reads_per_operation": 3,
            "max_blocks": 1000,
            "max_import_batch": 100,
            "max_attempts_per_block": 1_000_000,
        },
        "fixture": {
            "base_time": base.isoformat(),
            "synthetic_public_key": public,
            "qualification_attempts": certificate["nonce"] + 1,
            "block_pow_attempts": attempts,
            "last_block_body_bytes": len(canonical(body)),
        },
        "measurements": measurements,
        "limits": [
            "Local cumulative linear DAG; one small event per block; temporary SQLite database.",
            "Authentic signatures and real proofs; normal import and complete read validation.",
            "Development proofs reduce setup cost; this does not benchmark public-network mining.",
            "No HTTP, external nodes, large payloads, hostile forks or security guarantees measured.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", type=int, nargs="+", default=[100, 200, 400])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_benchmark(args.blocks)
    except ValueError as exc:
        parser.error(str(exc))
    document = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document)
    print(document, end="")


if __name__ == "__main__":
    main()
