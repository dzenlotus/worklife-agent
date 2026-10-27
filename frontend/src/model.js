export const list = (value) => (Array.isArray(value) ? value : []);
export const labels = {
  saved: "Сохранена",
  new: "Новая",
  applied: "Отклик отправлен",
  reply: "Ответ получен",
  interview: "Интервью",
  offer: "Предложение",
  accepted: "Принято",
  rejected: "Отказ",
  withdrawn: "Снята",
  draft: "Черновик",
  approved: "Разрешено",
  sent: "Отправлено",
  cancelled: "Остановлено",
  uncertain: "Нужна проверка",
  sending: "Отправляется",
  failed: "Ошибка",
  active: "В работе",
  planned: "Запланировано",
  proposed: "Предложено",
  confirmed: "Подтверждено",
  verified: "Подтверждено",
  done: "Выполнено",
  open: "Открыто",
  completed: "Завершено",
  running: "Агент работает",
  queued: "В очереди",
  paused: "На паузе",
  registering: "Регистрация",
  verification_required: "Ожидает подтверждения",
  blocked: "Заблокирован",
  closed: "Закрыт",
  insufficient_data: "Недостаточно данных",
  descriptive_only: "Результат наблюдения",
  success: "Выполнено",
};
export const label = (value) =>
  value === "step_limit"
    ? "Достигнут предел шагов"
    : labels[value] || value || "—";
export function formatDate(value, clockOnly = false) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(+d)) return "—";
  return d.toLocaleString(
    "ru-RU",
    clockOnly
      ? { hour: "2-digit", minute: "2-digit" }
      : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" },
  );
}
export function safeURL(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
export function statistics(state) {
  const applications = list(state.applications),
    responseStages = new Set(["reply", "interview", "offer", "accepted"]);
  return {
    jobs: state.statistics?.jobs ?? list(state.jobs).length,
    applied: applications.filter(
      (a) =>
        a.stage === "applied" ||
        responseStages.has(a.stage) ||
        list(a.history).some((h) => h.stage === "applied"),
    ).length,
    replies: applications.filter(
      (a) =>
        responseStages.has(a.stage) ||
        list(a.history).some((h) => responseStages.has(h.stage)),
    ).length,
  };
}
export function filterJobs(state, filter = "all") {
  const applications = new Map(
    list(state.applications).map((a) => [a.job_id, a]),
  );
  return list(state.jobs)
    .filter((job) => {
      const a = applications.get(job.id);
      if (filter === "new") return !a;
      if (filter === "active")
        return ["saved", "applied", "interview"].includes(a?.stage);
      if (filter === "reply")
        return ["reply", "offer", "accepted"].includes(a?.stage);
      return true;
    })
    .slice()
    .sort((a, b) => (b.fetched_at || "").localeCompare(a.fetched_at || ""));
}
export function employerGroups(records) {
  const groups = new Map();
  for (const entry of list(records)) {
    const domain = entry.subject || entry.domain;
    if (!domain || entry.kind === "retraction") continue;
    const payload = entry.payload || entry;
    if (!groups.has(domain))
      groups.set(domain, {
        domain,
        name: typeof payload.name === "string" && payload.name ? payload.name : domain,
        observations: [],
      });
    groups.get(domain).observations.push({ ...entry, payload });
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
}
export function exchangeSummary(network = {}) {
  const value = network.summary || network;
  const attention = value.status === "attention",
    detail = attention
      ? `Проверенные записи сохранены. ${value.auto ? "Продолжайте работу, повторим проверку автоматически." : "Сохранённая база остаётся доступна."}`
      : value.detail || "Состояние обмена появится после подключения.";
  return {
    status: value.status || "pending",
    label: attention
      ? value.invalid > 0 ? "Изменённая запись отклонена"
        : value.rollback || value.incomplete > 0 ? "В общей базе не хватает части истории"
          : "Повторяем проверку общей базы"
      : value.label || "Обмен подготавливается",
    detail,
    employers: value.employers,
    protected_copies: value.protected_copies,
    last_sync: value.last_sync,
    auto: value.auto === true,
  };
}
export const conditionLabels = {
  remote: "Удалённая работа", min_salary: "Доход от", currency: "Валюта",
  salary_period: "Период оплаты", salary_gross: "До вычета налогов",
  max_hours: "Часов в неделю, максимум", max_hiring_stages: "Этапов найма, максимум",
  max_test_hours: "Тестовое задание, часов максимум",
};
export function currentConditions(profile = {}) {
  const rules = profile.constraints || {}, rows = [...list(profile.life_preferences)];
  if (typeof rules.remote === "boolean") rows.push(rules.remote ? "Только удалённая работа" : "Удалённая работа не обязательна");
  if (rules.min_salary != null) rows.push(`Доход от: ${rules.min_salary} ${rules.currency || "(валюта не указана)"}${rules.salary_period ? ` / ${humanLabel(rules.salary_period)}` : ""}${typeof rules.salary_gross === "boolean" ? rules.salary_gross ? " до вычета налогов" : " после вычета налогов" : ""}`);
  for (const key of ["max_hours", "max_hiring_stages", "max_test_hours"]) {
    if (rules[key] != null) rows.push(`${conditionLabels[key]}: ${rules[key]}`);
  }
  return rows;
}
export function humanLabel(value) {
  return ({ source: "Источник", service: "Сервис", material: "Материал", learning: "Обучение", time: "Время",
    job_search: "Поиск вакансий", jobs_search: "Поиск вакансий", account_profile: "Профиль аккаунта",
    email: "Почта", mail: "Почта", registration: "Регистрация", search: "Поиск", read: "Чтение", write: "Действия",
    month: "месяц", year: "год", hour: "час", week: "неделя", day: "день", send: "Отправка", reminder: "Напоминание" })[value] || String(value);
}
export function usageMetric(key, value) {
  const names = { total_tokens: "Токены", tokens: "Токены", prompt_tokens: "Входящие токены", completion_tokens: "Исходящие токены",
    duration_seconds: "Время работы, секунд", cost: "Стоимость, единица не указана", cost_usd: "Стоимость, USD", applications: "Отклики", jobs_reviewed: "Изучено вакансий" };
  return [names[key] || key.replaceAll("_", " "), Number(value).toLocaleString("ru-RU", { maximumFractionDigits: key === "duration_seconds" ? 2 : 4 })];
}
export function observationBasis(entry) {
  const kind = entry.payload?.evidence_kind;
  return {
    label: ({ advertised: "По объявлению работодателя", observed: "Наблюдение участника", hypothesis: "Предположение", confirmed_author: "Подтверждено автором записи" })[kind] || "Основание не указано",
    verification: entry.trust === "confirmed_author" ? "Автор подтверждает запись. Независимая проверка не проводилась." : "Независимая проверка не проводилась.",
  };
}
export function scheduleResult(run, state = {}) {
  const schedule = list(state.schedules).find((item) => item.id === run.schedule_id),
    result = run.result,
    title = schedule?.name || run.name || "Поручение по расписанию";
  let text;
  if (run.error || run.status === "failed") text = `Не удалось выполнить поручение. ${run.error || "Причина не сохранена."}`;
  else if (run.tool === "reminder" && result?.title) text = `Создано напоминание: «${result.title}».`;
  else if (run.tool === "agent_cycle") text = "Поручение передано агенту. Ход работы и итог смотрите в журнале агента.";
  else if (run.tool === "jobs_search" && Array.isArray(result)) text = `Получено вакансий: ${result.length}.`;
  else if (run.tool === "repository_analyze" && result?.scanned_file_count != null) text = `Изучен проект «${result.name || "локальный проект"}», файлов: ${result.scanned_file_count}.`;
  else if (typeof result?.summary === "string") text = result.summary;
  else if (typeof result?.message === "string") text = result.message;
  else text = run.changed === false ? "Запуск завершён. Сохранённый результат не изменился." : "Запуск завершён. Сохранённый результат обновлён.";
  return { title, text, error: Boolean(run.error || run.status === "failed"), next: result?.due_at ? `Срок напоминания: ${formatDate(result.due_at)}.` : null };
}
export function goalExcerpt(goal = "") {
  let text = typeof goal === "string" ? goal.trim() : "";
  const heading = "Основная цель и ограничения пользователя (имеют приоритет):";
  if (text.startsWith(heading)) {
    text = text.slice(heading.length).trimStart().split("\n\nТекущее поручение в рамках этой цели:", 1)[0];
  }
  text = text.split("\nОбъект поручения:", 1)[0].replace(/\s+/g, " ").trim();
  return text.length > 160 ? `${text.slice(0, 159).trimEnd()}…` : text;
}
const toolDescriptions = {
  agent_brief: "Просмотр цели и состояния", profile_save: "Сохранение условий", records_list: "Просмотр сохранённых данных",
  research_note: "Сохранение исследования", cv_create: "Подготовка резюме", cv_export: "Экспорт резюме", cv_localize: "Перевод резюме",
  job_save: "Сохранение вакансии", jobs_search: "Поиск вакансий", job_assess: "Оценка вакансии", application_update: "Обновление отклика",
  experiment_create: "Создание эксперимента", experiment_assign: "Назначение варианта резюме", experiment_outcome: "Сохранение результата эксперимента", experiment_report: "Анализ эксперимента",
  task_add: "Сохранение следующего шага", task_complete: "Завершение следующего шага", connectors_list: "Просмотр подключений",
  connector_configure: "Настройка сервиса", connector_read: "Получение данных сервиса", action_draft: "Подготовка внешнего действия",
  action_approve: "Разрешение внешнего действия", action_execute: "Выполнение внешнего действия", action_cancel: "Отмена внешнего действия", action_reconcile: "Проверка доставки",
  browser_open: "Открытие страницы", browser_inspect: "Просмотр страницы", browser_prepare: "Подготовка действия в браузере", browser_screenshot: "Снимок страницы",
  knowledge_publish: "Сохранение наблюдения о работодателе", knowledge_query: "Поиск сведений о работодателях", knowledge_verify: "Проверка целостности общей базы",
  knowledge_export: "Экспорт наблюдений", knowledge_import: "Получение наблюдений", author_trust: "Обновление доверия к автору",
  peer_register: "Подключение общей базы", peer_sync: "Обмен с общей базой", backup_create: "Создание резервной копии",
  credential_create: "Подготовка доступа к сервису", browser_fill_credential: "Ввод данных доступа", resource_save: "Сохранение ресурса",
  activity_record: "Сохранение события", statistics_report: "Подсчёт статистики", schedule_save: "Настройка расписания",
  schedule_toggle: "Пауза или продолжение расписания", schedule_run: "Запуск поручения по расписанию", employer_block: "Изменение исключения компании",
  employer_block_status: "Проверка исключения компании", repository_analyze: "Анализ проекта", strength_save: "Сохранение сведений об опыте",
  tactic_save: "Сохранение тактики", platform_save: "Сохранение площадки", account_save: "Сохранение состояния аккаунта",
  agent_status: "Просмотр хода работы", agent_cancel: "Остановка агента",
};
export function activitySummary(event, state = {}) {
  const run = list(state.agent?.runs).find((item) => item.id === event.related_id);
  if (event.kind?.startsWith("agent_")) {
    const target = run ? { kind: "run", id: run.id } : null;
    if (["agent_tool", "agent_tool_failed"].includes(event.kind)) {
      const name = event.tool || event.summary?.match(/^Agent tool:\s*(\S+)/)?.[1];
      return { text: `${event.kind === "agent_tool_failed" ? "Ошибка действия агента" : "Действие агента"}: ${toolDescriptions[name] || "Работа с поручением"}`, target };
    }
    const title = ({ agent_started: "Агент начал поручение", agent_queued: "Поручение в очереди", agent_completed: "Поручение завершено",
      agent_failed: "Поручение завершилось ошибкой", agent_cancelled: "Поручение остановлено", agent_cancelling: "Остановка запрошена",
      agent_step_limit: "Достигнут предел шагов" })[event.kind] || "Событие агента";
    const excerpt = goalExcerpt(run?.goal);
    return { text: excerpt ? `${title}: ${excerpt}` : title, target };
  }
  const schedule = list(state.schedules).find((item) => item.id === event.related_id);
  if (schedule) {
    const latest = list(state.schedule_runs).filter((item) => item.schedule_id === schedule.id && (!event.at || item.started_at <= event.at)).sort((a, b) => (b.started_at || "").localeCompare(a.started_at || ""))[0];
    return { text: `${schedule.name}: ${latest ? scheduleResult(latest, state).text : "результат обновлён"}`, target: latest ? { kind: "schedule_run", id: latest.id } : null };
  }
  const action = list(state.actions).find((item) => item.id === event.related_id);
  if (action) return { text: `${humanLabel(action.operation)}: ${label(action.status)}`, target: { kind: "action", id: action.id } };
  const resource = list(state.resources).find((item) => item.id === event.related_id);
  return { text: resource ? `${resource.name}: ${event.summary || "обновлено"}` : (event.summary || event.title || label(event.kind)).replaceAll("result changed", "результат обновлён"), target: null };
}
export const topicGoals = {
  search:
    "Продолжи поиск подходящей работы с учётом моих условий. Сам выбери подходящие источники, изучи вакансии и сохрани следующие шаги.",
  schedules:
    "Организуй расписание поиска работы с учётом моих условий. Выбери полезные регулярные поручения и объясни, когда они будут выполняться.",
  experiments:
    "Предложи и проведи подходящий эксперимент для моего поиска работы. Заранее зафиксируй гипотезу, варианты, метрику и окно наблюдения.",
  strengths:
    "Изучи факты моего опыта и доступные проекты. Найди сильные стороны, сохрани подтверждения и уточни неизвестное.",
  cv: "Подготовь правдивый вариант CV для моего поиска работы из проверенных фактов профиля. Сохрани источники и не добавляй неподтверждённый опыт.",
  employers:
    "Изучи подходящих работодателей, их вакансии и условия. Сохраняй наблюдения о компаниях с источниками; личные сведения не публикуй.",
  resources:
    "Сам выбери и организуй полезные ресурсы для моего поиска работы: источники, сервисы и материалы. Учитывай мои условия и бюджет.",
  accounts:
    "Проверь, какие аккаунты и сервисы нужны для моего поиска работы. Сам организуй регистрацию и подтверждение почты в рамках моих поручений; сообщи, если требуется моё действие.",
  repositories:
    "Проанализируй мои локальные репозитории как подтверждение опыта. Сохрани найденные факты и предложи сильные стороны; результаты остаются локальными.",
  tactics:
    "Оцени результаты моего поиска и предложи следующую тактику: гипотезу, действия и измеряемый результат. Сохрани её локально.",
};
