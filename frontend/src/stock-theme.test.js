import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const source = new URL("./", import.meta.url);
test("official Magic UI keeps reduced-motion support", () => {
  const css = readFileSync(new URL("styles.css", source), "utf8"),
    magic = readFileSync(new URL("magicui.jsx", source), "utf8");
  assert.match(css, /prefers-reduced-motion/);
  assert.match(magic, /magicui.design/);
  assert.match(magic, /useSpring/);
  assert.match(magic, /useInView/);
  assert.match(magic, /useReducedMotion/);
  const overview = readFileSync(new URL("Overview.jsx", source), "utf8");
  assert.doesNotMatch(overview, /<BlurFade[^>]*>[\s]*<PageHeading/);
  assert.doesNotMatch(overview, /BorderBeam/);
});

test("graphite theme keeps normal text readable without pure black or white", () => {
  const css = readFileSync(new URL("styles.css", source), "utf8"),
    values = Object.fromEntries(
      [...css.matchAll(/--([a-z-]+): (#[0-9a-f]{6}|var\(--([a-z-]+)\));/g)].map(
        ([, key, value, ref]) => [key, ref ? { ref } : value],
      ),
    );
  const resolve = (key) =>
    typeof values[key] === "string" ? values[key] : resolve(values[key].ref);
  const luminance = (hex) =>
    hex
      .slice(1)
      .match(/../g)
      .map((value) => parseInt(value, 16) / 255)
      .map((value) =>
        value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
      )
      .reduce(
        (sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index],
        0,
      );
  for (const [front, back] of [
    ["foreground", "background"],
    ["surface-foreground", "surface"],
    ["surface-secondary-foreground", "surface-secondary"],
    ["surface-tertiary-foreground", "surface-tertiary"],
    ["muted", "surface"],
    ["muted", "overlay"],
    ["muted", "surface-tertiary"],
    ["muted", "default"],
    ["default-foreground", "default"],
    ["field-foreground", "field-background"],
    ["field-placeholder", "field-background"],
    ["accent-foreground", "accent"],
    ["segment-foreground", "segment"],
    ["link", "surface"],
    ["success-foreground", "success"],
    ["warning-foreground", "warning"],
    ["danger-foreground", "danger"],
  ]) {
    const a = luminance(resolve(front)),
      b = luminance(resolve(back)),
      contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    assert.ok(contrast >= 4.5, `${front}/${back}: ${contrast.toFixed(2)}`);
  }
  assert.doesNotMatch(css, /#(?:000000|ffffff)\b/i);
});
