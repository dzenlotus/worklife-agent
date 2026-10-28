import { cp, mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { verifyBuild } from "./verify-build.mjs";
import { siteFiles } from "../src/page-metadata.js";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const configFile = fileURLToPath(new URL("../vite.config.js", import.meta.url));
const targets = [
  {
    mode: "app",
    destination: fileURLToPath(
      new URL("../../src/worklife/web/", import.meta.url),
    ),
    obsolete: ["app.css", "app.js"],
  },
  {
    mode: "site",
    destination: fileURLToPath(new URL("../../docs/", import.meta.url)),
    obsolete: ["site.css", "site.js", "favicon.svg"],
  },
];

// Complete both builds before replacing the files served by the app or GitHub Pages.
for (const { mode } of targets) {
  await build({ root: frontend, configFile, mode });
  await cp(`${frontend}src/fonts/OFL-Golos-Text.txt`, `${frontend}dist/${mode}/assets/OFL-Golos-Text.txt`);
  if (mode === "site")
    await cp(`${frontend}src/site-assets/worklife-jobs.png`, `${frontend}dist/site/social-preview.png`);
  await verifyBuild(mode);
}

for (const { mode, destination, obsolete } of targets) {
  const source = `${frontend}dist/${mode}`;
  await mkdir(destination, { recursive: true });
  await rm(`${destination}/assets`, { recursive: true, force: true });
  await cp(`${source}/assets`, `${destination}/assets`, { recursive: true });
  await cp(`${source}/index.html`, `${destination}/index.html`);
  if (mode === "site")
    for (const filename of siteFiles)
      await cp(`${source}/${filename}`, `${destination}/${filename}`);
  for (const filename of obsolete)
    await rm(`${destination}/${filename}`, { force: true });
}

console.log("Built and synchronized the app and site.");
