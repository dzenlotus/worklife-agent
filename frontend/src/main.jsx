import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { I18nProvider } from "@heroui/react";
import Entry from "@entry";
import { useLocale } from "./i18n.js";
import { pageMetadata } from "./page-metadata.js";
import "./styles.css";

function LocalizedEntry() {
  const [locale] = useLocale();
  useEffect(() => {
    const site = import.meta.env.MODE === "site";
    const metadata = pageMetadata[site ? "site" : "app"][locale];
    document.documentElement.lang = locale;
    document.title = metadata.title;
    for (const selector of ['meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]'])
      document.querySelector(selector)?.setAttribute("content", metadata.description);
    for (const selector of ['meta[property="og:title"]', 'meta[name="twitter:title"]'])
      document.querySelector(selector)?.setAttribute("content", metadata.title);
    document.querySelector('meta[property="og:locale"]')?.setAttribute("content", locale === "ru" ? "ru_RU" : "en_US");
    document.querySelector('meta[property="og:locale:alternate"]')?.setAttribute("content", locale === "ru" ? "en_US" : "ru_RU");
  }, [locale]);
  return <I18nProvider locale={locale}><Entry /></I18nProvider>;
}

createRoot(document.getElementById("root")).render(<LocalizedEntry />);
