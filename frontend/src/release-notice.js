const dismissalKey = "worklife.release-notice.v1";

export function readDismissedRelease(storage) {
  try { return storage?.getItem(dismissalKey) || ""; } catch { return ""; }
}

export function saveDismissedRelease(storage, version) {
  try { storage?.setItem(dismissalKey, version); } catch {}
}

export function shouldShowReleaseNotice(release, dismissedVersion) {
  return Boolean(release?.update_available && release.latest_version && release.latest_version !== dismissedVersion);
}
