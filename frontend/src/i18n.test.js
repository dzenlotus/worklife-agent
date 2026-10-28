import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { parseAst } from "rolldown/parseAst";
import { initialLocale, localeKey, messages, resolveLocale, setLocale, t } from "./i18n.js";
import { label, formatDate, currentConditions } from "./model.js";
import { salaryLabel, selectJobs } from "./board.js";

test("locale detection honors saved selection and falls back across browser preferences", () => {
  assert.equal(resolveLocale("en-US"), "en");
  assert.equal(resolveLocale("ru_RU"), "ru");
  assert.equal(resolveLocale("de-DE"), null);
  assert.equal(initialLocale({ getItem: (key) => key === localeKey ? "ru" : null }, ["en-US"]), "ru");
  assert.equal(initialLocale(null, ["fr-FR", "ru-RU", "en"]), "ru");
  assert.equal(initialLocale({ getItem() { throw Error("denied"); } }, ["en-GB"]), "en");
  assert.equal(initialLocale(null, ["fr"]), "en");
});

test("switching language updates labels, interpolations and formatting without altering vacancy text", () => {
  try {
    setLocale("en");
    assert.equal(t("Обзор"), "Overview");
    assert.equal(label("applied"), "Application sent");
    assert.equal(t`от ${100}`, "from 100");
    assert.equal(t`Открыть снимок «${"Jobs {0}"}» в полном размере`, "Open the “Jobs {0}” screenshot at full size");
    assert.match(salaryLabel({ salary_min: 12000, currency: "EUR", salary_period: "month" }), /12,000/);
    assert.match(formatDate("2026-10-28T12:00:00Z"), /Oct/);
    assert.ok(currentConditions({ constraints: { remote: true } }).some((text) => /[Rr]emote/.test(text)));
    const job = { id: "test", title: "Инженер-разработчик", description: "Développeur Python", employer: "Компания" };
    assert.equal(selectJobs({ jobs: [job] }, { query: "DÉVELOPPEUR" })[0], job);
    assert.equal(job.title, "Инженер-разработчик");
    setLocale("ru");
    assert.equal(t("Обзор"), "Обзор");
    assert.equal(label("applied"), "Отклик отправлен");
    assert.equal(t`от ${100}`, "от 100");
  } finally { setLocale("ru"); }
});

test("all application translation calls have English copy and preserve template placeholders", () => {
  for (const [key, value] of Object.entries(messages)) {
    assert.ok(typeof value === "string" && value.trim(), `Empty translation: ${key}`);
    assert.doesNotMatch(value, /[А-Яа-яЁё]/, `Untranslated: ${key}`);
    assert.deepEqual([...key.matchAll(/\{\d+\}/g)].map(([x]) => x).sort(), [...value.matchAll(/\{\d+\}/g)].map(([x]) => x).sort(), `Placeholder mismatch: ${key}`);
  }
  const source = new URL("./", import.meta.url);
  for (const file of readdirSync(source).filter((name) => /\.(js|jsx)$/.test(name) && !name.endsWith(".test.js"))) {
    const ast = parseAst(readFileSync(new URL(file, source), "utf8"), { lang: "jsx" });
    function visit(node, parent) {
      if (!node || typeof node !== "object") return;
      let key;
      if (node.type === "CallExpression" && node.callee.name === "t" && node.arguments[0]?.type === "Literal") key = node.arguments[0].value;
      if (node.type === "TaggedTemplateExpression" && node.tag.name === "t") key = node.quasi.quasis.map((part, i) => part.value.cooked + (i < node.quasi.expressions.length ? `{${i}}` : "")).join("");
      if (typeof key === "string" && /[А-Яа-яЁё]/.test(key)) assert.ok(messages[key], `${file}: missing ${key}`);
      // Language options display their native names in every locale.
      if (node.type === "JSXText" && !parent?.openingElement?.attributes?.some((attribute) => attribute.name?.name === "lang")) assert.doesNotMatch(node.value, /[А-Яа-яЁё]/, `${file}: untranslated JSX text`);
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) value.forEach((child) => visit(child, node));
        else if (value && typeof value === "object") visit(value, node);
      }
    }
    visit(ast);
  }
});
