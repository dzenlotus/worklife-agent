import { t, getLocale } from "./i18n.js";
import { list } from "./model.js";
export const stages = [
  ["new", "Новые"],
  ["saved", "Сохранены"],
  ["applied", "Отклик"],
  ["reply", "Ответ"],
  ["interview", "Интервью"],
  ["offer", "Оффер"],
  ["accepted", "Принято"],
  ["rejected", "Отказ"],
  ["withdrawn", "Снята"],
];
export const employerName = (job) =>
  typeof job.employer === "object"
    ? job.employer?.name || t("Компания не указана")
    : job.employer || t("Компания не указана");
export const jobStage = (job, applications) =>
  list(applications).find((a) => a.job_id === job.id)?.stage || "new";
const locationName = (job) =>
  (typeof job.location === "object"
    ? job.location?.name || job.location?.label
    : job.location) ||
  job.area?.name;
const sourceName = (job) =>
  typeof job.source === "object"
    ? job.source?.name || job.source?.url || job.platform
    : job.source || job.platform;
// Keep selected filter values stable when their displayed fallback is translated.
export const jobLocationKey = (job) => locationName(job) || (job.remote === true ? "Удалённо" : "Не указано");
export const jobSourceKey = (job) => sourceName(job) || "Не указан";
export const jobLocation = (job) => locationName(job) || t(jobLocationKey(job));
export const jobSource = (job) => sourceName(job) || t(jobSourceKey(job));
export function selectJobs(state, filters = {}) {
  const query = (filters.query || "").trim().toLocaleLowerCase(getLocale());
  return list(state.jobs).filter(
    (job) =>
      (!query ||
        [job.title, employerName(job), job.description, jobLocation(job)]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase(getLocale())
          .includes(query)) &&
      (!filters.stage || jobStage(job, state.applications) === filters.stage) &&
      (!filters.location || jobLocationKey(job) === filters.location) &&
      (!filters.source || jobSourceKey(job) === filters.source) &&
      (!filters.remote || job.remote === true),
  );
}
export function salaryLabel(job) {
  const from = Number(job.salary_min),
    to = Number(job.salary_max),
    format = (n) => n.toLocaleString(getLocale());
  if (!(from > 0 || to > 0)) return t("Зарплата не указана");
  return `${from > 0 && to > 0 ? `${format(from)} – ${format(to)}` : from > 0 ? t`от ${format(from)}` : t`до ${format(to)}`} ${job.currency || t("валюта не указана")}${job.salary_period ? ` / ${{ month: t("мес."), monthly: t("мес."), year: t("год"), yearly: t("год"), hour: t("час"), week: t("нед."), day: t("день") }[job.salary_period] || job.salary_period}` : ""}`;
}
export const groupLabel = (group) =>
  `${group.currency || "—"} / ${{ month: t("мес."), year: t("год"), hour: t("час"), week: t("нед.") }[group.period] || group.period || "—"} · ${group.gross === true ? t("до налогов") : group.gross === false ? t("на руки") : t("налоги неизвестны")}`;
