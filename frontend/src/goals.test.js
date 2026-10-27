import test from "node:test";
import assert from "node:assert/strict";
import { composeGoal, draftKey, readDraft, saveDraft } from "./goals.js";

test("contextual delegation preserves the user's goal and restrictions first", () => {
  const goal = "Python удалённо. Бюджет 0 EUR. Новых регистраций не делай.";
  const context = { topic: "accounts", text: "Продолжи подтверждение account_id=demo." };
  const result = composeGoal(goal, context);
  assert.ok(result.includes(goal));
  assert.ok(result.includes(context.text));
  assert.ok(result.indexOf(goal) < result.indexOf(context.text));
  assert.match(result, /ограничения.*приоритет/i);
  assert.equal(composeGoal(goal, null), goal);
  assert.equal(composeGoal("", context), context.text);
  assert.equal(composeGoal(" ", null), "");
});

test("drafts persist only versioned goal/context fields under the local author", () => {
  const values = new Map();
  const storage = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) };
  const draft = { goal: "Ищу работу", context: { topic: "cv", text: "Переведи CV demo" }, api_key: "never-store" };
  saveDraft(storage, "author-a", draft);
  assert.notEqual(draftKey("author-a"), draftKey("author-b"));
  assert.deepEqual(readDraft(storage, "author-a"), { goal: draft.goal, context: draft.context });
  assert.deepEqual(readDraft(storage, "author-b"), { goal: "", context: null });
  assert.ok(!values.get(draftKey("author-a")).includes("never-store"));
  assert.equal(JSON.parse(values.get(draftKey("author-a"))).version, 1);
});

test("invalid, oversized, old or inaccessible draft storage does not restore data", () => {
  for (const value of ["{", '{"version":0,"goal":"old"}', '{"version":1,"goal":42}', JSON.stringify({ version: 1, goal: "x".repeat(16001) })]) {
    assert.deepEqual(readDraft({ getItem: () => value }, "author"), { goal: "", context: null });
  }
  assert.deepEqual(readDraft({ getItem: () => JSON.stringify({ version: 1, goal: "Valid", context: { topic: "unknown", text: "unsafe" } }) }, "author"), { goal: "Valid", context: null });
  assert.deepEqual(readDraft({ getItem: () => { throw new Error("denied"); } }, "author"), { goal: "", context: null });
  assert.doesNotThrow(() => saveDraft({ setItem: () => { throw new Error("full"); } }, "author", { goal: "Valid", context: null }));
  assert.equal(draftKey(""), null);
});

test("a selected account carries only its explicit reference into the composed instruction", () => {
  const values = new Map(), storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
  const context = { topic: "accounts", text: "Продолжи подтверждение demo.", record: { kind: "account", id: "demo", status: "verification_required", api_key: "excluded" } };
  saveDraft(storage, "owner", { goal: "Без новых регистраций", context });
  const draft = readDraft(storage, "owner");
  assert.deepEqual(draft.context.record, { kind: "account", id: "demo", status: "verification_required" });
  const composed = composeGoal(draft.goal, draft.context);
  assert.match(composed, /account_id=demo; status=verification_required/);
  assert.ok(!composed.includes("excluded"));
  assert.ok(!values.get(draftKey("owner")).includes("excluded"));
});
