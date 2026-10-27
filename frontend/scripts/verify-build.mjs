import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const frontend = fileURLToPath(new URL("../", import.meta.url));

export async function verifyBuild(mode) {
  const base = mode === "site" ? "/worklife-agent/" : "/";
  const directory = `${frontend}dist/${mode}`;
  const html = await readFile(`${directory}/index.html`, "utf8");
  const assets = [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)].map(
    (match) => match[1],
  );

  assert.match(html, /<html lang="ru" class="dark">/);
  assert.match(html, /type="module"/);
  assert.ok(
    assets.some((asset) => asset.endsWith(".js")),
    `${mode}: missing JavaScript`,
  );
  assert.ok(
    assets.some((asset) => asset.endsWith(".css")),
    `${mode}: missing CSS`,
  );
  for (const asset of assets) {
    assert.ok(
      asset.startsWith(`${base}assets/`),
      `${mode}: incorrect asset base ${asset}`,
    );
    assert.ok(
      (await stat(`${directory}/${asset.slice(base.length)}`)).size > 0,
      `${mode}: empty asset ${asset}`,
    );
  }
  assert.ok((await readdir(`${directory}/assets`)).length >= 2);
  assert.doesNotMatch(html, /\/src\/|site\.js|app\.js|site\.css|app\.css/);
  console.log(`Verified ${mode}: compiled JavaScript and CSS use ${base}`);
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await verifyBuild("app");
  await verifyBuild("site");
}
