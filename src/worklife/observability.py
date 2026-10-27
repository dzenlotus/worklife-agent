"""Private outcome metadata for public MCP tool calls, without copying their content."""

import inspect
import time
from functools import wraps

from mcp.server.fastmcp import FastMCP

from .storage import now
from .workspace import uid

QUIET_TOOLS = {
    "agent_brief",
    "records_list",
    "statistics_report",
    "agent_status",
    "connectors_list",
    "knowledge_query",
    "knowledge_verify",
    "knowledge_export",
    "employer_block_status",
    "activity_record",
    "browser_inspect",
    "experiment_report",
    "agency_brief",
    "conversation_list",
    "recruiter_start",
    "recruiter_skill",
}

SUMMARIES = {
    "profile_save": "Профиль обновлён",
    "research_note": "Наблюдение и следующий шаг сохранены",
    "cv_create": "Вариант CV подготовлен",
    "cv_export": "Файл CV создан",
    "cv_localize": "Перевод CV сохранён",
    "job_save": "Вакансия сохранена",
    "job_assess": "Вакансия проверена по условиям поиска",
    "application_update": "Этап отклика сохранён",
    "experiment_create": "Эксперимент создан",
    "experiment_assign": "Вариант CV назначен для эксперимента",
    "experiment_outcome": "Результат эксперимента сохранён",
    "task_add": "Следующий шаг сохранён",
    "task_complete": "Задача отмечена выполненной",
    "connector_configure": "Подключение сервиса сохранено",
    "browser_open": "Страница открыта",
    "browser_prepare": "Подготовка страницы выполнена",
    "browser_screenshot": "Снимок страницы сохранён",
    "knowledge_publish": "Предложение записи сохранено; требуется подтверждение цепочкой",
    "knowledge_import": "Записи работодателей проверены и импортированы",
    "author_trust": "Локальное доверие к источнику обновлено",
    "peer_register": "Адрес копии общей базы сохранён",
    "peer_sync": "Обмен с копией общей базы завершён",
    "backup_create": "Локальная резервная копия создана",
    "blockchain_qualify": "Месячная квалификация агента пройдена",
    "blockchain_mine": "Проверка работы для блока завершена",
    "blockchain_connect": "Узел новой сети подключён",
    "blockchain_sync": "Обмен блоками завершён",
    "credential_create": "Доступ сохранён в системном хранилище",
    "browser_fill_credential": "Сохранённый доступ подставлен в страницу",
    "resource_save": "Ресурс поиска сохранён",
    "schedule_save": "Расписание сохранено",
    "schedule_toggle": "Состояние расписания обновлено",
    "employer_block": "Исключение работодателя обновлено",
    "repository_analyze": "Репозиторий изучен, наблюдения сохранены",
    "strength_save": "Сильная сторона сохранена с доказательствами",
    "tactic_save": "Тактика поиска сохранена",
    "platform_save": "Площадка поиска сохранена",
    "account_save": "Состояние аккаунта сохранено",
    "agent_cancel": "Запрошена остановка автономного цикла",
    "market_snapshot": "Сохранена рыночная выборка",
    "market_collect": "Сбор рыночной выборки завершён",
    "market_report": "Подготовлен отчёт по рыночной выборке",
    "recommendations_report": "Подготовлена персональная подборка",
    "recommendation_save": "Сохранён анализ вакансии и резюме",
    "cv_match": "Сопоставлены варианты резюме",
    "resume_import": "Резюме импортировано",
    "pipeline_update": "Обновлён этап поиска и следующий шаг",
    "conversation_record": "Сообщение сохранено в истории",
    "conversation_update": "Связь и отметка сообщения обновлены",
    "inbox_sync": "Входящие сообщения синхронизированы",
    "interview_brief": "Подготовлены материалы к интервью",
    "interview_save": "Интервью сохранено",
    "offer_save": "Условия оффера сохранены",
    "offer_compare": "Условия офферов сопоставлены",
    "search_review": "Подготовлен обзор результатов поиска",
}

ACTION_STATES = {
    "draft": "Черновик внешнего действия сохранён",
    "approved": "Внешнее действие разрешено",
    "sent": "Получен результат внешнего действия",
    "uncertain": "Результат внешнего действия не подтверждён — нужна проверка",
    "failed": "Зафиксирована ошибка внешнего действия",
    "cancelled": "Внешнее действие отменено",
    "sending": "Внешнее действие ещё выполняется",
}

RESULT_TOOLS = {
    "job_save",
    "cv_create",
    "cv_localize",
    "resource_save",
    "schedule_run",
    "agent_run",
    "action_draft",
    "action_approve",
    "action_execute",
}


def outcome_summary(tool, result):
    if tool == "market_collect" and isinstance(result, dict):
        return (
            "Выборка собрана с ограничениями источников"
            if result.get("errors")
            else "Рыночная выборка собрана"
        )
    if tool == "market_report" and isinstance(result, dict) and result.get("status") == "empty":
        return "Рыночной выборки пока нет"
    if (
        tool == "recommendations_report"
        and isinstance(result, dict)
        and result.get("status") == "needs_profile"
    ):
        return "Для персонального подбора нужно уточнить профиль"
    if tool == "inbox_sync" and isinstance(result, dict):
        return f"Получено новых сообщений: {result.get('imported', 0)}" + (
            "; есть ошибки обработки" if result.get("errors") else ""
        )
    if tool == "jobs_search" and isinstance(result, list):
        return f"Поиск завершён: вакансий — {len(result)}"
    if tool == "connector_read":
        return (
            f"Данные сервиса прочитаны: записей — {len(result)}"
            if isinstance(result, list)
            else "Данные сервиса прочитаны"
        )
    if tool.startswith("action_") and isinstance(result, dict):
        return ACTION_STATES.get(result.get("status"), "Состояние внешнего действия проверено")
    if tool == "schedule_run" and isinstance(result, dict):
        return (
            "Запуск расписания завершился ошибкой"
            if result.get("status") == "failed"
            else "Запуск расписания завершён"
        )
    if tool == "agent_run":
        return "Автономный цикл поставлен в очередь"
    return SUMMARIES.get(tool, "Операция выполнена")


class ObservedMCP(FastMCP):
    def __init__(self, workspace, *args, allowed_tools=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._observation_store = workspace.store
        self._allowed_tools = frozenset(allowed_tools) if allowed_tools is not None else None

    def tool(self, name=None, **kwargs):
        register = super().tool(name=name, **kwargs)

        def decorate(function):
            tool_name = name or function.__name__
            if self._allowed_tools is not None and tool_name not in self._allowed_tools:
                return function
            if tool_name in QUIET_TOOLS:
                return register(function)

            @wraps(function)
            async def observed(*args, **arguments):
                started = time.monotonic()
                record = {
                    "id": uid(),
                    "tool": tool_name,
                    "status": "running",
                    "started_at": now(),
                    "finished_at": None,
                    "duration_seconds": 0.0,
                    "summary": "Выполняется операция",
                    "error": None,
                }
                self._observation_store.put("tool_call", record["id"], record)
                try:
                    result = function(*args, **arguments)
                    if inspect.isawaitable(result):
                        result = await result
                except BaseException as exc:
                    record.update(
                        status="failed",
                        summary="Операция не завершена",
                        error=f"{type(exc).__name__}: проверьте параметры и доступ к сервису",
                    )
                    raise
                else:
                    record.update(status="completed", summary=outcome_summary(tool_name, result))
                    if tool_name == "resume_import" and isinstance(result, dict):
                        record["related_id"] = result.get("cv", {}).get("id")
                    if tool_name in {
                        "pipeline_update",
                        "conversation_record",
                        "conversation_update",
                        "interview_save",
                        "offer_save",
                        "recommendation_save",
                    } and isinstance(result, dict):
                        record["related_id"] = result.get("job_id")
                    if tool_name in RESULT_TOOLS and isinstance(result, dict):
                        if isinstance(result.get("id"), str):
                            record["related_id"] = result["id"]
                    return result
                finally:
                    record.update(finished_at=now(), duration_seconds=round(time.monotonic() - started, 6))
                    self._observation_store.put("tool_call", record["id"], record)

            return register(observed)

        return decorate
