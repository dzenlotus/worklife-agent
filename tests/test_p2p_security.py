"""Bounded hostile-peer checks; all keys, files and identities are synthetic."""

import asyncio
import base64
import copy
import hashlib
import json
import random
import sys
from types import SimpleNamespace

import pytest

from worklife.blockchain import BLOCK_BITS, meets_work, pow_digest
from worklife.p2p import IPC_LIMIT, P2PNode
from worklife.p2p_protocol import MAX_FRAME, MAX_PEERS, BlockSwarm
from worklife.storage import canonical
from worklife.workspace import Workspace

AT = "2026-10-15T10:00:00Z"


def resign(block, key):
    body = {k: v for k, v in block.items() if k not in {"nonce", "block_id", "signature"}}
    digest = hashlib.sha256(canonical(body)).digest()
    for nonce in range(100_000):
        proof = pow_digest(digest, nonce)
        if meets_work(proof, BLOCK_BITS):
            return {**block, "nonce": nonce, "block_id": proof.hex(), "signature": key.sign(proof).hex()}
    pytest.fail("Development proof budget exhausted")


@pytest.fixture(scope="module")
def public_history(tmp_path_factory):
    origin = Workspace(tmp_path_factory.mktemp("security-public-origin"))
    origin.ledger.publish(
        "employer",
        "public.example",
        {
            "claim": "Synthetic public employer observation",
            "evidence_kind": "advertised",
            "source_url": "https://public.example/jobs",
            "observed_at": AT,
        },
    )
    origin.blockchain.qualify(at=AT)
    for second in range(3):
        assert origin.blockchain.mine(at=f"2026-10-15T10:00:{second:02d}Z")["mined"]
    return origin.blockchain.all(), origin.ledger.key


@pytest.fixture
def endpoint(tmp_path):
    workspace = Workspace(tmp_path / "home")
    sent, dropped = [], []
    protocol = BlockSwarm(workspace, lambda p, m: sent.append((p, copy.deepcopy(m))), dropped.append)
    protocol.connected("good")
    hello = copy.deepcopy(sent[-1][1])
    protocol.receive("good", hello)
    protocol.receive("good", {"type": "page", "after": 0, "blocks": [], "next_cursor": 0})
    return workspace, protocol, sent, dropped, hello


def assert_good_peer_works(protocol, sent):
    start = len(sent)
    protocol.receive("good", {"type": "get_page", "after": 0, "limit": 100})
    assert len(sent) == start + 1
    assert sent[-1][0] == "good" and sent[-1][1]["type"] == "page"
    assert protocol.status()["verified_peers"] == 1


def test_private_requests_exec_and_control_commands_are_inert(endpoint, tmp_path, public_history):
    workspace, protocol, sent, dropped, hello = endpoint
    history, _ = public_history
    workspace.blockchain.import_blocks(history)
    workspace.save_profile({"name": "PRIVATE-PROFILE-CANARY-192a", "facts": []})
    private = workspace.home / "private-cv.txt"
    private.write_text("PRIVATE-CV-CANARY-53ab")
    transport_key = workspace.home / "p2p-identity.key"
    transport_key.write_bytes(b"SYNTHETIC-TRANSPORT-KEY-CANARY!")
    executed = tmp_path / "peer-command-was-executed"
    secrets = [private.read_text(), workspace.get_profile()["name"], transport_key.read_text()]
    secrets.append((workspace.home / "identity.key").read_bytes().hex())
    commands = [
        {"type": "profile"},
        {"type": "cv", "path": str(private)},
        {"type": "keys", "path": str(transport_key)},
        {"type": "read_file", "path": str(private)},
        {"type": "exec", "command": ["touch", str(executed)]},
        {"type": "shutdown"},
        {"type": "stats"},
        {"type": "disconnect", "peer": "good"},
        {"type": "join_peer", "peer": "f" * 64},
        {"type": "send_raw", "peer": "good", "payload": "eyJ0eXBlIjoic2h1dGRvd24ifQ=="},
        {"type": "get_page", "after": 0, "limit": 100, "path": str(private)},
    ]
    for command in commands:
        protocol.connected("bad")
        protocol.receive("bad", hello)
        before = len(sent)
        protocol.receive("bad", command)
        assert dropped[-1] == "bad" and "bad" not in protocol.peers
        assert len(sent) == before
        assert_good_peer_works(protocol, sent)
    assert not executed.exists()
    assert workspace.blockchain.all() == history
    assert private.read_text() == secrets[0]
    assert transport_key.read_text() == secrets[2]
    transcript = canonical({"sent": sent, "status": protocol.status()}).decode()
    assert all(secret not in transcript for secret in secrets)
    assert sent[-1][1]["blocks"] == history
    # A fresh real receiver still accepts the public page after all hostile requests.
    receiver = Workspace(tmp_path / "receiver")
    other = BlockSwarm(receiver, lambda *_: None, lambda _: pytest.fail("Good peer was rejected"))
    other.connected("host")
    other.receive("host", {**hello, "head": history[-1]["block_id"], "height": 3, "blocks": 3})
    other.receive("host", sent[-1][1])
    assert receiver.blockchain.all() == history
    assert receiver.store.list("profile") == []


@pytest.mark.parametrize("fault", ["signature", "proof", "network", "qualification", "foreign_key"])
def test_forged_batches_do_not_change_accepted_history(endpoint, public_history, tmp_path, fault):
    workspace, protocol, sent, dropped, hello = endpoint
    history, key = public_history
    workspace.blockchain.import_blocks(history[:1])
    before = workspace.blockchain.all()
    forged = copy.deepcopy(history[2])
    if fault == "signature":
        forged["signature"] = "0" * 128
    elif fault == "proof":
        forged["nonce"] += 1
    elif fault == "network":
        forged = resign({**forged, "network": "foreign-network"}, key)
    elif fault == "qualification":
        forged["qualification"]["network"] = "foreign-network"
        forged = resign(forged, key)
    else:
        foreign = Workspace(tmp_path / "foreign")
        forged["public_key"] = foreign.ledger.public_key
        forged = resign(forged, foreign.ledger.key)
    protocol.connected("bad")
    protocol.receive("bad", hello)
    protocol.receive("bad", {"type": "page", "after": 0, "blocks": [history[1], forged], "next_cursor": 2})
    assert dropped == ["bad"]
    assert workspace.blockchain.all() == before
    assert protocol.status()["transfers"]["blocks_imported"] == 0
    assert_good_peer_works(protocol, sent)


def test_replayed_event_with_valid_block_work_and_signature_is_atomic(endpoint, public_history):
    workspace, protocol, sent, dropped, hello = endpoint
    history, key = public_history
    workspace.blockchain.import_blocks(history[:1])
    forged = resign({**history[2], "events": copy.deepcopy(history[0]["events"])}, key)
    protocol.connected("bad")
    protocol.receive("bad", hello)
    protocol.receive("bad", {"type": "page", "after": 0, "blocks": [history[1], forged], "next_cursor": 2})
    assert dropped == ["bad"]
    assert workspace.blockchain.all() == history[:1]
    assert_good_peer_works(protocol, sent)


@pytest.mark.parametrize("field", ["profile", "genesis", "rules"])
def test_foreign_hello_cannot_enter_verified_set(endpoint, field):
    workspace, protocol, sent, dropped, hello = endpoint
    protocol.connected("bad")
    forged = copy.deepcopy(hello)
    forged[field] = {**hello["rules"], "block_bits": 0} if field == "rules" else "foreign"
    before = len(sent)
    protocol.receive("bad", forged)
    assert dropped == ["bad"] and len(sent) == before
    assert workspace.blockchain.all() == []
    assert_good_peer_works(protocol, sent)


@pytest.mark.parametrize("attack", ["oversized", "deep_json"])
def test_bounded_hostile_frames_reject_only_the_sender(endpoint, attack):
    workspace, protocol, sent, dropped, hello = endpoint
    if attack == "oversized":
        message = {"type": "get_page", "padding": "x" * MAX_FRAME}
    else:
        nested = None
        for _ in range(max(10_000, sys.getrecursionlimit() + 100)):
            nested = [nested]
        message = {"type": "get_page", "padding": nested}
    protocol.connected("bad")
    protocol.receive("bad", hello)
    protocol.receive("bad", message)
    assert dropped == ["bad"]
    assert workspace.blockchain.all() == []
    assert_good_peer_works(protocol, sent)


def test_deterministic_json_type_fuzz_is_contained(endpoint, public_history):
    workspace, protocol, sent, dropped, hello = endpoint
    history, _ = public_history
    workspace.blockchain.import_blocks(history[:1])
    values = [None, True, False, -1, 0, 1.5, "", "\ud800", [], [0], {}, {"type": "shutdown"}]
    messages = list(values)
    templates = [
        hello,
        {"type": "get_page", "after": 0, "limit": 100},
        {"type": "page", "after": 0, "blocks": [], "next_cursor": 0},
    ]
    for template in templates:
        for field in template:
            for value in values:
                if type(value) is type(template[field]) and value == template[field]:
                    continue
                messages.append({**template, field: value})
    for field in history[1]:
        for value in values:
            if type(value) is type(history[1][field]) and value == history[1][field]:
                continue
            block = {**history[1], field: value}
            messages.append({"type": "page", "after": 0, "blocks": [block], "next_cursor": 1})
    random.Random(73193).shuffle(messages)
    rejected = 0
    for message in messages:
        protocol.connected("bad")
        protocol.receive("bad", hello)
        protocol.receive("bad", message)
        # A mutation may remain a valid empty page/hello; both cases must preserve history.
        rejected += "bad" not in protocol.peers
        protocol.disconnected("bad")
        assert workspace.blockchain.all() == history[:1]
    assert rejected > 300 and len(dropped) == rejected
    assert_good_peer_works(protocol, sent)


def test_peer_and_error_limits_remain_bounded_under_reconnects(endpoint):
    _, protocol, sent, dropped, _ = endpoint
    for number in range(MAX_PEERS + 50):
        protocol.connected(f"unverified-{number}")
    assert len(protocol.peers) == MAX_PEERS
    for number in range(100):
        protocol.receive(f"hostile-{number}", {"type": "shutdown", "private": "ATTACK-CANARY"})
    assert len(protocol.peers) == MAX_PEERS
    assert len(protocol.errors) == 20
    assert "ATTACK-CANARY" not in canonical(protocol.status()).decode()
    assert "good" not in dropped
    assert_good_peer_works(protocol, sent)


@pytest.mark.asyncio
async def test_transport_envelope_never_promotes_peer_shutdown_to_local_control(endpoint):
    workspace, _, _, _, hello = endpoint
    node = P2PNode(workspace)
    stream = asyncio.StreamReader()
    node.process = SimpleNamespace(stdout=stream)

    def event(kind, peer, message=None):
        value = {"type": kind, "peer": peer}
        if message is not None:
            value["payload"] = base64.b64encode(canonical(message)).decode("ascii")
        stream.feed_data(canonical(value) + b"\n")

    reader = asyncio.create_task(node._reader())
    try:
        for peer in ("bad", "good"):
            event("connected", peer)
            event("message", peer, hello)
        event("message", "bad", {"type": "shutdown"})
        event("message", "good", {"type": "get_page", "after": 0, "limit": 100})
        for _ in range(20):
            await asyncio.sleep(0)
            if node.outgoing.qsize() == 6:
                break
        assert not reader.done() and not node.stop.is_set()
        commands = [node.outgoing.get_nowait() for _ in range(node.outgoing.qsize())]
        assert len(commands) == 6
        assert [c for c in commands if c["type"] == "disconnect"] == [{"type": "disconnect", "peer": "bad"}]
        assert not any(c["type"] == "shutdown" for c in commands)
        pages = [json.loads(base64.b64decode(c["payload"])) for c in commands if c["type"] == "send_raw"]
        assert pages[-1] == {"type": "page", "after": 0, "blocks": [], "next_cursor": 0}
        assert node.protocol.status()["verified_peers"] == 1
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ["invalid_base64", "deep_json", "oversized_json"])
async def test_runtime_rejects_hostile_payload_without_stopping_other_peer(endpoint, attack):
    workspace, _, _, _, hello = endpoint
    node = P2PNode(workspace)
    stream = asyncio.StreamReader(limit=IPC_LIMIT)
    node.process = SimpleNamespace(stdout=stream)
    if attack == "invalid_base64":
        payload = "not base64!"
    elif attack == "deep_json":
        depth = max(10_000, sys.getrecursionlimit() + 100)
        raw = b'{"private":"RUNTIME-CANARY","padding":' + b"[" * depth + b"0" + b"]" * depth + b"}"
        payload = base64.b64encode(raw).decode("ascii")
    else:
        payload = base64.b64encode(b" " * (MAX_FRAME + 1)).decode("ascii")
    envelopes = []
    for peer in ("bad", "good"):
        envelopes.extend(
            [
                {"type": "connected", "peer": peer},
                {
                    "type": "message",
                    "peer": peer,
                    "payload": base64.b64encode(canonical(hello)).decode("ascii"),
                },
            ]
        )
    envelopes.extend(
        [
            {"type": "message", "peer": "bad", "payload": payload},
            {
                "type": "message",
                "peer": "good",
                "payload": base64.b64encode(canonical({"type": "get_page", "after": 0, "limit": 100})).decode(
                    "ascii"
                ),
            },
        ]
    )
    stream.feed_data(b"".join(canonical(value) + b"\n" for value in envelopes))
    reader = asyncio.create_task(node._reader())
    try:
        for _ in range(20):
            await asyncio.sleep(0)
            if node.outgoing.qsize() == 6:
                break
        assert not reader.done() and not node.stop.is_set()
        assert "bad" not in node.protocol.peers and "good" in node.protocol.peers
        assert node.errors == ["invalid_transport_event"]
        assert "RUNTIME-CANARY" not in canonical(node._save(False)).decode()
        commands = [node.outgoing.get_nowait() for _ in range(node.outgoing.qsize())]
        assert len(commands) == 6
        assert commands[-2] == {"type": "disconnect", "peer": "bad"}
        assert commands[-1]["type"] == "send_raw" and commands[-1]["peer"] == "good"
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
