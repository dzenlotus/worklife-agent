"""Participant-device P2P runtime: Hyperswarm discovery/Noise, existing chain verification."""

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from .ledger import Ledger
from .p2p_protocol import MAX_FRAME, BlockSwarm, swarm_topic
from .storage import canonical, now

IPC_LIMIT = 2 * MAX_FRAME + 4096
ASSETS = ("swarm.mjs", "neighbors.mjs", "package.json", "package-lock.json")


def transport_environment(home):
    """Transport receives runtime basics, not the person's model/mail/provider credentials."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "TMPDIR", "TEMP", "TMP", "SystemRoot", "WINDIR", "LANG", "LC_ALL"}
    }
    env["WORKLIFE_P2P_HOME"] = str(home)
    return env


def prepare_transport(home):
    """Use an image bundle, or install the exact locked public package into a private cache."""
    selected = os.getenv("WORKLIFE_P2P_TRANSPORT_DIR")
    if selected:
        folder = Path(selected).expanduser().resolve()
        if not (folder / "swarm.mjs").is_file() or not (folder / "node_modules/hyperswarm").is_dir():
            raise ValueError("Prebundled P2P transport is incomplete")
        return folder
    assets = Path(__file__).with_name("p2p_transport")
    fingerprint = hashlib.sha256(b"".join((assets / name).read_bytes() for name in ASSETS)).hexdigest()
    folder = Path(home) / "p2p-transport"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = folder / ".source-sha256"
    if (
        marker.exists()
        and marker.read_text() == fingerprint
        and (folder / "node_modules/hyperswarm").is_dir()
    ):
        return folder
    npm = shutil.which("npm")
    if not npm:
        raise ValueError("P2P setup requires Node.js 22+ and npm, or the prepared P2P Docker image")
    for name in ASSETS:
        Ledger._write_private(folder / name, (assets / name).read_bytes())
    Ledger._write_private(folder / ".npmrc", b"registry=https://registry.npmjs.org/\n")
    result = subprocess.run(
        [
            npm,
            "ci",
            "--omit=dev",
            "--no-audit",
            "--no-fund",
            "--userconfig=" + str(folder / ".npmrc"),
            "--cache=" + str(folder / ".npm-cache"),
        ],
        cwd=folder,
        env=transport_environment(folder),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        raise ValueError("P2P dependency installation failed: " + result.stderr[-1000:])
    Ledger._write_private(marker, fingerprint.encode())
    return folder


def make_invite(genesis, topic, peer):
    if any(
        type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value) for value in (genesis, topic, peer)
    ):
        raise ValueError("Invite requires a genesis, topic and transport public key")
    return "worklife://" + genesis + "?" + urlencode({"topic": topic, "peer": peer})


def _invite(uri, genesis):
    if type(uri) is not str or len(uri) > 1024:
        raise ValueError("Invalid P2P invite")
    parsed = urlsplit(uri)
    values = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != "worklife"
        or parsed.netloc != genesis
        or parsed.path
        or parsed.fragment
        or set(values) != {"topic", "peer"}
        or any(len(value) != 1 or not re.fullmatch(r"[0-9a-f]{64}", value[0]) for value in values.values())
    ):
        raise ValueError("Invite belongs to another network or has invalid fields")
    return values["topic"][0], values["peer"][0]


def parse_invite(uri, genesis, topic):
    actual, peer = _invite(uri, genesis)
    if actual != topic:
        raise ValueError("Invite belongs to another swarm topic")
    return peer


def read_status(workspace, path=None):
    source = Path(path) if path else workspace.home / "p2p-status.json"
    if source.exists():
        return json.loads(source.read_text())
    return {
        "running": False,
        "connected_verified": 0,
        "transfers": {},
        "chain": workspace.blockchain.status(),
    }


class P2PNode:
    def __init__(
        self,
        workspace,
        *,
        bootstrap=None,
        isolated=False,
        port=0,
        room="",
        join=None,
        mine=False,
        cpu_fraction=0.25,
        status_file=None,
    ):
        from .chain_worker import cpu_pause

        cpu_pause(0, 0, cpu_fraction)
        if type(port) is not int or not 0 <= port <= 65535 or len(room) > 200:
            raise ValueError("Invalid P2P port or room")
        self.workspace, self.bootstrap, self.isolated, self.port = workspace, bootstrap or [], isolated, port
        chain = workspace.blockchain.status()
        self.topic = swarm_topic(chain["genesis"], room)
        self.join_peer = None
        if join:
            topic, peer = _invite(join, chain["genesis"])
            if room and self.topic != topic:
                raise ValueError("Invite does not match the selected room")
            self.topic, self.join_peer = topic, peer
        self.mine, self.cpu_fraction = mine, cpu_fraction
        self.path = Path(status_file) if status_file else workspace.home / "p2p-status.json"
        self.transport = {"ready": False}
        self.neighbors = {}
        self.errors, self.worker = [], None
        self.stop = asyncio.Event()
        self.outgoing = asyncio.Queue(maxsize=64)
        self.pending_disconnects = set()
        self.pending_verified = set()
        self.notified_verified = set()
        self.process = None
        self.failed = False
        self.protocol = BlockSwarm(workspace, self._send, self._disconnect)

    def _send(self, peer, message):
        payload = canonical(message)
        if len(payload) > MAX_FRAME:
            raise ValueError("P2P frame exceeds the transport limit")
        try:
            self.outgoing.put_nowait(
                {"type": "send_raw", "peer": peer, "payload": base64.b64encode(payload).decode("ascii")}
            )
        except asyncio.QueueFull:
            raise ValueError("P2P outgoing queue full") from None

    def _disconnect(self, peer):
        self.pending_verified.discard(peer)
        self.notified_verified.discard(peer)
        try:
            self.outgoing.put_nowait({"type": "disconnect", "peer": peer})
        except asyncio.QueueFull:
            self.pending_disconnects.add(peer)

    def _error(self, code):
        self.errors = [*self.errors[-9:], code]

    async def _writer(self):
        while not self.stop.is_set():
            if self.pending_disconnects:
                command = {"type": "disconnect", "peer": self.pending_disconnects.pop()}
            elif self.pending_verified:
                command = {"type": "peer_verified", "peer": self.pending_verified.pop()}
            else:
                command = await self.outgoing.get()
            self.process.stdin.write(canonical(command) + b"\n")
            await self.process.stdin.drain()

    async def _reader(self):
        while not self.stop.is_set():
            line = await self.process.stdout.readline()
            if not line:
                self.failed = not self.stop.is_set()
                self._error("transport_exited")
                self.stop.set()
                return
            event = None
            try:
                event = json.loads(line)
                if type(event) is not dict:
                    raise ValueError("Invalid transport envelope")
                kind, peer = event.get("type"), event.get("peer")
                if kind == "ready":
                    self.transport = {**event, "ready": True}
                    if self.join_peer:
                        self.outgoing.put_nowait({"type": "join_peer", "peer": self.join_peer})
                elif kind == "connected":
                    self.notified_verified.discard(peer)
                    self.protocol.connected(peer)
                elif kind == "disconnected":
                    self.notified_verified.discard(peer)
                    self.pending_verified.discard(peer)
                    self.protocol.disconnected(peer)
                elif kind == "message":
                    # Node transports bytes; it never rounds consensus integers through JS Number.
                    raw = base64.b64decode(event["payload"], validate=True)
                    if len(raw) > MAX_FRAME:
                        raise ValueError("P2P frame too large")
                    self.protocol.receive(peer, json.loads(raw))
                    state = self.protocol.peers.get(peer, {})
                    if state.get("synced") and state.get("verified") and peer not in self.notified_verified:
                        self.notified_verified.add(peer)
                        try:
                            self.outgoing.put_nowait({"type": "peer_verified", "peer": peer})
                        except asyncio.QueueFull:
                            self.pending_verified.add(peer)
                elif kind == "neighbors":
                    self.neighbors = event["status"]
                elif kind in {"error", "fatal"}:
                    self._error(str(event.get("code", "transport_error"))[:100])
                    if kind == "fatal":
                        self.failed = True
                        self.stop.set()
            except (ValueError, KeyError, TypeError, RecursionError):
                self._error("invalid_transport_event")
                if isinstance(event, dict) and event.get("peer"):
                    self.protocol.disconnected(event["peer"])
                    self._disconnect(event["peer"])

    async def _stderr(self):
        while await self.process.stderr.readline():
            # Diagnostics stay local and bounded; peer payloads are not copied into app logs.
            self._error("transport_diagnostic")

    def _save(self, running):
        state = self.protocol.status()
        value = {
            "running": running,
            "updated_at": now(),
            "pid": os.getpid(),
            "topic": self.topic,
            "transport": self.transport,
            "neighbors": self.neighbors,
            "connected_verified": state["verified_peers"],
            "transfers": state["transfers"],
            "peers": state,
            "chain": self.workspace.blockchain.status(),
            "errors": list(self.errors),
            "mining": self.mine,
        }
        if self.transport.get("public_key"):
            value["invite"] = make_invite(value["chain"]["genesis"], self.topic, self.transport["public_key"])
        if self.worker:
            value["worker"] = self.worker
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        Ledger._write_private(self.path, canonical(value))
        return value

    async def _ticker(self):
        last = None
        while not self.stop.is_set():
            self.protocol.tick()
            value = self._save(True)
            summary = {
                "running": True,
                "topic": self.topic,
                "peers": value["connected_verified"],
                "height": value["chain"]["height"],
                "head": value["chain"]["head"],
            }
            if summary != last:
                print(json.dumps(summary), flush=True)
                last = summary
            await asyncio.sleep(1)

    async def _miner(self):
        from .chain_network import BlockchainNetwork
        from .chain_worker import cpu_pause, run_cycle

        network = BlockchainNetwork(self.workspace, lambda: [])
        while not self.stop.is_set():
            before, cpu = time.monotonic(), time.process_time()
            result = await asyncio.to_thread(run_cycle, self.workspace, network, 250000)
            self.worker = {key: result[key] for key in ("qualification", "mining")}
            pause = cpu_pause(time.process_time() - cpu, time.monotonic() - before, self.cpu_fraction)
            await asyncio.sleep(max(0.01, pause))

    async def run(self):
        folder = await asyncio.to_thread(prepare_transport, self.workspace.home)
        node = shutil.which("node")
        if not node:
            raise ValueError("P2P requires Node.js 22+ or the prepared Docker image")
        command = [
            node,
            str(folder / "swarm.mjs"),
            "--topic",
            self.topic,
            "--key-file",
            str(self.workspace.home / "p2p-identity.key"),
            "--port",
            str(self.port),
        ]
        if self.isolated:
            command.append("--isolated")
        for address in self.bootstrap:
            command.extend(["--bootstrap", address])
        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=transport_environment(self.workspace.home),
            cwd=folder,
            limit=IPC_LIMIT,
        )
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.stop.set)
            except NotImplementedError:
                pass
        tasks = [asyncio.create_task(function()) for function in (self._reader, self._writer, self._ticker)]
        diagnostics = asyncio.create_task(self._stderr())
        if self.mine:
            tasks.append(asyncio.create_task(self._miner()))
        waiter = asyncio.create_task(self.stop.wait())
        try:
            done, _ = await asyncio.wait([*tasks, waiter], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not waiter:
                    task.result()
        finally:
            self.stop.set()
            for task in [*tasks, diagnostics, waiter]:
                task.cancel()
            await asyncio.gather(*tasks, diagnostics, waiter, return_exceptions=True)
            if self.process.returncode is None:
                try:
                    self.process.stdin.write(b'{"type":"shutdown"}\n')
                    await self.process.stdin.drain()
                    await asyncio.wait_for(self.process.wait(), timeout=8)
                except (TimeoutError, BrokenPipeError, ConnectionResetError):
                    if self.process.returncode is None:
                        self.process.kill()
                        await self.process.wait()
            self.protocol.peers.clear()
            self._save(False)
        if self.failed:
            raise ValueError("P2P transport stopped unexpectedly; inspect local status errors")


def run_p2p(workspace, **kwargs):
    asyncio.run(P2PNode(workspace, **kwargs).run())
