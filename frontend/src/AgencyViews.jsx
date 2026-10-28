import { t, getLocale } from "./i18n.js";
import { useEffect, useState } from "react";
import { Button, Input, TextArea, Typography } from "@heroui/react";
import {
  Panel,
  PageHeading,
  Empty,
  Icon,
  Status,
  Dialog,
  DetailAccordion,
  Timestamp,
} from "./ui.jsx";
import { BlurFade, NumberTicker } from "./magicui.jsx";
import { list, label, safeURL, formatDate, marketText, advisorText } from "./model.js";
import {
  stages,
  employerName,
  jobStage,
  jobLocation,
  jobLocationKey,
  jobSource,
  jobSourceKey,
  selectJobs,
  salaryLabel,
  groupLabel,
} from "./board.js";

export function SelectField({
  label: title,
  value,
  onChange,
  children,
  ...props
}) {
  return (
    <label className="select-field">
      <span>{title}</span>
      <select
        aria-label={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}
const itemText = (value) =>
  typeof value === "string"
    ? value
    : value?.text ||
      value?.requirement ||
      value?.title ||
      value?.reason ||
      JSON.stringify(value);
function EvidenceList({ items, empty = t("Пока нет подтверждённых данных."), systemCopy = false }) {
  return list(items).length ? (
    <ul className="evidence-list">
      {items.map((item, i) => (
        <li key={i}>
          {systemCopy ? advisorText(itemText(item)) : itemText(item)}
          {typeof item === "object" && list(item.evidence).length ? (
            <ul className="evidence-sources">
              {item.evidence.map((e, n) => (
                <li key={n}>
                  {e.text || e.excerpt || t("Факт из резюме")}
                  {safeURL(e.source) ? (
                    <a href={e.source} target="_blank" rel="noreferrer">
                      {" "}{t("· Источник")}</a>
                  ) : e.source || e.fact_id ? (
                    <details>
                      <summary className="cursor-pointer text-link">{t("Источник")}</summary>
                      {e.source ? <div>{e.source}</div> : null}
                      {e.fact_id ? <div>{t("Факт:")}{" "}{e.fact_id}</div> : null}
                    </details>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">{empty}</p>
  );
}
const filterOptions = (jobs, keyOf, labelOf) =>
  [...new Map(jobs.map((job) => [keyOf(job), labelOf(job)]))]
    .sort(([, a], [, b]) => a.localeCompare(b, getLocale()));

const companyTone = (name) => {
  let value = 0;
  for (const letter of String(name)) value = (value * 31 + letter.codePointAt(0)) >>> 0;
  return ["blue", "teal", "violet", "amber", "rose"][value % 5];
};
const initials = (name) => {
  const words = String(name).match(/[\p{L}\p{N}]+/gu) || [];
  return (words.length > 1
    ? `${Array.from(words[0])[0]}${Array.from(words.at(-1))[0]}`
    : Array.from(words[0] || "?").slice(0, 2).join("")
  ).toLocaleUpperCase(getLocale());
};
function CompanyAvatar({ name, className = "", tone = companyTone(name) }) {
  return (
    <span className={`company-avatar ${className}`} data-tone={tone} aria-hidden="true">
      {initials(name)}
    </span>
  );
}
const messageChannel = (message) => ({ email: t("Почта"), telegram: "Telegram", phone: t("Телефон") }[message.channel] || message.channel || t("Канал не указан"));
const messageSender = (message, job) => {
  const sender = message.source?.sender;
  if (typeof sender === "string" && sender.trim()) return sender;
  if (sender && typeof sender === "object") {
    const name = sender.name || [sender.first_name, sender.last_name].filter(Boolean).join(" ") || sender.username;
    if (name) return name;
  }
  if (message.direction === "outbound") return t("Вы");
  return job ? employerName(job) : t("Сообщение без вакансии");
};

function JobCard({
  job,
  state,
  onInspect,
  onCommand,
  pending,
  compact = false,
}) {
  const stage = jobStage(job, state.applications),
    company = employerName(job),
    recommendation = list(state.advisor?.recommendations).find(
      (r) => r.job_id === job.id,
    ),
    fit = recommendation?.assessment_status === "stale" ? "stale" : recommendation?.decision,
    reason = fit === "stale"
      ? t("Анализ нужно обновить")
      : fit === "reject"
        ? t("Не соответствует вашим условиям")
        : fit === "clarify"
          ? list(recommendation?.questions)[0] || t("Есть условия для уточнения")
          : (recommendation?.assessment_status === "fresh" && list(recommendation.agent_assessment?.reasons)[0]) || list(recommendation?.reasons)[0] || t("Откройте условия вакансии");
  return (
    <BlurFade className={`job-card ${compact ? "compact" : "job-row"}`} data-tone={companyTone(company)}>
      <div className="job-card-heading">
        <CompanyAvatar name={company} />
        <div className="job-card-identity">
          <p className="job-company">{company}</p>
          <p className="job-source">{jobSource(job)}</p>
        </div>
        <Status value={job.blocked ? "blocked" : stage} />
      </div>
      <div className="job-card-body">
        <button className="job-title" onClick={() => onInspect("job", job.id)}>
          {job.title || t("Вакансия без названия")}
        </button>
        <p className="job-salary">{salaryLabel(job)}</p>
        <div className="job-attributes">
          <span><Icon name={jobLocation(job) === t("Удалённо") ? "remote" : "location"} />{jobLocation(job)}</span>
          {job.remote === true && jobLocation(job) !== t("Удалённо") ? <span><Icon name="remote" />{t("Удалённо")}</span> : null}
        </div>
      </div>
      {!compact && recommendation ? (
        <div className="job-fit" data-fit={fit || "unknown"} data-verdict={fit || "unknown"}>
          <Icon name={fit === "consider" ? "check" : fit === "stale" ? "refresh" : "activity"} />
          <p>{advisorText(reason)}</p>
        </div>
      ) : null}
      <div className="job-card-footer">
        <Button variant="ghost" size="sm" onPress={() => onInspect("job", job.id)}>{t("Открыть вакансию")}<Icon name="next" />
        </Button>
        {stage === "new" ? (
          <Button
            variant="secondary"
            size="sm"
            isPending={pending === `save:${job.id}`}
            onPress={() => onCommand("pipeline_update", { job_id: job.id, stage: "saved" }, `save:${job.id}`)}
          >{t("Сохранить")}</Button>
        ) : null}
      </div>
    </BlurFade>
  );
}
export function SearchBoard({
  state,
  onInspect,
  onCommand,
  pending,
  onConditions,
}) {
  const [filters, setFilters] = useState({
      query: "",
      stage: "",
      location: "",
      source: "",
      remote: false,
    }),
    [mode, setMode] = useState("list"),
    [filtersOpen, setFiltersOpen] = useState(false);
  const filterCount = [filters.stage, filters.location, filters.source, filters.remote].filter(Boolean).length;
  const jobs = selectJobs(state, filters),
    all = list(state.jobs),
    set = (key, value) =>
      setFilters((previous) => ({ ...previous, [key]: value }));
  return (
    <>
      <PageHeading
        title={
          <span>{t("Вакансии")}{" "}<span className="count-badge">{all.length}</span>
          </span>
        }
      >
        <div className="view-switch" role="group" aria-label={t("Вид вакансий")}>
          {[
            ["list", t("Карточки")],
            ["board", t("Воронка")],
          ].map(([key, title]) => (
            <Button
              key={key}
              variant="ghost"
              size="sm"
              aria-pressed={mode === key}
              onPress={() => setMode(key)}
            >
              {title}
            </Button>
          ))}
        </div>
        <Button variant="outline" size="sm" onPress={onConditions}>
          <Icon name="settings" />{t("Условия поиска")}</Button>
      </PageHeading>
      <Panel className="board-panel search-results-panel">
        <div className="job-filters search-toolbar">
          <div className="search-input">
            <Icon name="discover" />
            <Input
              aria-label={t("Поиск вакансий")}
              placeholder={t("Должность, компания или навык")}
              value={filters.query}
              onChange={(e) => set("query", e.target.value)}
            />
          </div>
          <Button
            className="filter-toggle"
            variant={filterCount ? "secondary" : "outline"}
            size="sm"
            aria-label={t("Фильтры")}
            aria-expanded={filtersOpen}
            aria-controls="job-search-filters"
            onPress={() => setFiltersOpen(!filtersOpen)}
          >
            <Icon name="settings" />{t("Фильтры")}{filterCount ? <span className="filter-count">{filterCount}</span> : null}
          </Button>
        </div>
        {filtersOpen ? <div className="advanced-filters" id="job-search-filters">
          <SelectField
            label={t("Этап")}
            value={filters.stage}
            onChange={(value) => set("stage", value)}
          >
            <option value="">{t("Все этапы")}</option>
            {stages.map(([key, title]) => (
              <option key={key} value={key}>
                {t(title)}
              </option>
            ))}
          </SelectField>
          <SelectField
            label={t("Город")}
            value={filters.location}
            onChange={(value) => set("location", value)}
          >
            <option value="">{t("Все города")}</option>
            {filterOptions(all, jobLocationKey, jobLocation).map(([value, title]) => (
              <option key={value} value={value}>{title}</option>
            ))}
          </SelectField>
          <SelectField
            label={t("Источник")}
            value={filters.source}
            onChange={(value) => set("source", value)}
          >
            <option value="">{t("Все источники")}</option>
            {filterOptions(all, jobSourceKey, jobSource).map(([value, title]) => (
              <option key={value} value={value}>{title}</option>
            ))}
          </SelectField>
          <label className="remote-check">
            <input
              type="checkbox"
              checked={filters.remote}
              onChange={(e) => set("remote", e.target.checked)}
            />{t("Удалённо")}</label>
          {filterCount ? <Button variant="ghost" size="sm" onPress={() => setFilters((previous) => ({ ...previous, stage: "", location: "", source: "", remote: false }))}>{t("Сбросить")}</Button> : null}
        </div> : null}
        <p className="muted small board-result-count" aria-live="polite">{t("Показано")}{" "}{jobs.length}{" "}{t("из")}{" "}{all.length}
        </p>
        {!jobs.length ? (
          <Empty
            icon="search"
            title={
              all.length
                ? t("По этим условиям вакансий нет")
                : t("Начнём с вашей цели")
            }
            action={
              <Button variant="outline" onPress={all.length ? () => setFilters({ query: "", stage: "", location: "", source: "", remote: false }) : onConditions}>
                {all.length ? t("Сбросить фильтры") : t("Указать, какую работу ищу")}
              </Button>
            }
          >
            {all.length
              ? t("Измените поисковый запрос или фильтры.")
              : t("Передайте агенту резюме и расскажите, какую работу ищете. Подобранные вакансии появятся здесь.")}
          </Empty>
        ) : mode === "list" ? (
          <div className="job-list">
            {jobs.map((job) => (
              <JobCard
                key={job.id}
                {...{ job, state, onInspect, onCommand, pending }}
              />
            ))}
          </div>
        ) : (
          <div className="pipeline-board">
            {stages
              .filter(
                ([stage]) =>
                  !["accepted", "rejected", "withdrawn"].includes(stage) ||
                  jobs.some((j) => jobStage(j, state.applications) === stage),
              )
              .map(([stage, title]) => (
                <section className="pipeline-column" key={stage}>
                  <h3>
                    {t(title)}
                    <span>
                      {
                        jobs.filter(
                          (j) => jobStage(j, state.applications) === stage,
                        ).length
                      }
                    </span>
                  </h3>
                  {jobs
                    .filter((j) => jobStage(j, state.applications) === stage)
                    .map((job) => (
                      <JobCard
                        key={job.id}
                        compact
                        {...{ job, state, onInspect, onCommand, pending }}
                      />
                    ))}
                  {!jobs.some(
                    (j) => jobStage(j, state.applications) === stage,
                  ) ? (
                    <p className="column-empty">{t("Пока пусто")}</p>
                  ) : null}
                </section>
              ))}
          </div>
        )}
      </Panel>
      {list(state.messages).length ? (
        <a className="inbox-shortcut" href="#messages">
          <Icon name="activity" />
          <span>{t("Переписка")}{" "}<span className="muted">{list(state.messages).length}{" "}{t("сообщений")}</span></span>
          <Icon name="next" />
        </a>
      ) : null}
    </>
  );
}
export function ConversationBoard(props) {
  return (
    <>
      <PageHeading title={<span>{t("Переписка")}{" "}<span className="count-badge">{list(props.state.messages).length}</span></span>} />
      <ConversationPanel {...props} standalone />
    </>
  );
}
function ConversationPanel({ state, onInspect, onCommand, pending, standalone = false }) {
  const [scope, setScope] = useState("all"),
    [selected, setSelected] = useState(null),
    [jobId, setJobId] = useState(""),
    [read, setRead] = useState("");
  const messages = list(state.messages);
  const unassigned = messages.filter((message) => !message.job_id);
  const unread = messages.filter((message) => message.unread === true);
  const visible = scope === "unassigned" ? unassigned : scope === "unread" ? unread : messages;
  const selectedJob = selected && list(state.jobs).find((job) => job.id === selected.job_id);
  const selectedSender = selected ? messageSender(selected, selectedJob) : "";
  const update = async (changes) => {
    const result = await onCommand("conversation_update", {
      message_id: selected.id,
      ...changes,
    });
    if (result) setSelected(null);
  };
  return (
    <Panel
      className={`conversation-panel${standalone ? " is-standalone" : ""}`}
      id="search-inbox"
      tabIndex={-1}
      title={
        standalone ? undefined : <span>{t("Переписка")}{" "}<span className="count-badge">{messages.length}</span>
        </span>
      }
      action={
        <div className="view-switch" role="group" aria-label={t("Фильтр переписки")}>
          <button
            aria-pressed={scope === "all"}
            onClick={() => setScope("all")}
          >{t("Все сообщения")}</button>
          <button
            aria-pressed={scope === "unread"}
            onClick={() => setScope("unread")}
          >{t("Непрочитанные ·")}{" "}{unread.length}
          </button>
          <button
            aria-pressed={scope === "unassigned"}
            onClick={() => setScope("unassigned")}
          >{t("Не привязано ·")}{" "}{unassigned.length}
          </button>
        </div>
      }
    >
      {visible.length ? (
        <div className="event-list conversation-list">
          {visible.map((message) => {
            const job = list(state.jobs).find((entry) => entry.id === message.job_id),
              sender = messageSender(message, job),
              tone = companyTone(job ? employerName(job) : sender),
              subject = message.source?.subject || job?.title || (message.job_id ? t("Вакансия недоступна") : t("Без привязки к вакансии"));
            return (
              <article className="event-row conversation-row conversation-card" key={message.id} data-unread={message.unread === true} data-tone={tone}>
                <CompanyAvatar name={sender} tone={tone} className="conversation-avatar" />
                <div className="conversation-main">
                  <div className="conversation-card-header">
                    <p className="conversation-sender">{sender}</p>
                    <span className="conversation-time"><Timestamp value={message.occurred_at || message.created_at} /></span>
                  </div>
                  <div className="conversation-subject-line">
                    {message.unread ? <span className="unread-dot" aria-label={t("Не прочитано")} /> : null}
                    <button className="conversation-subject" onClick={() => { setSelected(message); setJobId(""); setRead(""); }}>
                      {subject}
                    </button>
                  </div>
                  <p className="preserve-lines conversation-preview">{message.text || t("Текст сообщения отсутствует")}</p>
                  <div className="conversation-card-footer">
                    <p className="conversation-meta">
                      <span className="channel-label" data-channel={message.channel}>{messageChannel(message)}</span>
                      <span>{message.direction === "inbound" ? t("Входящее") : message.direction === "outbound" ? t("Исходящее") : t("Направление не указано")}</span>
                      {message.unread ? <span>{t("Не прочитано")}</span> : message.read_at ? <span>{t("Прочитано")}</span> : null}
                    </p>
                    <Button className="conversation-open" variant="ghost" size="sm" aria-label={t("Управлять сообщением")} onPress={() => { setSelected(message); setJobId(""); setRead(""); }}>{t("Открыть")}<Icon name="next" />
                    </Button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <Empty
          title={
            scope === "unassigned"
              ? t("Непривязанных сообщений нет")
              : scope === "unread"
                ? t("Непрочитанных сообщений нет")
              : t("Сообщений пока нет")
          }
        >
          {scope === "unassigned"
            ? t("Все сообщения связаны с вакансиями.")
            : scope === "unread"
              ? t("Нет сообщений с отметкой «Не прочитано».")
            : t("Ответы компаний и другая переписка появятся здесь после проверки агентом.")}
        </Empty>
      )}
      <Dialog
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.source?.subject || selectedJob?.title || t("Сообщение")}
        size="md"
      >
        {selected ? (
          <>
          <div className="message-reader-header">
            <CompanyAvatar name={selectedSender} tone={companyTone(selectedJob ? employerName(selectedJob) : selectedSender)} />
            <div>
              <strong>{selectedSender}</strong>
              <p><Timestamp value={selected.occurred_at || selected.created_at} /> · {messageChannel(selected)}</p>
            </div>
          </div>
          <p className="message-reader-body preserve-lines">
            {selected.text || t("Текст сообщения отсутствует")}
          </p>
          <div className="message-reader-actions">
            {selected.job_id ? <Button variant="outline" size="sm" onPress={() => { setSelected(null); onInspect("job", selected.job_id); }}>{t("Открыть вакансию")}<Icon name="next" /></Button> : null}
            {selected.unread ? <Button variant="secondary" size="sm" isPending={pending === "conversation_update"} onPress={async () => {
              const result = await onCommand("conversation_update", { message_id: selected.id, read: true });
              if (result) setSelected(result);
            }}>{t("Отметить прочитанным")}</Button> : <span className="muted small">{selected.read_at ? t("Прочитано") : t("Сохранено")}</span>}
          </div>
          <DetailAccordion title={t("Связь и отметка прочтения")}>
          <form
            className="resume-form"
            onSubmit={(event) => {
              event.preventDefault();
              update({
                ...(jobId ? { job_id: jobId } : {}),
                ...(read ? { read: read === "read" } : {}),
              });
            }}
          >
            <p className="muted small">
              {selected.job_id
                ? t`Связано с вакансией: ${list(state.jobs).find((job) => job.id === selected.job_id)?.title || t("Вакансия недоступна")}`
                : t("Связь с вакансией не указана.")}
              {selected.unread
                ? t(" Не прочитано.")
                : selected.read_at
                  ? t(" Прочитано.")
                  : ""}
            </p>
            <SelectField
              label={t("Привязать к вакансии")}
              value={jobId}
              onChange={setJobId}
            >
              <option value="">{t("Оставить связь как есть")}</option>
              {list(state.jobs).map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title} · {employerName(job)}
                </option>
              ))}
            </SelectField>
            <SelectField label={t("Прочтение")} value={read} onChange={setRead}>
              <option value="">{t("Оставить как есть")}</option>
              <option value="read">{t("Отметить прочитанным")}</option>
              {selected.direction === "inbound" &&
              ["observed", "received", "read"].includes(selected.status) ? (
                <option value="unread">{t("Отметить непрочитанным")}</option>
              ) : null}
            </SelectField>
            <div className="inline-actions">
              <Button
                type="submit"
                variant="secondary"
                isDisabled={!jobId && !read}
                isPending={pending === "conversation_update"}
              >{t("Сохранить изменения")}</Button>
              {selected.job_id ? (
                <Button
                  type="button"
                  variant="ghost"
                  isDisabled={pending === "conversation_update"}
                  onPress={() => update({ unlink: true })}
                >{t("Убрать связь с вакансией")}</Button>
              ) : null}
            </div>
          </form>
          </DetailAccordion>
          </>
        ) : null}
      </Dialog>
    </Panel>
  );
}
export function RecommendationSummary({ state, onInspect, onConditions }) {
  const report = state.advisor,
    rows = list(report?.recommendations)
      .filter((r) => r.decision !== "reject")
      .slice(0, 3);
  if (!rows.length)
    return (
      <div className="setup-note">
        <Icon name="strengths" />
        <div>
          <h3>
            {report?.status === "needs_profile"
              ? t("Нужно познакомиться с вашим опытом")
              : t("Рекомендации появятся после анализа")}
          </h3>
          <p className="muted">
            {report?.status === "needs_profile"
              ? t("Загрузите резюме и задайте желаемые роли, формат работы и доход. Агент сопоставит сведения из резюме с требованиями вакансий.")
              : t("Агент сравнит вакансии, резюме и ваши условия. Основания и неизвестные условия будут видны в каждой рекомендации.")}
          </p>
          <div className="inline-actions">
            <a href="#cv">{t("Добавить резюме")}<Icon name="next" />
            </a>
            <button onClick={onConditions}>{t("Мои условия")}</button>
          </div>
        </div>
      </div>
    );
  return (
    <div className="recommendations">
      {rows.map((row) => (
        <button
          key={row.job_id}
          className="recommendation"
          onClick={() => onInspect("job", row.job_id)}
        >
          <span className="recommendation-rank">{row.rank}</span>
          <span>
            <strong>
              {list(state.jobs).find((j) => j.id === row.job_id)?.title ||
                row.job_id}
            </strong>
            <span className="muted">
              {advisorText(list(row.reasons)[0] || "Требует уточнения")}
            </span>
          </span>
          <Icon name="next" />
        </button>
      ))}
    </div>
  );
}
export function JobDetails({ job, state, onCommand, pending, onInspect }) {
  const application = list(state.applications).find((a) => a.job_id === job.id),
    recommendation = list(state.advisor?.recommendations).find(
      (r) => r.job_id === job.id,
    );
  const [stage, setStage] = useState(application?.stage || "saved"),
    [cv, setCV] = useState(application?.cv_id || ""),
    [next, setNext] = useState(application?.next_action || ""),
    [due, setDue] = useState(application?.due_at?.slice(0, 16) || ""),
    [note, setNote] = useState(""),
    [match, setMatch] = useState(null),
    [messageText, setMessageText] = useState(""),
    [messageDirection, setMessageDirection] = useState("inbound"),
    [messageChannel, setMessageChannel] = useState("email");
  useEffect(() => {
    setStage(application?.stage || "saved");
    setCV(application?.cv_id || "");
    setNext(application?.next_action || "");
    setDue(application?.due_at?.slice(0, 16) || "");
    setMatch(null);
  }, [job.id, application?.stage]);
  const literalMatch = match || recommendation?.cv_match;
  const recommendedCV =
    literalMatch?.recommended_cv_id ?? recommendation?.recommended_cv_id;
  const compare = async () => {
    const result = await onCommand("cv_match", { job_id: job.id });
    if (result) setMatch(result);
  };
  const save = () =>
    onCommand(
      "pipeline_update",
      {
        job_id: job.id,
        stage,
        cv_id: cv || null,
        note,
        next_action: next,
        due_at: due ? new Date(due).toISOString() : null,
      },
      `pipeline:${job.id}`,
    );
  return (
    <>
      <div className="job-detail-heading">
        <p className="job-company">{employerName(job)}</p>
        <h2>{job.title}</h2>
        {recommendation?.assessment_status === "fresh" ? (
          <Status value="active">{t("Анализ агента")}</Status>
        ) : recommendation?.assessment_status === "stale" ? (
          <Status value="partial">{t("Анализ нужно обновить")}</Status>
        ) : null}
        <p className="job-salary">{salaryLabel(job)}</p>
        <p className="muted">
          {jobLocation(job)} · {jobSource(job)}
        </p>
        {safeURL(job.url) ? (
          <a
            className="inline-link"
            href={safeURL(job.url)}
            target="_blank"
            rel="noreferrer"
          >{t("Открыть оригинал")}<Icon name="external" />
          </a>
        ) : null}
      </div>
      <div className="detail-grid">
        <section>
          <h3>{t("Почему подходит")}</h3>
          <EvidenceList items={recommendation?.reasons} systemCopy />
        </section>
        <section>
          <h3>{t("Что нужно уточнить")}</h3>
          <EvidenceList
            items={recommendation?.questions}
            systemCopy
            empty={t("Агент ещё не проверил неизвестные условия.")}
          />
        </section>
      </div>
      {recommendation ? (
        <div className="detail-grid">
          <section>
            <h3>{t("Факты из резюме")}</h3>
            <EvidenceList items={recommendation.matched_requirements} />
          </section>
          <section>
            <h3>{t("Пробелы в требованиях")}</h3>
            <EvidenceList items={recommendation.missing_requirements} />
          </section>
        </div>
      ) : null}
      <section className="detail-section">
        <div className="section-heading">
          <h3>{t("Резюме для этой вакансии")}</h3>
          <Button
            size="sm"
            variant="outline"
            onPress={compare}
            isPending={pending === "cv_match"}
          >{t("Сравнить варианты")}</Button>
        </div>
        {recommendedCV ? (
          <p className="small">{t("Предлагаемое резюме:")}{" "}
            <button
              className="inline-link"
              onClick={() => onInspect("cv", recommendedCV)}
            >
              {list(state.cvs).find((item) => item.id === recommendedCV)
                ?.name || t("Открыть вариант")}
            </button>
          </p>
        ) : null}
        {match ? (
          <>
            <p className="muted">{list(match.notes).map(advisorText).join(" ")}</p>
            {list(match.variants).map((variant) => (
              <div className="cv-comparison" key={variant.cv_id || variant.id}>
                <button
                  onClick={() => onInspect("cv", variant.cv_id || variant.id)}
                >
                  {variant.name ||
                    list(state.cvs).find(
                      (c) => c.id === (variant.cv_id || variant.id),
                    )?.name ||
                    variant.cv_id}
                </button>
                {recommendedCV === (variant.cv_id || variant.id) ? (
                  <span className="fit-badge">{t("Рекомендовано")}</span>
                ) : null}
                <EvidenceList
                  items={
                    variant.reasons ||
                    variant.matched_requirements ||
                    variant.matches
                  }
                />
                <p className="small muted">{t("Неподтверждённые требования:")}</p>
                <EvidenceList
                  items={variant.missing_requirements}
                  empty={t("Нет указанных пробелов.")}
                />
                <EvidenceList items={variant.notes} empty="" systemCopy />
              </div>
            ))}
          </>
        ) : (
          <p className="muted">{t("Сравнение опирается на подтверждённые факты из ваших версий резюме.")}</p>
        )}
      </section>
      <form
        className="detail-section"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <h3>{t("Следующий шаг")}</h3>
        <div className="detail-grid">
          <SelectField label={t("Этап поиска")} value={stage} onChange={setStage}>
            {stages
              .filter(([key]) => key !== "new")
              .map(([key, title]) => (
                <option value={key} key={key}>
                  {t(title)}
                </option>
              ))}
          </SelectField>
          <SelectField label={t("Вариант резюме")} value={cv} onChange={setCV}>
            <option value="">{t("Без резюме")}</option>
            {list(state.cvs).map((c) => (
              <option value={c.id} key={c.id}>
                {c.name || c.headline}
              </option>
            ))}
          </SelectField>
        </div>
        <label className="form-field">{t("Следующее действие")}<Input
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder={t("Например, уточнить условия у рекрутера")}
          />
        </label>
        <label className="form-field">{t("Срок")}<input
            className="native-input"
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </label>
        <label className="form-field">{t("Заметка")}<TextArea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
          />
        </label>
        <Button
          type="submit"
          variant="secondary"
          isPending={pending === `pipeline:${job.id}`}
        >{t("Сохранить этап и следующий шаг")}</Button>
      </form>
      {job.description ? (
        <DetailAccordion title={t("Описание вакансии")}>
          <p className="preserve-lines">{job.description}</p>
        </DetailAccordion>
      ) : null}
      <DetailAccordion title={t("Переписка и история")}>
        <form
          className="resume-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const result = await onCommand("conversation_record", {
              job_id: job.id,
              direction: messageDirection,
              channel: messageChannel,
              text: messageText,
            });
            if (result) setMessageText("");
          }}
        >
          <p className="muted">{t("Сохраните состоявшееся сообщение в истории вакансии.")}</p>
          <div className="detail-grid">
            <SelectField
              label={t("Направление")}
              value={messageDirection}
              onChange={setMessageDirection}
            >
              <option value="inbound">{t("Получено от работодателя")}</option>
              <option value="outbound">{t("Отправлено вами")}</option>
            </SelectField>
            <SelectField
              label={t("Канал")}
              value={messageChannel}
              onChange={setMessageChannel}
            >
              <option value="email">{t("Почта")}</option>
              <option value="telegram">Telegram</option>
              <option value="phone">{t("Телефон")}</option>
              <option value="other">{t("Другой")}</option>
            </SelectField>
          </div>
          <label className="form-field">{t("Текст сообщения")}<TextArea
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              required
              rows={3}
            />
          </label>
          <Button
            type="submit"
            variant="outline"
            isPending={pending === "conversation_record"}
          >{t("Сохранить запись")}</Button>
        </form>
        <EvidenceList
          items={list(state.messages)
            .filter((m) => m.job_id === job.id)
            .map(
              (m) =>
                `${formatDate(m.occurred_at || m.created_at)} · ${m.channel || ""} · ${m.text || m.summary || ""}`,
            )}
          empty={t("Переписки по этой вакансии пока нет.")}
        />
        <EvidenceList
          items={list(application?.history).map(
            (h) =>
              `${formatDate(h.at)} · ${label(h.stage)}${h.note ? ` · ${h.note}` : ""}`,
          )}
          empty={t("Этапы ещё не менялись.")}
        />
      </DetailAccordion>
    </>
  );
}

export function MarketSummary({ state }) {
  const report = state.market?.report,
    group = list(report?.salary_groups)[0],
    median = group?.midpoint?.median,
    count = report?.counts?.with_salary;
  return (
    <Panel
      className="market-summary"
      title={
        <span className="heading-with-icon">{t("Рынок")}<span
            title={t("Описательная статистика сохранённой выборки")}
            className="info-icon"
          >
            i
          </span>
        </span>
      }
      action={
        <span className="small muted">
          {state.demo
            ? t("Демо-данные")
            : report?.snapshot
              ? t("Снимок данных")
              : t("Нет выборки")}
        </span>
      }
    >
      <a href="#market" className="market-stat">
        <span className="muted">{t("Медиана предложений")}</span>
        {Number.isFinite(median) ? (
          <strong className="market-number">
            <NumberTicker value={median} />{" "}
            {group.currency === "RUB" ? "₽" : group.currency}
          </strong>
        ) : (
          <strong className="market-missing">{t("Пока нет данных")}</strong>
        )}
        <span className="muted market-context">
          {group
            ? `${report?.snapshot?.scope?.location || report?.snapshot?.scope?.region || t("Выборка")} · ${groupLabel(group)}`
            : t("Соберите вакансии для сравнения")}
        </span>
        <span className="market-count">
          <strong>
            <NumberTicker value={count || 0} />
          </strong>{" "}{t("вакансий с зарплатой")}</span>
      </a>
    </Panel>
  );
}
export function MarketBoard({ state, onCommand, pending }) {
  const [snapshot, setSnapshot] = useState(""),
    [report, setReport] = useState(null),
    [groupIndex, setGroupIndex] = useState("0"),
    [name, setName] = useState(""),
    [error, setError] = useState("");
  const current = report || state.market?.report,
    groups = list(current?.salary_groups),
    group = groups[Number(groupIndex)] || groups[0],
    coverage = current?.language_coverage,
    requestedLanguages = list(coverage?.requested),
    collectedLanguages = list(coverage?.collected),
    missingLanguages = list(coverage?.missing);
  const load = async (id) => {
    setSnapshot(id);
    setGroupIndex("0");
    const result = await onCommand("market_report", {
      snapshot_id: id || null,
    });
    if (result) setReport(result);
  };
  const create = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const result = await onCommand("market_snapshot", {
        name: name.trim(),
        job_ids: list(state.jobs).map((j) => j.id),
        scope: {},
        sources: list(state.resources)
          .map((r) => r.url)
          .filter(Boolean),
      });
      if (result) {
        setName("");
        await load(result.id || result.snapshot_id);
      }
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <>
      <PageHeading
        title={t("Рынок")}
        description={t("Сравнивайте реальные предложения с одинаковой валютой и периодом оплаты.")}
      />
      <Panel
        title={t("Рыночная выборка")}
        action={
          <SelectField label={t("Снимок")} value={snapshot} onChange={load}>
            <option value="">{t("Последний снимок")}</option>
            {list(state.market?.snapshots).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {formatDate(s.created_at)}
              </option>
            ))}
          </SelectField>
        }
      >
        {requestedLanguages.length || collectedLanguages.length ? (
          <div className="flex flex-col gap-2" role="region" aria-label={t("Языки поисковых запросов")}>
            <p className="small muted">{t`Выбранные языки запросов: ${requestedLanguages.join(", ") || t("без ограничений")}`}</p>
            <p className="small muted">{t`Поиск выполнен: ${collectedLanguages.join(", ") || t("пока нет")}`}</p>
            {missingLanguages.length ? <p className="small" role="status">{t`Ещё не выполнен поиск: ${missingLanguages.join(", ")}`}</p> : null}
            <p className="small muted">{t("Это языки поисковых запросов. Язык и требования каждой вакансии сохраняются в оригинале.")}</p>
          </div>
        ) : null}
        {!current || !current.counts?.unique_jobs ? (
          <Empty icon="market" title={t("Сопоставимой выборки пока нет")}>{t("Сначала соберите вакансии с помощью своего MCP-агента, затем сохраните снимок рынка. Мы покажем объём выборки, источники и неизвестные условия.")}</Empty>
        ) : (
          <>
            <div className="market-metrics">
              {[
                [t("Наблюдения"), current.counts.observations],
                [t("Уникальные вакансии"), current.counts.unique_jobs],
                [t("С зарплатой"), current.counts.with_salary],
                [t("Без зарплаты"), current.counts.missing_salary],
              ].map(([title, value]) => (
                <div key={title}>
                  <span className="muted">{title}</span>
                  <strong>
                    <NumberTicker value={value || 0} />
                  </strong>
                </div>
              ))}
            </div>
            <SelectField
              label={t("Сопоставимая группа оплаты")}
              value={groupIndex}
              onChange={setGroupIndex}
            >
              {groups.map((g, i) => (
                <option key={i} value={String(i)}>
                  {groupLabel(g)}
                </option>
              ))}
            </SelectField>
            {group ? (
              <div className="salary-distribution">
                {[
                  [t("Нижняя граница"), group.lower],
                  [t("Середина диапазона"), group.midpoint],
                  [t("Верхняя граница"), group.upper],
                ].map(([title, stats]) => (
                  <div key={title}>
                    <p className="muted">{title}</p>
                    <strong>
                      {Number.isFinite(stats?.median)
                        ? stats.median.toLocaleString(getLocale())
                        : "—"}
                    </strong>
                    <p className="small muted">{t("Медиана ·")}{" "}{stats?.n || 0}{" "}{t("наблюдений")}</p>
                    <p className="small">
                      25–75%: {stats?.p25?.toLocaleString(getLocale()) ?? "—"} –{" "}
                      {stats?.p75?.toLocaleString(getLocale()) ?? "—"}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">{t("Нет сопоставимых зарплат. Неизвестные валюты и периоды не объединяются.")}</p>
            )}
            <div className="detail-grid">
              {[
                [t("Города"), "locations"],
                [t("Формат работы"), "work_formats"],
                [t("Источники"), "sources"],
                [t("Требования"), "requirements"],
              ].map(([title, key]) => (
                <section key={key}>
                  <h3>{title}</h3>
                  <div className="distribution-list">
                    {list(current.distributions?.[key])
                      .slice(0, 8)
                      .map((d, i) => (
                        <div key={i}>
                          <span>
                            {key === "work_formats"
                              ? {
                                  remote: t("Удалённо"),
                                  hybrid: t("Гибрид"),
                                  office: t("Офис"),
                                  onsite: t("Офис"),
                                  unknown: t("Не указан"),
                                }[d.label] || d.label
                              : d.label}
                          </span>
                          <strong>{d.count}</strong>
                        </div>
                      ))}
                  </div>
                </section>
              ))}
            </div>
          </>
        )}
      </Panel>
      <Panel>
        <p className="muted small">{t("Статистика описывает сохранённую выборку, а не весь рынок.")}{groups.some((entry) => entry.small_sample)
            ? t(" В группах меньше 5 вакансий показатели неустойчивы.")
            : ""}
          {groups.some(
            (entry) =>
              entry.gross == null ||
              !entry.currency ||
              entry.currency === "unknown" ||
              !["month", "year", "hour", "week", "day"].includes(entry.period),
          )
            ? t(" Есть предложения с неизвестной валютой, периодом оплаты или налогами.")
            : ""}
          {current?.counts?.invalid_salary
            ? t` Некорректные зарплаты исключены: ${current.counts.invalid_salary}.`
            : ""}
          {snapshot && current && !current.snapshot
            ? t(" Запрошенный снимок не найден.")
            : ""}
        </p>
        <DetailAccordion title={t("Как рассчитана статистика")}>
          <p>
            {typeof current?.methodology === "string"
              ? t(current.methodology)
              : t("Статистика описывает только собранные вакансии и не представляет весь рынок труда.")}
          </p>
          <EvidenceList
            items={list(current?.limitations).map(marketText)}
            empty={t("Для оценки покрытия ещё нужны вакансии и источники.")}
          />
          {current?.snapshot ? (
            <p className="muted">{t("Снимок:")}{" "}{current.snapshot.name} ·{" "}
              <Timestamp value={current.snapshot.created_at} />{" "}{t("· Дубликаты:")}{" "}
              {current.counts?.duplicates || 0}{" "}{t("· Некорректные зарплаты:")}{" "}
              {current.counts?.invalid_salary || 0}
            </p>
          ) : null}
          <div className="source-links">
            {list(current?.snapshot?.sources).map((s, i) => (
              <span key={i}>
                {safeURL(typeof s === "string" ? s : s.url) ? (
                  <a
                    href={typeof s === "string" ? s : s.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {typeof s === "string" ? s : s.name || s.url}
                    <Icon name="external" />
                  </a>
                ) : (
                  itemText(s)
                )}
              </span>
            ))}
          </div>
        </DetailAccordion>
      </Panel>
      <Panel title={t("Сохранить текущую выборку")}>
        <form className="snapshot-form" onSubmit={create}>
          <label className="form-field">{t("Название снимка")}<Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder={t("Например, руководители логистики · октябрь")}
            />
          </label>
          <Button
            type="submit"
            variant="secondary"
            isPending={pending === "market_snapshot"}
            isDisabled={!list(state.jobs).length}
          >{t("Сохранить")}{" "}{list(state.jobs).length}{" "}{t("вакансий")}</Button>
        </form>
        {error ? <p role="alert">{error}</p> : null}
      </Panel>
    </>
  );
}

export function ResumeBoard({
  state,
  onInspect,
  onRefresh,
  onDownload,
  pending: downloadPending,
}) {
  const [file, setFile] = useState(null),
    [name, setName] = useState(""),
    [language, setLanguage] = useState("ru"),
    [pending, setPending] = useState(false),
    [message, setMessage] = useState("");
  async function upload(e) {
    e.preventDefault();
    if (!file) return;
    setPending(true);
    setMessage("");
    try {
      if (file.size > 10 * 1024 * 1024)
        throw new Error(t("Файл должен быть не больше 10 МБ."));
      const file_base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const response = await fetch("/api/resume", {
        method: "POST",
        headers: {
          "X-Worklife-Client": "local",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name || file.name,
          filename: file.name,
          language,
          file_base64,
        }),
      });
      const result = await response.json();
      if (!response.ok || result.ok === false)
        throw new Error(
          typeof result.error === "string"
            ? result.error
            : t("Не удалось импортировать резюме."),
        );
      await onRefresh();
      setMessage(t("Резюме импортировано. Оно доступно в списке вариантов."));
      setFile(null);
      setName("");
      e.target.reset();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPending(false);
    }
  }
  const importForm = (
    <form onSubmit={upload} className="resume-form">
      <label className="file-drop">
        <Icon name="cv" />
        <strong>{file ? file.name : t("Выберите файл резюме")}</strong>
        <span>{t("TXT, Markdown, PDF или DOCX")}</span>
        <input
          type="file"
          accept=".txt,.md,.pdf,.docx"
          aria-label={t("Файл резюме")}
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          required
        />
      </label>
      <label className="form-field">{t("Название версии")}<Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("Основное резюме")}
        />
      </label>
      <SelectField label={t("Язык")} value={language} onChange={setLanguage}>
        <option value="ru">{t("Русский")}</option>
        <option value="en">English</option>
        <option value="it">Italiano</option>
        <option value="fr">Français</option>
      </SelectField>
      <Button
        type="submit"
        variant="secondary"
        isPending={pending}
        isDisabled={!file}
      >{t("Импортировать")}</Button>
    </form>
  );
  return (
    <>
      <PageHeading
        title={t("Резюме")}
        description={t("Ваш опыт, подтверждённые факты и версии под разные вакансии.")}
      />
      {list(state.cvs).length ? (
        <Panel title={t`Варианты резюме · ${list(state.cvs).length}`}>
          <div className="cv-list">
            {state.cvs.map((cv) => (
              <BlurFade key={cv.id} className="cv-row">
                <span className="icon-circle">
                  <Icon name="cv" />
                </span>
                <div>
                  <h3>{cv.name || cv.headline || t("Резюме")}</h3>
                  <p className="muted">
                    {cv.language || t("Язык не указан")} · {list(cv.facts).length}{" "}{t("фактов ·")}{" "}{formatDate(cv.created_at)}
                  </p>
                </div>
                {cv.original_filename || cv.original_path ? (
                  <Button
                    variant="outline"
                    isPending={downloadPending === "download:original"}
                    onPress={() => onDownload(cv.id, "original")}
                  >{t("Оригинал")}</Button>
                ) : null}
                <Button
                  variant="outline"
                  onPress={() => onInspect("cv", cv.id)}
                >{t("Открыть")}<Icon name="next" />
                </Button>
              </BlurFade>
            ))}
          </div>
        </Panel>
      ) : null}
      {list(state.cvs).length ? (
        <DetailAccordion title={t("Добавить резюме")}>{importForm}</DetailAccordion>
      ) : (
        <Panel title={t("Добавить резюме")}>{importForm}</Panel>
      )}
      {message ? <p role="status">{message}</p> : null}
    </>
  );
}

export function CareerEvents({ state, onCommand, onInspect, pending }) {
  const [form, setForm] = useState(null),
    [job, setJob] = useState(""),
    [date, setDate] = useState(""),
    [notes, setNotes] = useState(""),
    [amount, setAmount] = useState(""),
    [currency, setCurrency] = useState("RUB"),
    [meeting, setMeeting] = useState(""),
    [brief, setBrief] = useState(null),
    [tax, setTax] = useState("unknown"),
    [remote, setRemote] = useState("unknown"),
    [hours, setHours] = useState(""),
    [startDate, setStartDate] = useState(""),
    [incomeDate, setIncomeDate] = useState("");
  async function save(e) {
    e.preventDefault();
    const result = await onCommand(
      form === "interview" ? "interview_save" : "offer_save",
      form === "interview"
        ? {
            job_id: job,
            scheduled_at: new Date(date).toISOString(),
            notes,
            meeting_url: meeting,
          }
        : {
            job_id: job,
            terms: {
              salary_min: Number(amount),
              salary_max: Number(amount),
              currency,
              salary_period: "month",
              salary_gross: tax === "unknown" ? null : tax === "gross",
              remote: remote === "unknown" ? null : remote === "yes",
              ...(hours ? { hours: Number(hours) } : {}),
              ...(startDate ? { start_date: startDate } : {}),
              ...(incomeDate ? { income_date: incomeDate } : {}),
            },
            notes,
          },
    );
    if (result) setForm(null);
  }
  return (
    <>
      <Panel
        title={t("Интервью и офферы")}
        action={
          <div className="inline-actions">
            <Button
              variant="outline"
              size="sm"
              isDisabled={!list(state.jobs).length}
              onPress={() => {
                setForm("interview");
                setJob(list(state.jobs)[0]?.id || "");
              }}
            >{t("Добавить интервью")}</Button>
            <Button
              variant="outline"
              size="sm"
              isDisabled={!list(state.jobs).length}
              onPress={() => {
                setForm("offer");
                setJob(list(state.jobs)[0]?.id || "");
              }}
            >{t("Добавить оффер")}</Button>
          </div>
        }
      >
        {!list(state.interviews).length && !list(state.offers).length ? (
          <Empty icon="schedules" title={t("Переговоры ещё впереди")}>{t("Сохраните вакансии, чтобы планировать интервью и сравнивать полученные предложения.")}</Empty>
        ) : (
          <div className="event-list">
            {[
              ...list(state.interviews).map((e) => ({
                ...e,
                kind: "interview",
              })),
              ...list(state.offers).map((e) => ({ ...e, kind: "offer" })),
            ].map((event) => (
              <div className="event-row" key={event.id}>
                <Icon
                  name={event.kind === "interview" ? "schedules" : "search"}
                />
                <div>
                  <button onClick={() => onInspect("job", event.job_id)}>
                    {list(state.jobs).find((j) => j.id === event.job_id)
                      ?.title || event.job_id}
                  </button>
                  <p className="muted">
                    {event.kind === "interview"
                      ? t`Интервью · ${formatDate(event.scheduled_at)}`
                      : t`Оффер · ${salaryLabel(event.terms || {})}`}
                  </p>
                  {event.notes ? <p>{event.notes}</p> : null}
                  {safeURL(event.meeting_url) ? (
                    <a
                      href={event.meeting_url}
                      target="_blank"
                      rel="noreferrer"
                    >{t("Ссылка на встречу")}</a>
                  ) : null}
                </div>
                <div className="event-actions">
                  <Status value={event.status} />
                  {event.kind === "interview" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      isPending={pending === "interview_brief"}
                      onPress={async () => {
                        const result = await onCommand("interview_brief", {
                          job_id: event.job_id,
                        });
                        if (result) setBrief(result);
                      }}
                    >{t("Подготовиться")}</Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
        {list(state.offers).length ? (
          <DetailAccordion title={t("Сравнение офферов")}>
            <p className="muted">{t("Сравнение учитывает только сохранённые условия и ваши ограничения. Валюты, периоды оплаты и налоги рассматриваются отдельно.")}</p>
            <div className="offer-grid">
              {list(state.offer_comparison?.offers).length
                ? state.offer_comparison.offers.map((offer) => (
                    <div key={offer.offer_id}>
                      <h3>
                        {
                          list(state.jobs).find((j) => j.id === offer.job_id)
                            ?.title
                        }
                      </h3>
                      <strong>{salaryLabel(offer.terms || {})}</strong>
                      <p className="small muted">
                        {groupLabel(offer.salary || {})}
                      </p>
                      <p className="offer-decision">
                        {
                          {
                            consider: t("Соответствует заданным условиям"),
                            clarify: t("Нужно уточнить условия"),
                            reject: t("Есть несоответствие условиям"),
                          }[offer.decision]
                        }
                      </p>
                      <EvidenceList items={offer.reasons} systemCopy />
                      <h4>{t("Вопросы к работодателю")}</h4>
                      <EvidenceList
                        items={offer.questions}
                        systemCopy
                        empty={t("Неизвестных условий по заданным критериям нет.")}
                      />
                    </div>
                  ))
                : state.offers.map((offer) => (
                    <div key={offer.id}>
                      <h3>
                        {
                          list(state.jobs).find((j) => j.id === offer.job_id)
                            ?.title
                        }
                      </h3>
                      <strong>{salaryLabel(offer.terms || {})}</strong>
                      <p>
                        {offer.notes || t("Дополнительные условия не указаны")}
                      </p>
                    </div>
                  ))}
            </div>
          </DetailAccordion>
        ) : null}
      </Panel>
      <Dialog
        open={!!form}
        onClose={() => setForm(null)}
        title={form === "interview" ? t("Добавить интервью") : t("Добавить оффер")}
      >
        <form className="resume-form" onSubmit={save}>
          <SelectField label={t("Вакансия")} value={job} onChange={setJob}>
            {list(state.jobs).map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </SelectField>
          {form === "interview" ? (
            <>
              <label className="form-field">{t("Дата и время")}<input
                  className="native-input"
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                />
              </label>
              <label className="form-field">{t("Ссылка на встречу")}<Input
                  type="url"
                  value={meeting}
                  onChange={(e) => setMeeting(e.target.value)}
                />
              </label>
            </>
          ) : (
            <div className="detail-grid">
              <label className="form-field">{t("Зарплата в месяц")}<Input
                  type="number"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </label>
              <SelectField
                label={t("Валюта")}
                value={currency}
                onChange={setCurrency}
              >
                {["RUB", "USD", "EUR"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </SelectField>
              <SelectField label={t("Налоги")} value={tax} onChange={setTax}>
                <option value="unknown">{t("Не указано")}</option>
                <option value="gross">{t("До налогов")}</option>
                <option value="net">{t("На руки")}</option>
              </SelectField>
              <SelectField
                label={t("Удалённая работа")}
                value={remote}
                onChange={setRemote}
              >
                <option value="unknown">{t("Не указано")}</option>
                <option value="yes">{t("Да")}</option>
                <option value="no">{t("Нет")}</option>
              </SelectField>
              <label className="form-field">{t("Часов в неделю")}<Input
                  type="number"
                  min="0"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                />
              </label>
              <label className="form-field">{t("Дата выхода")}<input
                  className="native-input"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </label>
              <label className="form-field">{t("Первая выплата")}<input
                  className="native-input"
                  type="date"
                  value={incomeDate}
                  onChange={(e) => setIncomeDate(e.target.value)}
                />
              </label>
            </div>
          )}
          <label className="form-field">{t("Заметки")}<TextArea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <Button
            type="submit"
            variant="secondary"
            isPending={pending === "interview_save" || pending === "offer_save"}
          >{t("Сохранить")}</Button>
        </form>
      </Dialog>
      <Dialog
        open={!!brief}
        onClose={() => setBrief(null)}
        title={t("Подготовка к интервью")}
      >
        {brief ? (
          <>
            <h3>{brief.job?.title}</h3>
            <h4>{t("Вопросы работодателю")}</h4>
            <EvidenceList items={brief.questions_for_employer} systemCopy />
            <h4>{t("Примеры из опыта")}</h4>
            {list(brief.preparation).map((item, i) => (
              <div className="preparation-item" key={i}>
                <strong>{item.requirement}</strong>
                <p className="muted">{t(item.prompt)}</p>
              </div>
            ))}
            <h4>{t("Факты из резюме")}</h4>
            <EvidenceList items={brief.evidence} />
            <EvidenceList items={brief.notes} systemCopy />
          </>
        ) : null}
      </Dialog>
    </>
  );
}
