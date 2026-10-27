import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from .config import load_config
from .federation import create_app, sync_peer
from .storage import now
from .workspace import Workspace


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def call(config, name, arguments):
    from .server import create_server

    server = create_server(config)
    try:
        result = asyncio.run(server.call_tool(name, arguments))
        if isinstance(result, dict):
            return result
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
            return result[1]
        text = "\n".join(block.text for block in result if getattr(block, "type", None) == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
    finally:
        server.worklife_browser.close()


def demo(workspace):
    w = workspace
    w.save_profile(
        {
            "name": "Demo candidate",
            "constraints": {"remote": True, "max_hours": 32},
            "life_preferences": ["Leave time and energy for life outside work"],
            "facts": [{"id": "python", "text": "Built Python APIs", "source": "Demo portfolio"}],
        }
    )
    cv = w.create_cv("Backend", ["python"], "Python developer")
    cv2 = w.create_cv("Alternative", ["python"], "Backend engineer")
    job = w.save_job(
        {
            "id": "demo-1",
            "platform": "demo",
            "title": "Python engineer",
            "employer": "Example",
            "url": "https://example.org/jobs/1",
            "remote": True,
            "hours": 30,
        }
    )
    experiment = w.create_experiment("A clearer headline increases replies", [cv["id"], cv2["id"]])
    assignment = w.assign_experiment(experiment["id"], job["id"])
    w.application(job["id"], assignment["variant_id"], "saved", "Demo only: nothing sent")
    action = w.draft_action(
        "not-configured-demo-mail",
        "send",
        {"to": "hr@example.org", "subject": "Demo only", "body": "Not sent"},
        "demo-email",
    )
    w.add_task("Confirm salary and number of hiring stages", job["id"])
    event = w.ledger.publish(
        "employer",
        "example.org",
        {
            "claim": "DEMO: remote work advertised",
            "source_url": job["url"],
            "evidence_kind": "hypothesis",
            "observed_at": now(),
        },
    )
    replica = Workspace(w.home / "demo-replica")
    for offset in range(0, len(w.ledger.all()), 1000):
        replica.ledger.import_events(w.ledger.all()[offset : offset + 1000])
    forged = json.loads(json.dumps(event))
    forged["payload"]["claim"] = "FORGED"
    rejected = False
    try:
        replica.ledger.import_events([forged])
    except ValueError:
        rejected = True
    return {
        "home": str(w.home),
        "job": job,
        "assessment": w.assess_job(job["id"]),
        "cv_id": cv["id"],
        "experiment": w.experiment_report(experiment["id"]),
        "draft_action": action,
        "replication": replica.ledger.verify(),
        "tampering_rejected": rejected,
        "note": "Synthetic local data only; no account connected, message sent, or job application submitted",
    }


def worker_cycle(config, w):
    peers = {
        **{p.get("name", p["url"]): p for p in config.peers},
        **{p["id"]: p["config"] for p in w.store.list("peer")},
    }
    reports = {}
    for name, peer in peers.items():
        try:
            reports[name] = sync_peer(w, peer)
        except Exception as exc:
            reports[name] = {
                "error": type(exc).__name__,
                "message": "Peer sync failed; inspect configuration/connectivity",
            }
    packet = {
        "at": now(),
        "due_tasks": w.due_tasks(),
        "peers": reports,
        "note": "An external MCP host must run the reasoning/search/reply cycle",
    }
    path = w.home / "worker-status.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
    temp.replace(path)
    return packet


def main():
    parser = argparse.ArgumentParser(
        description="Worklife — personal job-search tools and signed shared knowledge"
    )
    parser.add_argument("--config", help="TOML configuration path (or WORKLIFE_CONFIG)")
    parser.add_argument("--home", help="Private local state directory (or WORKLIFE_HOME)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "identity", "mcp", "demo", "verify", "tools"):
        sub.add_parser(name)
    invoke = sub.add_parser("call", help="Call any MCP tool with a JSON object")
    invoke.add_argument("tool")
    invoke.add_argument("arguments", nargs="?", default="{}")
    serve = sub.add_parser("serve", help="Serve ONLY shared signed events; private data has no HTTP endpoint")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    sync = sub.add_parser("sync")
    sync.add_argument("peer", nargs="?")
    backup = sub.add_parser("backup")
    backup.add_argument("destination")
    restore = sub.add_parser("restore")
    restore.add_argument("source")
    restore.add_argument("destination")
    export = sub.add_parser("export", help="Export only signed shared records as JSONL")
    export.add_argument("destination")
    ingest = sub.add_parser("import")
    ingest.add_argument("source")
    worker = sub.add_parser(
        "worker", help="Periodic shared replication and local follow-up status; no autonomous sends"
    )
    worker.add_argument("--interval", type=int, default=300)
    worker.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.home:
            config.home = Path(args.home).expanduser().resolve()
        if args.command == "restore":
            restored = Workspace.restore(args.source, args.destination)
            emit({"home": str(restored.home), "integrity": restored.ledger.verify()})
            return
        if args.command == "mcp":
            from .server import create_server

            create_server(config).run()
            return
        if args.command == "call":
            emit(call(config, args.tool, json.loads(args.arguments)))
            return
        if args.command == "tools":
            from .server import create_server

            server = create_server(config)
            try:
                emit(
                    [
                        {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                        for t in asyncio.run(server.list_tools())
                    ]
                )
            finally:
                server.worklife_browser.close()
            return
        w = Workspace(config.home)
        if args.command in {"identity", "init"}:
            emit({"home": str(w.home), "author": w.ledger.author_id, "public_key": w.ledger.public_key})
        elif args.command == "demo":
            emit(demo(w))
        elif args.command == "verify":
            emit(w.ledger.verify())
        elif args.command == "backup":
            emit({"path": w.backup(args.destination), "contains_private_data": True})
        elif args.command == "export":
            path = Path(args.destination).expanduser().resolve()
            path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in w.ledger.all()))
            emit({"path": str(path), "events": len(w.ledger.all())})
        elif args.command == "import":
            events = [json.loads(line) for line in Path(args.source).read_text().splitlines() if line.strip()]
            imported = 0
            for offset in range(0, len(events), 1000):
                imported += w.ledger.import_events(events[offset : offset + 1000])["imported"]
            emit({"imported": imported, "integrity": w.ledger.verify()})
        elif args.command == "serve":
            import uvicorn

            token = os.getenv(config.network_token_env, "")
            uvicorn.run(create_app(w, token), host=args.host, port=args.port, log_level="info")
        elif args.command == "sync":
            peers = {
                **{p.get("name", p["url"]): p for p in config.peers},
                **{p["id"]: p["config"] for p in w.store.list("peer")},
            }
            if args.peer and args.peer not in peers:
                raise ValueError("Unknown peer")
            emit([sync_peer(w, peer) for name, peer in peers.items() if not args.peer or name == args.peer])
        elif args.command == "worker":
            if args.interval < 1:
                raise ValueError("Worker interval must be positive")
            while True:
                emit(worker_cycle(config, w))
                if args.once:
                    break
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # Full transport exception URLs can contain secrets (e.g. Telegram bot tokens).
        message = (
            str(exc)
            if isinstance(exc, (ValueError, FileNotFoundError))
            else "Operation failed; check provider/configuration"
        )
        print(
            json.dumps({"error": type(exc).__name__, "message": message}, ensure_ascii=False), file=sys.stderr
        )
        raise SystemExit(1) from None
