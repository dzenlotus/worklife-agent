import hmac
import json
import os

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .storage import now


def create_app(workspace, token):
    if not token:
        raise ValueError("Network token is required")

    async def endpoint(request: Request):
        if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            path = request.url.path
            if path == "/v1/identity":
                return JSONResponse(
                    {
                        "protocol": 1,
                        "author": workspace.ledger.author_id,
                        "public_key": workspace.ledger.public_key,
                    }
                )
            if path == "/v1/heads":
                return JSONResponse(workspace.ledger.verify())
            if request.method == "GET":
                return JSONResponse(
                    workspace.ledger.page(
                        int(request.query_params.get("after", 0)), int(request.query_params.get("limit", 200))
                    )
                )
            # Shared endpoint deliberately has no private-state routes.
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    return JSONResponse({"error": "batch exceeds 8 MiB"}, status_code=413)
                chunks.append(chunk)
            data = json.loads(b"".join(chunks))
            return JSONResponse(workspace.ledger.import_events(data["events"]))
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    return Starlette(
        routes=[
            Route("/v1/identity", endpoint),
            Route("/v1/heads", endpoint),
            Route("/v1/events", endpoint, methods=["GET", "POST"]),
        ]
    )


def sync_peer(workspace, peer):
    url = peer["url"].rstrip("/")
    if not url.startswith(("https://", "http://")) or len(peer.get("author", "")) != 64:
        raise ValueError("Peer requires HTTP(S) URL and independently verified author fingerprint")
    token = peer.get("token") or os.getenv(peer.get("token_env", "WORKLIFE_NETWORK_TOKEN"), "")
    if not token:
        raise ValueError("Missing peer token")
    # Replay from zero is intentional: cursor-only sync can miss data after a restored peer snapshot.
    # ponytail: O(total shared events) each sync; add head-based deltas once volume warrants it.
    pulled, pushed = 0, 0
    with httpx.Client(
        base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=30, follow_redirects=False
    ) as client:
        response = client.get("/v1/identity")
        response.raise_for_status()
        if response.json().get("author") != peer["author"]:
            raise ValueError("Peer identity mismatch; verify its fingerprint out of band")
        cursor = 0
        while True:
            response = client.get("/v1/events", params={"after": cursor, "limit": 100})
            response.raise_for_status()
            page = response.json()
            if not page["events"]:
                break
            if page["next_cursor"] <= cursor:
                raise ValueError("Peer returned a non-advancing cursor")
            pulled += workspace.ledger.import_events(page["events"])["imported"]
            cursor = page["next_cursor"]
        cursor = 0
        while True:
            page = workspace.ledger.page(cursor, 100)
            if not page["events"]:
                break
            response = client.post("/v1/events", json={"events": page["events"]})
            response.raise_for_status()
            pushed += response.json()["imported"]
            cursor = page["next_cursor"]
    workspace.store.put("sync", url, {"id": url, "last_success": now(), "author": peer["author"]})
    return {"peer": url, "pulled": pulled, "pushed": pushed, "integrity": workspace.ledger.verify()}
