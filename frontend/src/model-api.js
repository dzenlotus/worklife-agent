import { t } from "./i18n.js";

export function connectionPayload({ base_url, model, api_key = "", persist = true }) {
  const base = base_url?.trim().replace(/\/+$/, "");
  if (!base) throw new Error(t("Укажите адрес сервиса модели."));
  let url;
  try { url = new URL(base); } catch { throw new Error(t("Адрес должен начинаться с http:// или https://.")); }
  if (!["http:", "https:"].includes(url.protocol))
    throw new Error(t("Адрес должен начинаться с http:// или https://."));
  if (!model?.trim()) throw new Error(t("Выберите или укажите модель."));
  return { base_url: base, model: model.trim(), persist: Boolean(persist), ...(api_key.trim() ? { api_key: api_key.trim() } : {}) };
}

export async function modelRequest(path = "", payload, fetcher = fetch) {
  const response = await fetcher(`/api/model${path}`, {
    method: payload === undefined ? "GET" : "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-Worklife-Client": "local" },
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
  });
  let data;
  try { data = await response.json(); } catch { throw new Error(t("Не удалось прочитать ответ подключения.")); }
  if (!response.ok || data.ok === false)
    throw new Error(t(data.error || "Не удалось сохранить подключение модели."));
  return data.result ?? data;
}
