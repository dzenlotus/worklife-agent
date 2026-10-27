import hashlib
import json
from copy import deepcopy

import pytest

from worklife.blockchain import BLOCK_BITS, CONFIRMATIONS, GENESIS, Blockchain, meets_work, pow_digest
from worklife.ledger import Ledger
from worklife.storage import Store, canonical

AT = "2026-10-15T10:00:00Z"


def node(path):
    store = Store(path)
    return Blockchain(store, Ledger(store))


def publish(chain, supersedes=None, kind="employer"):
    payload = {
        "claim": "Employer advertises a remote role",
        "evidence_kind": "advertised",
        "source_url": "https://acme.example/jobs",
        "observed_at": AT,
    }
    if supersedes:
        payload["supersedes"] = supersedes
    return chain.ledger.publish(kind, "acme.example", payload)


def mine(chain, events=None, at=AT):
    result = chain.mine(events, at=at)
    assert result["mined"]
    assert 1 <= result["attempts"] <= 100000
    return result["block"]


def next_time(second):
    return f"2026-10-15T10:00:{second:02d}Z"


def resign(block, ledger):
    body = {k: v for k, v in block.items() if k not in {"nonce", "block_id", "signature"}}
    digest = hashlib.sha256(canonical(body)).digest()
    for nonce in range(100000):
        proof = pow_digest(digest, nonce)
        if meets_work(proof):
            return {
                **body,
                "nonce": nonce,
                "block_id": proof.hex(),
                "signature": ledger.key.sign(proof).hex(),
            }
    raise AssertionError("Fixture exhausted proof budget")


def test_first_block_requires_temporary_qualification_and_persists(tmp_path):
    chain = node(tmp_path)
    event = publish(chain)
    assert chain.status()["height"] == 0
    assert chain.status()["head"] == GENESIS
    with pytest.raises(ValueError, match="qualif"):
        chain.mine(at=AT)
    certificate = chain.qualify(at=AT)
    assert certificate["anchor"] == GENESIS
    block = mine(chain)
    assert block["events"] == [event]
    assert block["parent"] == GENESIS
    assert meets_work(bytes.fromhex(block["block_id"]), BLOCK_BITS)
    assert chain.status()["cumulative_work"] == 2**BLOCK_BITS
    assert chain.confirmation(event["event_id"])["status"] == "included"
    reopened = node(tmp_path)
    assert reopened.all() == [block]
    assert reopened.status()["head"] == block["block_id"]
    assert reopened.page()["blocks"] == [block]
    assert reopened.page(after=1) == {"blocks": [], "next_cursor": 1}


def test_month_expiration_renewal_and_historical_import(tmp_path):
    chain, replica = node(tmp_path / "a"), node(tmp_path / "b")
    chain.qualify(at="2026-09-30T23:59:58Z")
    old = mine(chain, [], at="2026-09-30T23:59:59Z")
    with pytest.raises(ValueError, match="qualif"):
        chain.mine([], at="2026-10-01T00:00:00Z")
    assert replica.import_blocks([old])["height"] == 1
    renewed = chain.qualify(at="2026-10-01T00:00:00Z")
    assert renewed["anchor"] == old["block_id"]
    new = mine(chain, [], at="2026-10-01T00:00:01Z")
    assert replica.import_blocks([new])["height"] == 2


@pytest.mark.parametrize("representation", ["upper", "spaces"])
def test_noncanonical_signature_cannot_poison_same_block_id(tmp_path, representation):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    block = mine(a, [])
    variant = deepcopy(block)
    signature = variant["signature"]
    variant["signature"] = (
        signature.upper()
        if representation == "upper"
        else " ".join(signature[index : index + 2] for index in range(0, len(signature), 2))
    )
    with pytest.raises(ValueError, match="signature"):
        b.import_blocks([variant])
    assert b.all() == []
    assert b.import_blocks([block])["imported"] == 1
    assert b.all() == a.all()


def test_core_mining_budget_has_a_finite_operational_ceiling(tmp_path):
    chain = node(tmp_path)
    chain.qualify(at=AT)
    with pytest.raises(ValueError, match="budget"):
        chain.mine([], max_attempts=1_000_001, at=AT)


def test_confirmation_depth_and_pending_retraction_do_not_hide_confirmed_claim(tmp_path):
    chain = node(tmp_path)
    original = publish(chain)
    chain.qualify(at=AT)
    mine(chain)
    for second in range(1, CONFIRMATIONS):
        mine(chain, [], at=next_time(second))
    assert chain.confirmation(original["event_id"])["status"] == "confirmed"
    assert chain.active_events() == [original]
    correction = publish(chain, original["event_id"])
    assert chain.active_events() == [original]
    mine(chain, at=next_time(4))
    assert chain.active_events() == [original]
    assert chain.active_events(confirmed_only=False) == [correction]
    for second in range(5, 5 + CONFIRMATIONS - 1):
        mine(chain, [], at=next_time(second))
    assert chain.active_events() == [correction]
    retraction = publish(chain, correction["event_id"], "retraction")
    mine(chain, at=next_time(10))
    assert chain.active_events() == [correction]
    for second in range(11, 11 + CONFIRMATIONS - 1):
        mine(chain, [], at=next_time(second))
    assert chain.active_events() == []
    assert chain.confirmation(retraction["event_id"])["scope"] == "protocol_validity"


def test_valid_forks_converge_by_work_then_deterministic_tie(tmp_path):
    a, b, c, d = [node(tmp_path / name) for name in "abcd"]
    a.qualify(at=AT)
    b.qualify(at=AT)
    left, right = mine(a, []), mine(b, [])
    c.import_blocks([left, right])
    d.import_blocks([right, left])
    assert c.status()["head"] == d.status()["head"] == min(left["block_id"], right["block_id"])
    extended = mine(a, [], at=next_time(1))
    result = c.import_blocks([extended])
    assert result["height"] == 2
    assert result["head"] == extended["block_id"]
    assert c.status()["cumulative_work"] == 2 * 2**BLOCK_BITS
    before = c.status()
    assert c.import_blocks([extended, left, right])["imported"] == 0
    assert c.status() == before
    assert c.page()["blocks"] == sorted(
        [left, right, extended], key=lambda block: (block["height"], block["block_id"])
    )


def test_reorganization_restores_original_event_and_drops_orphan_confirmation(tmp_path):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    original = publish(a)
    first = mine(a)
    b.import_blocks([first])
    b.qualify(at=next_time(1))
    correction = publish(a, original["event_id"])
    orphan = mine(a, at=next_time(1))
    second = mine(b, [], at=next_time(2))
    third = mine(b, [], at=next_time(3))
    result = a.import_blocks([second, third])
    assert result["reorganized"] is True
    assert a.confirmation(correction["event_id"])["status"] == "pending"
    assert a.active_events(confirmed_only=False) == [original]
    assert orphan in a.all()


@pytest.mark.parametrize("field,value", [("nonce", 0), ("height", 44), ("network", "foreign")])
def test_tampered_block_import_is_atomic(tmp_path, field, value):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    first, second = mine(a, []), mine(a, [], at=next_time(1))
    bad = deepcopy(second)
    bad[field] = value if bad[field] != value else value + 1
    with pytest.raises(ValueError):
        b.import_blocks([first, bad])
    assert b.all() == []


def test_fixed_difficulty_and_foreign_key_qualification_rejected(tmp_path):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    b.qualify(at=AT)
    block = mine(a, [])
    bad = deepcopy(block)
    bad["qualification"] = b.store.get("chain_qualification", b.ledger.author_id)
    with pytest.raises(ValueError, match="qualif|author"):
        b.import_blocks([resign(bad, a.ledger)])
    bad = {**block, "bits": 0}
    with pytest.raises(ValueError):
        b.import_blocks([resign(bad, a.ledger)])


def test_qualification_anchor_must_belong_to_parent_ancestry(tmp_path):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    b.qualify(at=AT)
    first, sibling = mine(a, []), mine(b, [])
    a.qualify(at=next_time(1))
    child = mine(a, [], at=next_time(2))
    bad = resign({**child, "parent": sibling["block_id"]}, a.ledger)
    with pytest.raises(ValueError, match="anchor"):
        b.import_blocks([first, bad])
    assert b.all() == [sibling]


def test_replayed_missing_predecessor_and_foreign_retraction_rejected(tmp_path):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    first = publish(a)
    base = mine(a)
    with pytest.raises(ValueError, match="replay|duplicate"):
        a.mine([first], at=next_time(1))
    second = publish(a)
    bad = resign({**base, "events": [second]}, a.ledger)
    with pytest.raises(ValueError, match="author chain"):
        b.import_blocks([bad])
    foreign = deepcopy(first)
    foreign.update(author=b.ledger.author_id, public_key=b.ledger.public_key, kind="retraction")
    foreign["payload"]["supersedes"] = first["event_id"]
    body = {k: v for k, v in foreign.items() if k not in {"event_id", "signature"}}
    foreign["event_id"] = hashlib.sha256(canonical(body)).hexdigest()
    foreign["signature"] = b.ledger.key.sign(bytes.fromhex(foreign["event_id"])).hex()
    with pytest.raises(ValueError, match="author"):
        a.mine([foreign], at=next_time(1))


def test_persisted_corruption_detected_by_status_and_export(tmp_path):
    chain = node(tmp_path)
    chain.qualify(at=AT)
    block = mine(chain, [])
    block["created_at"] = next_time(1)
    with chain.store.connect() as db:
        db.execute("UPDATE objects SET data=? WHERE bucket='chain_blocks'", (json.dumps(block),))
    for read in (chain.status, chain.all, chain.page, chain.canonical_blocks):
        with pytest.raises(ValueError):
            read()


def test_strict_work_budget_and_timestamp_rules(tmp_path):
    a, b = node(tmp_path / "a"), node(tmp_path / "b")
    a.qualify(at=AT)
    assert a.mine([], max_attempts=0, at=AT) == {
        "mined": False,
        "attempts": 0,
        "block": None,
        "head": GENESIS,
    }
    block = mine(a, [])
    with pytest.raises(ValueError, match="time"):
        a.mine([], at=AT)
    future = resign({**block, "created_at": "2099-01-01T00:00:00Z"}, a.ledger)
    with pytest.raises(ValueError):
        b.import_blocks([future])
    with pytest.raises(ValueError, match="100"):
        b.import_blocks([block] * 101)


@pytest.mark.parametrize("count,claim_size", [(101, 30), (12, 60000)])
def test_default_mining_batches_pending_proposals_within_protocol_limits(tmp_path, count, claim_size):
    chain = node(tmp_path)
    chain.qualify(at=AT)
    proposals = [
        chain.ledger.publish(
            "employer",
            "acme.example",
            {
                "claim": "A" * claim_size,
                "evidence_kind": "advertised",
                "source_url": "https://acme.example/jobs",
                "observed_at": AT,
            },
        )
        for _ in range(count)
    ]
    first = mine(chain)
    assert 0 < len(first["events"]) < count
    second = mine(chain, at=next_time(1))
    assert first["events"] + second["events"] == proposals
