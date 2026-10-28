#!/usr/bin/env python3
"""Check real P2P block exchange in isolated Docker containers, retaining all data.

Replays authentic public-testnet PoW blocks; does not mine new work or measure
public NAT traversal, independent operators, or resistance to a majority attack.
Requires an already built image, or --build-context with reviewed source.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NODES = ("node-a", "node-b", "node-c")
ROUTERS = ("bootstrap-a", "bootstrap-b", "bootstrap-c", "bootstrap-d")
SURVIVORS = NODES[1:]
RULES = {"block_bits": 25, "qualification_bits": 18, "confirmations": 6}
PREFIX_HEIGHT = 10


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def valid_chain(chain):
    return (
        chain.get("profile") == "public-testnet-v1"
        and chain.get("network") == "worklife-public-testnet-v1"
        and all(chain.get("rules", {}).get(key) == value for key, value in RULES.items())
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="worklife-p2p:local")
    parser.add_argument("--build-context", type=Path)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/p2p-public-blocks.json")
    parser.add_argument("--project", default="worklife-p2p-check-" + uuid4().hex[:12])
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/blockchain/p2p-three-node/report.json"
    )
    parser.add_argument("--timeout", type=float, default=300, help="Whole acceptance deadline in seconds")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.project) or args.timeout <= 0:
        parser.error("Use a lowercase Compose project name and a positive timeout")
    fixture = json.loads(args.fixture.read_text())
    blocks = fixture["blocks"]
    if len(blocks) != 15 or [b["height"] for b in blocks] != list(range(1, 16)):
        parser.error("Fixture must contain the 15 authentic public-testnet blocks in height order")
    if any(b["network"] != "worklife-public-testnet-v1" for b in blocks):
        parser.error("Fixture belongs to a different network")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    events, logs = output.with_suffix(".events.jsonl"), output.with_suffix(".containers.log")
    events.write_text("")
    started = time.monotonic()
    deadline = started + args.timeout
    env = {**os.environ, "WORKLIFE_P2P_IMAGE": args.image}
    compose = ["docker", "compose", "-f", str(ROOT / "deploy/p2p-network/compose.yaml"), "-p", args.project]
    report = {
        "success": False,
        "project": args.project,
        "image": args.image,
        "started_at": utc_now(),
        "profile": "public-testnet-v1",
        "rules": RULES,
        "fixture": str(args.fixture.resolve()),
        "fixture_blocks": len(blocks),
        "new_pow_mined": False,
        "event_id": fixture["event_id"],
        "phases": {},
        "events_path": str(events),
        "container_logs_path": str(logs),
        "limits": [
            "One Docker host; no independent-operator claim",
            "Internal-only network; public NAT traversal is not tested",
            "Authentic premined 25/18/6 public-testnet fixture; no new mining",
            "Four stateless discovery routers have no blockchain data or acceptance authority",
        ],
    }

    def emit(kind, **data):
        item = {
            "at": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "event": kind,
            **data,
        }
        with events.open("a") as stream:
            stream.write(json.dumps(item, sort_keys=True) + "\n")
        print(json.dumps(item, sort_keys=True), flush=True)

    def run(command, *, data=None, cleanup=False, record=True):
        budget = 45 if cleanup else min(90, max(0.1, deadline - time.monotonic()))
        result = subprocess.run(command, input=data, env=env, text=True, capture_output=True, timeout=budget)
        if record or result.returncode:
            emit("command", command=command, returncode=result.returncode)
        if result.returncode:
            raise RuntimeError(
                f"Command failed: {' '.join(command)}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
            )
        return result.stdout

    def dc(*command, **options):
        return run([*compose, *command], **options)

    def import_blocks(node, documents, *, running):
        command = ("exec", "-T", node, "worklife") if running else ("run", "--rm", "--no-deps", "-T", node)
        packet = json.dumps({"network": "worklife-public-testnet-v1", "blocks": documents})
        return json.loads(dc(*command, "chain", "import", "/dev/stdin", data=packet))

    def containers():
        ids = dc("ps", "--all", "--quiet", record=False).split()
        inspected = json.loads(run(["docker", "inspect", *ids], record=False))
        return {
            item["Config"]["Labels"]["com.docker.compose.service"]: {
                "id": item["Id"],
                "image_id": item["Image"],
                "status": item["State"]["Status"],
                "mounts": [
                    {"type": m["Type"], "name": m.get("Name"), "destination": m["Destination"]}
                    for m in item["Mounts"]
                ],
            }
            for item in inspected
        }

    def snapshots(nodes):
        code = (
            "import hashlib,json,sys; from pathlib import Path; from worklife.workspace import Workspace; "
            "p=Path('/data/p2p-status.json'); k=Path('/data/p2p-identity.key'); "
            "caches=list(Path('/data').glob('p2p-identity.key.neighbors-*.json')); "
            "w=Workspace(Path('/data')); "
            "print(json.dumps({'ready':False} if not p.exists() or not k.exists() else "
            "{'ready':True,'status':json.loads(p.read_text()),'chain':w.blockchain.status(),"
            "'author':w.ledger.author_id,'transport_key_sha256':hashlib.sha256(k.read_bytes()).hexdigest(),"
            "'neighbor_cache':[{'mode':oct(c.stat().st_mode&0o777),'topic':json.loads(c.read_text())['topic'],"
            "'entries':len(json.loads(c.read_text())['peers'])} for c in caches],"
            "'confirmation':w.blockchain.confirmation(sys.argv[1])}))"
        )
        result = {
            node: json.loads(dc("exec", "-T", node, "python", "-c", code, fixture["event_id"], record=False))
            for node in nodes
        }
        for snapshot in result.values():
            if snapshot["ready"] and not valid_chain(snapshot["chain"]):
                raise ValueError("Public-testnet profile or consensus rules differ")
        return result

    def wait_for(label, predicate, nodes=NODES):
        while time.monotonic() < deadline:
            values = snapshots(nodes)
            detail = {
                node: {
                    "ready": value["ready"],
                    **(
                        {
                            "height": value["chain"]["height"],
                            "head": value["chain"]["head"],
                            "connected_verified": value["status"].get("connected_verified"),
                            "transfers": value["status"].get("transfers"),
                        }
                        if value["ready"]
                        else {}
                    ),
                }
                for node, value in values.items()
            }
            emit("progress", phase=label, nodes=detail)
            if all(v["ready"] for v in values.values()) and predicate(values):
                return values
            time.sleep(min(3, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"Acceptance deadline reached during {label}")

    def at_head(values, height):
        head = blocks[height - 1]["block_id"]
        return all(
            v["chain"]["height"] == height
            and v["chain"]["head"] == head
            and v["status"]["chain"]["head"] == head
            for v in values.values()
        )

    def phase(name, **details):
        report["phases"][name] = {"passed": True, "at": utc_now(), **details}
        emit("phase_passed", phase=name)

    services_started = False
    try:
        emit("start", project=args.project, image=args.image, report=str(output))
        if args.build_context:
            context = args.build_context.resolve()
            run(
                [
                    "docker",
                    "build",
                    "-f",
                    str(context / "deploy/p2p-network/Dockerfile"),
                    "-t",
                    args.image,
                    str(context),
                ]
            )
        report["image_id"] = json.loads(run(["docker", "image", "inspect", args.image]))[0]["Id"]
        if (
            dc("ps", "--all", "--quiet").strip()
            or run(
                [
                    "docker",
                    "volume",
                    "ls",
                    "--quiet",
                    "--filter",
                    f"label=com.docker.compose.project={args.project}",
                ]
            ).strip()
        ):
            raise ValueError("Project already has containers or retained volumes; choose a fresh --project")
        services_started = True
        initial = {
            node: json.loads(dc("run", "--rm", "--no-deps", "-T", node, "chain", "status")) for node in NODES
        }
        if (
            any(
                not valid_chain(s) or s["height"] != 0 or s["blocks"] != 0 or s["head"] != s["genesis"]
                for s in initial.values()
            )
            or len({s["genesis"] for s in initial.values()}) != 1
        ):
            raise ValueError("All three distinct stores must begin at the public-testnet genesis")
        phase("fresh_genesis", chains=initial)
        receipt = import_blocks("node-a", blocks[:PREFIX_HEIGHT], running=False)
        if receipt["imported"] != PREFIX_HEIGHT:
            raise ValueError("Only node A must receive the complete fixture prefix")
        dc("up", "-d")
        prefix = wait_for(
            "p2p_prefix_sync",
            lambda values: (
                at_head(values, PREFIX_HEIGHT)
                and all(v["status"]["connected_verified"] >= 1 for v in values.values())
                # Exactly three participants: either survivor having two peers proves the B-C link.
                and any(values[n]["status"]["connected_verified"] >= 2 for n in SURVIVORS)
                and all(v["status"].get("neighbors", {}).get("history", 0) >= 1 for v in values.values())
            ),
        )
        before = containers()
        if set(before) != {*ROUTERS, *NODES} or any(v["status"] != "running" for v in before.values()):
            raise ValueError("Expected three running participants and four discovery routers")
        volumes = {
            node: [
                m["name"]
                for m in before[node]["mounts"]
                if m["type"] == "volume" and m["destination"] == "/data"
            ]
            for node in NODES
        }
        if any(len(v) != 1 for v in volumes.values()) or len({v[0] for v in volumes.values()}) != 3:
            raise ValueError("Participants must have three separate data volumes")
        if any(before[router]["mounts"] for router in ROUTERS) or any(
            v["image_id"] != report["image_id"] for v in before.values()
        ):
            raise ValueError("Routers must have no data mounts; all services must run the inspected image")
        router_data = {
            router: json.loads(
                dc(
                    "exec",
                    "-T",
                    router,
                    "python",
                    "-c",
                    "import json; from pathlib import Path; print(json.dumps(sorted(p.name for p in Path('/data').iterdir())))",
                )
            )
            for router in ROUTERS
        }
        if any(router_data.values()):
            raise ValueError("Discovery routers must not create blockchain stores or participant keys")
        if (
            len({v["author"] for v in prefix.values()}) != 3
            or len({v["transport_key_sha256"] for v in prefix.values()}) != 3
        ):
            raise ValueError("Participants must generate distinct local author and transport keys")
        if any(prefix[n]["status"]["transfers"]["blocks_received"] < PREFIX_HEIGHT for n in SURVIVORS):
            raise ValueError("Fresh B and C must receive the prefix through P2P")
        for value in prefix.values():
            neighbors = value["status"]["neighbors"]
            if (
                any(
                    neighbors["limits"][role] != limit
                    for role, limit in {"selected": 8, "probe": 2, "incoming": 22}.items()
                )
                or neighbors["active"] > 32
                or neighbors["dial_queue"] > 10
                or neighbors["dialing"] > 3
                or not value["neighbor_cache"]
                or any(
                    cache["mode"] != "0o600" or not 1 <= cache["entries"] <= 32
                    for cache in value["neighbor_cache"]
                )
            ):
                raise ValueError("Neighbor policy budgets and private successful-history cache must hold")
        phase(
            "p2p_prefix_sync",
            snapshots=prefix,
            containers=before,
            router_data_entries=router_data,
            seed_receipt=receipt,
        )
        dc("stop", *ROUTERS, "node-a")
        stopped = containers()
        if any(stopped[n]["status"] != "exited" for n in (*ROUTERS, "node-a")):
            raise ValueError("All discovery routers and original block source must be stopped")
        tail_receipt = import_blocks("node-b", blocks[PREFIX_HEIGHT:], running=True)
        if tail_receipt["imported"] != len(blocks) - PREFIX_HEIGHT:
            raise ValueError("Only B must import the remaining authentic blocks locally")

        def survivor_check(values):
            return (
                at_head(values, len(blocks))
                and all(v["status"]["connected_verified"] >= 1 for v in values.values())
                and all(v["status"].get("neighbors", {}).get("history", 0) >= 1 for v in values.values())
                and values["node-c"]["status"]["transfers"]["blocks_received"]
                >= prefix["node-c"]["status"]["transfers"]["blocks_received"] + len(blocks) - PREFIX_HEIGHT
                and all(
                    v["confirmation"]["status"] == "confirmed" and v["confirmation"]["depth"] >= 6
                    for v in values.values()
                )
            )

        survivors = wait_for("exchange_without_router_or_initial_source", survivor_check, SURVIVORS)
        phase(
            "exchange_without_router_or_initial_source",
            stopped=[*ROUTERS, "node-a"],
            snapshots=survivors,
            containers=stopped,
            local_tail_receipt=tail_receipt,
        )
        # Fresh discovery after recreation uses the routers again; the preceding phase had none.
        dc("start", *ROUTERS)
        dc("stop", "node-c")
        dc(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "node-c",
            "-c",
            "from pathlib import Path; Path('/data/p2p-status.json').unlink()",
        )
        dc("up", "-d", "--no-deps", "--force-recreate", "node-c")
        restarted = wait_for(
            "restart_persistence",
            lambda values: (
                at_head(values, len(blocks))
                and all(v["status"]["connected_verified"] >= 1 for v in values.values())
                and all(v["status"].get("neighbors", {}).get("history", 0) >= 1 for v in values.values())
            ),
            SURVIVORS,
        )
        after = containers()
        old, new = survivors["node-c"], restarted["node-c"]
        if (
            old["author"] != new["author"]
            or old["transport_key_sha256"] != new["transport_key_sha256"]
            or not new["neighbor_cache"]
            or any(cache["mode"] != "0o600" for cache in new["neighbor_cache"])
            or new["confirmation"]["status"] != "confirmed"
            or new["confirmation"]["depth"] < 6
            or before["node-c"]["id"] == after["node-c"]["id"]
            or before["node-c"]["mounts"] != after["node-c"]["mounts"]
            or before["node-c"]["image_id"] != after["node-c"]["image_id"]
            or after["node-a"]["status"] != "exited"
        ):
            raise ValueError(
                "C recreation must preserve volume, author key, transport key, head, and confirmation"
            )
        phase(
            "restart_persistence",
            snapshots=restarted,
            containers=after,
            discovery_routers_restarted=list(ROUTERS),
            original_source_still_stopped=after["node-a"]["status"] == "exited",
        )
        report["success"] = True
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        emit("failed", **report["error"])
    finally:
        if services_started:
            try:
                logs.write_text(dc("logs", "--no-color", "--timestamps", "--tail", "200", cleanup=True))
            except Exception as exc:
                report["logs_error"] = str(exc)
            try:
                dc("stop", cleanup=True)
                report["cleanup"] = {"containers_stopped": True, "volumes_retained": True}
            except Exception as exc:
                report["cleanup_error"] = str(exc)
                report["success"] = False
        report["finished_at"] = utc_now()
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        emit("complete", success=report["success"], report=str(output))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
