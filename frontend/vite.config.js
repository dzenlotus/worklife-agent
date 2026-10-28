import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { packageUrl, pageMetadata, repositoryUrl, siteUrl, socialImageUrl } from "./src/page-metadata.js";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig(({ mode }) => {
  const site = mode === "site";

  return {
    root,
    base: site ? "/worklife-agent/" : "/",
    publicDir: site ? fileURLToPath(new URL("./site", import.meta.url)) : false,
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "worklife-page-metadata",
        transformIndexHtml: (html) => {
          const metadata = pageMetadata[site ? "site" : "app"].ru;
          const titled = html.replace(
            /<title>.*?<\/title>/,
            `<title>${metadata.title}</title>`,
          ).replace(/<meta\s+name="description"\s+content="[^"]*"\s*\/>/, `<meta name="description" content="${metadata.description}" />`);
          const tags = [{ tag: "meta", attrs: { name: "robots", content: site ? "index, follow, max-image-preview:large" : "noindex, nofollow" } }];
          if (!site) return { html: titled, tags };

          tags.push(
            { tag: "link", attrs: { rel: "canonical", href: siteUrl } },
            { tag: "link", attrs: { rel: "sitemap", type: "application/xml", href: `${siteUrl}sitemap.xml` } },
            { tag: "meta", attrs: { property: "og:type", content: "website" } },
            { tag: "meta", attrs: { property: "og:site_name", content: "Worklife" } },
            { tag: "meta", attrs: { property: "og:url", content: siteUrl } },
            { tag: "meta", attrs: { property: "og:title", content: metadata.title } },
            { tag: "meta", attrs: { property: "og:description", content: metadata.description } },
            { tag: "meta", attrs: { property: "og:locale", content: "ru_RU" } },
            { tag: "meta", attrs: { property: "og:locale:alternate", content: "en_US" } },
            { tag: "meta", attrs: { property: "og:image", content: socialImageUrl } },
            { tag: "meta", attrs: { property: "og:image:type", content: "image/png" } },
            { tag: "meta", attrs: { property: "og:image:width", content: "1440" } },
            { tag: "meta", attrs: { property: "og:image:height", content: "1080" } },
            { tag: "meta", attrs: { property: "og:image:alt", content: "Worklife: демонстрационный список вакансий / demo job-search board" } },
            { tag: "meta", attrs: { name: "twitter:card", content: "summary_large_image" } },
            { tag: "meta", attrs: { name: "twitter:title", content: metadata.title } },
            { tag: "meta", attrs: { name: "twitter:description", content: metadata.description } },
            { tag: "meta", attrs: { name: "twitter:image", content: socialImageUrl } },
            { tag: "meta", attrs: { name: "twitter:image:alt", content: "Worklife demo job-search board with fictional vacancies" } },
            { tag: "script", attrs: { type: "application/ld+json" }, children: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "SoftwareSourceCode",
              name: "Worklife",
              alternateName: "worklife-agent",
              description: pageMetadata.site.en.description,
              url: siteUrl,
              codeRepository: repositoryUrl,
              sameAs: packageUrl,
              programmingLanguage: "Python",
              runtimePlatform: "Python 3.12+",
              inLanguage: ["ru", "en"],
              keywords: ["MCP server", "Model Context Protocol", "AI job search", "career agent", "resume matching", "CV", "application tracking"],
              image: socialImageUrl,
            }) },
          );
          const withIcon = titled.replace("</head>", '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22%3E%3Crect width=%2240%22 height=%2240%22 rx=%228%22 fill=%22%23202b35%22/%3E%3Cpath d=%22M7 13q6-6 13 0t13 0M7 21q6-6 13 0t13 0M7 29q6-6 13 0t13 0%22 fill=%22none%22 stroke=%22%23bed4e7%22 stroke-width=%222%22/%3E%3C/svg%3E" /></head>');
          return { html: withIcon.replace('<div id="root"></div>', `<div id="root"></div>
    <noscript>
      <main lang="en">
        <h1>Worklife — AI job search MCP server</h1>
        <p>${pageMetadata.site.en.description}</p>
        <p lang="ru">${metadata.description}</p>
        <p>Requires Python 3.12+ and uv. Install for Codex:</p>
        <pre><code>uvx --python 3.12 worklife-agent --target codex</code></pre>
        <p>Also supports Claude Code, Cursor, OpenCode, and generic MCP configuration. Enable JavaScript for the interactive site and client selector.</p>
        <p><a href="${repositoryUrl}">Source and documentation on GitHub</a> · <a href="${packageUrl}">Python package on PyPI</a> · <a href="${repositoryUrl}/blob/main/docs/recruiter-agent.md">Client setup guide</a></p>
      </main>
    </noscript>`), tags };
        },
      },
    ],
    resolve: {
      alias: {
        "@entry": fileURLToPath(
          new URL(site ? "./src/Site.jsx" : "./src/App.jsx", import.meta.url),
        ),
      },
    },
    build: {
      outDir: `dist/${site ? "site" : "app"}`,
      emptyOutDir: true,
    },
    server: {
      proxy: {
        "/api": "http://127.0.0.1:8877",
      },
    },
  };
});
