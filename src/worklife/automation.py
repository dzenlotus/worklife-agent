"""Set up recurring checks using the existing deterministic schedule executor."""

import hashlib
import math
import os
from copy import deepcopy

from .storage import canonical, now

OWNER = "automation:checks"
DEFAULTS = {
    "enabled": False,
    "interval_minutes": 60,
    "check_inbox": True,
    "refresh_search": True,
    "review": True,
    "agent_goal": "",
}
CURSORS = {"after_uid", "uidvalidity", "offset", "page", "cursor"}
COVERED_NOTE = "Некоторые проверки уже работают по отдельным расписаниям. Их частота и пауза настраиваются в списке поручений."


def _identity(tool, arguments):
    result = deepcopy(arguments)
    if tool in {"inbox_sync", "jobs_search"}:
        parameters = result.get("parameters")
        if parameters is None:
            parameters = {}
        result["parameters"] = parameters
        if not isinstance(parameters, dict):
            return None
        if tool == "inbox_sync":
            result.setdefault("operation", "inbox")
            result["parameters"] = {key: value for key, value in parameters.items() if key not in CURSORS}
        else:
            result.setdefault("query", "")
            parameter_language = parameters.pop("language", None)
            language = result.pop("language", None)
            if language is None:
                language = parameter_language
            if language is not None:
                result["language"] = language
    return canonical([tool, result])


class Automation:
    def __init__(self, server, workspace, operations, connectors, runtime):
        self.server, self.store = server, workspace.store
        self.operations, self.connectors, self.runtime = operations, connectors, runtime

    def _config(self):
        try:
            return {**DEFAULTS, **self.store.get("automation", "checks")}
        except ValueError:
            return dict(DEFAULTS)

    def _managed(self):
        return [row for row in self.store.list("schedule") if row.get("managed_by") == OWNER]

    def _access(self, name, inbox=False):
        config = self.connectors.config(name)
        if config["type"] == "email":
            if not config.get("imap_host") or any(
                not os.getenv(config.get(key + "_env", "")) for key in ("username", "password")
            ):
                raise ValueError("нужны IMAP-адрес и доступ к почте")
        elif inbox:
            references = [
                value for key, value in config.items() if key.endswith("_env") and key != "headers_env"
            ]
            references.extend(config.get("headers_env", {}).values())
            if any(not os.getenv(reference) for reference in references):
                raise ValueError("не настроены переменные доступа")
        return config

    def _plan(self, config):
        planned, warnings = {}, []
        manual = [row for row in self.store.list("schedule") if row.get("managed_by") != OWNER]

        def add(tool, arguments, name):
            arguments = deepcopy(arguments)
            identity = _identity(tool, arguments)
            if identity is None:
                warnings.append("Сохранённые параметры проверки требуют исправления.")
                return
            key = OWNER + ":" + hashlib.sha256(identity).hexdigest()[:20]
            covered_by = None
            for row in manual:
                if not row["enabled"]:
                    continue
                candidates = (
                    [row["arguments"]]
                    if row["tool"] == tool
                    else row["arguments"].get("searches", [])
                    if tool == "jobs_search" and row["tool"] == "market_collect"
                    else []
                )
                if not isinstance(candidates, list):
                    continue
                if any(
                    isinstance(candidate, dict) and _identity(tool, candidate) == identity
                    for candidate in candidates
                ):
                    covered_by = row["id"]
                    break
            planned[key] = {
                "id": key,
                "name": name,
                "tool": tool,
                "arguments": arguments,
                "covered_by": covered_by,
            }

        if config["check_inbox"]:
            explicit = [row for row in manual if row["tool"] == "inbox_sync"]
            covered = set()
            for row in explicit:
                arguments = row["arguments"]
                connector = arguments.get("connector", "")
                covered.add(connector)
                try:
                    self._access(connector, inbox=True)
                    add("inbox_sync", arguments, "Проверка входящих: " + connector)
                except ValueError as exc:
                    warnings.append(f"Входящие {connector}: {exc}.")
            for connector in self.connectors.capabilities():
                name = connector["name"]
                if connector["type"] != "email" or name in covered:
                    continue
                try:
                    self._access(name, inbox=True)
                    add(
                        "inbox_sync",
                        {"connector": name, "parameters": {"folder": "INBOX"}},
                        "Проверка входящих: " + name,
                    )
                except ValueError as exc:
                    warnings.append(f"Входящие {name}: {exc}.")
            if not any(row["tool"] == "inbox_sync" for row in planned.values()):
                warnings.append(
                    "Для проверки входящих подключите почту или поручите агенту настроить канал переписки."
                )

        if config["refresh_search"]:
            searches = []
            for row in manual:
                if row["tool"] == "jobs_search":
                    searches.append(row["arguments"])
                elif row["tool"] == "market_collect":
                    candidates = row["arguments"].get("searches", [])
                    if isinstance(candidates, list):
                        searches.extend(candidates)
                    else:
                        warnings.append("Сохранённые параметры проверки требуют исправления.")
            snapshots = sorted(
                self.store.list("market_snapshot"), key=lambda row: row["created_at"], reverse=True
            )
            for source in snapshots[0].get("sources", []) if snapshots else []:
                if not isinstance(source, dict) or source.get("status") != "collected":
                    continue
                if source.get("parameters_redacted") or not isinstance(source.get("parameters"), dict):
                    warnings.append(
                        "Один из сохранённых поисков пропущен: его параметры отсутствуют или скрыты."
                    )
                    continue
                searches.append(
                    {
                        key: source[key]
                        for key in ("connector", "query", "parameters", "language")
                        if key in source
                    }
                )
            for search in searches:
                if not isinstance(search, dict) or not isinstance(search.get("connector"), str):
                    warnings.append("Сохранённый поиск пропущен: источник не указан.")
                    continue
                connector = search["connector"]
                if (
                    search.get("parameters") is not None
                    and not isinstance(search.get("parameters"), dict)
                    or not isinstance(search.get("query", ""), str)
                ):
                    warnings.append(f"Поиск {connector}: проверьте сохранённые параметры.")
                    continue
                try:
                    source = self._access(connector)
                    if source["type"] not in {"hh", "greenhouse", "lever"}:
                        raise ValueError("источник не поддерживает jobs_search")
                    arguments = {
                        "connector": connector,
                        "query": search.get("query", ""),
                        "parameters": search.get("parameters") or {},
                    }
                    if search.get("language") is not None:
                        arguments["language"] = search["language"]
                    add("jobs_search", arguments, "Обновление поиска: " + (arguments["query"] or connector))
                except ValueError as exc:
                    warnings.append(f"Поиск {connector}: {exc}.")
            if not any(row["tool"] == "jobs_search" for row in planned.values()):
                warnings.append(
                    "Для обновления вакансий сначала выполните поиск с явными запросами и сохраните выборку или расписание поиска."
                )

        if config["review"]:
            add("search_review", {}, "Обзор результатов поиска")
            add("recommendations_report", {}, "Проверка вакансий по условиям")
        if config["agent_goal"]:
            if self.server.worklife_profile == "recruiter":
                warnings.append("Профиль Recruiter выполняет проверки без встроенного цикла агента.")
            elif not self.runtime.status()["configured"]:
                warnings.append("Для сохранённого поручения подключите модель встроенного исполнителя.")
            else:
                add("agent_cycle", {"goal": config["agent_goal"]}, "Поручение встроенному агенту")
        if config["enabled"] and any(row["covered_by"] for row in planned.values()):
            warnings.append(COVERED_NOTE)
        return planned, list(dict.fromkeys(warnings))

    def status(self):
        config = self._config()
        planned, warnings = self._plan(config)
        needs_setup = any(warning != COVERED_NOTE for warning in warnings)
        return {
            "config": config,
            "schedules": self._managed(),
            "warnings": warnings,
            "ready": bool(planned) and not needs_setup,
            "readiness": "needs_setup" if not planned else "partial" if needs_setup else "ready",
            "executor_required": True,
            "executor_note": "Регулярные проверки выполняются, пока запущено локальное приложение Worklife или worker. Новые рассуждения требуют действующего агента.",
            "sources": {
                "inbox": sum(row["tool"] == "inbox_sync" for row in planned.values()),
                "search": sum(row["tool"] == "jobs_search" for row in planned.values()),
            },
        }

    def configure(
        self, enabled, interval_minutes=60, check_inbox=True, refresh_search=True, review=True, agent_goal=""
    ):
        if any(type(value) is not bool for value in (enabled, check_inbox, refresh_search, review)):
            raise ValueError("Параметры автоматических проверок должны быть логическими значениями")
        if (
            isinstance(interval_minutes, bool)
            or not isinstance(interval_minutes, (int, float))
            or not math.isfinite(interval_minutes)
            or interval_minutes <= 0
        ):
            raise ValueError("Интервал проверок должен быть положительным конечным числом")
        if not isinstance(agent_goal, str) or len(agent_goal) > 16000:
            raise ValueError("Поручение агента должно быть текстом длиной до 16000 символов")
        agent_goal = agent_goal.strip()
        if (
            enabled
            and agent_goal
            and (self.server.worklife_profile == "recruiter" or not self.runtime.status()["configured"])
        ):
            raise ValueError(
                "Поручение по расписанию требует полного профиля MCP и настроенной модели исполнителя"
            )
        config = dict(
            enabled=enabled,
            interval_minutes=interval_minutes,
            check_inbox=check_inbox,
            refresh_search=refresh_search,
            review=review,
            agent_goal=agent_goal,
        )
        self._apply(config)
        self.store.put("automation", "checks", config)
        return self.status()

    def _apply(self, config):
        enabled, interval_minutes = config["enabled"], config["interval_minutes"]
        planned, _ = self._plan(config)
        previous = {row["id"]: row for row in self._managed()}
        for key, row in planned.items():
            old = previous.get(key)
            arguments = row["arguments"]
            schedule_enabled = enabled and not row["covered_by"]
            if old and row["tool"] == "inbox_sync":
                arguments["parameters"] = {
                    **(arguments.get("parameters") or {}),
                    **{
                        name: value
                        for name, value in (old["arguments"].get("parameters") or {}).items()
                        if name in CURSORS
                    },
                }
            if old:
                if any(
                    old.get(name) != value
                    for name, value in {
                        "tool": row["tool"],
                        "arguments": arguments,
                        "interval_minutes": interval_minutes,
                        "enabled": schedule_enabled,
                        "covered_by": row["covered_by"],
                    }.items()
                ):
                    updated = self.operations.schedule_save(
                        row["name"], row["tool"], arguments, interval_minutes, schedule_enabled, key
                    )
                    self.store.put("schedule", key, {**updated, "covered_by": row["covered_by"]})
            else:
                self.store.put(
                    "schedule",
                    key,
                    {
                        **row,
                        "managed_by": OWNER,
                        "enabled": schedule_enabled,
                        "interval_minutes": interval_minutes,
                        "next_run_at": now(),
                        "last_run_at": None,
                        "last_status": None,
                        "last_error": None,
                    },
                )
        for key, row in previous.items():
            if key not in planned and row["enabled"]:
                self.operations.schedule_toggle(key, False)

    def refresh(self):
        """Materialize newly available sources in the existing app/worker loop."""
        config = self._config()
        if config["enabled"]:
            self._apply(config)

    def run(self):
        config = self._config()
        self._apply(config)
        planned, _ = self._plan(config)
        runs = [self.operations.schedule_run(key) for key in planned]
        status = self.status()
        return {
            **status,
            "status": "needs_setup"
            if not runs
            else "failed"
            if all(row["status"] == "failed" for row in runs)
            else "partial"
            if status["warnings"] or any(row["status"] != "success" for row in runs)
            else "success",
            "runs": runs,
        }
