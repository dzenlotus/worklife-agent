#!/usr/bin/env python3
"""Measure local Python PoW paths; estimate timing, never network security."""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from worklife import blockchain, chain_profile, qualification  # noqa: E402
from worklife.storage import canonical  # noqa: E402


def _positive(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Rate and time must be positive finite numbers")


def recommend_bits(hash_rate, target_seconds):
    """Smallest supported bit count whose mean wait meets the supplied target."""
    _positive(hash_rate)
    _positive(target_seconds)
    work = hash_rate * target_seconds
    if not math.isfinite(work) or work > 2**256:
        raise ValueError("Target requires more than 256 bits")
    bits = max(0, math.ceil(math.log2(work))) if work > 1 else 0
    return bits + (2**bits < work)


def work_stats(bits, hash_rate):
    """Independent fresh hashes: geometric attempts, including the successful hash."""
    if type(bits) is not int or not 0 <= bits <= 256:
        raise ValueError("Bits must be an integer from 0 to 256")
    _positive(hash_rate)
    log_failure = math.log1p(-(2.0**-bits)) if bits else None

    def quantile(q):
        return math.ceil(math.log1p(-q) / log_failure) if bits else 1

    return {
        "bits": bits,
        "expected_seconds": 2**bits / hash_rate,
        "p50_seconds": quantile(0.5) / hash_rate,
        "p95_seconds": quantile(0.95) / hash_rate,
        "success_probability": {
            str(n): -math.expm1(n * log_failure) if bits else 1.0 for n in (100_000, 1_000_000)
        },
    }


def _samples():
    # Public synthetic seed only; never a user's key, claim or machine identity.
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public, at = key.public_key().public_bytes_raw().hex(), "2026-10-01T00:00:01Z"
    for start_nonce in range(0, 3_000_000, 1_000_000):
        try:
            certificate = qualification.qualify(
                key, blockchain.GENESIS, at=at, max_attempts=1_000_000, start_nonce=start_nonce
            )
            break
        except ValueError as exc:
            if str(exc) != "Qualification proof exhausted maximum attempts":
                raise
    else:
        raise ValueError("Synthetic benchmark fixture exhausted 3000000 qualification attempts")
    qual_body = {k: v for k, v in certificate.items() if k != "signature"}
    event = {
        "version": 1,
        "public_key": public,
        "author": hashlib.sha256(bytes.fromhex(public)).hexdigest(),
        "seq": 1,
        "prev": "0" * 64,
        "kind": "employer",
        "subject": "synthetic.example",
        "created_at": at,
        "payload": {
            "claim": "Synthetic employer advertises a remote engineering role",
            "source_url": "https://synthetic.example/jobs",
            "evidence_kind": "advertised",
            "observed_at": at,
        },
    }
    event_id = hashlib.sha256(canonical(event)).digest()
    event.update(event_id=event_id.hex(), signature=key.sign(event_id).hex())
    body = {
        "version": blockchain.VERSION,
        "network": blockchain.NETWORK,
        "parent": blockchain.GENESIS,
        "height": 1,
        "created_at": at,
        "author": event["author"],
        "public_key": public,
        "qualification": certificate,
        "events": [event],
    }
    return canonical(body), qual_body


def run_benchmark(attempts=300_000, repeats=3, cpu_fraction=0.25, target_seconds=30):
    for value in (attempts, repeats):
        if type(value) is not int or value < 1:
            raise ValueError("Attempts and repeats must be positive integers")
    _positive(cpu_fraction)
    _positive(target_seconds)
    if cpu_fraction > 1:
        raise ValueError("CPU fraction must be at most 1")
    encoded, qual_body = _samples()
    body_digest = hashlib.sha256(encoded).digest()

    def qual_hash(nonce):
        qual_body["nonce"] = nonce
        return qualification._work(qual_body)

    def block_attempt(nonce):
        return blockchain.meets_work(blockchain.pow_digest(body_digest, nonce), blockchain.BLOCK_BITS)

    measurements = {}
    for name, function in (
        ("block_digest", lambda n: blockchain.pow_digest(body_digest, n)),
        ("block", block_attempt),
        ("qualification", qual_hash),
    ):
        for nonce in range(min(attempts, 1000)):
            function(nonce)
        runs = []
        for _ in range(repeats):
            started = perf_counter()
            for nonce in range(attempts):
                function(nonce)
            seconds = perf_counter() - started
            runs.append({"attempts": attempts, "seconds": seconds, "hashes_per_second": attempts / seconds})
        rates = [run["hashes_per_second"] for run in runs]
        measurements[name] = {
            "runs": runs,
            "median_hashes_per_second": statistics.median(rates),
            "min_hashes_per_second": min(rates),
            "max_hashes_per_second": max(rates),
        }
    scenarios = []
    for nodes in (1, 3, 5):
        rate = measurements["block"]["median_hashes_per_second"] * nodes * cpu_fraction
        bits = recommend_bits(rate, target_seconds)
        scenarios.append(
            {
                "nodes": nodes,
                "network_hashes_per_second": rate,
                "recommended_bits": bits,
                "candidates": [work_stats(b, rate) for b in range(max(0, bits - 1), min(256, bits + 1) + 1)],
            }
        )
    return {
        "benchmark_profile": "pow-digest-and-check-v1",
        "chain_profile": chain_profile.PROFILE,
        "rules": blockchain.PROTOCOL,
        "measured_at": datetime.now(UTC).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "parameters": {
            "attempts": attempts,
            "repeats": repeats,
            "cpu_fraction": cpu_fraction,
            "target_seconds": target_seconds,
            "warmup_attempts": min(attempts, 1000),
        },
        "samples": {
            "synthetic_public_key": qual_body["public_key"],
            "block_body_bytes": len(encoded),
            "qualification_body_bytes": len(canonical(qual_body)),
        },
        "measurements": measurements,
        "block_scenarios": scenarios,
        "qualification_candidates": [
            work_stats(b, measurements["qualification"]["median_hashes_per_second"]) for b in (14, 16, 18)
        ],
        "assumptions": {
            "repeated_nonce_range_adds_attempts": False,
            "timing": "Geometric independent fresh hashes; estimates exclude networking and validation.",
            "cpu_fraction": "Linear duty-cycle estimate per measured single Python thread; benchmark is unthrottled.",
            "qualification": "Actual _work canonical-body path; no early stop at its current fixed difficulty.",
            "block": "Tables use full pow_digest + meets_work attempts; block_digest measures raw hashing only.",
            "scope": "Local host only; external operators must benchmark their actual VPS and software.",
            "cost": "No tokens, fees or per-key weight bonus; PoW still costs CPU time and electricity.",
            "security": "Hash timing and node counts do not establish independence or resistance to optimized miners.",
            "retry": "Same body and repeated nonce range repeats the same hashes; advance nonce or change valid body.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=300_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cpu-fraction", type=float, default=0.25)
    parser.add_argument("--target-seconds", type=float, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_benchmark(args.attempts, args.repeats, args.cpu_fraction, args.target_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    document = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document)
    print(document, end="")


if __name__ == "__main__":
    main()
