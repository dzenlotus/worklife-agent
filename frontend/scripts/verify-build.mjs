import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { packageUrl, pageMetadata, repositoryUrl, siteFiles, siteUrl, socialImageUrl } from "../src/page-metadata.js";

const frontend = fileURLToPath(new URL("../", import.meta.url));

export async function verifyBuild(mode) {
  const base = mode === "site" ? "/worklife-agent/" : "/";
  const directory = `${frontend}dist/${mode}`;
  const html = await readFile(`${directory}/index.html`, "utf8");
  const assets = [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css|woff2))"/g)].map(
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
  assert.equal(assets.filter((asset) => asset.endsWith(".woff2")).length, 2, `${mode}: missing local font preloads`);
  assert.match(await readFile(`${directory}/assets/OFL-Golos-Text.txt`, "utf8"), /SIL OPEN FONT LICENSE/);
  assert.doesNotMatch(html, /\/src\/|site\.js|app\.js|site\.css|app\.css/);
  const metadata = pageMetadata[mode].ru;
  assert.ok(html.includes(`<title>${metadata.title}</title>`), `${mode}: missing descriptive title`);
  assert.ok(html.includes(`content="${metadata.description}"`), `${mode}: missing static description`);
  if (mode === "site") {
    assert.match(html, /name="robots" content="index, follow, max-image-preview:large"/);
    assert.doesNotMatch(html, /noindex/);
    assert.ok(html.includes(`rel="canonical" href="${siteUrl}"`));
    assert.ok(html.includes(`property="og:url" content="${siteUrl}"`));
    assert.ok(html.includes(`property="og:image" content="${socialImageUrl}"`));
    assert.ok(html.includes(`name="twitter:image" content="${socialImageUrl}"`));
    assert.match(html, /name="twitter:card" content="summary_large_image"/);
    const structuredData = html.match(/<script[^>]+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/);
    assert.ok(structuredData, "site: missing JSON-LD");
    const software = JSON.parse(structuredData[1]);
    assert.equal(software["@type"], "SoftwareSourceCode");
    assert.equal(software.url, siteUrl);
    assert.equal(software.codeRepository, repositoryUrl);
    assert.equal(software.sameAs, packageUrl);
    assert.equal(software.aggregateRating, undefined);
    assert.equal(software.license, undefined);
    const fallback = html.match(/<noscript>([\s\S]*?)<\/noscript>/)?.[1];
    assert.ok(fallback?.includes("uvx --python 3.12 worklife-agent --target codex"), "site: missing installation without JavaScript");
    assert.ok(fallback.includes(`href="${repositoryUrl}"`));
    assert.ok(fallback.includes(`href="${packageUrl}"`));
    for (const filename of siteFiles)
      assert.ok((await stat(`${directory}/${filename}`)).size > 0, `site: missing ${filename}`);
    const sitemap = await readFile(`${directory}/sitemap.xml`, "utf8");
    assert.ok(sitemap.includes(`<loc>${siteUrl}</loc>`));
    assert.equal([...sitemap.matchAll(/<loc>/g)].length, 1);
    assert.match(await readFile(`${directory}/robots.txt`, "utf8"), /Sitemap: https:\/\/dzenlotus\.github\.io\/worklife-agent\/sitemap\.xml/);
    assert.match(await readFile(`${directory}/llms.txt`, "utf8"), /Model Context Protocol/);
    assert.deepEqual(await readFile(`${directory}/social-preview.png`), await readFile(`${frontend}src/site-assets/worklife-jobs.png`));
  } else {
    assert.match(html, /name="robots" content="noindex, nofollow"/);
    assert.doesNotMatch(html, /rel="canonical"|application\/ld\+json|property="og:/);
    const files = await readdir(directory);
    for (const filename of siteFiles)
      assert.ok(!files.includes(filename), `app: public discovery file ${filename}`);
  }
  console.log(`Verified ${mode}: compiled assets use ${base}; ${mode === "site" ? "public SEO and discovery files present" : "private app is noindex"}`);
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await verifyBuild("app");
  await verifyBuild("site");
}
