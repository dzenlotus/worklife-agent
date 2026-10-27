import test from "node:test";
import assert from "node:assert/strict";
import {
  statistics,
  filterJobs,
  employerGroups,
  exchangeSummary,
  safeURL,
  observationBasis,
  scheduleResult,
  activitySummary,
  usageMetric,
  currentConditions,
  goalExcerpt,
} from "./model.js";
import { composeGoal } from "./goals.js";
test("search statistics retain actual earlier replies after rejection without counting a saved job as sent", () => {
  const state = {
    jobs: [{ id: "j1" }, { id: "j2" }],
    applications: [
      {
        job_id: "j1",
        stage: "rejected",
        history: [
          { stage: "applied" },
          { stage: "reply" },
          { stage: "reply" },
          { stage: "rejected" },
        ],
      },
      { job_id: "j2", stage: "saved", history: [] },
    ],
  };
  assert.deepEqual(statistics(state), { jobs: 2, applied: 1, replies: 1 });
  assert.deepEqual(
    filterJobs(state, "active").map((j) => j.id),
    ["j2"],
  );
});
test("employer list groups company observations without treating authors as organizations", () => {
  const groups = employerGroups([
    {
      kind: "employer",
      author: "key-a",
      subject: "acme.example",
      payload: { name: "Acme", claim: "remote" },
    },
    {
      kind: "employer",
      author: "key-b",
      subject: "acme.example",
      payload: { claim: "two stages" },
    },
    { kind: "retraction", subject: "other.example", payload: {} },
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].domain, "acme.example");
  assert.equal(groups[0].observations.length, 2);
});
test("automatic network status never fabricates protected copies or successful synchronization", () => {
  assert.equal(exchangeSummary({}).protected_copies, undefined);
  assert.equal(
    exchangeSummary({
      summary: {
        status: "ready",
        label: "Готово",
        protected_copies: 3,
        auto: true,
      },
    }).protected_copies,
    3,
  );
});
test("external source links accept only HTTP(S)", () => {
  assert.equal(safeURL("javascript:alert(1)"), null);
  assert.equal(safeURL("file:///private/cv"), null);
  assert.equal(safeURL("https://example.org/job"), "https://example.org/job");
});

test("network attention preserves stored facts and explains automatic retry without inventing success", () => {
  const result = exchangeSummary({ summary: { status: "attention", invalid: 1, rollback: true, auto: true, last_sync: "2026-10-27T10:00:00Z" } });
  assert.equal(result.label, "Изменённая запись отклонена");
  assert.match(result.detail, /повторим проверку автоматически/);
  assert.equal(result.last_sync, "2026-10-27T10:00:00Z");
  assert.equal(result.protected_copies, undefined);
  assert.match(observationBasis({ trust: "confirmed_author", payload: { evidence_kind: "advertised" } }).label, /По объявлению/);
  assert.match(observationBasis({ trust: "confirmed_author", payload: {} }).verification, /Независимая проверка не проводилась/);
});

test("actual reminder results and failures are readable without exposing identifiers", () => {
  const state = { schedules: [{ id: "s", name: "Утренний обзор" }], schedule_runs: [{ id: "r", schedule_id: "s", started_at: "2026-10-27T10:00:00Z", status: "success", tool: "reminder", result: { title: "Посмотреть вакансии" } }] };
  assert.equal(scheduleResult(state.schedule_runs[0], state).text, "Создано напоминание: «Посмотреть вакансии».");
  const event = activitySummary({ related_id: "s", at: "2026-10-27T10:00:01Z", summary: "result changed" }, state);
  assert.match(event.text, /Утренний обзор: Создано напоминание/);
  assert.deepEqual(event.target, { kind: "schedule_run", id: "r" });
  assert.match(scheduleResult({ status: "failed", error: "Нужен доступ" }).text, /Нужен доступ/);
  assert.match(scheduleResult({ tool: "agent_cycle", status: "success" }).text, /передано агенту/);
  assert.equal(usageMetric("cost_usd", 0.02)[0], "Стоимость, USD");
  assert.equal(usageMetric("duration_seconds", 0.1234567)[1], "0,12");
});

test("the goal shows saved preferences followed by remote and comparable salary constraints", () => {
  assert.deepEqual(currentConditions({ life_preferences: ["Без длинных тестовых"], constraints: { currency: "EUR", max_hours: 40, min_salary: 5000, remote: true, salary_gross: true, salary_period: "month" } }), ["Без длинных тестовых", "Только удалённая работа", "Доход от: 5000 EUR / месяц до вычета налогов", "Часов в неделю, максимум: 40"]);
});

test("historical start, tool and completion events retain their own meaning after the run completes", () => {
  const master = "Найди удалённую работу Python. Бюджет 0 EUR; новых регистраций не делай.",
    goal = composeGoal(master, { topic: "accounts", text: "Продолжи подтверждение текущего аккаунта. ".repeat(30), record: { kind: "account", id: "private-demo", status: "verification_required" } }),
    state = { agent: { runs: [{ id: "run", status: "completed", goal }] } },
    events = [
      { kind: "agent_started", related_id: "run", summary: "Agent run started" },
      { kind: "agent_tool", related_id: "run", summary: "Agent tool: task_add" },
      { kind: "agent_completed", related_id: "run", summary: "Agent run completed" },
    ],
    messages = events.map((event) => activitySummary(event, state));
  assert.match(messages[0].text, /^Агент начал поручение:/);
  assert.equal(messages[1].text, "Действие агента: Сохранение следующего шага");
  assert.match(messages[2].text, /^Поручение завершено:/);
  assert.equal(new Set(messages.map((message) => message.text)).size, 3);
  for (const message of messages) {
    assert.ok(message.text.length < 230);
    assert.doesNotMatch(message.text, /Основная цель и ограничения пользователя|Текущее поручение в рамках|Объект поручения|private-demo|task_add/);
    assert.deepEqual(message.target, { kind: "run", id: "run" });
  }
  assert.equal(goalExcerpt(goal), master);
  assert.equal(goalExcerpt(composeGoal("", { topic: "accounts", text: "Продолжи подтверждение.", record: { kind: "account", id: "private-demo" } })), "Продолжи подтверждение.");
  assert.ok(goalExcerpt("Длинная цель ".repeat(100)).length <= 160);
});

test("failure, cancellation and step-limit activity do not borrow a later run status", () => {
  const state = { agent: { runs: [{ id: "run", status: "completed", goal: "Ищу работу" }] } };
  for (const [kind, expected] of [["agent_failed", "Поручение завершилось ошибкой"], ["agent_cancelled", "Поручение остановлено"], ["agent_step_limit", "Достигнут предел шагов"], ["agent_tool_failed", "Ошибка действия агента"]]) {
    assert.match(activitySummary({ kind, related_id: "run", summary: "Agent tool: jobs_search" }, state).text, new RegExp(`^${expected}`));
  }
  assert.equal(activitySummary({ kind: "agent_started", related_id: "missing" }).text, "Агент начал поручение");
});
