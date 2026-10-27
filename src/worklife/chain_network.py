"""Automatic public block synchronization; signing and mining require explicit agent actions."""

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

    def __init__(self, workspace, peers_callable, interval_seconds=300):
        self.workspace, self.peers_callable = workspace, peers_callable
        self.interval_seconds, self._last_attempt = interval_seconds, None
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
        self._save("local_only", self._summary["detail"])

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
        current = time.monotonic()
        if (
            not force
            and self._last_attempt is not None
            and current - self._last_attempt < self.interval_seconds
        ):
            return self.status()
        self._last_attempt = current
        try:
            configured = self.peers_callable()
            values = configured.values() if isinstance(configured, dict) else configured
            peers = {
                peer["url"]: peer for peer in values if isinstance(peer, dict) and peer.get("protocol") == 2
            }
            if not peers:
                return self._save("local_only", "Для обмена блоками нужен адрес известного узла сети.")
            connected, invalid = 0, False
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
                return self._save("attention", "Узел вернул неподходящие блоки или правила сети.", connected)
            if connected:
                return self._save(
                    "healthy",
                    "Блоки проверены и синхронизированы. Подтверждение сети не доказывает истинность сведений.",
                    connected,
                )
            return self._save("offline", "Локальная история доступна. Повторим соединение автоматически.")
        except (ValueError, TypeError, KeyError, OSError, sqlite3.DatabaseError):
            return self._save("attention", "Не удалось завершить обмен блоками. Повторим автоматически.")
