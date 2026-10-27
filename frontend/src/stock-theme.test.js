import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const source = new URL("./", import.meta.url);
test("HeroUI dark theme has no application CSS overrides or custom component visuals", () => {
  assert.equal(readFileSync(new URL("styles.css", source), "utf8"), '@import "tailwindcss";\n@import "@heroui/styles";\n');
  assert.deepEqual(readdirSync(source).filter((file) => file.endsWith(".css")), ["styles.css"]);
  for (const file of readdirSync(source).filter((file) => file.endsWith(".jsx"))) {
    const content = readFileSync(new URL(file, source), "utf8");
    assert.doesNotMatch(content, /\bstyle\s*=|<svg\b|<path\b|#[0-9a-f]{3,8}\b|--(?:wl|site|accent)|\b(?:wl|site)-[a-z]+\b/i, file);
    for (const [, classes] of content.matchAll(/className="([^"]*)"/g)) {
      assert.ok(classes.split(/\s+/).every((value) => /^(?:(?:sm|md|lg|xl):)?(?:flex(?:-\w+)?|grid(?:-cols-\d+)?|gap-\d+|p[xytrbl]?-\d+|m[xy]?-auto|w-(?:full|\d+)|min-w-0|max-w-[a-z0-9]+|overflow(?:-[xy])?-(?:auto|hidden)|items-\w+|justify-\w+|shrink-0|block|hidden)$/.test(value)), `${file}: only layout utilities are allowed (${classes})`);
    }
  }
  const html = readFileSync(new URL("../index.html", source), "utf8");
  assert.match(html, /class="dark"/);
  assert.doesNotMatch(html, /theme-color/);
});
