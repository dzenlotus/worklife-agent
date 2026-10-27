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
    "knowledge_publish": "Запись общей базы опубликована",
    "knowledge_import": "Записи работодателей проверены и импортированы",
    "author_trust": "Локальное доверие к источнику обновлено",
    "peer_register": "Адрес копии общей базы сохранён",
    "peer_sync": "Обмен с копией общей базы завершён",
    "backup_create": "Локальная резервная копия создана",
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
    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._observation_store = workspace.store

    def tool(self, name=None, **kwargs):
        register = super().tool(name=name, **kwargs)

        def decorate(function):
            tool_name = name or function.__name__
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
                    if tool_name in RESULT_TOOLS and isinstance(result, dict):
                        if isinstance(result.get("id"), str):
                            record["related_id"] = result["id"]
                    return result
                finally:
                    record.update(finished_at=now(), duration_seconds=round(time.monotonic() - started, 6))
                    self._observation_store.put("tool_call", record["id"], record)

            return register(observed)

        return decorate
