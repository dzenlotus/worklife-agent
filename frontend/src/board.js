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
    ? job.employer?.name || "Компания не указана"
    : job.employer || "Компания не указана";
export const jobStage = (job, applications) =>
  list(applications).find((a) => a.job_id === job.id)?.stage || "new";
export const jobLocation = (job) =>
  (typeof job.location === "object"
    ? job.location?.name || job.location?.label
    : job.location) ||
  job.area?.name ||
  (job.remote === true ? "Удалённо" : "Не указано");
export const jobSource = (job) =>
  typeof job.source === "object"
    ? job.source?.name || job.source?.url || job.platform || "Не указан"
    : job.source || job.platform || "Не указан";
export function selectJobs(state, filters = {}) {
  const query = (filters.query || "").trim().toLocaleLowerCase("ru");
  return list(state.jobs).filter(
    (job) =>
      (!query ||
        [job.title, employerName(job), job.description, jobLocation(job)]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase("ru")
          .includes(query)) &&
      (!filters.stage || jobStage(job, state.applications) === filters.stage) &&
      (!filters.location || jobLocation(job) === filters.location) &&
      (!filters.source || jobSource(job) === filters.source) &&
      (!filters.remote || job.remote === true),
  );
}
export function salaryLabel(job) {
  const from = Number(job.salary_min),
    to = Number(job.salary_max),
    format = (n) => n.toLocaleString("ru-RU");
  if (!(from > 0 || to > 0)) return "Зарплата не указана";
  return `${from > 0 && to > 0 ? `${format(from)} – ${format(to)}` : from > 0 ? `от ${format(from)}` : `до ${format(to)}`} ${job.currency || "валюта не указана"}${job.salary_period ? ` / ${{ month: "мес.", monthly: "мес.", year: "год", yearly: "год", hour: "час", week: "нед.", day: "день" }[job.salary_period] || job.salary_period}` : ""}`;
}
export const groupLabel = (group) =>
  `${group.currency || "—"} / ${{ month: "мес.", year: "год", hour: "час", week: "нед." }[group.period] || group.period || "—"} · ${group.gross === true ? "до налогов" : group.gross === false ? "на руки" : "налоги неизвестны"}`;
