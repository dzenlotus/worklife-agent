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
        transformIndexHtml: (html) =>
          html.replace(
            "<title>Worklife — управление поиском</title>",
            `<title>${site ? "Worklife — MCP-инструменты поиска работы" : "Worklife — монитор работы агента"}</title>`,
          ),
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
