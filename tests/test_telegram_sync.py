import json
from datetime import UTC, datetime, timedelta

import pytest

from worklife.storage import canonical
from worklife.workspace import Workspace


class Channel:
    def __init__(self, key="-100123"):
        self.key = key
        self.messages = []
        self.sent = []
        self.fail_read = False
        self.fail_send = False

    def append(self, data):
        identifier = len(self.messages) + 1
        self.messages.append({"id": identifier, "data": data})
        return identifier

    async def read(self, after, limit=100):
        if self.fail_read:
            raise OSError("private transport detail")
        return [message for message in self.messages if message["id"] > after][:limit]

    async def send(self, data):
        if self.fail_send:
            raise OSError("private transport detail")
        self.sent.append(data)
        return self.append(data)


def mine(workspace, count=1, events=None):
    start = datetime(2026, 10, 15, 10, tzinfo=UTC)
    workspace.blockchain.qualify(at=start)
    result = []
    offset = workspace.blockchain.status()["height"]
    for index in range(count):
        mined = workspace.blockchain.mine(
            events if index == 0 and events else [], at=start + timedelta(seconds=offset + index)
        )
        assert mined["mined"]
        result.append(mined["block"])
    return result


def packet(workspace, blocks, **changes):
    status = workspace.blockchain.status()
    return canonical(
        {
            "protocol": "worklife-telegram-blocks-v1",
            "network": status["network"],
            "genesis": status["genesis"],
            "rules": status["rules"],
            "blocks": blocks,
            **changes,
        }
    )


@pytest.mark.asyncio
async def test_two_workspaces_sync_only_verified_blocks_and_do_not_echo(tmp_path):
    from worklife.telegram_sync import sync_channel

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    public = a.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "Public employer observation",
            "evidence_kind": "advertised",
            "source_url": "https://acme.example/jobs",
            "observed_at": "2026-10-15T10:00:00Z",
        },
    )
    blocks = mine(a, 2, events=[public])
    a.save_profile({"name": "PRIVATE PROFILE", "facts": []})
    a.store.put("message", "private-mail", {"body": "PRIVATE MAIL"})
    pending = a.ledger.publish(
        "employer",
        "acme.example",
        {
            "claim": "PRIVATE RAW PROPOSAL",
            "evidence_kind": "hypothesis",
            "source_url": "https://acme.example/jobs",
            "observed_at": "2026-10-15T10:00:00Z",
        },
    )
    assert a.blockchain.confirmation(pending["event_id"])["status"] == "pending"
    channel = Channel()
    channel.append(None)

    first = await sync_channel(a, channel)
    assert first["pushed"] == 2
    assert first["status"] == "healthy"
    assert json.loads(channel.sent[0]) == json.loads(packet(a, blocks))
    assert all(b"PRIVATE" not in data for data in channel.sent)

    imported = await sync_channel(b, channel)
    assert imported["pulled"] == 2
    assert imported["pushed"] == 0
    assert b.blockchain.all() == blocks
    assert (await sync_channel(a, channel))["pushed"] == 0
    assert (await sync_channel(b, channel))["pushed"] == 0
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_offline_node_catches_up_after_restart_and_empty_node_bootstraps(tmp_path):
    from worklife.telegram_sync import sync_channel

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    channel = Channel()
    mine(a)
    await sync_channel(a, channel)
    await sync_channel(b, channel)
    mine(a, 2)
    await sync_channel(a, channel)

    b = Workspace(tmp_path / "b")
    assert (await sync_channel(b, channel))["pulled"] == 2
    c = Workspace(tmp_path / "c")
    assert (await sync_channel(c, channel))["pulled"] == 3
    assert a.blockchain.all() == b.blockchain.all() == c.blockchain.all()
    assert len(channel.sent) == 2


@pytest.mark.asyncio
async def test_invalid_messages_are_rejected_without_poisoning_later_valid_blocks(tmp_path):
    from worklife.telegram_sync import sync_channel

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    block = mine(a)[0]
    channel = Channel()
    channel.append(packet(a, [block], network="foreign"))
    channel.append(packet(a, [block], genesis="0" * 64))
    channel.append(packet(a, [block], rules={}))
    channel.append(packet(a, [block], rules={**a.blockchain.status()["rules"], "version": True}))
    channel.append(packet(a, [block], private="PRIVATE INBOUND PAYLOAD"))
    channel.append(b"not-json PRIVATE INBOUND PAYLOAD")
    channel.append(packet(a, [{**block, "signature": "0" * 128}]))
    channel.append(packet(a, [block]))

    report = await sync_channel(b, channel)
    assert report["pulled"] == 1
    assert report["rejected"] == 7
    assert report["last_message_id"] == 8
    assert report["status"] == "attention"
    assert "PRIVATE" not in json.dumps(report)
    assert b.blockchain.all() == [block]
    assert channel.sent == []


@pytest.mark.asyncio
async def test_missing_parent_is_revisited_after_restart_without_echoing(tmp_path):
    from worklife.telegram_sync import sync_channel

    a, b = Workspace(tmp_path / "a"), Workspace(tmp_path / "b")
    parent, child = mine(a, 2)
    channel = Channel()
    channel.append(packet(a, [child]))

    first = await sync_channel(b, channel)
    assert first["pending"] == 1
    assert first["last_message_id"] == 0
    assert b.blockchain.all() == []
    # The deferred packet is replayed from Telegram, not copied into local objects.
    assert child["block_id"] not in canonical(b.store.list("telegram_sync")).decode()

    b = Workspace(tmp_path / "b")
    channel.append(packet(a, [parent]))
    await sync_channel(b, channel)
    b = Workspace(tmp_path / "b")
    recovered = await sync_channel(b, channel)
    assert recovered["pulled"] == 1
    assert recovered["pending"] == 0
    assert recovered["last_message_id"] == 2
    assert b.blockchain.all() == [parent, child]
    assert channel.sent == []


@pytest.mark.asyncio
async def test_failed_send_retries_unsent_blocks_after_restart(tmp_path):
    from worklife.telegram_sync import sync_channel

    a = Workspace(tmp_path / "a")
    mine(a, 2)
    channel = Channel()
    channel.fail_send = True
    failed = await sync_channel(a, channel)
    assert failed["pushed"] == 0
    assert failed["errors"] == ["send_failed"]
    assert "private transport detail" not in json.dumps(failed)

    a = Workspace(tmp_path / "a")
    channel.fail_send = False
    assert (await sync_channel(a, channel))["pushed"] == 2
    assert (await sync_channel(a, channel))["pushed"] == 0
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_successful_batch_stays_published_when_a_later_send_fails(tmp_path, monkeypatch):
    import worklife.telegram_sync as telegram_sync

    # Keep the real signed chain small while forcing multiple transport batches.
    monkeypatch.setattr(telegram_sync, "MAX_BLOCKS", 1)
    a = Workspace(tmp_path / "a")
    blocks = mine(a, 2)
    channel = Channel()
    original_send = channel.send

    async def fail_second(data):
        if channel.sent:
            raise OSError("private transport detail")
        return await original_send(data)

    channel.send = fail_second
    failed = await telegram_sync.sync_channel(a, channel)
    assert failed["pushed"] == 1
    assert failed["errors"] == ["send_failed"]
    channel.send = original_send
    a = Workspace(tmp_path / "a")
    assert (await telegram_sync.sync_channel(a, channel))["pushed"] == 1
    assert [json.loads(data)["blocks"][0] for data in channel.sent] == blocks


@pytest.mark.asyncio
async def test_failed_history_read_retries_before_publishing_or_advancing_cursor(tmp_path):
    from worklife.telegram_sync import sync_channel

    a = Workspace(tmp_path / "a")
    blocks = mine(a)
    channel = Channel()
    channel.append(packet(a, blocks))
    channel.fail_read = True

    failed = await sync_channel(a, channel)
    assert failed["last_message_id"] == 0
    assert failed["errors"] == ["read_failed"]
    assert channel.sent == []

    a = Workspace(tmp_path / "a")
    channel.fail_read = False
    recovered = await sync_channel(a, channel)
    assert recovered["last_message_id"] == 1
    assert recovered["pushed"] == 0
    assert channel.sent == []


@pytest.mark.asyncio
async def test_existing_chain_publishes_all_blocks_when_attached_to_a_new_chat(tmp_path):
    from worklife.telegram_sync import sync_channel

    a = Workspace(tmp_path / "a")
    blocks = mine(a, 2)
    first, second = Channel("-1001"), Channel("-1002")
    assert (await sync_channel(a, first))["pushed"] == 2
    a = Workspace(tmp_path / "a")
    assert (await sync_channel(a, second))["pushed"] == 2
    assert json.loads(second.sent[0])["blocks"] == blocks
    assert (await sync_channel(a, first))["pushed"] == 0


def test_packet_batching_respects_block_count_and_encoded_byte_limit(tmp_path):
    from worklife.telegram_sync import MAX_PACKET_BYTES, _batches

    workspace = Workspace(tmp_path)
    identity = json.loads(packet(workspace, []))
    identity.pop("blocks")
    small = [{"height": index, "block_id": str(index)} for index in range(101)]
    batches = list(_batches(identity, small))
    assert [len(batch) for batch, _ in batches] == [100, 1]
    large = [{**block, "events": ["ж" * 250_000]} for block in small[:17]]
    batches = list(_batches(identity, large))
    assert len(batches) == 2
    assert [block for batch, _ in batches for block in batch] == large
    assert all(len(encoded) <= MAX_PACKET_BYTES for _, encoded in batches)
    assert all(json.loads(encoded) == {**identity, "blocks": batch} for batch, encoded in batches)
