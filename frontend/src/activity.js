import { activitySummary, list, scheduleResult } from "./model.js";

export function resultTarget(id, state) {
  if (!id) return null;
  for (const [bucket, kind] of [["jobs", "job"], ["cvs", "cv"], ["actions", "action"], ["resources", "resource"], ["schedule_runs", "schedule_run"]]) {
    if (list(state[bucket]).some((item) => item.id === id)) return { kind, id };
  }
  if (list(state.agent?.runs).some((item) => item.id === id)) return { kind: "run", id };
  return null;
}

export function monitorActivity(state = {}) {
  const calls = list(state.tool_calls);
  if (calls.length) return calls.map((call) => ({
    ...call, at: call.started_at, source: "mcp", target: resultTarget(call.related_id, state),
  })).sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""));
  const events = list(state.activity).map((event, index) => {
    const summary = activitySummary(event, state);
    return { id: event.id || `event-${index}`, at: event.at, source: "event", tool: event.tool || "Событие", summary: summary.text, target: summary.target, status: event.status || null };
  });
  for (const run of list(state.schedule_runs)) {
    if (events.some((event) => event.target?.kind === "schedule_run" && event.target.id === run.id)) continue;
    events.push({ id: `schedule-${run.id}`, at: run.started_at, source: "schedule", tool: run.tool || "Расписание", summary: scheduleResult(run, state).text, status: run.status, target: { kind: "schedule_run", id: run.id } });
  }
  return events.sort((a, b) => (b.at || "").localeCompare(a.at || ""));
}
