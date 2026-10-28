import { siteUrl } from "./page-metadata.js";

export async function copyProjectLink(browserNavigator) {
  try {
    if (!browserNavigator.clipboard?.writeText) return "manual";
    await browserNavigator.clipboard.writeText(siteUrl);
    return "copied";
  } catch {
    return "manual";
  }
}

export async function shareProject(browserNavigator, text) {
  if (browserNavigator.share) {
    try {
      await browserNavigator.share({ title: "Worklife", text, url: siteUrl });
      return "";
    } catch (error) {
      if (error?.name === "AbortError") return "";
    }
  }
  return copyProjectLink(browserNavigator);
}
