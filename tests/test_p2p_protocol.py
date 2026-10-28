import copy
import hashlib
import importlib.util
from collections import deque

import pytest

from worklife.blockchain import BLOCK_BITS, GENESIS, meets_work, pow_digest
from worklife.storage import canonical
from worklife.workspace import Workspace

AT = "2026-10-15T10:00:00Z"


def test_public_block_swarm_exists():
    assert importlib.util.find_spec("worklife.p2p_protocol") is not None, "P2P block protocol is missing"


@pytest.fixture
def history(tmp_path):
    workspace = Workspace(tmp_path / "origin")
    workspace.ledger.publish(
        "employer",
        "public.example",
        {
            "claim": "Public employer observation",
            "evidence_kind": "advertised",
            "source_url": "https://public.example/jobs",
            "observed_at": AT,
        },
    )
    workspace.blockchain.qualify(at=AT)
    for second in range(3):
        assert workspace.blockchain.mine(at=f"2026-10-15T10:00:{second:02d}Z")["mined"]
    return workspace.blockchain.all()


class Mesh:
    def __init__(self, tmp_path):
        self.workspaces, self.nodes, self.links = {}, {}, set()
        self.queue, self.sent, self.dropped = deque(), [], []
        self.clock = 0
        self.tmp_path = tmp_path

    def add(self, name):
        from worklife.p2p_protocol import BlockSwarm

        workspace = self.workspaces[name] = Workspace(self.tmp_path / name)
        self.nodes[name] = BlockSwarm(
            workspace,
            lambda peer, message: self.send(name, peer, message),
            lambda peer: self.drop(name, peer),
            now=lambda: self.clock,
        )
        return workspace

    def send(self, sender, peer, message):
        self.sent.append((sender, peer, copy.deepcopy(message)))
        self.queue.append((sender, peer, copy.deepcopy(message)))

    def drop(self, sender, peer):
        self.dropped.append((sender, peer))
        self.links.discard(frozenset((sender, peer)))

    def connect(self, a, b):
        self.links.add(frozenset((a, b)))
        self.nodes[a].connected(b)
        self.nodes[b].connected(a)

    def drain(self):
        for _ in range(1000):
            if not self.queue:
                return
            sender, peer, message = self.queue.popleft()
            if frozenset((sender, peer)) in self.links:
                self.nodes[peer].receive(sender, message)
        pytest.fail("P2P exchange did not settle")


def endpoint(tmp_path):
    mesh = Mesh(tmp_path)
    workspace = mesh.add("local")
    node = mesh.nodes["local"]
    node.connected("remote")
    hello = copy.deepcopy(mesh.sent[-1][2])
    return mesh, workspace, node, hello


def test_three_nodes_relay_verified_blocks_and_continue_without_bootstrap(tmp_path, history):
    mesh = Mesh(tmp_path)
    a, b, c = (mesh.add(name) for name in ("a", "b", "c"))
    a.blockchain.import_blocks(history)
    mesh.connect("a", "b")
    mesh.connect("b", "c")
    mesh.drain()
    for node in mesh.nodes.values():
        node.tick()
    mesh.drain()
    assert a.blockchain.all() == b.blockchain.all() == c.blockchain.all() == history

    mesh.drop("a", "b")
    mesh.nodes["b"].disconnected("a")
    b.blockchain.qualify(at="2026-10-15T10:00:03Z")
    assert b.blockchain.mine(at="2026-10-15T10:00:03Z")["mined"]
    mesh.clock += 16
    mesh.nodes["b"].tick()
    mesh.nodes["c"].tick()
    mesh.drain()
    assert b.blockchain.all() == c.blockchain.all()
    assert c.blockchain.status()["height"] == 4
    assert mesh.nodes["c"].status()["verified_peers"] == 1


def test_relay_keeps_verified_forks_as_well_as_the_canonical_chain(tmp_path, history):
    mesh = Mesh(tmp_path)
    a, b, c = (mesh.add(name) for name in ("a", "b", "c"))
    a.blockchain.import_blocks(history)
    b.blockchain.qualify(at=AT)
    assert b.blockchain.mine(at=AT)["mined"]
    mesh.connect("a", "b")
    mesh.connect("b", "c")
    mesh.drain()
    for node in mesh.nodes.values():
        node.tick()
    mesh.drain()
    assert a.blockchain.all() == b.blockchain.all() == c.blockchain.all()
    assert len(c.blockchain.all()) == 4
    assert c.blockchain.canonical_blocks() == history


@pytest.mark.parametrize(
    "field,value",
    [
        ("network", "foreign"),
        ("genesis", "0" * 64),
        ("profile", "public-testnet-v1"),
        ("version", True),
        ("height", True),
        ("blocks", False),
        ("head", "bad"),
        ("extra", "private request"),
    ],
)
def test_bad_hello_is_rejected_before_any_page_exchange(tmp_path, field, value):
    mesh, workspace, node, hello = endpoint(tmp_path)
    hello[field] = value
    node.receive("remote", hello)
    assert mesh.dropped == [("local", "remote")]
    assert not any(message["type"] == "get_page" for _, _, message in mesh.sent)
    assert workspace.blockchain.all() == []


@pytest.mark.parametrize(
    "field,value", [("block_bits", True), ("qualification_bits", 0), ("confirmations", 6)]
)
def test_fixed_rules_require_exact_values_and_integer_types(tmp_path, field, value):
    mesh, _, node, hello = endpoint(tmp_path)
    hello["rules"][field] = value
    node.receive("remote", hello)
    assert mesh.dropped
    assert node.status()["verified_peers"] == 0


@pytest.mark.parametrize(
    "message",
    [
        {"type": "get_page", "after": 0, "limit": 100},
        {"type": "page", "after": 0, "blocks": [], "next_cursor": 0},
        {"type": "profile"},
        {"type": "query", "query": "private job search"},
    ],
)
def test_unverified_peer_cannot_request_or_push_data(tmp_path, message):
    mesh, _, node, _ = endpoint(tmp_path)
    node.receive("remote", message)
    assert mesh.dropped
    assert len(mesh.sent) == 1


@pytest.mark.parametrize(
    "message",
    [
        {"type": "get_page", "after": -1, "limit": 100},
        {"type": "get_page", "after": True, "limit": 100},
        {"type": "get_page", "after": 0, "limit": 101},
        {"type": "get_page", "after": 0, "limit": False},
        {"type": "get_page", "after": 0, "limit": 100, "profile": True},
        {"type": "page", "after": 1, "blocks": [], "next_cursor": 1},
        {"type": "page", "after": 0, "blocks": [], "next_cursor": True},
        {"type": "page", "after": 0, "blocks": [{}] * 101, "next_cursor": 101},
        {"type": "page", "after": 0, "blocks": [], "next_cursor": 1},
        {"type": "page", "after": 0, "blocks": [], "next_cursor": 0, "events": []},
        {"type": "mine"},
    ],
)
def test_invalid_schema_cursor_or_batch_disconnects(tmp_path, message):
    mesh, workspace, node, hello = endpoint(tmp_path)
    node.receive("remote", hello)
    node.receive("remote", message)
    assert mesh.dropped
    assert workspace.blockchain.all() == []


@pytest.mark.parametrize("fault", ["signature", "proof", "parent", "schema"])
def test_invalid_block_batch_is_atomic_and_preserves_accepted_history(tmp_path, history, fault):
    mesh, workspace, node, hello = endpoint(tmp_path)
    workspace.blockchain.import_blocks(history[:1])
    node.receive("remote", hello)
    forged = copy.deepcopy(history[2])
    if fault == "signature":
        forged["signature"] = "0" * 128
    elif fault == "proof":
        forged["nonce"] += 1
    elif fault == "parent":
        forged["parent"] = "f" * 64
    else:
        forged["profile"] = "private"
    node.receive("remote", {"type": "page", "after": 0, "blocks": [history[1], forged], "next_cursor": 2})
    assert mesh.dropped
    assert workspace.blockchain.all() == history[:1]


def test_even_valid_work_and_signature_cannot_replay_an_ancestral_event(tmp_path, history):
    mesh, workspace, node, hello = endpoint(tmp_path)
    forged = copy.deepcopy(history[2])
    forged["events"] = history[0]["events"]
    body = {key: value for key, value in forged.items() if key not in {"nonce", "block_id", "signature"}}
    digest = hashlib.sha256(canonical(body)).digest()
    for nonce in range(100_000):
        proof = pow_digest(digest, nonce)
        if meets_work(proof, BLOCK_BITS):
            break
    else:
        pytest.fail("Development proof budget exhausted")
    origin = Workspace(tmp_path / "origin")
    forged.update(nonce=nonce, block_id=proof.hex(), signature=origin.ledger.key.sign(proof).hex())
    node.receive("remote", hello)
    node.receive("remote", {"type": "page", "after": 0, "blocks": [*history[:2], forged], "next_cursor": 3})
    assert mesh.dropped
    assert workspace.blockchain.all() == []


def test_oversized_frame_and_unsolicited_repeat_page_are_rejected(tmp_path):
    from worklife.p2p_protocol import MAX_FRAME

    mesh, _, node, hello = endpoint(tmp_path)
    node.receive("remote", {**hello, "padding": "x" * MAX_FRAME})
    assert mesh.dropped
    mesh, _, node, hello = endpoint(tmp_path / "repeat")
    node.receive("remote", hello)
    empty = {"type": "page", "after": 0, "blocks": [], "next_cursor": 0}
    node.receive("remote", empty)
    assert node.status()["synced_peers"] == 1
    node.receive("remote", empty)
    assert mesh.dropped


def test_pages_are_trimmed_to_wire_frame_limit(tmp_path, monkeypatch):
    from worklife.p2p_protocol import MAX_FRAME

    mesh, workspace, node, hello = endpoint(tmp_path)
    node.receive("remote", hello)
    blocks = [{"data": "x" * 600_000, "number": i} for i in range(3)]
    monkeypatch.setattr(workspace.blockchain, "all", lambda: blocks)
    node.receive("remote", {"type": "get_page", "after": 0, "limit": 100})
    page = mesh.sent[-1][2]
    assert page["type"] == "page"
    assert len(canonical(page)) <= MAX_FRAME
    assert page["blocks"] == blocks[:1]
    assert page["next_cursor"] == 1


def test_repeated_sync_is_idempotent_and_never_exports_private_workspace_data(tmp_path, history):
    mesh = Mesh(tmp_path)
    a, b = mesh.add("a"), mesh.add("b")
    a.blockchain.import_blocks(history)
    a.save_profile({"name": "PRIVATE PERSON", "facts": []})
    pending = a.ledger.publish(
        "employer",
        "private.example",
        {
            "claim": "PRIVATE PROPOSAL",
            "evidence_kind": "advertised",
            "source_url": "https://private.example/jobs",
            "observed_at": AT,
        },
    )
    mesh.connect("a", "b")
    mesh.drain()
    sent = len(mesh.sent)
    for node in mesh.nodes.values():
        node.tick()
    mesh.drain()
    settled = len(mesh.sent)
    for node in mesh.nodes.values():
        node.tick()
    mesh.drain()
    assert len(mesh.sent) == settled
    mesh.clock += 16
    for node in mesh.nodes.values():
        node.tick()
    mesh.drain()
    assert len(mesh.sent) > sent
    assert b.blockchain.all() == history
    assert b.ledger.all() == []
    assert b.store.list("profile") == []
    assert a.ledger.all() == [pending]
    transcript = canonical(mesh.sent).decode()
    assert "PRIVATE PERSON" not in transcript and "PRIVATE PROPOSAL" not in transcript
    assert "private.example" not in transcript
    assert b.store.list("chain_qualification_progress") == []
    assert mesh.nodes["b"].status()["transfers"]["blocks_imported"] == len(history)


def test_empty_startup_peer_limit_timeouts_and_private_free_status(tmp_path):
    mesh, workspace, node, hello = endpoint(tmp_path)
    state = node.status()
    assert state["head"] == GENESIS and state["height"] == 0
    assert state["peers"] == 1 and state["verified_peers"] == 0
    for i in range(33):
        node.connected(f"host-secret-{i}")
    assert node.status()["peers"] == 32
    assert "host-secret" not in canonical(node.status()).decode()
    mesh.clock = 31
    node.tick()
    assert node.status()["peers"] == 0
    assert workspace.blockchain.all() == []
    node.connected("again")
    node.receive("again", hello)
    mesh.clock += 31
    node.tick()
    assert node.status()["peers"] == 0
    assert len(node.status()["errors"]) <= 20


@pytest.mark.parametrize("already_queued", [1, 2])
def test_tick_queue_overflow_drops_one_peer_and_keeps_other_connections(tmp_path, history, already_queued):
    mesh, workspace, node, hello = endpoint(tmp_path)
    peers = ["remote", *(f"peer-{number}" for number in range(31))]
    empty = {"type": "page", "after": 0, "blocks": [], "next_cursor": 0}
    for peer in peers:
        node.connected(peer)
        node.receive(peer, hello)
        node.receive(peer, empty)

    # The runtime has 64 queued sends; a changed head emits hello + get_page per peer.
    outgoing = [None] * already_queued

    def bounded_send(peer, message):
        if len(outgoing) >= 64:
            raise ValueError("P2P outgoing queue full")
        outgoing.append((peer, message))

    node.send = bounded_send
    workspace.blockchain.import_blocks(history)
    state = node.tick()
    assert len(outgoing) == 64
    assert mesh.dropped == [("local", peers[-1])]
    assert state["peers"] == state["verified_peers"] == 31
    assert state["errors"][-1] == "send_failed"

    # Once the writer drains, accepted connections can finish and poll again.
    outgoing.clear()
    for peer in peers[:-1]:
        node.receive(peer, empty)
    state = node.tick(force=True)
    assert len(outgoing) == 31
    assert state["peers"] == state["verified_peers"] == 31


def test_swarm_topic_uses_genesis_and_optional_test_room():
    from worklife.p2p_protocol import swarm_topic

    topic = swarm_topic(GENESIS)
    assert len(topic) == 64 and int(topic, 16) >= 0
    assert topic == swarm_topic(GENESIS)
    assert topic != swarm_topic("0" * 64)
    assert topic != swarm_topic(GENESIS, "isolated-test")
