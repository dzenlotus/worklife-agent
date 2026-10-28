"""Exchange verified public blocks through an already connected Telegram chat."""

import hashlib
import json

from .storage import canonical

PROTOCOL = "worklife-telegram-blocks-v1"
MAX_PACKET_BYTES = 8 * 1024 * 1024
MAX_BLOCKS = 100


def _decode(data, identity):
    if not isinstance(data, bytes) or len(data) > MAX_PACKET_BYTES:
        raise ValueError("Invalid packet size")
    packet = json.loads(data)
    if (
        not isinstance(packet, dict)
        or set(packet) != {"protocol", "network", "genesis", "rules", "blocks"}
        or any(canonical(packet[key]) != canonical(value) for key, value in identity.items())
        or not isinstance(packet["blocks"], list)
        or len(packet["blocks"]) > MAX_BLOCKS
        or any(
            not isinstance(block, dict)
            or type(block.get("height")) is not int
            or not isinstance(block.get("block_id"), str)
            for block in packet["blocks"]
        )
    ):
        raise ValueError("Invalid packet identity or schema")
    return sorted(packet["blocks"], key=lambda block: (block["height"], block["block_id"]))


def _batches(identity, blocks):
    batch = []
    for block in blocks:
        encoded = canonical({**identity, "blocks": [*batch, block]})
        if batch and (len(batch) == MAX_BLOCKS or len(encoded) > MAX_PACKET_BYTES):
            yield batch, canonical({**identity, "blocks": batch})
            batch = []
            encoded = canonical({**identity, "blocks": [block]})
        if len(encoded) > MAX_PACKET_BYTES:
            raise ValueError("Verified block exceeds Telegram packet limit")
        batch.append(block)
    if batch:
        yield batch, canonical({**identity, "blocks": batch})


async def sync_channel(workspace, channel):
    """Pull chat history, then publish locally verified blocks absent from this chat.

    ``channel`` supplies a canonical ``key``, ``read(after, limit=100)`` and
    ``send(bytes)``. Transport errors become fixed report codes, never raw text.
    """
    chain = workspace.blockchain
    status = chain.status()
    identity = {
        "protocol": PROTOCOL,
        "network": status["network"],
        "genesis": status["genesis"],
        "rules": status["rules"],
    }
    key = hashlib.sha256(canonical({**identity, "channel": channel.key})).hexdigest()
    try:
        state = workspace.store.get("telegram_sync", key)
    except ValueError:
        state = {"cursor": 0, "known_blocks": []}
    known = set(state["known_blocks"])
    cursor = after = state["cursor"]
    unresolved = None
    report = {
        "transport": "telegram",
        "channel": channel.key,
        "network": status["network"],
        "pulled": 0,
        "pushed": 0,
        "rejected": 0,
        "pending": 0,
        "last_message_id": cursor,
        "status": "healthy",
        "errors": [],
    }

    def save():
        workspace.store.put(
            "telegram_sync",
            key,
            {
                **identity,
                "channel": channel.key,
                "cursor": cursor,
                "known_blocks": sorted(known),
            },
        )

    while True:
        try:
            messages = await channel.read(after=after, limit=100)
        except Exception:
            report["errors"].append("read_failed")
            break
        if not messages:
            break
        for message in messages:
            identifier, data = message["id"], message["data"]
            pending = False
            if data is not None:
                try:
                    blocks = _decode(data, identity)
                except (ValueError, TypeError, RecursionError):
                    report["rejected"] += 1
                else:
                    for block in blocks:
                        try:
                            imported = chain.import_blocks([block])
                        except (ValueError, TypeError, KeyError, RecursionError) as exc:
                            if str(exc) == "Unknown block parent; import predecessors first":
                                pending = True
                            else:
                                report["rejected"] += 1
                        else:
                            report["pulled"] += imported["imported"]
                            known.add(block["block_id"])
            if pending:
                report["pending"] += 1
                unresolved = identifier if unresolved is None else unresolved
            after = identifier
        # ponytail: replay from the earliest missing ancestor, storing no unverified
        # payloads. Long unresolved histories cost rereads; index them only at scale.
        cursor = unresolved - 1 if unresolved is not None else after
        save()

    outgoing = [] if report["errors"] else chain.all()
    for batch, encoded in _batches(identity, (block for block in outgoing if block["block_id"] not in known)):
        try:
            await channel.send(encoded)
        except Exception:
            report["errors"].append("send_failed")
            break
        known.update(block["block_id"] for block in batch)
        report["pushed"] += len(batch)
        save()
    report["last_message_id"] = cursor
    if report["errors"] or report["rejected"] or report["pending"]:
        report["status"] = "attention"
    return report
