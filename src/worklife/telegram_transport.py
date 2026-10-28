"""Telegram documents carrying public Worklife block batches."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from io import BytesIO

FILENAME = "worklife-blocks-v1.json"
MAX_BYTES = 8 * 1024 * 1024
OPERATION_TIMEOUT = 30


class TelegramTransportError(RuntimeError):
    """A reportable error containing no Telegram response or credential data."""


def _credential(settings, field, default):
    variable = settings.get(field, default)
    if not isinstance(variable, str) or not variable:
        raise TelegramTransportError(f"Telegram {field} must reference an environment variable")
    value = os.environ.get(variable, "")
    if not value:
        raise TelegramTransportError(f"Telegram {field} environment variable is not configured")
    return value


@asynccontextmanager
async def _connected(settings):
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        raise TelegramTransportError("Install the telegram extra to use Telegram sync") from None

    raw_api_id = _credential(settings, "api_id_env", "TELEGRAM_API_ID")
    if not raw_api_id.isascii() or not raw_api_id.isdecimal() or int(raw_api_id) <= 0:
        raise TelegramTransportError("Telegram api_id_env must contain a positive numeric API ID")
    api_hash = _credential(settings, "api_hash_env", "TELEGRAM_API_HASH")
    session = _credential(settings, "session_env", "TELEGRAM_SESSION_STRING")
    client = None
    try:
        try:
            client = TelegramClient(
                StringSession(session),
                int(raw_api_id),
                api_hash,
                timeout=OPERATION_TIMEOUT,
                flood_sleep_threshold=0,
                request_retries=0,
                connection_retries=0,
                receive_updates=False,
            )
            async with asyncio.timeout(OPERATION_TIMEOUT):
                await client.connect()
                if not await client.is_user_authorized():
                    raise TelegramTransportError(
                        "Telegram session is not authorized; authorize it separately"
                    )
        except TelegramTransportError:
            raise
        except Exception:
            raise TelegramTransportError("Telegram connection failed") from None
        yield client
    finally:
        if client is not None:
            with suppress(Exception):
                async with asyncio.timeout(OPERATION_TIMEOUT):
                    await client.disconnect()


class TelegramChannel:
    def __init__(self, settings):
        self.settings = dict(settings)
        chat = self.settings.get("chat")
        if isinstance(chat, str):
            chat = chat.strip()
            if chat.lstrip("-").isascii() and chat.lstrip("-").isdecimal():
                chat = int(chat)
        if isinstance(chat, bool) or not isinstance(chat, (str, int)) or not chat:
            raise TelegramTransportError("Telegram chat must be a username or numeric ID")
        self.chat = chat
        self.key = ""
        self._client = None
        self._entity = None
        self._connection = None

    async def __aenter__(self):
        self._connection = _connected(self.settings)
        self._client = await self._connection.__aenter__()
        try:
            from telethon import utils

            async with asyncio.timeout(OPERATION_TIMEOUT):
                try:
                    self._entity = await self._client.get_entity(self.chat)
                except ValueError:
                    if not isinstance(self.chat, int):
                        raise
                    # StringSession does not retain the private channel's access hash.
                    async for dialog in self._client.iter_dialogs():
                        if utils.get_peer_id(dialog.entity) == self.chat:
                            self._entity = dialog.entity
                            break
                    if self._entity is None:
                        raise TelegramTransportError("Telegram chat was not found in account dialogs")
                self.key = str(utils.get_peer_id(self._entity))
                if int(self.key) >= 0:
                    raise TelegramTransportError("Telegram sync requires a group or channel")
        except Exception as error:
            await self.__aexit__(None, None, None)
            if isinstance(error, TelegramTransportError):
                raise error from None
            raise TelegramTransportError("Telegram chat resolution failed") from None
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._connection is not None:
                await self._connection.__aexit__(exc_type, exc, tb)
        finally:
            self._connection = self._client = self._entity = None

    async def _download(self, message):
        document = message.document
        if document is None or message.file.name != FILENAME:
            return None
        size = document.size
        if not isinstance(size, int) or not 0 <= size <= MAX_BYTES:
            return None
        data = bytearray()
        stream = self._client.iter_download(document, request_size=64 * 1024)
        try:
            async for chunk in stream:
                if len(data) + len(chunk) > MAX_BYTES:
                    return None
                data.extend(chunk)
        finally:
            await stream.close()
        return bytes(data)

    async def read(self, after: int, limit: int = 100) -> list[dict]:
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise TelegramTransportError(
                "Telegram read requires a nonnegative cursor and limit from 1 to 100"
            )
        if self._client is None:
            raise TelegramTransportError("Telegram channel is not connected")
        result = []
        try:
            async with asyncio.timeout(OPERATION_TIMEOUT):
                async for message in self._client.iter_messages(
                    self._entity,
                    min_id=after,
                    limit=limit,
                    reverse=True,
                    wait_time=0,
                ):
                    result.append({"id": message.id, "data": await self._download(message)})
                return result
        except Exception:
            if result:
                return result
            raise TelegramTransportError("Telegram read failed; retry in the next sync cycle") from None

    async def send(self, data: bytes) -> int:
        if not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise TelegramTransportError("Telegram batch must be bytes no larger than 8 MiB")
        if self._client is None:
            raise TelegramTransportError("Telegram channel is not connected")
        try:
            with BytesIO(data) as document:
                document.name = FILENAME
                async with asyncio.timeout(OPERATION_TIMEOUT):
                    message = await self._client.send_file(
                        self._entity,
                        document,
                        force_document=True,
                        mime_type="application/json",
                        parse_mode=None,
                    )
                    return message.id
        except Exception:
            raise TelegramTransportError("Telegram send failed; retry in the next sync cycle") from None


async def create_sync_group(settings, title="Worklife — общая база") -> dict:
    """Create a private service group with visible history, without invites or block uploads."""
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 128:
        raise TelegramTransportError("Telegram group title must contain 1 to 128 characters")
    title = title.strip()
    async with _connected(settings) as client:
        created = None
        try:
            from telethon import functions, utils

            async with asyncio.timeout(OPERATION_TIMEOUT):
                result = await client(
                    functions.channels.CreateChannelRequest(
                        title=title,
                        about="Служебная группа для обмена публичными блоками Worklife.",
                        megagroup=True,
                    )
                )
                created = result.chats[0]
                await client(functions.channels.TogglePreHistoryHiddenRequest(channel=created, enabled=False))
                return {"chat": str(utils.get_peer_id(created)), "title": title}
        except Exception:
            if created is not None:
                raise TelegramTransportError(
                    "Telegram service group was created, but making history visible failed"
                ) from None
            raise TelegramTransportError("Telegram service group creation failed") from None
