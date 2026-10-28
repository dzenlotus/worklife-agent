import { t, getLocale } from "./i18n.js";
import { useState } from "react";
import {
  Button,
  TextArea,
  Tabs,
  Link,
  Label,
  Typography,
  Select,
  ListBox,
} from "@heroui/react";
import { MarketSummary } from "./AgencyViews.jsx";
import { employerName, jobStage, jobLocation, salaryLabel } from "./board.js";
import {
  Panel,
  Status,
  Empty,
  DataTable,
  Timestamp,
  DetailAccordion,
  Icon,
} from "./ui.jsx";
import {
  list,
  filterJobs,
  safeURL,
  currentConditions,
  goalExcerpt,
  advisorText,
} from "./model.js";
import { monitorActivity, callSummary } from "./activity.js";

function JobTable({ state, filter, limit, onInspect }) {
  const applications = new Map(
    list(state.applications).map((a) => [a.job_id, a]),
  );
  let jobs = filterJobs(state, filter);
  if (limit) jobs = jobs.slice(0, limit);
  if (!jobs.length)
    return (
      <Empty
        icon="search"
        title={
          list(state.jobs).length
            ? t("Нет вакансий по этому фильтру")
            : t("Вакансии появятся здесь")
        }
      >{t("Агент сохранит предложения, условия и источники во время поиска.")}</Empty>
    );
  return (
    <DataTable
      headers={[t("Вакансия"), t("Компания"), t("Состояние"), t("Обновлено"), ""]}
      rows={jobs.map((job) => {
        const application = applications.get(job.id),
          href = safeURL(job.url);
        const salary =
          job.salary_min || job.salary_max
            ? [job.salary_min, job.salary_max].filter(Boolean).join(" — ") +
              " " +
              (job.currency || "")
            : job.remote === true
              ? t("Удалённо")
              : job.remote === false
                ? t("В офисе")
                : t("Условия уточняются");
        return [
          <>
            <span className="block">
              {href ? (
                <Link href={href} target="_blank" rel="noreferrer">
                  {job.title}
                  <Icon name="external" className="size-4 shrink-0" />
                </Link>
              ) : (
                job.title
              )}
            </span>
            <span className="block">{salary}</span>
          </>,
          typeof job.employer === "object" ? job.employer.name : job.employer,
          <Status
            value={job.blocked ? "blocked" : application?.stage || "new"}
          />,
          <Timestamp value={job.fetched_at} />,
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect("job", job.id)}
          >{t("Подробнее")}</Button>,
        ];
      })}
    />
  );
}
export function Pipeline({ state, onInspect, limit }) {
  const [filter, setFilter] = useState("all");
  const filters = [
    ["all", t("Все")],
    ["new", t("Новые")],
    ["active", t("В работе")],
    ["reply", t("Ответ получен")],
  ];
  return (
    <section className="flex flex-col gap-4" aria-label={t("Вакансии")}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Typography.Paragraph size="sm" color="muted">
          {list(state.jobs).length}{" "}{t("в вашей истории")}</Typography.Paragraph>
      </div>
      <div className="sm:hidden">
        <Select
          aria-label={t("Состояние вакансий")}
          value={filter}
          onChange={(value) => {
            if (typeof value === "string") setFilter(value);
          }}
        >
          <Select.Trigger>
            <Select.Value />
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox>
              {filters.map(([key, title]) => (
                <ListBox.Item id={key} key={key} textValue={title}>
                  {title}
                  <ListBox.ItemIndicator />
                </ListBox.Item>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
      </div>
      <Tabs selectedKey={filter} onSelectionChange={setFilter}>
        <Tabs.ListContainer className="hidden sm:block">
          <Tabs.List aria-label={t("Состояние вакансий")}>
            {filters.map(([key, title]) => (
              <Tabs.Tab id={key} key={key}>
                {title}
                <Tabs.Indicator />
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs.ListContainer>
        {filters.map(([key]) => (
          <Tabs.Panel id={key} key={key}>
            <JobTable
              state={state}
              filter={key}
              limit={limit}
              onInspect={onInspect}
            />
          </Tabs.Panel>
        ))}
      </Tabs>
    </section>
  );
}
export function GoalComposer({
  goal,
  setGoal,
  onRun,
  pending,
  configured,
  inputRef,
  context,
  setContext,
  profile,
  onConditions,
}) {
  const conditions = currentConditions(profile || {});
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onRun();
      }}
    >
      <Label htmlFor="agent-goal">{t("Поручение встроенному исполнителю")}</Label>
      <TextArea
        id="agent-goal"
        ref={context ? undefined : inputRef}
        aria-label={t("Поручение агенту")}
        placeholder={t("Например: найди работу руководителем в логистике, от 180 000 ₽, без переезда. Изучи компании и сохрани подходящие вакансии.")}
        rows={3}
        maxLength={16000}
        value={goal}
        onChange={(event) => setGoal(event.target.value)}
        className="w-full"
      />
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <strong>{t("Условия поиска")}</strong>
          <Button variant="ghost" size="sm" onPress={onConditions}>
            {conditions.length ? t("Изменить условия") : t("Добавить условия")}
          </Button>
        </div>
        {conditions.length ? (
          <ul className="flex flex-col gap-2">
            {conditions.slice(0, 2).map((condition, index) => (
              <li key={index}>{condition}</li>
            ))}
          </ul>
        ) : (
          <Typography.Paragraph size="sm" color="muted">{t("Доход, график и ограничения сохраняются для всех поручений.")}</Typography.Paragraph>
        )}
        {conditions.length > 2 ? (
          <DetailAccordion title={t`Ещё условий: ${conditions.length - 2}`}>
            <ul className="flex flex-col gap-2">
              {conditions.slice(2).map((condition, index) => (
                <li key={index}>{condition}</li>
              ))}
            </ul>
          </DetailAccordion>
        ) : null}
      </div>
      {context ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Label htmlFor="agent-context">{t("Текущее уточнение")}</Label>
            <Button variant="ghost" size="sm" onPress={() => setContext(null)}>{t("Убрать уточнение")}</Button>
          </div>
          <TextArea
            id="agent-context"
            ref={inputRef}
            aria-label={t("Уточнение поручения")}
            rows={3}
            maxLength={16000}
            value={context.text}
            onChange={(event) =>
              setContext({ ...context, text: event.target.value })
            }
          />
          <p>{t("Выполнится вместе с основной целью и её ограничениями.")}</p>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          isPending={pending}
          isDisabled={
            configured !== false && !goal.trim() && !context?.text?.trim()
          }
        >
          {configured === false
            ? t("Подключить модель исполнителя")
            : t("Запустить поручение")}
        </Button>
        <Typography.Paragraph size="sm" color="muted">{t("Черновик сохраняется локально.")}</Typography.Paragraph>
      </div>
    </form>
  );
}
export function RunHistory({ runs, onInspect }) {
  if (!runs.length) return null;
  return (
    <Panel title={t("Запуски агента")}>
      <DataTable
        headers={[t("Поручение"), t("Состояние"), t("Шаги"), t("Начало"), ""]}
        rows={runs.map((run) => [
          <span className="block">{goalExcerpt(run.goal)}</span>,
          <Status value={run.status} />,
          `${list(run.steps).length} / ${run.max_steps}`,
          <Timestamp value={run.started_at || run.created_at} />,
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect("run", run.id)}
          >{t("Журнал")}</Button>,
        ])}
      />
    </Panel>
  );
}
export function ActivityLog({ state, onInspect, limit }) {
  let rows = monitorActivity(state);
  if (limit) rows = rows.slice(0, limit);
  if (!rows.length)
    return (
      <Empty title={t("Вызовов MCP пока нет")}>{t("Дайте поручение в чате вашего агента.")}</Empty>
    );
  if (!list(state.tool_calls).length) {
    const hasStatus = rows.some((row) => row.status),
      hasTarget = rows.some((row) => row.target);
    return (
      <DataTable
        headers={[
          t("Событие"),
          ...(hasStatus ? [t("Состояние")] : []),
          t("Время"),
          ...(hasTarget ? [""] : []),
        ]}
        rows={rows.map((row) => [
          row.error || row.summary,
          ...(hasStatus
            ? [row.status ? <Status value={row.status} /> : "—"]
            : []),
          <Timestamp value={row.at} />,
          ...(hasTarget
            ? [
                row.target ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onPress={() => onInspect(row.target.kind, row.target.id)}
                  >{t("Результат")}</Button>
                ) : null,
              ]
            : []),
        ])}
      />
    );
  }
  return (
    <DataTable
      headers={[t("Инструмент"), t("Что произошло"), t("Состояние"), t("Время"), ""]}
      rows={rows.map((row) => [
        <Typography.Code>{row.tool}</Typography.Code>,
        row.error || row.summary || t("Результат ещё не сохранён"),
        row.status ? <Status value={row.status} /> : "—",
        <div className="flex flex-col gap-2">
          <Timestamp value={row.at} />
          {Number.isFinite(row.duration_seconds) ? (
            <Typography.Paragraph size="sm" color="muted">
              {row.duration_seconds.toLocaleString(getLocale(), {
                maximumFractionDigits: 2,
              })}{" "}{t("с")}</Typography.Paragraph>
          ) : null}
        </div>,
        row.source === "mcp" ? (
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect("tool_call", row.id)}
          >{t("Подробнее")}</Button>
        ) : row.target ? (
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect(row.target.kind, row.target.id)}
          >{t("Результат")}</Button>
        ) : null,
      ])}
    />
  );
}

export const MarketPanel = MarketSummary;

function OverviewJob({ job, recommendation, state, onInspect, onCommand, pending }) {
  const stage = jobStage(job, state.applications);
  return (
    <article className="overview-job-row">
      <div className="overview-job-main">
        <p className="overview-job-company">{employerName(job)}</p>
        <button className="overview-job-title" onClick={() => onInspect("job", job.id)}>
          {job.title || t("Вакансия без названия")}
        </button>
        <p className="overview-job-meta">
          <strong>{salaryLabel(job)}</strong><span>{jobLocation(job)}</span>
        </p>
        {recommendation ? (
          <p className="overview-job-reason">
            {recommendation.assessment_status === "stale" ? t("Анализ нужно обновить. ") : ""}
            {advisorText(list(recommendation.reasons)[0] || "Откройте вакансию, чтобы проверить условия.")}
          </p>
        ) : null}
      </div>
      <div className="overview-job-actions">
        <Status value={job.blocked ? "blocked" : stage} />
        {stage === "new" && !job.blocked ? (
          <Button
            variant="outline"
            size="sm"
            isPending={pending === `save:${job.id}`}
            onPress={() => onCommand("pipeline_update", { job_id: job.id, stage: "saved" }, `save:${job.id}`)}
          >{t("Сохранить")}</Button>
        ) : (
          <Button variant="ghost" size="sm" onPress={() => onInspect("job", job.id)}>{t("Открыть")}<Icon name="next" />
          </Button>
        )}
      </div>
    </article>
  );
}

export default function Overview({ state, pending, onInspect, onCommand, onConditions }) {
  const jobs = list(state.jobs),
    cvs = list(state.cvs),
    profile = state.profile || {},
    conditions = currentConditions(profile),
    roles = list(profile.target_roles),
    needsProfile = !state.demo && (state.advisor?.status === "needs_profile" || (!cvs.length && !list(profile.facts).length)),
    activity = monitorActivity(state).slice(0, 3),
    activeRuntime = list(state.agent?.runs).find((run) => ["running", "queued", "cancelling"].includes(run.status)),
    runningCall = list(state.tool_calls).find((call) => call.status === "running"),
    activeJobs = jobs.filter((job) => !job.blocked && !["accepted", "rejected", "withdrawn"].includes(jobStage(job, state.applications))),
    recommendations = list(state.advisor?.recommendations).filter((row) => row.decision !== "reject" && row.assessment_status !== "stale" && activeJobs.some((job) => job.id === row.job_id)),
    featured = recommendations.length
      ? recommendations.slice(0, 3).map((row) => jobs.find((job) => job.id === row.job_id))
      : filterJobs({ ...state, jobs: activeJobs }).slice(0, 3),
    nextActions = list(state.advisor?.next_actions).filter((action) => !["consider", "complete_profile"].includes(action.kind) && (!action.job_id || activeJobs.some((job) => job.id === action.job_id))).slice(0, 3),
    next = list(state.schedules).filter((schedule) => schedule.enabled && schedule.next_run_at).sort((a, b) => a.next_run_at.localeCompare(b.next_run_at))[0],
    marketCount = state.market?.report?.counts?.unique_jobs,
    unread = list(state.messages).filter((message) => message.unread === true && message.direction === "inbound").length,
    showWorkspace = jobs.length > 0 || !needsProfile;

  return (
    <div className="overview-home">
      <header className="overview-header">
        <div>
          <h1>{t("Поиск работы")}</h1>
          {roles.length ? <p className="overview-intro">{roles.join(" · ")}</p> : null}
        </div>
        {state.demo ? <span className="demo-badge">{t("Демонстрационные данные")}</span> : !needsProfile ? (
          <Button variant="outline" size="sm" onPress={onConditions}>
            <Icon name="settings" />{t("Условия поиска")}</Button>
        ) : null}
      </header>

      {needsProfile ? (
        <section className="overview-start" aria-labelledby="overview-start-title">
          <div className="overview-section-heading">
            <h2 id="overview-start-title">{t("С чего начнём?")}</h2>
          </div>
          <div className="overview-start-step">
            <span className="overview-step-icon" data-tone="cv"><Icon name="cv" /></span>
            <div>
              <h3>{cvs.length ? t("Резюме добавлено") : t("Опыт и навыки")}</h3>
              <p>{cvs.length ? cvs[0].name || cvs[0].headline || t("Ваш опыт сохранён") : t("Подойдёт резюме в PDF, DOCX или текстовом файле.")}</p>
            </div>
            <Button variant={cvs.length ? "outline" : "primary"} size="sm" onPress={() => { location.hash = "cv"; }}>
              {cvs.length ? t("Открыть") : t("Загрузить резюме")}<Icon name="next" />
            </Button>
          </div>
          <div className="overview-start-step">
            <span className="overview-step-icon" data-tone="settings"><Icon name="settings" /></span>
            <div>
              <h3>{conditions.length || roles.length ? t("Условия сохранены") : t("Желаемая работа")}</h3>
              <p>{[...roles, ...conditions].slice(0, 2).join(" · ") || t("Роль, доход и формат работы.")}</p>
            </div>
            <Button variant="outline" size="sm" onPress={onConditions}>
              {conditions.length || roles.length ? t("Изменить") : t("Указать условия")}
            </Button>
          </div>
          <p className="overview-context-note">{t("Можно начать с разговора об этом с вашим агентом.")}</p>
        </section>
      ) : null}

      {activeRuntime || runningCall ? (
        <section className="overview-running" aria-label={t("Текущая работа агента")}>
          <Status value={activeRuntime?.status || "running"} />
          <p>{activeRuntime ? goalExcerpt(activeRuntime.goal) : callSummary(runningCall.summary) || t("Агент выполняет поручение")}</p>
          <Button variant="ghost" size="sm" onPress={() => onInspect(activeRuntime ? "run" : "tool_call", activeRuntime?.id || runningCall.id)}>{t("Журнал")}</Button>
          {activeRuntime ? (
            <Button variant="danger-soft" size="sm" isPending={pending === `cancel:${activeRuntime.id}`} onPress={() => onCommand("agent_cancel", { run_id: activeRuntime.id }, `cancel:${activeRuntime.id}`)}>{t("Остановить")}</Button>
          ) : null}
        </section>
      ) : null}

      {showWorkspace ? (
        <div className="overview-layout">
          <div className="overview-main-column">
            <section className="overview-opportunities" aria-labelledby="overview-jobs-title">
              <div className="overview-section-heading">
                <h2 id="overview-jobs-title">{recommendations.length ? t("Стоит рассмотреть") : t("Ваши вакансии")}</h2>
                {jobs.length ? <Link href="#search">{t("Все вакансии")}<Icon name="next" /></Link> : null}
              </div>
              {featured.length ? (
                <div className="overview-job-list">
                  {featured.map((job) => (
                    <OverviewJob key={job.id} {...{ job, state, onInspect, onCommand, pending }} recommendation={recommendations.find((row) => row.job_id === job.id)} />
                  ))}
                </div>
              ) : (
                <div className="overview-empty-search">
                  <Icon name="discover" />
                  <h3>{jobs.length ? t("Активных вакансий пока нет") : t("Готовы к поиску")}</h3>
                  <p>{jobs.length ? t("Завершённые вакансии сохранены в истории.") : t("Обсудите с агентом, какую работу ищете. Найденные предложения будут собраны здесь.")}</p>
                  {jobs.length ? <Link href="#search">{t("Открыть историю")}<Icon name="next" /></Link> : <Button variant="outline" size="sm" onPress={onConditions}>{t("Проверить условия")}</Button>}
                </div>
              )}
            </section>

            {nextActions.length || unread ? (
              <section className="overview-attention" aria-labelledby="overview-attention-title">
                <div className="overview-section-heading"><h2 id="overview-attention-title">{t("Следующие шаги")}</h2></div>
                <div className="overview-attention-list">
                  {unread ? (
                    <a className="overview-attention-item" href="#messages">
                      <Icon name="activity" /><span><strong>{t("Входящие сообщения ·")}{" "}{unread}</strong><span>{t("Откройте переписку по вакансиям")}</span></span><Icon name="next" />
                    </a>
                  ) : null}
                  {nextActions.map((action, index) => {
                    const job = jobs.find((item) => item.id === action.job_id);
                    return (
                      <button className="overview-attention-item" key={`${action.kind}-${action.job_id || index}`} onClick={() => job ? onInspect("job", job.id) : onConditions()}>
                        <Icon name={action.kind === "prepare_interview" ? "schedules" : "cv"} />
                        <span><strong>{t(action.title)}</strong>{job ? <span>{job.title} · {employerName(job)}</span> : null}{action.reason ? <span>{advisorText(action.reason)}</span> : null}</span>
                        <Icon name="next" />
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>

          <aside className="overview-side-column" aria-label={t("Контекст поиска")}>
            <section className="overview-brief">
              <div className="overview-section-heading"><h2>{t("Условия поиска")}</h2><Button variant="ghost" size="sm" onPress={onConditions}>{t("Изменить")}</Button></div>
              <div className="overview-brief-list">
                {conditions.length ? conditions.slice(0, 3).map((condition, index) => <p className="overview-brief-row" key={index}><Icon name="check" /><span>{condition}</span></p>) : <p className="overview-context-note">{t("Уточните доход и формат работы, чтобы агент мог учитывать их при поиске.")}</p>}
                {list(profile.target_locations).length ? <p className="overview-brief-row"><Icon name="employers" /><span>{profile.target_locations.join(" · ")}</span></p> : null}
                <a className="overview-brief-row" href="#cv"><Icon name="cv" /><span>{cvs.length ? cvs[0].name || cvs[0].headline || t("Моё резюме") : t("Добавить резюме")}</span><Icon name="next" /></a>
              </div>
            </section>
            {marketCount > 0 ? (
              <section className="overview-brief overview-market-brief">
                <div className="overview-section-heading"><h2>{t("Контекст рынка")}</h2></div>
                <p>{t("В сохранённой выборке:")}{" "}<strong>{marketCount}</strong>{" "}{t("вакансий.")}</p>
                <Link href="#market">{t("Сравнить условия")}<Icon name="next" /></Link>
              </section>
            ) : null}
            {next ? (
              <section className="overview-brief overview-schedule-brief">
                <div className="overview-section-heading"><h2>{t("По расписанию")}</h2></div>
                <p><strong>{next.name}</strong></p>
                <p className="overview-context-note"><Timestamp value={next.next_run_at} /></p>
                <Link href="#schedules">{t("Открыть расписание")}<Icon name="next" /></Link>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}

      {activity.length ? (
        <section className="overview-journal" aria-labelledby="overview-journal-title">
          <div className="overview-section-heading">
            <h2 id="overview-journal-title">{t("Последние действия")}</h2>
            <Button variant="ghost" size="sm" onPress={() => onInspect("activity")}>{t("Весь журнал")}<Icon name="next" /></Button>
          </div>
          {activity.map((entry) => (
            <div className="overview-journal-row" key={entry.id}>
              <Timestamp value={entry.at} />
              <span>{entry.error || entry.summary || t("Действие агента")}</span>
              {entry.source === "mcp" || entry.target ? (
                <Button variant="ghost" size="sm" aria-label={t`Открыть действие: ${entry.summary || t("действие агента")}`} onPress={() => entry.source === "mcp" ? onInspect("tool_call", entry.id) : onInspect(entry.target.kind, entry.target.id)}><Icon name="next" /></Button>
              ) : null}
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
