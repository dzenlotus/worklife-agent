#!/usr/bin/env python3
"""Exercise real public-testnet PoW in three local containers; keep their volumes.

Requires an already built image, or --build-context pointing at reviewed source.
This functional test on one Docker host does not establish independent operators,
Byzantine safety, public reachability, or the truth of the synthetic proposal.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
NODES = ("node-a", "node-b", "node-c")
WORKERS = ("worker-a", "worker-b", "worker-c")
PORTS = dict(zip(NODES, (18761, 18762, 18763)))
EXPECTED = {"block_bits": 25, "qualification_bits": 18, "confirmations": 6}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def valid_state(state):
    return (
        state.get("transport_protocol") == 2
        and state.get("profile") == "public-testnet-v1"
        and state.get("network") == "worklife-public-testnet-v1"
        and all(state.get("rules", {}).get(key) == value for key, value in EXPECTED.items())
    )


def normalized_mounts(mounts):
    """Compare mount identities despite Docker ordering and macOS host aliases."""
    normalized = []
    for mount in mounts:
        value = dict(mount)
        if sys.platform == "darwin" and value["Type"] == "bind":
            source = value["Source"]
            if source.startswith("/host_mnt/"):
                source = source[len("/host_mnt") :]
            value["Source"] = str(Path(source).resolve())
        normalized.append(value)
    return sorted(normalized, key=lambda mount: mount["Destination"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="worklife-public-testnet:695b13c-local")
    parser.add_argument("--build-context", type=Path)
    parser.add_argument(
        "--project",
        default="worklife-chain-check-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6],
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/blockchain/docker-three-node/report.json"
    )
    parser.add_argument("--timeout", type=float, default=900, help="Whole acceptance deadline in seconds")
    parser.add_argument("--cpu-fraction", type=float, default=0.25)
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave APIs up; workers are stopped to freeze the proven head",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.project):
        parser.error("--project must be a lowercase Docker Compose project name")
    if args.timeout <= 0 or not 0 < args.cpu_fraction <= 1:
        parser.error("--timeout must be positive and --cpu-fraction must be in (0, 1]")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    events = output.with_suffix(".events.jsonl")
    logs = output.with_suffix(".containers.log")
    started, deadline = time.monotonic(), time.monotonic() + args.timeout
    env = {**os.environ, "WORKLIFE_IMAGE": args.image, "WORKER_CPU_FRACTION": str(args.cpu_fraction)}
    compose = ["docker", "compose", "-f", str(ROOT / "deploy/local-network/compose.yaml"), "-p", args.project]
    report = {
        "success": False,
        "project": args.project,
        "started_at": utc_now(),
        "image": args.image,
        "profile": "public-testnet-v1",
        "rules": EXPECTED,
        "cpu_fraction": args.cpu_fraction,
        "phases": {},
        "events_path": str(events),
        "container_logs_path": str(logs),
        "limits": [
            "Three containers on one Docker host",
            "Real PoW; fixed public-testnet rules",
            "Synthetic employer proposal only",
            "No independent-operator or Byzantine-safety claim",
        ],
    }
    events.write_text("")

    def emit(kind, **data):
        entry = {
            "at": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "event": kind,
            **data,
        }
        with events.open("a") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")
        print(json.dumps(entry, sort_keys=True), flush=True)

    def run(command, *, cleanup=False):
        before = time.monotonic()
        budget = 45 if cleanup else min(90, max(0.1, deadline - before))
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=budget)
        emit(
            "command",
            command=command,
            returncode=result.returncode,
            seconds=round(time.monotonic() - before, 2),
        )
        if result.returncode:
            raise RuntimeError(
                f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
            )
        return result.stdout

    def dc(*command, cleanup=False):
        return run([*compose, *command], cleanup=cleanup)

    def call(node, *command):
        return json.loads(dc("exec", "-T", node, "worklife", *command))

    def containers():
        ids = dc("ps", "--all", "--quiet").split()
        inspected = json.loads(run(["docker", "inspect", *ids]))
        result = {}
        for item in inspected:
            service = item["Config"]["Labels"]["com.docker.compose.service"]
            result[service] = {
                "id": item["Id"],
                "image_id": item["Image"],
                "configured_image": item["Config"]["Image"],
                "command": item["Config"]["Cmd"],
                "status": item["State"]["Status"],
                "health": item["State"].get("Health", {}).get("Status"),
                "mounts": [
                    {key: mount.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")}
                    for mount in item["Mounts"]
                ],
            }
        if set(result) != set((*NODES, *WORKERS)):
            raise ValueError("Expected exactly this project's three nodes and three workers")
        volumes = {}
        for service, item in result.items():
            data = [m for m in item["mounts"] if m["Destination"] == "/data" and m["Type"] == "volume"]
            if len(data) != 1 or item["image_id"] != report["image_details"]["Id"]:
                raise ValueError("Every service must use its data volume and the inspected image")
            volumes[service] = data[0]["Name"]
        if len({volumes[n] for n in NODES}) != 3 or any(
            volumes[n] != volumes[w] for n, w in zip(NODES, WORKERS)
        ):
            raise ValueError(
                "Nodes require distinct volumes; each worker must share only its own node's volume"
            )
        return result

    def http(node, path="/v2/state"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORTS[node]}{path}", timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, None

    def states(nodes=NODES):
        result = {node: http(node)[1] for node in nodes}
        if not all(isinstance(state, dict) and valid_state(state) for state in result.values()):
            raise ValueError("Public-testnet state/profile/rules mismatch")
        return result

    def proofs(nodes=NODES):
        result = {}
        code = "import json,sys; from pathlib import Path; from worklife.workspace import Workspace; print(json.dumps(Workspace(Path('/data')).blockchain.confirmation(sys.argv[1])))"
        for node in nodes:
            result[node] = json.loads(dc("exec", "-T", node, "python", "-c", code, report["event_id"]))
        return result

    def wait_for(label, check, interval=10):
        while time.monotonic() < deadline:
            try:
                passed, detail = check()
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                passed, detail = False, {"waiting_for_http": str(exc)}
            emit("progress", phase=label, detail=detail)
            if passed:
                return detail
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"Acceptance deadline reached during {label}")

    def healthy():
        snapshot = states()
        ids = dc("ps", "--quiet", *NODES).split()
        status = json.loads(run(["docker", "inspect", *ids]))
        health = {
            item["Config"]["Labels"]["com.docker.compose.service"]: item["State"]
            .get("Health", {})
            .get("Status")
            for item in status
        }
        if set(health) != set(NODES) or any(value != "healthy" for value in health.values()):
            return False, {"states": snapshot, "container_health": health}
        return True, snapshot

    def phase(name, **details):
        report["phases"][name] = {"passed": True, "at": utc_now(), **details}
        emit("phase_passed", phase=name, **details)

    def confirmation_check(nodes=NODES, same_head=True):
        snapshot, confirmation = states(nodes), proofs(nodes)
        same = len({state["head"] for state in snapshot.values()}) == 1
        confirmed = all(p["status"] == "confirmed" and p["depth"] >= 6 for p in confirmation.values())
        return confirmed and (same or not same_head), {"states": snapshot, "confirmations": confirmation}

    services_started = False
    try:
        emit("start", project=args.project, image=args.image, report=str(output))
        if args.build_context:
            run(["docker", "build", "-t", args.image, str(args.build_context.resolve())])
        report["image_details"] = json.loads(run(["docker", "image", "inspect", args.image]))[0]
        # Never adopt existing containers or delete a previous run's retained volumes.
        existing = dc("ps", "--all", "--quiet").strip()
        if existing:
            raise ValueError("Project already has containers; choose a fresh --project")
        services_started = True
        dc("up", "-d", *NODES)
        initial = wait_for("healthy_public_apis", healthy, 3)
        if any(s["height"] != 0 or s["blocks"] != 0 or s["head"] != s["genesis"] for s in initial.values()):
            raise ValueError("Fresh genesis required; choose a new project to retain existing data")
        if len({s["genesis"] for s in initial.values()}) != 1:
            raise ValueError("Nodes disagree about genesis")
        identities = {node: call(node, "identity") for node in NODES}
        if len({identity["author"] for identity in identities.values()}) != 3:
            raise ValueError("Three independent local author keys required")
        report["identities"] = identities
        phase("fresh_genesis", states=initial, identities=identities)
        denied = {}
        for node in NODES:
            denied[node] = {
                path: http(node, path)[0]
                for path in (
                    "/v1/identity",
                    "/v1/heads",
                    "/v1/events",
                    "/api/state",
                    "/api/profile",
                    "/v1/profile",
                )
            }
            if any(
                code != (401 if path.startswith("/v1/") and path != "/v1/profile" else 404)
                for path, code in denied[node].items()
            ):
                raise ValueError("Unexpected access to v1 or private HTTP path")
        phase("private_http_denied", responses=denied)
        proposal = {
            "kind": "employer",
            "subject": "synthetic.example",
            "payload": {
                "claim": "SYNTHETIC local Docker acceptance proposal; no real employer claim",
                "source_url": "https://synthetic.example/local-acceptance",
                "observed_at": utc_now(),
                "evidence_kind": "hypothesis",
            },
        }
        event = call("node-a", "call", "knowledge_publish", json.dumps(proposal))
        report["event_id"], report["proposal"] = event["event_id"], event
        dc("up", "-d", *WORKERS)
        report["containers_started"] = containers()
        if any(item["status"] != "running" for item in report["containers_started"].values()):
            raise ValueError("All three node/worker pairs must be running at initial capture")
        exchange = wait_for(
            "block_exchange_and_six_confirmations", lambda: confirmation_check(same_head=False)
        )
        phase("block_exchange", **exchange)
        dc("stop", "worker-c", "node-c")
        try:
            http("node-c")
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        else:
            raise ValueError("Node C endpoint remained available after intentional stop")
        baseline = max(s["height"] for s in states(NODES[:2]).values())

        def survivors_advance():
            snapshot = states(NODES[:2])
            return min(s["height"] for s in snapshot.values()) >= baseline + 2, snapshot

        survivors = wait_for("two_nodes_advance_while_c_is_down", survivors_advance)
        try:
            http("node-c")
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        else:
            raise ValueError("Node C became available during the intentional failure interval")
        phase(
            "one_node_failure",
            stopped=["worker-c", "node-c"],
            endpoint_unavailable_before_and_after=True,
            baseline_height=baseline,
            states=survivors,
        )
        dc("stop", "worker-a", "worker-b")
        dc("up", "-d", "node-c")
        wait_for("restored_c_api", healthy, 3)

        def converge():
            receipts = [
                call(source, "chain", "sync", f"http://{target}:8765")
                for source, target in (("node-a", "node-b"), ("node-c", "node-a"), ("node-b", "node-c"))
            ]
            passed, detail = confirmation_check()
            return passed, {**detail, "sync_receipts": receipts}

        restored = wait_for("restored_node_c_catches_up", converge, 3)
        phase("node_restored", **restored)
        frozen = restored["states"]
        dc("stop", *WORKERS, *NODES)
        before_containers = containers()
        dc("up", "-d", "--force-recreate", *NODES)
        restarted = wait_for("full_api_restart", healthy, 3)
        after_containers = containers()
        after_ids = {node: call(node, "identity") for node in NODES}
        after_proofs = proofs()
        if any(
            restarted[n]["head"] != frozen[n]["head"]
            or restarted[n]["height"] != frozen[n]["height"]
            or after_ids[n] != identities[n]
            or after_proofs[n]["status"] != "confirmed"
            or after_proofs[n]["depth"] < 6
            for n in NODES
        ):
            raise ValueError("Head, identity, or confirmation did not persist across container recreation")
        for node in NODES:
            before, after = before_containers[node], after_containers[node]
            if (
                before["id"] == after["id"]
                or before["image_id"] != after["image_id"]
                or normalized_mounts(before["mounts"]) != normalized_mounts(after["mounts"])
            ):
                raise ValueError(
                    "Recreation must change API container IDs and retain their images and mounts"
                )
        phase(
            "restart_persistence",
            before=frozen,
            after=restarted,
            identities=after_ids,
            confirmations=after_proofs,
            containers_before=before_containers,
            containers_after=after_containers,
        )
        report["success"] = True
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        emit("failed", **report["error"])
    finally:
        if services_started:
            try:
                logs.write_text(dc("logs", "--no-color", "--timestamps", "--tail", "300", cleanup=True))
            except Exception as exc:
                report["logs_error"] = str(exc)
            try:
                dc(
                    "stop",
                    *(WORKERS if args.keep_running and report["success"] else (*WORKERS, *NODES)),
                    cleanup=True,
                )
                report["cleanup"] = {
                    "apis_running": bool(args.keep_running and report["success"]),
                    "workers_running": False,
                    "volumes_retained": True,
                    "daemon_stopped": False,
                }
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
