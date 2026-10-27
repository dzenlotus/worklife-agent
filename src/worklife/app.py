"""Private local application. The public replica server remains separate."""

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from .server import create_server


def normalize_result(value):
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], dict):
        value = value[1]
    if isinstance(value, dict):
        return value["result"] if set(value) == {"result"} else value
    content = "\n".join(block.text for block in value if getattr(block, "type", None) == "text")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"text": content}


async def invoke(server, name, arguments):
    def call():
        return normalize_result(asyncio.run(server.call_tool(name, arguments)))

    return await asyncio.to_thread(call)


def snapshot(server):
    w = server.worklife_workspace
    try:
        profile = w.get_profile()
    except ValueError:
        profile = None
    try:
        integrity = w.ledger.verify()
        employers = w.shared_records()
    except ValueError as exc:
        integrity, employers = {"valid": False, "events": None, "heads": {}, "error": str(exc)}, []
    peers = [
        {"name": name, **{k: v for k, v in config.items() if k in {"url", "author", "token_env"}}}
        for name, config in server.worklife_peers().items()
    ]
    buckets = {
        "jobs": "job",
        "applications": "application",
        "cvs": "cv",
        "experiments": "experiment",
        "tasks": "task",
        "research": "research",
        "resources": "resource",
        "activity": "activity",
        "schedules": "schedule",
        "schedule_runs": "schedule_run",
        "strengths": "strength",
        "tactics": "tactic",
        "repositories": "repository",
        "platforms": "platform",
        "accounts": "account",
        "employer_blocks": "employer_block",
    }
    result = {name: w.store.list(bucket) for name, bucket in buckets.items()}
    return {
        **result,
        "profile": profile,
        "actions": w.actions(),
        "employers": employers,
        "experiment_reports": [w.experiment_report(e["id"]) for e in result["experiments"]],
        "network": {
            **integrity,
            "author": w.ledger.author_id,
            "peers": peers,
            "last_sync": w.store.list("sync"),
            "scope": "employers_only",
        },
        "statistics": server.worklife_operations.statistics(),
        "connectors": server.worklife_connectors.capabilities(),
        "agent": server.worklife_runtime.status(),
    }


def create_app(config, scheduler=True):
    server = create_server(config)
    web = Path(__file__).parent / "web"

    async def tick():
        while True:
            try:
                await asyncio.to_thread(server.worklife_operations.run_due)
            except Exception as exc:
                server.worklife_operations.activity_record("scheduler_error", type(exc).__name__)
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(tick()) if scheduler else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            server.worklife_runtime.close()
            server.worklife_browser.close()

    async def state(request):
        return JSONResponse(await asyncio.to_thread(snapshot, server), headers={"Cache-Control": "no-store"})

    async def tool(request):
        try:
            args = await request.json()
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be a JSON object")
            result = await invoke(server, request.path_params["name"], args)
            return JSONResponse({"ok": True, "result": result})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def download(request):
        try:
            result = await invoke(
                server,
                "cv_export",
                {"cv_id": request.path_params["cv_id"], "format": request.query_params.get("format", "pdf")},
            )
            return FileResponse(
                result["path"], filename=Path(result["path"]).name, headers={"Cache-Control": "no-store"}
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def static(request):
        filename = request.path_params.get("filename", "index.html")
        if filename not in {"index.html", "app.css", "app.js"}:
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(web / filename, headers={"Cache-Control": "no-store"})

    app = Starlette(
        routes=[
            Route("/api/state", state),
            Route("/api/tools/{name}", tool, methods=["POST"]),
            Route("/api/cv/{cv_id}/download", download),
            Route("/", static),
            Route("/{filename}", static),
        ],
        lifespan=lifespan,
    )
    app.state.worklife = server

    async def local_requests(request, call_next):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if origin and origin != expected:
            return JSONResponse({"error": "Private local app: cross-origin access refused"}, status_code=403)
        if request.method == "POST" and request.headers.get("x-worklife-client") != "local":
            return JSONResponse({"error": "Use the local application client"}, status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=local_requests)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    return app
