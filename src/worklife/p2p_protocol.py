"""Transport-independent exchange of the verified public block DAG only.

Methods run serially; transport peer identities are connection labels, never votes.
The optional room isolates tests and supplies neither authority nor secrecy.
"""

import hashlib
import re
import time
from collections import deque

from .storage import canonical

MAX_FRAME = 1024 * 1024
MAX_PEERS = 32
POLL_SECONDS = 15
TIMEOUT_SECONDS = 30


def swarm_topic(genesis, room=""):
    if type(genesis) is not str or not re.fullmatch(r"[0-9a-f]{64}", genesis) or type(room) is not str:
        raise ValueError("Invalid swarm genesis or room")
    return hashlib.sha256(b"worklife-chain-v1:swarm\0" + genesis.encode() + b"\0" + room.encode()).hexdigest()


class BlockSwarm:
    def __init__(self, workspace, send, disconnect, now=time.monotonic):
        self.chain, self.send, self.disconnect, self.now = workspace.blockchain, send, disconnect, now
        local = self.chain.status()
        self.identity = {key: local[key] for key in ("network", "genesis", "profile", "rules")}
        self.peers, self.errors = {}, deque(maxlen=20)
        self.last_local = (local["head"], local["blocks"])
        self.transfer = dict.fromkeys(
            (
                "messages_sent",
                "messages_received",
                "bytes_sent",
                "bytes_received",
                "blocks_sent",
                "blocks_received",
                "blocks_imported",
                "rounds_completed",
            ),
            0,
        )

    def _emit(self, peer, message):
        size = len(canonical(message))
        if size > MAX_FRAME:
            raise ValueError("frame_too_large")
        self.send(peer, message)
        self.transfer["messages_sent"] += 1
        self.transfer["bytes_sent"] += size

    def _hello(self, peer, local=None):
        local = local or self.chain.status()
        self._emit(
            peer,
            {
                "type": "hello",
                "version": 1,
                **self.identity,
                "rules": dict(self.identity["rules"]),
                **{key: local[key] for key in ("head", "height", "blocks")},
            },
        )

    def _reject(self, peer, reason):
        self.errors.append(reason)
        self.peers.pop(peer, None)
        self.disconnect(peer)

    def connected(self, peer):
        if peer in self.peers:
            return
        if len(self.peers) >= MAX_PEERS:
            self._reject(peer, "peer_limit")
            return
        self.peers[peer] = {
            "verified": False,
            "synced": False,
            "remote": None,
            "pending": None,
            "since": self.now(),
            "last_poll": self.now(),
            "resync": False,
            "serving": None,
        }
        self._hello(peer)

    def disconnected(self, peer):
        self.peers.pop(peer, None)

    def _request(self, peer, after=0):
        state = self.peers[peer]
        state.update(pending=after, since=self.now(), synced=False, last_poll=self.now())
        self._emit(peer, {"type": "get_page", "after": after, "limit": 100})

    @staticmethod
    def _fields(message, fields):
        if set(message) != set(fields.split()):
            raise ValueError("invalid_schema")

    @staticmethod
    def _integer(value, minimum=0, maximum=None):
        if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
            raise ValueError("invalid_integer")

    def _receive_hello(self, peer, message):
        self._fields(message, "type version network genesis profile rules head height blocks")
        if type(message["version"]) is not int or message["version"] != 1:
            raise ValueError("wrong_protocol")
        for key in ("network", "genesis", "profile"):
            if type(message[key]) is not str or message[key] != self.identity[key]:
                raise ValueError("wrong_network")
        rules, expected = message["rules"], self.identity["rules"]
        if (
            type(rules) is not dict
            or set(rules) != set(expected)
            or any(
                type(rules[key]) is not type(value) or rules[key] != value for key, value in expected.items()
            )
        ):
            raise ValueError("wrong_rules")
        self._integer(message["height"])
        self._integer(message["blocks"], message["height"])
        head = message["head"]
        if type(head) is not str or not re.fullmatch(r"[0-9a-f]{64}", head):
            raise ValueError("invalid_head")
        if (message["height"] == 0) != (head == self.identity["genesis"]) or (
            message["height"] == 0 and message["blocks"] != 0
        ):
            raise ValueError("invalid_head")
        state = self.peers[peer]
        remote = (head, message["blocks"])
        changed = state["remote"] != remote
        state.update(verified=True, remote=remote)
        if changed and state["pending"] is not None:
            state["resync"] = True
        elif changed:
            self._request(peer)

    def _serve_page(self, peer, message):
        self._fields(message, "type after limit")
        self._integer(message["after"])
        self._integer(message["limit"], 1, 100)
        state = self.peers[peer]
        # New fork blocks can sort before an existing cursor: freeze each served round.
        if message["after"] == 0 or state["serving"] is None:
            state["serving"] = self.chain.all()
        blocks = state["serving"][message["after"] : message["after"] + message["limit"]]
        had_blocks = bool(blocks)
        page = {
            "type": "page",
            "after": message["after"],
            "blocks": blocks,
            "next_cursor": message["after"] + len(blocks),
        }
        while len(canonical(page)) > MAX_FRAME and blocks:
            blocks.pop()
            page["next_cursor"] -= 1
        if had_blocks and not blocks:
            raise ValueError("frame_too_large")
        self._emit(peer, page)
        self.transfer["blocks_sent"] += len(blocks)
        if not blocks:
            state["serving"] = None

    def _receive_page(self, peer, message):
        self._fields(message, "type after blocks next_cursor")
        state = self.peers[peer]
        self._integer(message["after"])
        self._integer(message["next_cursor"])
        blocks = message["blocks"]
        if (
            state["pending"] is None
            or message["after"] != state["pending"]
            or type(blocks) is not list
            or len(blocks) > 100
            or message["next_cursor"] != message["after"] + len(blocks)
        ):
            raise ValueError("invalid_page")
        # import_blocks validates proofs, signatures, author chains and parent scope atomically.
        result = self.chain.import_blocks(blocks)
        self.transfer["blocks_received"] += len(blocks)
        self.transfer["blocks_imported"] += result["imported"]
        if blocks:
            self._request(peer, message["next_cursor"])
        else:
            state.update(pending=None, synced=True, last_poll=self.now())
            self.transfer["rounds_completed"] += 1
            if state["resync"]:
                state["resync"] = False
                self._request(peer)

    def receive(self, peer, message):
        try:
            if peer not in self.peers or type(message) is not dict:
                raise ValueError("invalid_message")
            size = len(canonical(message))
            if size > MAX_FRAME:
                raise ValueError("frame_too_large")
            self.transfer["messages_received"] += 1
            self.transfer["bytes_received"] += size
            method = message.get("type")
            if method == "hello":
                self._receive_hello(peer, message)
            elif not self.peers[peer]["verified"]:
                raise ValueError("hello_required")
            elif method == "get_page":
                self._serve_page(peer, message)
            elif method == "page":
                self._receive_page(peer, message)
            else:
                raise ValueError("unknown_method")
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            # Never expose hostile payloads, addresses, local keys or database contents in status.
            self._reject(peer, "invalid_peer_message")

    def tick(self, force=False):
        current, local = self.now(), self.chain.status()
        changed = self.last_local != (local["head"], local["blocks"])
        self.last_local = (local["head"], local["blocks"])
        for peer, state in list(self.peers.items()):
            if (not state["verified"] or state["pending"] is not None) and current - state[
                "since"
            ] >= TIMEOUT_SECONDS:
                self._reject(peer, "peer_timeout")
                continue
            if state["verified"]:
                try:
                    if changed:
                        self._hello(peer, local)
                    if state["pending"] is None and (
                        force or changed or current - state["last_poll"] >= POLL_SECONDS
                    ):
                        self._request(peer)
                except ValueError:
                    self._reject(peer, "send_failed")
        return self.status()

    def status(self):
        local = self.chain.status()
        verified = [state for state in self.peers.values() if state["verified"]]
        return {
            **{key: local[key] for key in ("network", "genesis", "profile", "head", "height", "blocks")},
            "peers": len(self.peers),
            "verified_peers": len(verified),
            "synced_peers": sum(state["synced"] for state in verified),
            "heads": sorted({local["head"], *(state["remote"][0] for state in verified)}),
            "errors": list(self.errors),
            "transfers": dict(self.transfer),
        }
