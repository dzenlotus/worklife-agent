import test from "node:test";
import assert from "node:assert/strict";
import { monitorActivity, resultTarget } from "./activity.js";

test("a saved resource can be opened from its actual tool call without guessing a missing result", () => {
  const state = { resources: [{ id: "source" }], tool_calls: [{ id: "call", tool: "resource_save", related_id: "source" }] };
  assert.deepEqual(monitorActivity(state)[0].target, { kind: "resource", id: "source" });
  assert.equal(resultTarget("absent", state), null);
});

test("the monitor shows actual MCP calls first, preserving running/error states and missing results", () => {
  const state = { jobs: [{ id: "job" }], activity: [{ at: "2026-10-27T12:00:00Z", summary: "older event" }], tool_calls: [
    { id: "a", tool: "jobs_search", status: "failed", started_at: "2026-10-27T11:00:00Z", error: "Доступ запрещён", duration_seconds: 0.3 },
    { id: "b", tool: "job_save", status: "running", started_at: "2026-10-27T12:00:00Z", related_id: "job" },
  ] };
  const rows = monitorActivity(state);
  assert.deepEqual(rows.map((row) => row.id), ["b", "a"]);
  assert.equal(rows[0].status, "running");
  assert.equal(rows[0].finished_at, undefined);
  assert.deepEqual(rows[0].target, { kind: "job", id: "job" });
  assert.equal(rows[1].error, "Доступ запрещён");
  assert.equal(rows[1].target, null);
  assert.equal(rows[1].duration_seconds, 0.3);
});

test("legacy events remain events and scheduler-only history remains inspectable", () => {
  const rows = monitorActivity({ activity: [{ id: "e", at: "2026-10-27T10:00:00Z", summary: "Источник найден" }], schedule_runs: [{ id: "s", started_at: "2026-10-27T11:00:00Z", status: "failed", error: "Нужен доступ" }] });
  assert.equal(rows[0].source, "schedule");
  assert.equal(rows[0].status, "failed");
  assert.deepEqual(rows[0].target, { kind: "schedule_run", id: "s" });
  assert.equal(rows[1].source, "event");
  assert.equal(rows[1].status, null);
  assert.equal(rows[1].summary, "Источник найден");
  assert.deepEqual(monitorActivity(), []);
});
