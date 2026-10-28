import test from "node:test";
import assert from "node:assert/strict";
import { readDismissedRelease, saveDismissedRelease, shouldShowReleaseNotice } from "./release-notice.js";

test("dismissing one release survives reload and leaves the next release visible", () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) };
  const release = { latest_version: "0.4.2", update_available: true };
  assert.equal(shouldShowReleaseNotice(release, readDismissedRelease(storage)), true);
  saveDismissedRelease(storage, release.latest_version);
  assert.equal(shouldShowReleaseNotice(release, readDismissedRelease(storage)), false);
  assert.equal(shouldShowReleaseNotice({ ...release, latest_version: "0.4.3" }, readDismissedRelease(storage)), true);
  assert.equal(shouldShowReleaseNotice({ ...release, update_available: false }, ""), false);
  assert.equal(shouldShowReleaseNotice(null, ""), false);
});

test("blocked browser storage does not prevent displaying or closing the notice", () => {
  const storage = { getItem() { throw Error("blocked"); }, setItem() { throw Error("blocked"); } };
  assert.equal(readDismissedRelease(storage), "");
  assert.doesNotThrow(() => saveDismissedRelease(storage, "0.4.2"));
});
