import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import pytest

BENCHMARK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_chain_pow.py"
spec = importlib.util.spec_from_file_location("benchmark_chain_pow", BENCHMARK_PATH)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_recommend_bits_rounds_up_and_respects_digest_bounds():
    assert benchmark.recommend_bits(4096, 1) == 12
    assert benchmark.recommend_bits(4097, 1) == 13
    assert benchmark.recommend_bits(2, 30) == 6
    assert benchmark.recommend_bits(0.1, 1) == 0
    assert benchmark.recommend_bits(2**256, 1) == 256
    with pytest.raises(ValueError):
        benchmark.recommend_bits(2**257, 1)


@pytest.mark.parametrize("value", [0, -1, True, "10", math.inf, math.nan])
def test_recommend_bits_rejects_invalid_rates_and_targets(value):
    with pytest.raises(ValueError):
        benchmark.recommend_bits(value, 30)
    with pytest.raises(ValueError):
        benchmark.recommend_bits(10, value)


def test_geometric_timings_use_discrete_attempts_and_finite_budgets():
    stats = benchmark.work_stats(1, 2)
    assert stats["expected_seconds"] == 1
    assert stats["p50_seconds"] == 0.5
    assert stats["p95_seconds"] == 2.5
    assert stats["success_probability"] == {"100000": 1.0, "1000000": 1.0}
    certain = benchmark.work_stats(0, 10)
    assert certain["expected_seconds"] == certain["p95_seconds"] == 0.1
    hard = benchmark.work_stats(18, 1000)
    assert hard["success_probability"]["100000"] == pytest.approx(0.317143438669)
    assert hard["success_probability"]["1000000"] == pytest.approx(0.977955773357)
    for bits in (-1, 257, True, 1.5):
        with pytest.raises(ValueError):
            benchmark.work_stats(bits, 1000)


def test_benchmark_measures_real_hash_paths_and_builds_network_scenarios(monkeypatch):
    from worklife import blockchain

    checked_bits, original_check = [], blockchain.meets_work

    def check(digest, bits):
        checked_bits.append(bits)
        return original_check(digest, bits)

    monkeypatch.setattr(blockchain, "meets_work", check)

    report = benchmark.run_benchmark(attempts=8, repeats=2, cpu_fraction=0.25, target_seconds=30)
    for name in ("block_digest", "block", "qualification"):
        measured = report["measurements"][name]
        assert len(measured["runs"]) == 2
        assert measured["median_hashes_per_second"] > 0
        assert measured["min_hashes_per_second"] <= measured["median_hashes_per_second"]
        assert measured["max_hashes_per_second"] >= measured["median_hashes_per_second"]
        assert all(run["attempts"] == 8 and run["seconds"] > 0 for run in measured["runs"])
    assert report["samples"]["block_body_bytes"] > 500
    assert report["samples"]["qualification_body_bytes"] > 500
    assert [row["nodes"] for row in report["block_scenarios"]] == [1, 3, 5]
    assert [row["bits"] for row in report["qualification_candidates"]] == [14, 16, 18]
    assert report["assumptions"]["repeated_nonce_range_adds_attempts"] is False
    assert checked_bits == [blockchain.BLOCK_BITS] * 24
    assert report["benchmark_profile"] == "pow-digest-and-check-v1"
    rate = report["measurements"]["block"]["median_hashes_per_second"]
    assert report["block_scenarios"][1]["network_hashes_per_second"] == rate * 3 * 0.25


def test_standalone_benchmark_does_not_import_the_server():
    code = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('benchmark', {str(BENCHMARK_PATH)!r}); "
        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); "
        "assert 'worklife.server' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], cwd=BENCHMARK_PATH.parent, check=True)


def test_synthetic_fixture_resumes_distinct_bounded_qualification_ranges(monkeypatch):
    from worklife import qualification

    calls, original = [], qualification.qualify

    def qualify(key, anchor, at, max_attempts=100_000, start_nonce=0):
        calls.append((start_nonce, max_attempts))
        if start_nonce < 2_000_000:
            raise ValueError("Qualification proof exhausted maximum attempts")
        return original(key, anchor, at, max_attempts, start_nonce)

    monkeypatch.setattr(qualification, "qualify", qualify)
    _, body = benchmark._samples()
    assert calls == [(0, 1_000_000), (1_000_000, 1_000_000), (2_000_000, 1_000_000)]
    assert body["nonce"] >= 2_000_000


def test_synthetic_fixture_stops_after_three_million_qualification_attempts(monkeypatch):
    from worklife import qualification

    calls = []

    def exhausted(*args, **kwargs):
        calls.append((kwargs["start_nonce"], kwargs["max_attempts"]))
        raise ValueError("Qualification proof exhausted maximum attempts")

    monkeypatch.setattr(qualification, "qualify", exhausted)
    with pytest.raises(ValueError, match="Synthetic.*3000000"):
        benchmark._samples()
    assert calls == [(0, 1_000_000), (1_000_000, 1_000_000), (2_000_000, 1_000_000)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"attempts": True},
        {"repeats": 0},
        {"cpu_fraction": 0},
        {"cpu_fraction": 1.1},
        {"cpu_fraction": True},
        {"target_seconds": math.inf},
    ],
)
def test_benchmark_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        benchmark.run_benchmark(**kwargs)
