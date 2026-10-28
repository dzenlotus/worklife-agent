import test from "node:test";
import assert from "node:assert/strict";
import { copyProjectLink, shareProject } from "./project-actions.js";
import { siteUrl } from "./page-metadata.js";

test("project sharing uses only the public project link, handles cancel, and keeps copy fallback", async () => {
  let shared, copied;
  const clipboard = { async writeText(value) { copied = value; } };
  assert.equal(await shareProject({ clipboard, async share(value) { shared = value; } }, "Public project"), "");
  assert.deepEqual(shared, { title: "Worklife", text: "Public project", url: siteUrl });
  assert.equal(copied, undefined);
  assert.equal(await shareProject({ clipboard, async share() { throw { name: "AbortError" }; } }, "Public project"), "");
  assert.equal(copied, undefined);
  assert.equal(await shareProject({ clipboard }, "Public project"), "copied");
  assert.equal(copied, "https://dzenlotus.github.io/worklife-agent/");
  copied = undefined;
  assert.equal(await shareProject({ clipboard, async share() { throw Error("Unavailable"); } }, "Public project"), "copied");
  assert.equal(copied, siteUrl);
  assert.equal(await copyProjectLink({ clipboard: { async writeText() { throw Error("Denied"); } } }), "manual");
  assert.equal(await shareProject({}, "Public project"), "manual");
});
