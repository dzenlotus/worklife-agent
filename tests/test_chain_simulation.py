import json

import pytest

from worklife import chain_simulation


def test_fixed_budget_counts_real_key_bound_hashes(monkeypatch):
    actual_pow = chain_simulation.pow_digest
    actual_meets_work = chain_simulation.meets_work
    calls = []

    def record(body_digest, nonce):
        digest = actual_pow(body_digest, nonce)
        calls.append((body_digest, nonce, actual_meets_work(digest)))
        return digest

    monkeypatch.setattr(chain_simulation, "pow_digest", record)
    report = chain_simulation.simulate(keys=(1, 1000), total_trials=20_000, attacker_fraction=0.2)
    assert len(calls) == 40_000
    assert len({(body, nonce) for body, nonce, _ in calls}) == len(calls)
    assert len({body for body, _, _ in calls}) == 1003
    for index, case in enumerate(report["cases"]):
        assert case["attacker"]["attempts"] == 4000
        assert case["honest"]["attempts"] == 16_000
        assert case["expected_attacker_share"] == 0.2
        assert case["attacker"]["work"] == case["attacker"]["accepted_proofs"] * 2 ** report["block_bits"]
        assert case["honest"]["work"] == case["honest"]["accepted_proofs"] * 2 ** report["block_bits"]
        proofs = sum(valid for _, _, valid in calls[index * 20_000 : (index + 1) * 20_000])
        assert case["accepted_proofs"] == proofs
    assert report["naive_identity_vote_control"][-1]["attacker_share"] == 1000 / 1001
    assert report["identity_bonus"] == 0
    json.dumps(report, allow_nan=False)


def test_reproducible_sampling_reports_uncertainty_and_higher_power():
    options = dict(keys=(1, 1000), total_trials=50_000, attacker_fraction=0.2, seed=17, repeats=2)
    report = chain_simulation.simulate(**options)
    assert report == chain_simulation.simulate(**options)
    for case in report["cases"]:
        assert case["attempts"] == 100_000
        assert case["attacker"]["attempts"] == 20_000
        assert case["honest"]["attempts"] == 80_000
        assert case["accepted_proofs"] > 0
        low, high = case["attacker_share_ci95"]
        assert 0 <= low <= case["observed_attacker_share"] <= high <= 1
    assert report["cases"][0]["attacker"] != report["cases"][1]["attacker"]
    difference = report["cases"][1]["difference_from_single_key"]
    assert difference["expected"] == 0
    assert difference["sampling_tolerance95"] > 0
    assert len(difference["ci95"]) == 2
    more_power = chain_simulation.simulate(keys=(1000,), total_trials=100, attacker_fraction=0.4)
    assert more_power["cases"][0]["expected_attacker_share"] == 0.4
    assert more_power["cases"][0]["attacker"]["attempts"] == 40


def test_unused_keys_add_no_attempts_and_report_scope_is_explicit():
    report = chain_simulation.simulate(keys=(1, 10_000), total_trials=1, attacker_fraction=0.2)
    for case in report["cases"]:
        assert case["attacker"]["attempts"] == 0
        assert case["attacker"]["keys_used"] == 0
        assert case["attacker"]["work"] == 0
        assert case["expected_attacker_share"] == 0
        if not case["accepted_proofs"]:
            assert case["observed_attacker_share"] is None
            assert case["attacker_share_ci95"] is None
            assert case["difference_from_single_key"]["observed"] is None
    assert report["assumptions"]["all_keys_already_qualified"] is True
    assert {"qualification", "signatures", "LLM", "key_setup"} <= set(report["excluded_costs"])
    assert "consensus_safety" in report["not_established"]
    assert "wall_clock_performance" in report["not_established"]


@pytest.mark.parametrize(
    "options",
    [
        {"keys": ()},
        {"keys": (0,)},
        {"keys": (1, 1)},
        {"keys": (1.5,)},
        {"total_trials": 0},
        {"total_trials": 1.5},
        {"repeats": 0},
        {"attacker_fraction": -0.1},
        {"attacker_fraction": 1.1},
        {"attacker_fraction": float("nan")},
    ],
)
def test_invalid_budget_is_rejected(options):
    with pytest.raises(ValueError):
        chain_simulation.simulate(total_trials=10, **options) if "total_trials" not in options else (
            chain_simulation.simulate(**options)
        )
