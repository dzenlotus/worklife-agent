import asyncio
import importlib
import importlib.util
import sys
import traceback
from io import BytesIO
from types import ModuleType, SimpleNamespace

import pytest

FILENAME = "worklife-blocks-v1.json"
MAX_BYTES = 8 * 1024 * 1024


def adapter():
    assert importlib.util.find_spec("worklife.telegram_transport") is not None, "Telegram adapter is missing"
    return importlib.import_module("worklife.telegram_transport")


class Download:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.read = 0
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration from None
        self.read += 1
        if isinstance(chunk, Exception):
            raise chunk
        if chunk is None:
            await asyncio.sleep(60)
        return chunk

    async def close(self):
        self.closed = True


@pytest.fixture
def telegram(monkeypatch):
    state = SimpleNamespace(
        authorized=True,
        messages=[],
        downloads=[],
        sent=[],
        resolved=[],
        clients=[],
        failure=None,
        dialogs=[],
        requests=[],
        entity=SimpleNamespace(id=-10012345),
    )

    class StringSession:
        def __init__(self, value):
            self.value = value

    class Client:
        def __init__(self, session, api_id, api_hash, **kwargs):
            state.clients.append(self)
            self.arguments = (session, api_id, api_hash, kwargs)
            self.disconnected = False

        async def connect(self):
            if state.failure == "connect":
                raise RuntimeError("session-secret hash-secret private chat text")

        async def is_user_authorized(self):
            return state.authorized

        async def get_entity(self, chat):
            state.resolved.append(chat)
            if state.failure in {"resolve", "uncached"}:
                raise ValueError("session-secret hash-secret private chat text")
            return state.entity

        def iter_dialogs(self):
            async def dialogs():
                for entity in state.dialogs:
                    yield SimpleNamespace(entity=entity)

            return dialogs()

        async def __call__(self, request):
            state.requests.append(request)
            if state.failure == "create" or (state.failure == "history" and hasattr(request, "enabled")):
                raise RuntimeError("session-secret hash-secret private chat text")
            return SimpleNamespace(chats=[state.entity])

        async def disconnect(self):
            self.disconnected = True

        async def start(self, *args, **kwargs):
            pytest.fail("adapter must not start interactive login")

        def iter_messages(self, entity, **kwargs):
            state.history = (entity, kwargs)

            async def messages():
                if state.failure == "read":
                    raise RuntimeError("session-secret hash-secret private chat text")
                if state.failure == "timeout":
                    await asyncio.sleep(60)
                for message in state.messages:
                    if message.id > kwargs["min_id"]:
                        yield message

            return messages()

        def iter_download(self, document, **kwargs):
            stream = Download(document.chunks)
            state.downloads.append((document, kwargs, stream))
            return stream

        async def send_file(self, entity, file, **kwargs):
            assert isinstance(file, BytesIO)
            state.sent.append((entity, file.name, file.read(), kwargs))
            if state.failure == "send":
                raise RuntimeError("session-secret hash-secret private chat text")
            return SimpleNamespace(id=77)

    module = ModuleType("telethon")
    module.TelegramClient = Client
    module.utils = SimpleNamespace(get_peer_id=lambda entity: entity.id)
    module.functions = SimpleNamespace(
        channels=SimpleNamespace(
            CreateChannelRequest=SimpleNamespace,
            TogglePreHistoryHiddenRequest=SimpleNamespace,
        )
    )
    sessions = ModuleType("telethon.sessions")
    sessions.StringSession = StringSession
    monkeypatch.setitem(sys.modules, "telethon", module)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions)
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-secret")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "session-secret")
    return state


def message(number, filename=None, size=0, chunks=()):
    document = SimpleNamespace(size=size, chunks=chunks) if filename is not None else None
    return SimpleNamespace(id=number, document=document, file=SimpleNamespace(name=filename))


async def test_optional_dependency_is_imported_only_when_connecting(monkeypatch):
    monkeypatch.setitem(sys.modules, "telethon", None)
    monkeypatch.setitem(sys.modules, "telethon.sessions", None)
    module = adapter()
    channel = module.TelegramChannel({"chat": "@blocks"})
    with pytest.raises(module.TelegramTransportError, match="telegram.*extra|extra.*telegram"):
        async with channel:
            pytest.fail("missing dependency must not connect")


async def test_connect_uses_memory_session_bounded_calls_and_canonical_chat_key(telegram):
    module = adapter()
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        assert channel.key == "-10012345"
    client = telegram.clients[0]
    session, api_id, api_hash, options = client.arguments
    assert session.value == "session-secret"
    assert (api_id, api_hash) == (12345, "hash-secret")
    assert options["timeout"] == 30
    assert options["flood_sleep_threshold"] == 0
    assert options["request_retries"] == 0
    assert options["connection_retries"] == 0
    assert options["receive_updates"] is False
    assert telegram.resolved == ["@blocks"]
    assert client.disconnected
    async with module.TelegramChannel({"chat": "-10012345"}) as channel:
        assert channel.key == "-10012345"
    assert telegram.resolved[-1] == -10012345


async def test_credentials_are_read_only_from_configured_environment_references(telegram, monkeypatch):
    module = adapter()
    monkeypatch.setenv("CUSTOM_API_ID", "987")
    monkeypatch.setenv("CUSTOM_API_HASH", "custom-hash")
    monkeypatch.setenv("CUSTOM_SESSION", "custom-session")
    async with module.TelegramChannel(
        {
            "chat": 42,
            "api_id_env": "CUSTOM_API_ID",
            "api_hash_env": "CUSTOM_API_HASH",
            "session_env": "CUSTOM_SESSION",
            "api_hash": "ignored-literal",
        }
    ):
        pass
    session, api_id, api_hash, _ = telegram.clients[0].arguments
    assert (session.value, api_id, api_hash) == ("custom-session", 987, "custom-hash")


async def test_numeric_private_chat_is_resolved_from_dialogs_with_fresh_string_session(telegram):
    module = adapter()
    telegram.failure = "uncached"
    telegram.dialogs = [SimpleNamespace(id=-1009876), telegram.entity]
    async with module.TelegramChannel({"chat": "-10012345"}) as channel:
        assert channel.key == "-10012345"
        await channel.send(b"{}")
    assert telegram.sent[0][0] is telegram.entity


async def test_person_or_bot_dialog_is_rejected_before_reading_or_sending(telegram):
    module = adapter()
    telegram.entity = SimpleNamespace(id=12345)
    with pytest.raises(module.TelegramTransportError, match="group|channel"):
        async with module.TelegramChannel({"chat": "@person"}) as channel:
            await channel.send(b"{}")
    assert telegram.sent == []
    assert not hasattr(telegram, "history")
    assert telegram.clients[0].disconnected


@pytest.mark.parametrize("chat", [None, "", " ", True, []])
async def test_missing_or_invalid_chat_cannot_connect(telegram, chat):
    module = adapter()
    with pytest.raises(module.TelegramTransportError, match="chat"):
        async with module.TelegramChannel({"chat": chat}):
            pytest.fail("invalid chat must not connect")
    assert telegram.clients == []


@pytest.mark.parametrize(
    "variable,value",
    [
        ("TELEGRAM_API_ID", ""),
        ("TELEGRAM_API_ID", "api-id-secret"),
        ("TELEGRAM_API_HASH", ""),
        ("TELEGRAM_SESSION_STRING", ""),
    ],
)
async def test_missing_or_invalid_credentials_do_not_open_a_client(telegram, monkeypatch, variable, value):
    module = adapter()
    monkeypatch.setenv(variable, value)
    with pytest.raises(module.TelegramTransportError) as error:
        async with module.TelegramChannel({"chat": "@blocks"}):
            pytest.fail("missing credentials must not connect")
    assert "api-id-secret" not in str(error.value)
    assert telegram.clients == []


async def test_unauthorized_session_is_disconnected_without_implicit_login(telegram):
    module = adapter()
    telegram.authorized = False
    with pytest.raises(module.TelegramTransportError, match="authorized"):
        async with module.TelegramChannel({"chat": "@blocks"}):
            pytest.fail("unauthorized session must not connect")
    assert telegram.clients[0].disconnected
    assert telegram.resolved == []


async def test_read_pages_all_messages_and_downloads_only_exact_protocol_document(telegram):
    module = adapter()
    telegram.messages = [
        message(9, FILENAME, 2, [b"old"]),
        message(10),
        message(11, "photo.jpg", 2, [b"no"]),
        message(12, "../" + FILENAME, 2, [b"no"]),
        message(13, FILENAME + ".zip", 2, [b"no"]),
        message(14, FILENAME, 2, [memoryview(b"{"), b"}"]),
    ]
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        result = await channel.read(after=9, limit=100)
    assert result == [
        {"id": 10, "data": None},
        {"id": 11, "data": None},
        {"id": 12, "data": None},
        {"id": 13, "data": None},
        {"id": 14, "data": b"{}"},
    ]
    entity, options = telegram.history
    assert entity is telegram.entity
    assert options == {"min_id": 9, "limit": 100, "reverse": True, "wait_time": 0}
    assert len(telegram.downloads) == 1
    assert telegram.downloads[0][2].closed


async def test_declared_oversize_protocol_document_is_not_downloaded(telegram):
    module = adapter()
    telegram.messages = [message(1, FILENAME, MAX_BYTES + 1, [b"never read"])]
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        assert await channel.read(0) == [{"id": 1, "data": None}]
    assert telegram.downloads == []


async def test_download_stops_before_retaining_bytes_above_limit(telegram):
    module = adapter()
    telegram.messages = [message(1, FILENAME, 1, [b"x" * MAX_BYTES, b"!", b"never read"])]
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        assert await channel.read(0) == [{"id": 1, "data": None}]
    stream = telegram.downloads[0][2]
    assert stream.read == 2
    assert stream.closed


async def test_exact_download_limit_is_accepted(telegram):
    module = adapter()
    data = b"x" * MAX_BYTES
    telegram.messages = [message(1, FILENAME, MAX_BYTES, [data])]
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        assert await channel.read(0) == [{"id": 1, "data": data}]


async def test_send_uploads_named_in_memory_document(telegram):
    module = adapter()
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        assert await channel.send(b'{"blocks": []}') == 77
    assert telegram.sent == [
        (
            telegram.entity,
            FILENAME,
            b'{"blocks": []}',
            {
                "force_document": True,
                "mime_type": "application/json",
                "parse_mode": None,
            },
        )
    ]


async def test_send_rejects_oversized_data_before_upload(telegram):
    module = adapter()
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        with pytest.raises(module.TelegramTransportError, match="8 MiB"):
            await channel.send(b"x" * (MAX_BYTES + 1))
    assert telegram.sent == []


@pytest.mark.parametrize("operation", ["connect", "resolve", "read", "send"])
async def test_errors_never_expose_credentials_or_chat_content(telegram, operation):
    module = adapter()
    telegram.failure = operation
    with pytest.raises(module.TelegramTransportError) as error:
        async with module.TelegramChannel({"chat": "@blocks"}) as channel:
            if operation == "read":
                await channel.read(0)
            elif operation == "send":
                await channel.send(b"{}")
    report = "".join(traceback.format_exception(error.value))
    assert all(secret not in report for secret in ("session-secret", "hash-secret", "private chat text"))
    assert telegram.clients[0].disconnected


async def test_read_timeout_is_bounded_and_sanitized(telegram, monkeypatch):
    module = adapter()
    monkeypatch.setattr(module, "OPERATION_TIMEOUT", 0.01)
    telegram.failure = "timeout"
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        with pytest.raises(module.TelegramTransportError, match="read"):
            await channel.read(0)


@pytest.mark.parametrize("failure", [RuntimeError("download failed"), None], ids=["error", "timeout"])
async def test_read_preserves_completed_prefix_and_resumes_failed_download(telegram, monkeypatch, failure):
    module = adapter()
    monkeypatch.setattr(module, "OPERATION_TIMEOUT", 0.01)
    first = message(1, FILENAME, 2, [b"{}"])
    second = message(2, FILENAME, 2, [failure])
    telegram.messages = [first, second, message(3)]
    async with module.TelegramChannel({"chat": "@blocks"}) as channel:
        completed = await channel.read(0)
        assert completed == [{"id": 1, "data": b"{}"}]
        assert telegram.downloads[-1][2].closed
        with pytest.raises(module.TelegramTransportError, match="read"):
            await channel.read(completed[-1]["id"])
        second.document.chunks = [b"{}"]
        assert await channel.read(completed[-1]["id"]) == [
            {"id": 2, "data": b"{}"},
            {"id": 3, "data": None},
        ]
        assert telegram.history[1]["min_id"] == 1


async def test_create_sync_group_creates_megagroup_then_exposes_history_without_invites(telegram):
    module = adapter()
    assert await module.create_sync_group({}, title="Worklife service") == {
        "chat": "-10012345",
        "title": "Worklife service",
    }
    assert len(telegram.requests) == 2
    request = telegram.requests[0]
    assert request.title == "Worklife service"
    assert request.megagroup is True
    assert request.about
    history_request = telegram.requests[1]
    assert history_request.channel is telegram.entity
    assert history_request.enabled is False
    assert telegram.sent == []
    assert telegram.resolved == []
    assert telegram.clients[0].disconnected


async def test_create_sync_group_sanitizes_errors(telegram):
    module = adapter()
    telegram.failure = "create"
    with pytest.raises(module.TelegramTransportError) as error:
        await module.create_sync_group({})
    report = "".join(traceback.format_exception(error.value))
    assert all(secret not in report for secret in ("session-secret", "hash-secret", "private chat text"))
    assert telegram.clients[0].disconnected


async def test_create_sync_group_history_failure_reports_partial_creation_without_secrets(telegram):
    module = adapter()
    telegram.failure = "history"
    with pytest.raises(module.TelegramTransportError, match="created.*history") as error:
        await module.create_sync_group({})
    assert len(telegram.requests) == 2
    report = "".join(traceback.format_exception(error.value))
    assert all(secret not in report for secret in ("session-secret", "hash-secret", "private chat text"))
    assert telegram.sent == []
    assert telegram.clients[0].disconnected


@pytest.mark.parametrize("title", ["", " ", "x" * 129, None])
async def test_create_sync_group_validates_title_before_connecting(telegram, title):
    module = adapter()
    with pytest.raises(module.TelegramTransportError, match="title"):
        await module.create_sync_group({}, title=title)
    assert telegram.clients == []
