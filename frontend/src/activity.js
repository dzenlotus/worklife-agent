import { t } from "./i18n.js";
import { activitySummary, list, scheduleResult } from "./model.js";

export function resultTarget(id, state) {
  if (!id) return null;
  for (const [bucket, kind] of [["jobs", "job"], ["cvs", "cv"], ["actions", "action"], ["resources", "resource"], ["schedule_runs", "schedule_run"]]) {
    if (list(state[bucket]).some((item) => item.id === id)) return { kind, id };
  }
  if (list(state.agent?.runs).some((item) => item.id === id)) return { kind: "run", id };
  return null;
}

export function callSummary(summary) {
  const jobs = /^Поиск завершён: вакансий — (\d+)$/.exec(summary);
  if (jobs) return t`Поиск завершён: вакансий — ${jobs[1]}`;
  const records = /^Данные сервиса прочитаны: записей — (\d+)$/.exec(summary);
  if (records) return t`Данные сервиса прочитаны: записей — ${records[1]}`;
  const messages = /^Получено новых сообщений: (\d+)(; есть ошибки обработки)?$/.exec(summary);
  if (messages) return t`Получено новых сообщений: ${messages[1]}` + (messages[2] ? t("; есть ошибки обработки") : "");
  return t(summary);
}

export function monitorActivity(state = {}) {
  const calls = list(state.tool_calls);
  if (calls.length) return calls.map((call) => ({
    ...call, summary: callSummary(call.summary), at: call.started_at, source: "mcp", target: resultTarget(call.related_id, state),
  })).sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));
  const events = list(state.activity).map((event, index) => {
    const summary = activitySummary(event, state);
    return { id: event.id || `event-${index}`, at: event.at, source: "event", tool: event.tool || t("Событие"), summary: summary.text, target: summary.target, status: event.status || null };
  });
  for (const run of list(state.schedule_runs)) {
    if (events.some((event) => event.target?.kind === "schedule_run" && event.target.id === run.id)) continue;
    events.push({ id: `schedule-${run.id}`, at: run.started_at, source: "schedule", tool: run.tool || t("Расписание"), summary: scheduleResult(run, state).text, status: run.status, target: { kind: "schedule_run", id: run.id } });
  }
  return events.sort((a, b) => (b.at || "").localeCompare(a.at || ""));
}
