import { topicGoals } from "./model.js";

const emptyDraft = () => ({ goal: "", context: null });
const validText = (value) => typeof value === "string" && value.length <= 16000;
function cleanContext(context) {
  if (!context || !Object.hasOwn(topicGoals, context.topic) || !validText(context.text)) return null;
  const result = { topic: context.topic, text: context.text };
  if (["cv", "job", "account", "repository", "tactic", "resource", "schedule"].includes(context.record?.kind) && validText(context.record.id)) {
    result.record = { kind: context.record.kind, id: context.record.id };
    if (validText(context.record.status)) result.record.status = context.record.status;
  }
  return result;
}
export const draftKey = (author) =>
  typeof author === "string" && author ? `worklife.goal.v1.${encodeURIComponent(author)}` : null;

export function composeGoal(goal, context) {
  const master = goal.trim(),
    reference = cleanContext(context)?.record,
    instruction = (context?.text?.trim() || "") + (reference ? `\nОбъект поручения: ${reference.kind}_id=${reference.id}${reference.status ? `; status=${reference.status}` : ""}.` : "");
  if (!master) return instruction;
  if (!instruction) return master;
  return `Основная цель и ограничения пользователя (имеют приоритет):\n${master}\n\nТекущее поручение в рамках этой цели:\n${instruction}\n\nВыполни текущее поручение, сохраняя исходные ограничения. Если оно им противоречит, сначала уточни у пользователя.`;
}

export function readDraft(storage, author) {
  try {
    const key = draftKey(author), data = key && JSON.parse(storage.getItem(key) || "null");
    if (data?.version !== 1 || !validText(data.goal)) return emptyDraft();
    const context = data.context;
    return {
      goal: data.goal,
      context: cleanContext(context),
    };
  } catch {
    return emptyDraft();
  }
}

export function saveDraft(storage, author, draft) {
  try {
    const key = draftKey(author);
    if (key && validText(draft.goal)) {
      const context = draft.context;
      storage.setItem(key, JSON.stringify({
        version: 1,
        goal: draft.goal,
        context: cleanContext(context),
      }));
    }
  } catch {
    // The current draft remains usable if browser storage is unavailable.
  }
}
