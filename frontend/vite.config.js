import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig(({ mode }) => {
  const site = mode === "site";

  return {
    root,
    base: site ? "/worklife-agent/" : "/",
    publicDir: false,
    plugins: [
      react(),
      tailwindcss(),
      {
        name: "worklife-page-title",
        transformIndexHtml: (html) => {
          const titled = html.replace(
            "<title>Worklife — управление поиском</title>",
            `<title>${site ? "Worklife — MCP-инструменты поиска работы" : "Worklife — монитор работы агента"}</title>`,
          );
          return site ? titled.replace("</head>", '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22%3E%3Crect width=%2240%22 height=%2240%22 rx=%228%22 fill=%22%23202b35%22/%3E%3Cpath d=%22M7 13q6-6 13 0t13 0M7 21q6-6 13 0t13 0M7 29q6-6 13 0t13 0%22 fill=%22none%22 stroke=%22%23bed4e7%22 stroke-width=%222%22/%3E%3C/svg%3E" /></head>') : titled;
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
