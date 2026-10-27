import test from "node:test";
import assert from "node:assert/strict";
import { documentBlocks } from "./document.js";

test("CV preview preserves factual paragraphs and lists while removing structural Markdown", () => {
  assert.deepEqual(documentBlocks("# Иван\r\n\r\n## Опыт\r\nПервая строка\r\nпродолжение\r\n\r\n- Пять лет\r\n- Учёт и отчётность\r\n\r\nДругой абзац"), [
    { type: "heading", level: 1, text: "Иван" }, { type: "heading", level: 2, text: "Опыт" },
    { type: "paragraph", text: "Первая строка продолжение" }, { type: "list", items: ["Пять лет", "Учёт и отчётность"] },
    { type: "paragraph", text: "Другой абзац" },
  ]);
  assert.deepEqual(documentBlocks("<script>alert(1)</script>"), [{ type: "paragraph", text: "<script>alert(1)</script>" }]);
  assert.deepEqual(documentBlocks(), []);
});
