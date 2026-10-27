"""Reproducible hash-budget experiment, not a network or consensus simulation."""

import hashlib
import math
from statistics import NormalDist

from .blockchain import BLOCK_BITS, meets_work, pow_digest
from .storage import canonical

DOMAIN = "worklife-chain-hash-budget-simulation-v1"
Z95 = NormalDist().inv_cdf(0.975)


def _wilson(successes, total):
    if not total:
        return None
    proportion = successes / total
    denominator = 1 + Z95**2 / total
    center = (proportion + Z95**2 / (2 * total)) / denominator
    radius = Z95 * math.sqrt(proportion * (1 - proportion) / total + Z95**2 / (4 * total**2)) / denominator
    return [max(0.0, min(center - radius, proportion)), min(1.0, max(center + radius, proportion))]


def _sample(key_count, attempts, *, role, case_keys, seed, repeat):
    keys_used = min(key_count, attempts)
    bodies = [
        hashlib.sha256(
            canonical(
                {
                    "domain": DOMAIN,
                    "seed": seed,
                    "repeat": repeat,
                    "case_keys": case_keys,
                    "role": role,
                    "author": hashlib.sha256(f"{DOMAIN}:{seed}:{role}:{key}".encode()).hexdigest(),
                }
            )
        ).digest()
        for key in range(keys_used)
    ]
    accepted = 0
    examples = []
    for attempt in range(attempts):
        key = attempt % key_count
        nonce = attempt // key_count
        body_digest = bodies[key]
        digest = pow_digest(body_digest, nonce)
        if meets_work(digest, BLOCK_BITS):
            accepted += 1
            if len(examples) < 3:
                examples.append(
                    {
                        "key_index": key,
                        "body_digest": body_digest.hex(),
                        "nonce": nonce,
                        "digest": digest.hex(),
                    }
                )
    return accepted, examples


def _difference(case, baseline):
    observed, reference = case["observed_attacker_share"], baseline["observed_attacker_share"]
    if observed is None or reference is None:
        return {
            "expected": 0.0,
            "observed": None,
            "ci95": None,
            "sampling_tolerance95": None,
            "zero_effect_in_ci95": None,
        }
    if baseline is case:
        return {
            "expected": 0.0,
            "observed": 0.0,
            "ci95": [0.0, 0.0],
            "sampling_tolerance95": 0.0,
            "zero_effect_in_ci95": True,
        }
    low, high = case["attacker_share_ci95"]
    base_low, base_high = baseline["attacker_share_ci95"]
    delta = observed - reference
    lower_margin = math.hypot(observed - low, base_high - reference)
    upper_margin = math.hypot(high - observed, reference - base_low)
    interval = [max(-1.0, delta - lower_margin), min(1.0, delta + upper_margin)]
    return {
        "expected": 0.0,
        "observed": delta,
        "ci95": interval,
        "sampling_tolerance95": max(lower_margin, upper_margin),
        "zero_effect_in_ci95": interval[0] <= 0 <= interval[1],
    }


def simulate(
    *, keys=(1, 1000, 10000), total_trials=1_500_000, attacker_fraction=0.2, seed=20261027, repeats=1
):
    """Spend the same exact combined PoW trial budget in every identity case.

    Synthetic 32-byte author identifiers stand in for already-qualified keys.
    Every attempt uses the chain's real PoW digest and fixed work threshold;
    signatures and qualification are deliberately outside this experiment.
    """
    keys = tuple(keys)
    if not keys or any(type(count) is not int or count < 1 for count in keys) or len(set(keys)) != len(keys):
        raise ValueError("keys must contain distinct positive integers")
    if type(total_trials) is not int or total_trials < 1 or type(repeats) is not int or repeats < 1:
        raise ValueError("total_trials and repeats must be positive integers")
    if not isinstance(attacker_fraction, (int, float)) or not math.isfinite(attacker_fraction):
        raise ValueError("attacker_fraction must be finite and between zero and one")
    if not 0 <= attacker_fraction <= 1:
        raise ValueError("attacker_fraction must be finite and between zero and one")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    attacker_attempts = math.floor(total_trials * attacker_fraction)
    honest_attempts = total_trials - attacker_attempts
    proof_work = 2**BLOCK_BITS
    cases = []
    for key_count in keys:
        sides = {}
        for role, count, attempts in (
            ("honest", 1, honest_attempts),
            ("attacker", key_count, attacker_attempts),
        ):
            accepted = 0
            examples = []
            for repeat in range(repeats):
                found, sample = _sample(
                    count, attempts, role=role, case_keys=key_count, seed=seed, repeat=repeat
                )
                accepted += found
                examples.extend({"repeat": repeat, **example} for example in sample[: 3 - len(examples)])
            sides[role] = {
                "keys": count,
                "keys_used": min(count, attempts),
                "attempts": attempts * repeats,
                "accepted_proofs": accepted,
                "expected_proofs": attempts * repeats / proof_work,
                "work": accepted * proof_work,
                "proof_examples": examples,
            }
        accepted = sum(side["accepted_proofs"] for side in sides.values())
        attacker_accepted = sides["attacker"]["accepted_proofs"]
        cases.append(
            {
                "attacker_keys": key_count,
                "attempts": total_trials * repeats,
                **sides,
                "accepted_proofs": accepted,
                "expected_attacker_share": attacker_attempts / total_trials,
                "observed_attacker_share": attacker_accepted / accepted if accepted else None,
                "attacker_share_ci95": _wilson(attacker_accepted, accepted),
            }
        )
    baseline = next((case for case in cases if case["attacker_keys"] == 1), None)
    for case in cases:
        case["difference_from_single_key"] = _difference(case, baseline) if baseline else None
    return {
        "experiment": DOMAIN,
        "parameters": {
            "keys": list(keys),
            "total_trials_per_repeat_per_case": total_trials,
            "repeats": repeats,
            "requested_attacker_fraction": attacker_fraction,
            "seed": seed,
        },
        "block_bits": BLOCK_BITS,
        "work_per_accepted_proof": proof_work,
        "total_attempts_executed": total_trials * repeats * len(keys),
        "identity_bonus": 0,
        "cases": cases,
        "naive_identity_vote_control": [
            {"attacker_keys": count, "honest_keys": 1, "attacker_share": count / (count + 1)}
            for count in keys
        ],
        "assumptions": {
            "all_keys_already_qualified": True,
            "honest_keys": 1,
            "hashes_behave_uniformly": True,
            "influence_measure": "accepted proof work at the chain's fixed difficulty",
            "budget_measure": "calls to the chain PoW hash primitive, including unsuccessful attempts",
            "key_material": "deterministic synthetic 32-byte author identifiers; no key generation or signing",
            "expected_effect_of_key_count": "zero at a fixed hash-trial allocation",
            "qualification_cost": "ignored in attacker's favor; paying it from a fixed budget leaves less mining work",
        },
        "uncertainty": {
            "share_ci95": "Wilson score interval conditional on the total accepted proofs",
            "difference_ci95": "Newcombe interval from independent Wilson intervals; baseline itself is identical data",
            "sampling_tolerance95": "maximum one-sided Newcombe margin for the observed share difference",
            "interpretation": "Finite samples fluctuate. An interval containing zero does not prove equal influence.",
            "multiplicity": "Intervals are per comparison, not a simultaneous confidence guarantee across cases.",
        },
        "excluded_costs": [
            "qualification",
            "signatures",
            "LLM",
            "key_setup",
            "body_setup",
            "network",
            "storage",
        ],
        "not_established": [
            "consensus_safety",
            "wall_clock_performance",
            "resistance_to_majority_hash_power",
            "truth_of_employer_claims",
            "qualification_cost_equivalence",
        ],
    }
