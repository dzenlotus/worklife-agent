"""Automatic public block synchronization; signing and mining require explicit agent actions."""

import asyncio
import re
import sqlite3
import time

import httpx

from .blockchain import CONFIRMATIONS
from .federation import sync_chain_peer
from .storage import now


class BlockchainNetwork:
    LABELS = {
        "healthy": "Сеть подключена",
        "local_only": "Данные на этом устройстве",
        "offline": "Нет связи с узлами",
        "attention": "Нужна проверка данных",
    }

    def __init__(self, workspace, peers_callable, interval_seconds=300, telegram=None):
        self.workspace, self.peers_callable = workspace, peers_callable
        self.interval_seconds, self._last_attempt = interval_seconds, None
        self.telegram = dict(telegram or {})
        if set(self.telegram) - {"chat", "api_id_env", "api_hash_env", "session_env"}:
            raise ValueError("Telegram sync accepts chat and credential environment references only")
        try:
            saved = workspace.store.get("telegram_sync_config", "chat")
            self.telegram["chat"] = saved["chat"]
        except ValueError:
            pass
        try:
            self.meta = workspace.store.get("chain_network_state", "meta")
        except ValueError:
            self.meta = {}
        self._summary = {
            "status": "local_only",
            "label": self.LABELS["local_only"],
            "detail": "Для обмена блоками нужен адрес известного узла.",
            "employers": 0,
            "protected_copies": 1,
            "last_sync": self.meta.get("last_sync"),
            "auto": True,
            "pending": 0,
            "height": 0,
            "qualified": False,
            "reachable_peers": 0,
        }
        if self.telegram.get("chat"):
            self._summary["telegram"] = {"status": "configured", "chat": self.telegram["chat"]}
        self._save("local_only", self._summary["detail"])

    def connect_telegram(self, chat):
        """Select a service group; this grants subsequent sync permission to publish public blocks there."""
        chat = str(chat).strip()
        if chat.startswith("https://t.me/"):
            chat = "@" + chat.removeprefix("https://t.me/").rstrip("/")
        if not (re.fullmatch(r"-[1-9][0-9]*", chat) or re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", chat)):
            raise ValueError("Telegram requires a joined service group ID or @username")
        self.telegram["chat"] = chat
        self.workspace.store.put("telegram_sync_config", "chat", {"chat": chat})
        self._summary["telegram"] = {"status": "configured", "chat": chat}
        self.mark_dirty()
        return {"chat": chat, "transport": "telegram", "public_blocks_only": True}

    async def create_telegram_group(self, title="Worklife — общая база"):
        from .telegram_transport import create_sync_group

        group = await create_sync_group(self.telegram, title)
        return {**group, "synchronization": self.connect_telegram(group["chat"])}

    async def _sync_telegram(self):
        from .telegram_sync import sync_channel
        from .telegram_transport import TelegramChannel

        async with TelegramChannel(self.telegram) as channel:
            return await sync_channel(self.workspace, channel)

    def status(self):
        """Cached status: rendering does not contact peers or start expensive proof work."""
        return dict(self._summary)

    def _save(self, state, detail, reachable_peers=0):
        try:
            chain = self.workspace.blockchain
            chain_state, path = chain.status(), chain.canonical_blocks()
            confirmed = {
                event["event_id"]
                for block in path[: max(0, len(path) - CONFIRMATIONS + 1)]
                for event in block["events"]
            }
            proposals = {
                event["event_id"]
                for event in self.workspace.ledger.all()
                if event["author"] == self.workspace.ledger.author_id
            }
            local = {
                "height": chain_state["height"],
                "qualified": chain_state["qualified"],
                "employers": len(
                    {event["subject"] for event in chain.active_events() if event["kind"] == "employer"}
                ),
                "pending": len(proposals - confirmed),
                # Endpoint count is not evidence of independent storage or operators.
                "protected_copies": 1,
            }
        except (ValueError, TypeError, KeyError, OSError, sqlite3.DatabaseError):
            state, detail = "attention", "Не удалось проверить локальную историю блоков."
            local = {"height": 0, "qualified": False, "employers": 0, "pending": 0, "protected_copies": 0}
        self._summary = {
            **self._summary,
            **local,
            "status": state,
            "label": self.LABELS[state],
            "detail": detail,
            "last_sync": self.meta.get("last_sync"),
            "reachable_peers": reachable_peers,
        }
        try:
            self.workspace.store.put("chain_network_state", "meta", self.meta)
        except (OSError, sqlite3.DatabaseError):
            self._summary.update(status="attention", label=self.LABELS["attention"])
        return self.status()

    def mark_dirty(self):
        self._last_attempt = None
        return self._save(
            "local_only", "Локальные изменения сохранены. Обмен блоками начнётся автоматически."
        )

    def tick(self, force=False):
        # CLI and the running app share this selection through the existing local store.
        try:
            chat = self.workspace.store.get("telegram_sync_config", "chat")["chat"]
        except ValueError:
            chat = self.telegram.get("chat")
        except (OSError, sqlite3.DatabaseError):
            return self._save("attention", "Не удалось прочитать настройки группы. Повторим автоматически.")
        if chat != self.telegram.get("chat"):
            self.telegram["chat"] = chat
            self._summary["telegram"] = {"status": "configured", "chat": chat}
            self._last_attempt = None
        current = time.monotonic()
        interval = min(self.interval_seconds, 60) if self.telegram.get("chat") else self.interval_seconds
        if not force and self._last_attempt is not None and current - self._last_attempt < interval:
            return self.status()
        self._last_attempt = current
        try:
            configured = self.peers_callable()
            values = configured.values() if isinstance(configured, dict) else configured
            peers = {
                peer["url"]: peer for peer in values if isinstance(peer, dict) and peer.get("protocol") == 2
            }
            if not peers and not self.telegram.get("chat"):
                return self._save("local_only", "Для обмена блоками нужен адрес известного узла сети.")
            connected, invalid = 0, False
            if self.telegram.get("chat"):
                from .telegram_transport import TelegramTransportError

                try:
                    report = asyncio.run(self._sync_telegram())
                    self._summary["telegram"] = report
                    connected += 1
                    invalid = report["status"] != "healthy"
                except TelegramTransportError as exc:
                    self._summary["telegram"] = {"status": "offline", "error": str(exc)}
                except (ValueError, TypeError, KeyError, RecursionError, OSError):
                    self._summary["telegram"] = {"status": "attention", "error": "Telegram block sync failed"}
                    invalid = True
            for peer in peers.values():
                try:
                    sync_chain_peer(self.workspace, peer)
                    connected += 1
                except httpx.HTTPError:
                    continue
                except (ValueError, TypeError, KeyError, RecursionError):
                    invalid = True
            if connected:
                self.meta["last_sync"] = now()
            if invalid:
                return self._save(
                    "attention", "Не все пакеты блоков удалось проверить или восстановить.", connected
                )
            if connected:
                return self._save(
                    "healthy",
                    "Блоки проверены и синхронизированы. Подтверждение сети не доказывает истинность сведений.",
                    connected,
                )
            return self._save("offline", "Локальная история доступна. Повторим соединение автоматически.")
        except (ValueError, TypeError, KeyError, OSError, sqlite3.DatabaseError):
            return self._save("attention", "Не удалось завершить обмен блоками. Повторим автоматически.")
        finally:
            # A slow peer must not make every mining cycle immediately retry synchronization.
            self._last_attempt = time.monotonic()
