import { useSyncExternalStore } from "react";
import app from "./locales/en-app.json" with { type: "json" };
import views from "./locales/en-views.json" with { type: "json" };
import site from "./locales/en-site.json" with { type: "json" };

export const messages = { ...site, ...views, ...app };
export const localeKey = "worklife.locale";
export const supportedLocales = ["ru", "en"];
export function resolveLocale(value) {
  const language = String(value || "").toLowerCase().split(/[-_]/)[0];
  return supportedLocales.includes(language) ? language : null;
}
export function initialLocale(storage, languages = []) {
  try {
    const saved = resolveLocale(storage?.getItem(localeKey));
    if (saved) return saved;
  } catch {}
  return languages.map(resolveLocale).find(Boolean) || "en";
}
let locale = "ru";
if (typeof window !== "undefined") {
  let storage;
  try { storage = window.localStorage; } catch {}
  locale = initialLocale(storage, navigator.languages || [navigator.language]);
}
const listeners = new Set();
export const getLocale = () => locale;
export function setLocale(value) {
  const next = resolveLocale(value);
  if (!next || next === locale) return;
  locale = next;
  try { window.localStorage.setItem(localeKey, locale); } catch {}
  for (const listener of listeners) listener();
}
function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export const useLocale = () => [useSyncExternalStore(subscribe, getLocale, getLocale), setLocale];

// Only application-owned copy passes through t; records keep their original language.
export function t(source, ...values) {
  const tagged = Array.isArray(source);
  const key = tagged ? source.map((part, i) => part + (i < values.length ? `{${i}}` : "")).join("") : source;
  const text = locale === "en" ? messages[key] || key : key;
  return tagged ? text.replace(/\{(\d+)\}/g, (_, i) => String(values[Number(i)])) : text;
}
