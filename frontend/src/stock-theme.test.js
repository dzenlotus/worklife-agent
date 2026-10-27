import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const source = new URL("./", import.meta.url);
test("HeroUI allows semantic color tokens only, with no component or typography overrides", () => {
  const css = readFileSync(new URL("styles.css", source), "utf8"), imports = '@import "tailwindcss";\n@import "@heroui/styles";\n';
  assert.ok(css.startsWith(imports));
  const block = css.slice(imports.length).match(/^\n@layer base \{\n  \.dark \{\n([\s\S]+)\n  \}\n\}\n$/);
  assert.ok(block, "Only the official dark-theme variable block may follow the imports");
  const allowed = new Set(["background", "foreground", "surface", "surface-foreground", "surface-secondary", "surface-secondary-foreground", "surface-tertiary", "surface-tertiary-foreground", "overlay", "overlay-foreground", "muted", "default", "default-foreground", "field-background", "field-foreground", "field-placeholder", "border", "separator", "accent", "accent-foreground", "focus", "link", "segment", "segment-foreground", "success", "success-foreground", "warning", "warning-foreground", "danger", "danger-foreground"]);
  const tokens = new Map();
  for (const line of block[1].split("\n")) {
    const declaration = line.match(/^    --([a-z-]+): (#[0-9a-f]{6}|var\(--([a-z-]+)\));$/);
    assert.ok(declaration && allowed.has(declaration[1]), `Non-color theme override: ${line}`);
    if (declaration[3]) assert.ok(allowed.has(declaration[3]));
    assert.ok(!tokens.has(declaration[1]), "Duplicate color token");
    tokens.set(declaration[1], declaration[2]);
  }
  assert.deepEqual([...tokens.keys()].sort(), [...allowed].sort());
  assert.deepEqual(readdirSync(source).filter((file) => file.endsWith(".css")), ["styles.css"]);
  for (const file of readdirSync(source).filter((file) => file.endsWith(".jsx"))) {
    const content = readFileSync(new URL(file, source), "utf8");
    assert.doesNotMatch(content, /\bstyle\s*=|<svg\b|<path\b|#[0-9a-f]{3,8}\b|--(?:wl|site|accent)|\b(?:wl|site)-[a-z]+\b/i, file);
    for (const [, classes] of content.matchAll(/className="([^"]*)"/g)) {
      assert.ok(classes.split(/\s+/).every((value) => ["sr-only", "focus:not-sr-only"].includes(value) || /^(?:(?:sm|md|lg|xl):)?(?:flex(?:-\w+)?|grid(?:-cols-\d+)?|gap-\d+|p[xytrbl]?-\d+|m[xy]?-auto|w-(?:full|\d+)|min-w-0|max-w-[a-z0-9]+|overflow(?:-[xy])?-(?:auto|hidden)|items-\w+|justify-\w+|shrink-0|block|hidden)$/.test(value)), `${file}: only layout and keyboard-accessibility utilities are allowed (${classes})`);
    }
  }
  const html = readFileSync(new URL("../index.html", source), "utf8");
  assert.match(html, /class="dark"/);
  assert.match(html, /<body class="bg-background text-foreground">/);
  assert.doesNotMatch(html, /theme-color/);
});

test("graphite theme keeps normal text readable without pure black or white", () => {
  const css = readFileSync(new URL("styles.css", source), "utf8"), values = Object.fromEntries([...css.matchAll(/--([a-z-]+): (#[0-9a-f]{6}|var\(--([a-z-]+)\));/g)].map(([, key, value, ref]) => [key, ref ? { ref } : value]));
  const resolve = (key) => typeof values[key] === "string" ? values[key] : resolve(values[key].ref);
  const luminance = (hex) => hex.slice(1).match(/../g).map((value) => parseInt(value, 16) / 255).map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  for (const [front, back] of [["foreground", "background"], ["surface-foreground", "surface"], ["surface-secondary-foreground", "surface-secondary"], ["surface-tertiary-foreground", "surface-tertiary"], ["muted", "surface"], ["muted", "overlay"], ["muted", "surface-tertiary"], ["muted", "default"], ["default-foreground", "default"], ["field-foreground", "field-background"], ["field-placeholder", "field-background"], ["accent-foreground", "accent"], ["segment-foreground", "segment"], ["link", "surface"], ["success-foreground", "success"], ["warning-foreground", "warning"], ["danger-foreground", "danger"]]) {
    const a = luminance(resolve(front)), b = luminance(resolve(back)), contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    assert.ok(contrast >= 4.5, `${front}/${back}: ${contrast.toFixed(2)}`);
  }
  assert.doesNotMatch(css, /#(?:000000|ffffff)\b/i);
});
