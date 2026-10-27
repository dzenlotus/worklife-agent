import copy
import hashlib
import importlib
import importlib.util
from datetime import UTC, datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from worklife.storage import canonical

ANCHOR = "a" * 64
AT = "2026-12-15T12:00:00Z"


def test_qualification_module_exists():
    assert importlib.util.find_spec("worklife.qualification") is not None, (
        "Monthly qualification is not implemented"
    )


@pytest.fixture
def qualification():
    assert importlib.util.find_spec("worklife.qualification") is not None, (
        "Monthly qualification is not implemented"
    )
    return importlib.import_module("worklife.qualification")


@pytest.fixture
def key():
    return Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def public(key):
    return key.public_key().public_bytes_raw().hex()


def reseal(certificate, key, bits):
    body = {field: value for field, value in certificate.items() if field != "signature"}
    for nonce in range(100_000):
        body["nonce"] = nonce
        encoded = canonical(body)
        digest = hashlib.sha256(b"worklife-chain-v1/qualification/v1/work\0" + encoded).digest()
        if int.from_bytes(digest, "big") < 1 << (256 - bits):
            signature = key.sign(
                b"worklife-chain-v1/qualification/v1/signature\0" + hashlib.sha256(encoded).digest()
            ).hex()
            return {**body, "signature": signature}
    raise AssertionError("test could not seal certificate")


def test_period_uses_utc_and_rotates_at_year_boundary(qualification):
    assert qualification.period(AT) == "2026-12"
    assert qualification.period("2027-01-01T00:00:00Z") == "2027-01"
    offset = timezone(timedelta(hours=2))
    assert qualification.period(datetime(2027, 1, 1, 1, tzinfo=offset)) == "2026-12"
    assert qualification.period(datetime(2026, 12, 1, tzinfo=UTC)) == "2026-12"


def test_challenge_is_public_reproducible_and_bound_to_month_key_and_anchor(qualification, key):
    original = qualification.challenge(public(key), ANCHOR, AT)
    assert original == qualification.challenge(public(key), ANCHOR, AT)
    assert original["network"] == "worklife-chain-v1"
    assert original["version"] == 1
    assert original["month"] == "2026-12"
    assert original["expires_at"] == "2027-01-01T00:00:00Z"
    assert original["scope"] == "confirm-employer"
    assert len(original["tasks"]) == 3
    assert original["tasks"] != qualification.challenge(public(key), ANCHOR, "2027-01-01T00:00:00Z")["tasks"]
    assert original["tasks"] != qualification.challenge(public(key), "b" * 64, AT)["tasks"]
    assert (
        original["tasks"]
        != qualification.challenge(public(Ed25519PrivateKey.generate()), ANCHOR, AT)["tasks"]
    )
    answers = qualification.solve(original)
    assert len(answers) == 3
    assert answers[0] == {
        "employer": original["tasks"][0]["document"]["company"]["name"],
        "role": original["tasks"][0]["document"]["position"],
        "remote": original["tasks"][0]["document"]["workplace"]["remote"],
        "salary_min": original["tasks"][0]["document"]["salary"]["from"],
        "salary_max": original["tasks"][0]["document"]["salary"]["to"],
        "currency": original["tasks"][0]["document"]["salary"]["currency"],
    }
    assert answers[2]["valid"] is False
    assert answers[2]["errors"]


def test_certificate_has_fixed_schema_and_real_proof_and_signature(qualification, key):
    assert qualification.QUALIFICATION_BITS == 10
    certificate = qualification.qualify(key, ANCHOR, AT)
    assert set(certificate) == {
        "network",
        "version",
        "public_key",
        "anchor",
        "month",
        "expires_at",
        "scope",
        "answers",
        "nonce",
        "signature",
    }
    assert qualification.verify(certificate, AT) == {
        "author": hashlib.sha256(bytes.fromhex(public(key))).hexdigest(),
        "month": "2026-12",
        "expires_at": "2027-01-01T00:00:00Z",
        "anchor": ANCHOR,
        "scope": "confirm-employer",
    }
    body = {field: value for field, value in certificate.items() if field != "signature"}
    digest = hashlib.sha256(b"worklife-chain-v1/qualification/v1/work\0" + canonical(body)).digest()
    assert int.from_bytes(digest, "big") < 1 << 246
    key.public_key().verify(
        bytes.fromhex(certificate["signature"]),
        b"worklife-chain-v1/qualification/v1/signature\0" + hashlib.sha256(canonical(body)).digest(),
    )


def test_expiration_and_historical_validation(qualification, key):
    certificate = qualification.qualify(key, ANCHOR, AT)
    with pytest.raises(ValueError, match="month|expired"):
        qualification.verify(certificate, "2027-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="month|expired"):
        qualification.verify(certificate, "2026-11-30T23:59:59Z")
    assert qualification.verify(certificate, AT)["month"] == "2026-12"


@pytest.mark.parametrize(
    "field,value",
    [
        ("network", "other-chain"),
        ("version", 2),
        ("public_key", "0" * 64),
        ("anchor", "b" * 64),
        ("month", "2027-01"),
        ("expires_at", "2027-02-01T00:00:00Z"),
        ("scope", "all"),
        ("answers", []),
        ("nonce", -1),
        ("signature", "0" * 128),
    ],
)
def test_certificate_mutations_are_rejected(qualification, key, field, value):
    certificate = qualification.qualify(key, ANCHOR, AT)
    certificate[field] = value
    with pytest.raises(ValueError):
        qualification.verify(certificate, AT)


def test_signed_wrong_answers_and_other_key_cannot_reuse_certificate(qualification, key):
    certificate = qualification.qualify(key, ANCHOR, AT)
    wrong = copy.deepcopy(certificate)
    wrong["answers"][0]["employer"] = "Wrong employer"
    with pytest.raises(ValueError, match="answers"):
        qualification.verify(reseal(wrong, key, qualification.QUALIFICATION_BITS), AT)
    other_key = Ed25519PrivateKey.generate()
    swapped = {**certificate, "public_key": public(other_key)}
    with pytest.raises(ValueError):
        qualification.verify(reseal(swapped, other_key, qualification.QUALIFICATION_BITS), AT)


def test_proof_threshold_cannot_be_advertised_down(qualification, key):
    certificate = qualification.qualify(key, ANCHOR, AT)
    certificate["bits"] = 0
    with pytest.raises(ValueError):
        qualification.verify(certificate, AT)


def test_work_is_bounded_and_does_not_change_on_retry(qualification, key, monkeypatch):
    monkeypatch.setattr(qualification, "QUALIFICATION_BITS", 255)
    with pytest.raises(ValueError, match="attempt"):
        qualification.qualify(key, ANCHOR, AT, max_attempts=3)
    for invalid in (True, 0, -1, 1_000_001, "100"):
        with pytest.raises(ValueError, match="attempt"):
            qualification.qualify(key, ANCHOR, AT, max_attempts=invalid)
    monkeypatch.setattr(qualification, "QUALIFICATION_BITS", 10)
    assert qualification.qualify(key, ANCHOR, AT) == qualification.qualify(key, ANCHOR, AT)


def test_qualification_search_can_resume_a_contiguous_bounded_nonce_range(qualification, key, monkeypatch):
    attempted = []

    def no_success(body):
        attempted.append(body["nonce"])
        return False

    monkeypatch.setattr(qualification, "_work", no_success)
    for offset in (7, 10):
        with pytest.raises(ValueError, match="exhausted"):
            qualification.qualify(key, ANCHOR, AT, max_attempts=3, start_nonce=offset)
    assert attempted == [7, 8, 9, 10, 11, 12]
    with pytest.raises(ValueError, match="exhausted"):
        qualification.qualify(key, ANCHOR, AT, max_attempts=1, start_nonce=2**63 - 1)
    assert attempted[-1] == 2**63 - 1


@pytest.mark.parametrize(
    "start_nonce,max_attempts", [(-1, 1), (True, 1), (1.0, 1), ("1", 1), (2**63, 1), (2**63 - 1, 2)]
)
def test_qualification_rejects_invalid_nonce_ranges(qualification, key, start_nonce, max_attempts):
    with pytest.raises(ValueError, match="nonce"):
        qualification.qualify(key, ANCHOR, AT, max_attempts=max_attempts, start_nonce=start_nonce)


def test_resumed_proof_uses_absolute_nonce_and_unchanged_certificate_schema(qualification, key):
    certificate = qualification.qualify(key, ANCHOR, AT)
    resumed = qualification.qualify(key, ANCHOR, AT, max_attempts=1, start_nonce=certificate["nonce"])
    assert resumed == certificate
    assert qualification.verify(resumed, AT)["month"] == "2026-12"


def test_strict_types_sizes_and_challenge_rules(qualification, key):
    for invalid in (None, True, "f", "G" * 64, "0" * 65):
        with pytest.raises(ValueError):
            qualification.challenge(invalid, ANCHOR, AT)
        with pytest.raises(ValueError):
            qualification.challenge(public(key), invalid, AT)
    for invalid_at in (True, "2026-12", "bad", datetime(2026, 12, 1)):
        with pytest.raises(ValueError):
            qualification.period(invalid_at)
    challenge = qualification.challenge(public(key), ANCHOR, AT)
    challenge["tasks"][0]["document"]["position"] = "Altered rules"
    with pytest.raises(ValueError):
        qualification.solve(challenge)
    certificate = qualification.qualify(key, ANCHOR, AT)
    for altered in (
        {**certificate, "version": True},
        {**certificate, "nonce": True},
        {**certificate, "extra": "field"},
        {**certificate, "answers": "x" * 20_000},
        [],
        None,
    ):
        with pytest.raises(ValueError):
            qualification.verify(altered, AT)


@pytest.mark.parametrize("invalid_month", [None, True, 202612, [], "not-a-month"])
def test_solver_rejects_malformed_month_as_value_error(qualification, key, invalid_month):
    challenge = qualification.challenge(public(key), ANCHOR, AT)
    challenge["month"] = invalid_month
    with pytest.raises(ValueError):
        qualification.solve(challenge)


def test_correct_signature_does_not_replace_proof_work(qualification, key):
    certificate = qualification.qualify(key, ANCHOR, AT)
    body = {field: value for field, value in certificate.items() if field != "signature"}
    for nonce in range(100):
        body["nonce"] = nonce
        encoded = canonical(body)
        digest = hashlib.sha256(b"worklife-chain-v1/qualification/v1/work\0" + encoded).digest()
        if int.from_bytes(digest, "big") >= 1 << (256 - qualification.QUALIFICATION_BITS):
            break
    signed = {
        **body,
        "signature": key.sign(
            b"worklife-chain-v1/qualification/v1/signature\0" + hashlib.sha256(encoded).digest()
        ).hex(),
    }
    with pytest.raises(ValueError, match="proof of work"):
        qualification.verify(signed, AT)
