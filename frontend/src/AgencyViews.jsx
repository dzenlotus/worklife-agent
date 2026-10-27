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
import { list, label, safeURL, formatDate } from "./model.js";
import {
  stages,
  employerName,
  jobStage,
  jobLocation,
  jobSource,
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
function EvidenceList({ items, empty = "Пока нет подтверждённых данных." }) {
  return list(items).length ? (
    <ul className="evidence-list">
      {items.map((item, i) => (
        <li key={i}>
          {itemText(item)}
          {typeof item === "object" && list(item.evidence).length ? (
            <ul className="evidence-sources">
              {item.evidence.map((e, n) => (
                <li key={n}>
                  {e.text || e.excerpt || "Факт из резюме"}
                  {safeURL(e.source) ? (
                    <a href={e.source} target="_blank" rel="noreferrer">
                      {" "}· Источник
                    </a>
                  ) : e.source || e.fact_id ? (
                    <details>
                      <summary className="cursor-pointer text-link">
                        Источник
                      </summary>
                      {e.source ? <div>{e.source}</div> : null}
                      {e.fact_id ? <div>Факт: {e.fact_id}</div> : null}
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
const unique = (values) => [...new Set(values)].sort();

function JobCard({
  job,
  state,
  onInspect,
  onCommand,
  pending,
  compact = false,
}) {
  const stage = jobStage(job, state.applications),
    recommendation = list(state.advisor?.recommendations).find(
      (r) => r.job_id === job.id,
    );
  return (
    <BlurFade className={`job-card ${compact ? "compact" : "job-row"}`}>
      <div className="job-card-main">
        {compact ? (
          <div className="job-company">
            <Icon name="employers" />
            {employerName(job)}
          </div>
        ) : null}
        <button className="job-title" onClick={() => onInspect("job", job.id)}>
          {job.title || "Вакансия без названия"}
        </button>
        {compact ? <p className="job-salary">{salaryLabel(job)}</p> : null}
        <p className="muted job-meta">
          {!compact ? (
            <>
              <span className="job-company">{employerName(job)}</span> ·{" "}
            </>
          ) : null}
          {jobLocation(job)} · {jobSource(job)}
        </p>
        {recommendation ? (
          <p className="job-reason">
            <Icon
              name={recommendation.decision === "reject" ? "activity" : "check"}
            />
            {list(recommendation.reasons)[0] || "Нужны уточнения"}
          </p>
        ) : null}
      </div>
      <div className="job-actions">
        {!compact ? <p className="job-salary">{salaryLabel(job)}</p> : null}
        <Status value={job.blocked ? "blocked" : stage} />
        {compact ? (
          <Button
            variant="outline"
            size="sm"
            onPress={() => onInspect("job", job.id)}
          >
            Подробнее
            <Icon name="next" />
          </Button>
        ) : null}
        {stage === "new" ? (
          <Button
            variant="secondary"
            size="sm"
            isPending={pending === `save:${job.id}`}
            onPress={() =>
              onCommand(
                "pipeline_update",
                { job_id: job.id, stage: "saved" },
                `save:${job.id}`,
              )
            }
          >
            Сохранить
          </Button>
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
  useEffect(() => {
    const focusInbox = () => {
      if (location.hash !== "#search/inbox") return;
      const inbox = document.getElementById("search-inbox");
      inbox?.scrollIntoView({ block: "start" });
      inbox?.focus({ preventScroll: true });
    };
    focusInbox();
    window.addEventListener("hashchange", focusInbox);
    return () => window.removeEventListener("hashchange", focusInbox);
  }, []);
  const [filters, setFilters] = useState({
      query: "",
      stage: "",
      location: "",
      source: "",
      remote: false,
    }),
    [mode, setMode] = useState("list");
  const jobs = selectJobs(state, filters),
    all = list(state.jobs),
    set = (key, value) =>
      setFilters((previous) => ({ ...previous, [key]: value }));
  return (
    <>
      <PageHeading
        title={
          <span>
            Вакансии <span className="count-badge">{all.length}</span>
          </span>
        }
      >
        <div className="view-switch" role="group" aria-label="Вид вакансий">
          {[
            ["list", "Список"],
            ["board", "Воронка"],
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
          <Icon name="settings" />
          Условия поиска
        </Button>
      </PageHeading>
      <Panel className="board-panel search-results-panel">
        <div className="job-filters search-toolbar">
          <div className="search-input">
            <Icon name="discover" />
            <Input
              aria-label="Поиск вакансий"
              placeholder="Должность, компания или навык"
              value={filters.query}
              onChange={(e) => set("query", e.target.value)}
            />
          </div>
          <SelectField
            label="Этап"
            value={filters.stage}
            onChange={(value) => set("stage", value)}
          >
            <option value="">Все этапы</option>
            {stages.map(([key, title]) => (
              <option key={key} value={key}>
                {title}
              </option>
            ))}
          </SelectField>
          <SelectField
            label="Город"
            value={filters.location}
            onChange={(value) => set("location", value)}
          >
            <option value="">Все города</option>
            {unique(all.map(jobLocation)).map((v) => (
              <option key={v}>{v}</option>
            ))}
          </SelectField>
          <SelectField
            label="Источник"
            value={filters.source}
            onChange={(value) => set("source", value)}
          >
            <option value="">Все источники</option>
            {unique(all.map(jobSource)).map((v) => (
              <option key={v}>{v}</option>
            ))}
          </SelectField>
          <label className="remote-check">
            <input
              type="checkbox"
              checked={filters.remote}
              onChange={(e) => set("remote", e.target.checked)}
            />
            Удалённо
          </label>
        </div>
        <p className="muted small board-result-count" aria-live="polite">
          Показано {jobs.length} из {all.length}
        </p>
        {!jobs.length ? (
          <Empty
            icon="search"
            title={
              all.length
                ? "По этим условиям вакансий нет"
                : "Начнём с вашей цели"
            }
            action={
              <Button variant="outline" onPress={onConditions}>
                {all.length
                  ? "Изменить условия поиска"
                  : "Указать, какую работу ищу"}
              </Button>
            }
          >
            {all.length
              ? "Измените поисковый запрос или фильтры."
              : "Передайте агенту резюме и расскажите, какую работу ищете. Подобранные вакансии появятся здесь."}
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
                    {title}
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
                    <p className="column-empty">Пока пусто</p>
                  ) : null}
                </section>
              ))}
          </div>
        )}
      </Panel>
      <ConversationPanel {...{ state, onInspect, onCommand, pending }} />
    </>
  );
}
function ConversationPanel({ state, onInspect, onCommand, pending }) {
  const [scope, setScope] = useState("all"),
    [selected, setSelected] = useState(null),
    [jobId, setJobId] = useState(""),
    [read, setRead] = useState("");
  const messages = list(state.messages);
  const unassigned = messages.filter((message) => !message.job_id);
  const visible = scope === "unassigned" ? unassigned : messages;
  const update = async (changes) => {
    const result = await onCommand("conversation_update", {
      message_id: selected.id,
      ...changes,
    });
    if (result) setSelected(null);
  };
  return (
    <Panel
      className="conversation-panel"
      id="search-inbox"
      tabIndex={-1}
      title={
        <span>
          Переписка <span className="count-badge">{messages.length}</span>
        </span>
      }
      action={
        <div className="view-switch" role="group" aria-label="Фильтр переписки">
          <button
            aria-pressed={scope === "all"}
            onClick={() => setScope("all")}
          >
            Все сообщения
          </button>
          <button
            aria-pressed={scope === "unassigned"}
            onClick={() => setScope("unassigned")}
          >
            Не привязано · {unassigned.length}
          </button>
        </div>
      }
    >
      {visible.length ? (
        <div className="event-list conversation-list">
          {visible.map((message) => {
            const job = list(state.jobs).find(
              (entry) => entry.id === message.job_id,
            );
            return (
              <article className="event-row conversation-row" key={message.id}>
                <div className="conversation-main">
                  <div className="conversation-heading">
                    {job ? (
                      <button onClick={() => onInspect("job", job.id)}>
                        {job.title}
                      </button>
                    ) : (
                      <span className="conversation-subject">
                        {message.job_id
                          ? "Вакансия недоступна"
                          : "Без вакансии"}
                      </span>
                    )}
                    <span className="muted small conversation-time">
                      <Timestamp
                        value={message.occurred_at || message.created_at}
                      />
                    </span>
                  </div>
                  <p className="preserve-lines conversation-preview">
                    {message.text || "Текст сообщения отсутствует"}
                  </p>
                  <p className="muted small conversation-meta">
                    {{
                      email: "Почта",
                      telegram: "Telegram",
                      phone: "Телефон",
                    }[message.channel] || message.channel || "Канал не указан"}
                    {message.direction === "inbound"
                      ? " · Входящее"
                      : message.direction === "outbound"
                        ? " · Исходящее"
                        : ""}
                    {message.unread
                      ? " · Не прочитано"
                      : message.read_at
                        ? " · Прочитано"
                        : null}
                  </p>
                </div>
                <Button
                  className="conversation-open"
                  variant="ghost"
                  size="sm"
                  aria-label="Управлять сообщением"
                  onPress={() => {
                    setSelected(message);
                    setJobId("");
                    setRead("");
                  }}
                >
                  Открыть <Icon name="next" />
                </Button>
              </article>
            );
          })}
        </div>
      ) : (
        <Empty
          title={
            scope === "unassigned"
              ? "Непривязанных сообщений нет"
              : "Сообщений пока нет"
          }
        >
          {scope === "unassigned"
            ? "Все сообщения связаны с вакансиями."
            : "Ответы компаний и другая переписка появятся здесь после проверки агентом."}
        </Empty>
      )}
      <Dialog
        open={!!selected}
        onClose={() => setSelected(null)}
        title="Сохранённое сообщение"
        size="md"
      >
        {selected ? (
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
            <p className="small preserve-lines break-words">
              {selected.text || "Текст сообщения отсутствует"}
            </p>
            <p className="muted small">
              {selected.job_id
                ? `Связано с вакансией: ${list(state.jobs).find((job) => job.id === selected.job_id)?.title || "Вакансия недоступна"}`
                : "Связь с вакансией не указана."}
              {selected.unread
                ? " Не прочитано."
                : selected.read_at
                  ? " Прочитано."
                  : ""}
            </p>
            <SelectField
              label="Привязать к вакансии"
              value={jobId}
              onChange={setJobId}
            >
              <option value="">Оставить связь как есть</option>
              {list(state.jobs).map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title} · {employerName(job)}
                </option>
              ))}
            </SelectField>
            <SelectField label="Прочтение" value={read} onChange={setRead}>
              <option value="">Оставить как есть</option>
              <option value="read">Отметить прочитанным</option>
              {selected.direction === "inbound" &&
              ["observed", "received", "read"].includes(selected.status) ? (
                <option value="unread">Отметить непрочитанным</option>
              ) : null}
            </SelectField>
            <div className="inline-actions">
              <Button
                type="submit"
                variant="secondary"
                isDisabled={!jobId && !read}
                isPending={pending === "conversation_update"}
              >
                Сохранить изменения
              </Button>
              {selected.job_id ? (
                <Button
                  type="button"
                  variant="ghost"
                  isDisabled={pending === "conversation_update"}
                  onPress={() => update({ unlink: true })}
                >
                  Убрать связь с вакансией
                </Button>
              ) : null}
            </div>
          </form>
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
              ? "Нужно познакомиться с вашим опытом"
              : "Рекомендации появятся после анализа"}
          </h3>
          <p className="muted">
            {report?.status === "needs_profile"
              ? "Загрузите резюме и задайте желаемые роли, формат работы и доход. Агент сопоставит сведения из резюме с требованиями вакансий."
              : "Агент сравнит вакансии, резюме и ваши условия. Основания и неизвестные условия будут видны в каждой рекомендации."}
          </p>
          <div className="inline-actions">
            <a href="#cv">
              Добавить резюме
              <Icon name="next" />
            </a>
            <button onClick={onConditions}>Мои условия</button>
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
              {list(row.reasons)[0] || "Требует уточнения"}
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
          <Status value="active">Анализ агента</Status>
        ) : recommendation?.assessment_status === "stale" ? (
          <Status value="partial">Анализ нужно обновить</Status>
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
          >
            Открыть оригинал
            <Icon name="external" />
          </a>
        ) : null}
      </div>
      <div className="detail-grid">
        <section>
          <h3>Почему подходит</h3>
          <EvidenceList items={recommendation?.reasons} />
        </section>
        <section>
          <h3>Что нужно уточнить</h3>
          <EvidenceList
            items={recommendation?.questions}
            empty="Агент ещё не проверил неизвестные условия."
          />
        </section>
      </div>
      {recommendation ? (
        <div className="detail-grid">
          <section>
            <h3>Факты из резюме</h3>
            <EvidenceList items={recommendation.matched_requirements} />
          </section>
          <section>
            <h3>Пробелы в требованиях</h3>
            <EvidenceList items={recommendation.missing_requirements} />
          </section>
        </div>
      ) : null}
      <section className="detail-section">
        <div className="section-heading">
          <h3>Резюме для этой вакансии</h3>
          <Button
            size="sm"
            variant="outline"
            onPress={compare}
            isPending={pending === "cv_match"}
          >
            Сравнить варианты
          </Button>
        </div>
        {recommendedCV ? (
          <p className="small">
            Предлагаемое резюме:{" "}
            <button
              className="inline-link"
              onClick={() => onInspect("cv", recommendedCV)}
            >
              {list(state.cvs).find((item) => item.id === recommendedCV)
                ?.name || "Открыть вариант"}
            </button>
          </p>
        ) : null}
        {match ? (
          <>
            <p className="muted">{list(match.notes).join(" ")}</p>
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
                  <span className="fit-badge">Рекомендовано</span>
                ) : null}
                <EvidenceList
                  items={
                    variant.reasons ||
                    variant.matched_requirements ||
                    variant.matches
                  }
                />
                <p className="small muted">Неподтверждённые требования:</p>
                <EvidenceList
                  items={variant.missing_requirements}
                  empty="Нет указанных пробелов."
                />
                <EvidenceList items={variant.notes} empty="" />
              </div>
            ))}
          </>
        ) : (
          <p className="muted">
            Сравнение опирается на подтверждённые факты из ваших версий резюме.
          </p>
        )}
      </section>
      <form
        className="detail-section"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <h3>Следующий шаг</h3>
        <div className="detail-grid">
          <SelectField label="Этап поиска" value={stage} onChange={setStage}>
            {stages
              .filter(([key]) => key !== "new")
              .map(([key, title]) => (
                <option value={key} key={key}>
                  {title}
                </option>
              ))}
          </SelectField>
          <SelectField label="Вариант резюме" value={cv} onChange={setCV}>
            <option value="">Без резюме</option>
            {list(state.cvs).map((c) => (
              <option value={c.id} key={c.id}>
                {c.name || c.headline}
              </option>
            ))}
          </SelectField>
        </div>
        <label className="form-field">
          Следующее действие
          <Input
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="Например, уточнить условия у рекрутера"
          />
        </label>
        <label className="form-field">
          Срок
          <input
            className="native-input"
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </label>
        <label className="form-field">
          Заметка
          <TextArea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
          />
        </label>
        <Button
          type="submit"
          variant="secondary"
          isPending={pending === `pipeline:${job.id}`}
        >
          Сохранить этап и следующий шаг
        </Button>
      </form>
      {job.description ? (
        <DetailAccordion title="Описание вакансии">
          <p className="preserve-lines">{job.description}</p>
        </DetailAccordion>
      ) : null}
      <DetailAccordion title="Переписка и история">
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
          <p className="muted">
            Сохраните состоявшееся сообщение в истории вакансии.
          </p>
          <div className="detail-grid">
            <SelectField
              label="Направление"
              value={messageDirection}
              onChange={setMessageDirection}
            >
              <option value="inbound">Получено от работодателя</option>
              <option value="outbound">Отправлено вами</option>
            </SelectField>
            <SelectField
              label="Канал"
              value={messageChannel}
              onChange={setMessageChannel}
            >
              <option value="email">Почта</option>
              <option value="telegram">Telegram</option>
              <option value="phone">Телефон</option>
              <option value="other">Другой</option>
            </SelectField>
          </div>
          <label className="form-field">
            Текст сообщения
            <TextArea
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
          >
            Сохранить запись
          </Button>
        </form>
        <EvidenceList
          items={list(state.messages)
            .filter((m) => m.job_id === job.id)
            .map(
              (m) =>
                `${formatDate(m.occurred_at || m.created_at)} · ${m.channel || ""} · ${m.text || m.summary || ""}`,
            )}
          empty="Переписки по этой вакансии пока нет."
        />
        <EvidenceList
          items={list(application?.history).map(
            (h) =>
              `${formatDate(h.at)} · ${label(h.stage)}${h.note ? ` · ${h.note}` : ""}`,
          )}
          empty="Этапы ещё не менялись."
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
        <span className="heading-with-icon">
          Рынок
          <span
            title="Описательная статистика сохранённой выборки"
            className="info-icon"
          >
            i
          </span>
        </span>
      }
      action={
        <span className="small muted">
          {state.demo
            ? "Демо-данные"
            : report?.snapshot
              ? "Снимок данных"
              : "Нет выборки"}
        </span>
      }
    >
      <a href="#market" className="market-stat">
        <span className="muted">Медиана предложений</span>
        {Number.isFinite(median) ? (
          <strong className="market-number">
            <NumberTicker value={median} />{" "}
            {group.currency === "RUB" ? "₽" : group.currency}
          </strong>
        ) : (
          <strong className="market-missing">Пока нет данных</strong>
        )}
        <span className="muted market-context">
          {group
            ? `${report?.snapshot?.scope?.location || report?.snapshot?.scope?.region || "Выборка"} · ${groupLabel(group)}`
            : "Соберите вакансии для сравнения"}
        </span>
        <span className="market-count">
          <strong>
            <NumberTicker value={count || 0} />
          </strong>{" "}
          вакансий с зарплатой
        </span>
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
    group = groups[Number(groupIndex)] || groups[0];
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
        title="Рынок"
        description="Сравнивайте реальные предложения с одинаковой валютой и периодом оплаты."
      />
      <Panel
        title="Рыночная выборка"
        action={
          <SelectField label="Снимок" value={snapshot} onChange={load}>
            <option value="">Последний снимок</option>
            {list(state.market?.snapshots).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {formatDate(s.created_at)}
              </option>
            ))}
          </SelectField>
        }
      >
        {!current || !current.counts?.unique_jobs ? (
          <Empty icon="market" title="Сопоставимой выборки пока нет">
            Сначала соберите вакансии с помощью своего MCP-агента, затем
            сохраните снимок рынка. Мы покажем объём выборки, источники и
            неизвестные условия.
          </Empty>
        ) : (
          <>
            <div className="market-metrics">
              {[
                ["Наблюдения", current.counts.observations],
                ["Уникальные вакансии", current.counts.unique_jobs],
                ["С зарплатой", current.counts.with_salary],
                ["Без зарплаты", current.counts.missing_salary],
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
              label="Сопоставимая группа оплаты"
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
                  ["Нижняя граница", group.lower],
                  ["Середина диапазона", group.midpoint],
                  ["Верхняя граница", group.upper],
                ].map(([title, stats]) => (
                  <div key={title}>
                    <p className="muted">{title}</p>
                    <strong>
                      {Number.isFinite(stats?.median)
                        ? stats.median.toLocaleString("ru-RU")
                        : "—"}
                    </strong>
                    <p className="small muted">
                      Медиана · {stats?.n || 0} наблюдений
                    </p>
                    <p className="small">
                      25–75%: {stats?.p25?.toLocaleString("ru-RU") ?? "—"} –{" "}
                      {stats?.p75?.toLocaleString("ru-RU") ?? "—"}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">
                Нет сопоставимых зарплат. Неизвестные валюты и периоды не
                объединяются.
              </p>
            )}
            <div className="detail-grid">
              {[
                ["Города", "locations"],
                ["Формат работы", "work_formats"],
                ["Источники", "sources"],
                ["Требования", "requirements"],
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
                                  remote: "Удалённо",
                                  hybrid: "Гибрид",
                                  office: "Офис",
                                  onsite: "Офис",
                                  unknown: "Не указан",
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
        <p className="muted small">
          Статистика описывает сохранённую выборку, а не весь рынок.
          {groups.some((entry) => entry.small_sample)
            ? " В группах меньше 5 вакансий показатели неустойчивы."
            : ""}
          {groups.some(
            (entry) =>
              entry.gross == null ||
              !entry.currency ||
              entry.currency === "unknown" ||
              !["month", "year", "hour", "week", "day"].includes(entry.period),
          )
            ? " Есть предложения с неизвестной валютой, периодом оплаты или налогами."
            : ""}
          {current?.counts?.invalid_salary
            ? ` Некорректные зарплаты исключены: ${current.counts.invalid_salary}.`
            : ""}
          {snapshot && current && !current.snapshot
            ? " Запрошенный снимок не найден."
            : ""}
        </p>
        <DetailAccordion title="Как рассчитана статистика">
          <p>
            {typeof current?.methodology === "string"
              ? current.methodology
              : "Статистика описывает только собранные вакансии и не представляет весь рынок труда."}
          </p>
          <EvidenceList
            items={current?.limitations}
            empty="Для оценки покрытия ещё нужны вакансии и источники."
          />
          {current?.snapshot ? (
            <p className="muted">
              Снимок: {current.snapshot.name} ·{" "}
              <Timestamp value={current.snapshot.created_at} /> · Дубликаты:{" "}
              {current.counts?.duplicates || 0} · Некорректные зарплаты:{" "}
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
      <Panel title="Сохранить текущую выборку">
        <form className="snapshot-form" onSubmit={create}>
          <label className="form-field">
            Название снимка
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Например, руководители логистики · октябрь"
            />
          </label>
          <Button
            type="submit"
            variant="secondary"
            isPending={pending === "market_snapshot"}
            isDisabled={!list(state.jobs).length}
          >
            Сохранить {list(state.jobs).length} вакансий
          </Button>
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
        throw new Error("Файл должен быть не больше 10 МБ.");
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
            : "Не удалось импортировать резюме.",
        );
      await onRefresh();
      setMessage("Резюме импортировано. Оно доступно в списке вариантов.");
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
        <strong>{file ? file.name : "Выберите файл резюме"}</strong>
        <span>TXT, Markdown, PDF или DOCX</span>
        <input
          type="file"
          accept=".txt,.md,.pdf,.docx"
          aria-label="Файл резюме"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          required
        />
      </label>
      <label className="form-field">
        Название версии
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Основное резюме"
        />
      </label>
      <SelectField label="Язык" value={language} onChange={setLanguage}>
        <option value="ru">Русский</option>
        <option value="en">English</option>
        <option value="it">Italiano</option>
        <option value="fr">Français</option>
      </SelectField>
      <Button
        type="submit"
        variant="secondary"
        isPending={pending}
        isDisabled={!file}
      >
        Импортировать
      </Button>
    </form>
  );
  return (
    <>
      <PageHeading
        title="Резюме"
        description="Ваш опыт, подтверждённые факты и версии под разные вакансии."
      />
      {list(state.cvs).length ? (
        <Panel title={`Варианты резюме · ${list(state.cvs).length}`}>
          <div className="cv-list">
            {state.cvs.map((cv) => (
              <BlurFade key={cv.id} className="cv-row">
                <span className="icon-circle">
                  <Icon name="cv" />
                </span>
                <div>
                  <h3>{cv.name || cv.headline || "Резюме"}</h3>
                  <p className="muted">
                    {cv.language || "Язык не указан"} · {list(cv.facts).length}{" "}
                    фактов · {formatDate(cv.created_at)}
                  </p>
                </div>
                {cv.original_filename || cv.original_path ? (
                  <Button
                    variant="outline"
                    isPending={downloadPending === "download:original"}
                    onPress={() => onDownload(cv.id, "original")}
                  >
                    Оригинал
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  onPress={() => onInspect("cv", cv.id)}
                >
                  Открыть
                  <Icon name="next" />
                </Button>
              </BlurFade>
            ))}
          </div>
        </Panel>
      ) : null}
      {list(state.cvs).length ? (
        <DetailAccordion title="Добавить резюме">{importForm}</DetailAccordion>
      ) : (
        <Panel title="Добавить резюме">{importForm}</Panel>
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
        title="Интервью и офферы"
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
            >
              Добавить интервью
            </Button>
            <Button
              variant="outline"
              size="sm"
              isDisabled={!list(state.jobs).length}
              onPress={() => {
                setForm("offer");
                setJob(list(state.jobs)[0]?.id || "");
              }}
            >
              Добавить оффер
            </Button>
          </div>
        }
      >
        {!list(state.interviews).length && !list(state.offers).length ? (
          <Empty icon="schedules" title="Переговоры ещё впереди">
            Сохраните вакансии, чтобы планировать интервью и сравнивать
            полученные предложения.
          </Empty>
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
                      ? `Интервью · ${formatDate(event.scheduled_at)}`
                      : `Оффер · ${salaryLabel(event.terms || {})}`}
                  </p>
                  {event.notes ? <p>{event.notes}</p> : null}
                  {safeURL(event.meeting_url) ? (
                    <a
                      href={event.meeting_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Ссылка на встречу
                    </a>
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
                    >
                      Подготовиться
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
        {list(state.offers).length ? (
          <DetailAccordion title="Сравнение офферов">
            <p className="muted">
              Сравнение учитывает только сохранённые условия и ваши ограничения.
              Валюты, периоды оплаты и налоги рассматриваются отдельно.
            </p>
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
                            consider: "Соответствует заданным условиям",
                            clarify: "Нужно уточнить условия",
                            reject: "Есть несоответствие условиям",
                          }[offer.decision]
                        }
                      </p>
                      <EvidenceList items={offer.reasons} />
                      <h4>Вопросы к работодателю</h4>
                      <EvidenceList
                        items={offer.questions}
                        empty="Неизвестных условий по заданным критериям нет."
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
                        {offer.notes || "Дополнительные условия не указаны"}
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
        title={form === "interview" ? "Добавить интервью" : "Добавить оффер"}
      >
        <form className="resume-form" onSubmit={save}>
          <SelectField label="Вакансия" value={job} onChange={setJob}>
            {list(state.jobs).map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </SelectField>
          {form === "interview" ? (
            <>
              <label className="form-field">
                Дата и время
                <input
                  className="native-input"
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                />
              </label>
              <label className="form-field">
                Ссылка на встречу
                <Input
                  type="url"
                  value={meeting}
                  onChange={(e) => setMeeting(e.target.value)}
                />
              </label>
            </>
          ) : (
            <div className="detail-grid">
              <label className="form-field">
                Зарплата в месяц
                <Input
                  type="number"
                  min="0"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                />
              </label>
              <SelectField
                label="Валюта"
                value={currency}
                onChange={setCurrency}
              >
                {["RUB", "USD", "EUR"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </SelectField>
              <SelectField label="Налоги" value={tax} onChange={setTax}>
                <option value="unknown">Не указано</option>
                <option value="gross">До налогов</option>
                <option value="net">На руки</option>
              </SelectField>
              <SelectField
                label="Удалённая работа"
                value={remote}
                onChange={setRemote}
              >
                <option value="unknown">Не указано</option>
                <option value="yes">Да</option>
                <option value="no">Нет</option>
              </SelectField>
              <label className="form-field">
                Часов в неделю
                <Input
                  type="number"
                  min="0"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                />
              </label>
              <label className="form-field">
                Дата выхода
                <input
                  className="native-input"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </label>
              <label className="form-field">
                Первая выплата
                <input
                  className="native-input"
                  type="date"
                  value={incomeDate}
                  onChange={(e) => setIncomeDate(e.target.value)}
                />
              </label>
            </div>
          )}
          <label className="form-field">
            Заметки
            <TextArea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <Button
            type="submit"
            variant="secondary"
            isPending={pending === "interview_save" || pending === "offer_save"}
          >
            Сохранить
          </Button>
        </form>
      </Dialog>
      <Dialog
        open={!!brief}
        onClose={() => setBrief(null)}
        title="Подготовка к интервью"
      >
        {brief ? (
          <>
            <h3>{brief.job?.title}</h3>
            <h4>Вопросы работодателю</h4>
            <EvidenceList items={brief.questions_for_employer} />
            <h4>Примеры из опыта</h4>
            {list(brief.preparation).map((item, i) => (
              <div className="preparation-item" key={i}>
                <strong>{item.requirement}</strong>
                <p className="muted">{item.prompt}</p>
              </div>
            ))}
            <h4>Факты из резюме</h4>
            <EvidenceList items={brief.evidence} />
            <EvidenceList items={brief.notes} />
          </>
        ) : null}
      </Dialog>
    </>
  );
}
