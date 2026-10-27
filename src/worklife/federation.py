import hmac
import json
import os
from urllib.parse import urlparse

import httpx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .blockchain import BLOCK_BITS, GENESIS, NETWORK, VERSION
from .storage import canonical, now

MAX_TRANSPORT_BYTES = 8 * 1024 * 1024


async def _read_json(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_TRANSPORT_BYTES:
            raise HTTPException(413, "batch exceeds 8 MiB")
        chunks.append(chunk)
    return json.loads(b"".join(chunks))


def _chain_page(chain, after, limit):
    page = chain.page(after, limit)
    while len(canonical(page)) > MAX_TRANSPORT_BYTES and page["blocks"]:
        page["blocks"].pop()
        page["next_cursor"] -= 1
    return page


def create_app(workspace, token=""):

    async def endpoint(request: Request):
        if not token or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
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
            data = await _read_json(request)
            return JSONResponse(workspace.ledger.import_events(data["events"]))
        except (ValueError, KeyError, TypeError, RecursionError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    async def chain_endpoint(request: Request):
        try:
            chain = workspace.blockchain
            if request.url.path == "/v2/state":
                return JSONResponse({**chain.status(), "transport_protocol": 2})
            if request.method == "GET":
                return JSONResponse(
                    _chain_page(
                        chain,
                        int(request.query_params.get("after", 0)),
                        int(request.query_params.get("limit", 100)),
                    )
                )
            data = await _read_json(request)
            if type(data) is not dict or set(data) != {"blocks"}:
                raise ValueError("Chain transport requires a blocks batch")
            return JSONResponse(chain.import_blocks(data["blocks"]))
        except (ValueError, KeyError, TypeError, RecursionError, OverflowError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    return Starlette(
        routes=[
            Route("/v1/identity", endpoint),
            Route("/v1/heads", endpoint),
            Route("/v1/events", endpoint, methods=["GET", "POST"]),
            Route("/v2/state", chain_endpoint),
            Route("/v2/blocks", chain_endpoint, methods=["GET", "POST"]),
        ]
    )


def sync_peer(workspace, peer):
    if peer.get("protocol") == 2:
        return sync_chain_peer(workspace, peer)
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


def _chain_url(peer):
    url = peer.get("url") if isinstance(peer, dict) else peer
    if not isinstance(url, str):
        raise ValueError("Chain peer requires an HTTP(S) URL")
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Chain peer requires a public HTTP(S) URL without credentials, query or fragment")
    return url.rstrip("/")


def _request_json(client, method, path, **kwargs):
    with client.stream(method, path, **kwargs) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_TRANSPORT_BYTES:
                raise ValueError("Chain response exceeds 8 MiB")
            chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except RecursionError:
            raise ValueError("Chain response JSON is too deeply nested") from None


def _block_batches(blocks):
    batch = []
    for block in blocks:
        candidate = batch + [block]
        if len(candidate) > 100 or len(canonical({"blocks": candidate})) > MAX_TRANSPORT_BYTES:
            if not batch:
                raise ValueError("A chain block exceeds the transport limit")
            yield batch
            batch = []
        batch.append(block)
    if batch:
        yield batch


def sync_chain_peer(workspace, peer):
    """Replay verified public block DAGs in both directions, without authority enrollment or tokens."""
    url = _chain_url(peer)
    chain = workspace.blockchain
    pulled, pushed = 0, 0
    expected = {
        "transport_protocol": 2,
        "protocol": VERSION,
        "network": NETWORK,
        "genesis": GENESIS,
        "block_bits": BLOCK_BITS,
    }
    with httpx.Client(base_url=url, timeout=httpx.Timeout(30, connect=5), follow_redirects=False) as client:
        state = _request_json(client, "GET", "/v2/state")
        if type(state) is not dict or any(
            type(state.get(field)) is not type(value) or state[field] != value
            for field, value in expected.items()
        ):
            raise ValueError("Peer chain identity/protocol mismatch")
        # ponytail: replay the full DAG each sync; use checkpoints only when history size warrants it.
        cursor = 0
        while True:
            page = _request_json(client, "GET", "/v2/blocks", params={"after": cursor, "limit": 100})
            if type(page) is not dict or set(page) != {"blocks", "next_cursor"}:
                raise ValueError("Invalid chain page")
            blocks, next_cursor = page["blocks"], page["next_cursor"]
            if type(blocks) is not list or len(blocks) > 100:
                raise ValueError("Invalid chain block batch")
            if type(next_cursor) is not int or next_cursor != cursor + len(blocks):
                raise ValueError("Peer returned an invalid/non-advancing cursor")
            if not blocks:
                break
            pulled += chain.import_blocks(blocks)["imported"]
            cursor = next_cursor
        for batch in _block_batches(chain.all()):
            result = _request_json(
                client,
                "POST",
                "/v2/blocks",
                content=canonical({"blocks": batch}),
                headers={"Content-Type": "application/json"},
            )
            if (
                type(result) is not dict
                or type(result.get("imported")) is not int
                or not 0 <= result["imported"] <= len(batch)
            ):
                raise ValueError("Peer returned an invalid block import receipt")
            pushed += result["imported"]
    workspace.store.put("chain_sync", url, {"id": url, "last_success": now()})
    return {"peer": url, "pulled": pulled, "pushed": pushed, "chain": chain.status()}
