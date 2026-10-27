"""Public monthly synthetic tasks and temporary, compute-backed confirmation rights.

Rules are public and reproducible, not a test of intelligence, independence or truth.
A new key must repeat the work; keys alone confer no additional voting weight.
"""

import hashlib
import re
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .storage import canonical

NETWORK = "worklife-chain-v1"
QUALIFICATION_VERSION = 1
QUALIFICATION_BITS = 10
SCOPE = "confirm-employer"
MAX_ATTEMPTS = 1_000_000
WORK_DOMAIN = b"worklife-chain-v1/qualification/v1/work\0"
SIGN_DOMAIN = b"worklife-chain-v1/qualification/v1/signature\0"
BASE_FIELDS = {"network", "version", "public_key", "anchor", "month", "expires_at", "scope"}
CERTIFICATE_FIELDS = BASE_FIELDS | {"answers", "nonce", "signature"}


def _time(at):
    if at is None:
        return datetime.now(UTC)
    if type(at) is str and len(at) <= 40:
        try:
            at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Qualification time must be an ISO timestamp") from None
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Qualification time must include a timezone")
    return at.astimezone(UTC)


def period(at=None):
    """Return the UTC calendar month, including for a supplied historical timestamp."""
    current = _time(at)
    return f"{current.year:04d}-{current.month:02d}"


def _hex(value, size, name):
    if type(value) is not str or re.fullmatch(f"[0-9a-f]{{{size}}}", value) is None:
        raise ValueError(f"Qualification {name} must be lowercase hexadecimal ({size} characters)")


def _bounded(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Invalid qualification fields")
    try:
        if len(canonical(value)) > 8192:
            raise ValueError("Qualification exceeds 8 KiB")
    except (TypeError, RecursionError, OverflowError):
        raise ValueError("Qualification must contain bounded JSON values") from None


def _base(public_key, anchor, at):
    _hex(public_key, 64, "public key")
    _hex(anchor, 64, "anchor")
    current = _time(at)
    expiry = datetime(current.year + (current.month == 12), current.month % 12 + 1, 1, tzinfo=UTC)
    return {
        "network": NETWORK,
        "version": QUALIFICATION_VERSION,
        "public_key": public_key,
        "anchor": anchor,
        "month": period(current),
        "expires_at": expiry.isoformat().replace("+00:00", "Z"),
        "scope": SCOPE,
    }


def challenge(public_key, anchor, at=None):
    """Generate public format-extraction and schema tasks, using synthetic employers only."""
    base = _base(public_key, anchor, at)
    seed = hashlib.sha256(canonical(base)).digest()
    employer = "Synthetic Employer " + seed.hex()[:16]
    role = ("Engineer", "Designer", "Analyst", "Researcher")[seed[0] % 4]
    low, high = 1000 + seed[1] * 10, 4000 + seed[2] * 10
    currency = ("USD", "EUR", "GBP")[seed[3] % 3]
    remote = bool(seed[4] % 2)
    candidate = {
        "employer": employer,
        "role": role,
        "remote": remote,
        "salary_min": low,
        "salary_max": high,
        "currency": currency,
    }
    invalid_field = ("salary_max", "remote", "currency")[seed[5] % 3]
    candidate[invalid_field] = {"salary_max": low - 1, "remote": "yes", "currency": "???"}[invalid_field]
    tasks = [
        {
            "format": "employer-json-v1",
            "document": {
                "company": {"name": employer},
                "position": role,
                "workplace": {"remote": remote},
                "salary": {"from": low, "to": high, "currency": currency},
            },
        },
        {
            "format": "employer-notice-v1",
            "document": "\n".join(
                [
                    f"Employer={employer} Notice",
                    f"Role={role}",
                    f"Remote={'yes' if remote else 'no'}",
                    f"SalaryMin={low + 100}",
                    f"SalaryMax={high + 100}",
                    f"Currency={currency}",
                ]
            ),
        },
        {
            "format": "employer-schema-v1",
            "document": candidate,
            "rules": {
                "employer": "nonempty string",
                "role": "nonempty string",
                "remote": "boolean",
                "salary_min": "positive integer",
                "salary_max": "integer >= salary_min",
                "currency": ["USD", "EUR", "GBP"],
                "extra_fields": "forbidden",
            },
        },
    ]
    return {**base, "tasks": tasks}


def solve(value):
    """Return ordered extraction results followed by {valid, errors} schema results."""
    _bounded(value, BASE_FIELDS | {"tasks"})
    if type(value["month"]) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}", value["month"]) is None:
        raise ValueError("Invalid qualification month")
    expected = challenge(value["public_key"], value["anchor"], value["month"] + "-01T00:00:00Z")
    if canonical(value) != canonical(expected):
        raise ValueError("Qualification challenge differs from public rules")
    document = value["tasks"][0]["document"]
    extracted = {
        "employer": document["company"]["name"],
        "role": document["position"],
        "remote": document["workplace"]["remote"],
        "salary_min": document["salary"]["from"],
        "salary_max": document["salary"]["to"],
        "currency": document["salary"]["currency"],
    }
    notice = dict(line.split("=", 1) for line in value["tasks"][1]["document"].splitlines())
    notice_result = {
        "employer": notice["Employer"],
        "role": notice["Role"],
        "remote": notice["Remote"] == "yes",
        "salary_min": int(notice["SalaryMin"]),
        "salary_max": int(notice["SalaryMax"]),
        "currency": notice["Currency"],
    }
    candidate, errors = value["tasks"][2]["document"], []
    for field in ("employer", "role"):
        if type(candidate[field]) is not str or not candidate[field].strip():
            errors.append(field)
    if type(candidate["remote"]) is not bool:
        errors.append("remote")
    if type(candidate["salary_min"]) is not int or candidate["salary_min"] <= 0:
        errors.append("salary_min")
    if type(candidate["salary_max"]) is not int or candidate["salary_max"] < candidate["salary_min"]:
        errors.append("salary_max")
    if candidate["currency"] not in ("USD", "EUR", "GBP"):
        errors.append("currency")
    return [extracted, notice_result, {"valid": not errors, "errors": sorted(errors)}]


def _work(body):
    digest = hashlib.sha256(WORK_DOMAIN + canonical(body)).digest()
    return int.from_bytes(digest, "big") < 1 << (256 - QUALIFICATION_BITS)


def qualify(key, anchor, at=None, max_attempts=100_000):
    """Solve tasks and do at most max_attempts hashes; return only the signed certificate."""
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Qualification requires an Ed25519 private key")
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError(f"Qualification attempts must be an integer from 1 to {MAX_ATTEMPTS}")
    tasks = challenge(key.public_key().public_bytes_raw().hex(), anchor, at)
    body = {field: tasks[field] for field in BASE_FIELDS}
    body["answers"] = solve(tasks)
    for nonce in range(max_attempts):
        body["nonce"] = nonce
        if _work(body):
            signature = key.sign(SIGN_DOMAIN + hashlib.sha256(canonical(body)).digest()).hex()
            return {**body, "signature": signature}
    raise ValueError("Qualification proof exhausted maximum attempts")


def verify(certificate, at=None):
    """Verify rights at the supplied time, preserving historical block validation."""
    _bounded(certificate, CERTIFICATE_FIELDS)
    if type(certificate["version"]) is not int or certificate["version"] != QUALIFICATION_VERSION:
        raise ValueError("Unsupported qualification version")
    if type(certificate["nonce"]) is not int or not 0 <= certificate["nonce"] < 2**63:
        raise ValueError("Invalid qualification nonce")
    _hex(certificate["signature"], 128, "signature")
    expected = challenge(certificate["public_key"], certificate["anchor"], at)
    if any(certificate[field] != expected[field] for field in BASE_FIELDS):
        raise ValueError("Qualification month expired or certificate fields differ from public rules")
    if canonical(certificate["answers"]) != canonical(solve(expected)):
        raise ValueError("Incorrect qualification answers")
    body = {field: value for field, value in certificate.items() if field != "signature"}
    if not _work(body):
        raise ValueError("Insufficient qualification proof of work")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(certificate["public_key"])).verify(
            bytes.fromhex(certificate["signature"]), SIGN_DOMAIN + hashlib.sha256(canonical(body)).digest()
        )
    except InvalidSignature:
        raise ValueError("Invalid qualification signature") from None
    return {
        "author": hashlib.sha256(bytes.fromhex(certificate["public_key"])).hexdigest(),
        "month": certificate["month"],
        "expires_at": certificate["expires_at"],
        "anchor": certificate["anchor"],
        "scope": certificate["scope"],
    }
