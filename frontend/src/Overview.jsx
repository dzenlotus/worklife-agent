import { useState } from "react";
import { Alert, Button, Card, TextArea, Tabs, Link, Label, Typography, Select, ListBox, Separator } from "@heroui/react";
import { typographyVariants } from "@heroui/styles";
import {
  Panel,
  PageHeading,
  Status,
  Empty,
  DataTable,
  AgentButton,
  Timestamp,
  DetailAccordion,
  Icon,
  IconCircle,
} from "./ui.jsx";
import { list, statistics, filterJobs, safeURL, currentConditions, goalExcerpt, employerGroups } from "./model.js";
import { monitorActivity } from "./activity.js";

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
            ? "Нет вакансий по этому фильтру"
            : "Вакансии появятся здесь"
        }
      >
        Агент сохранит предложения, условия и источники во время поиска.
      </Empty>
    );
  return (
    <DataTable
      headers={["Вакансия", "Компания", "Состояние", "Обновлено", ""]}
      rows={jobs.map((job) => {
        const application = applications.get(job.id),
          href = safeURL(job.url);
        const salary =
          job.salary_min || job.salary_max
            ? [job.salary_min, job.salary_max].filter(Boolean).join(" — ") +
              " " +
              (job.currency || "")
            : job.remote === true
              ? "Удалённо"
              : job.remote === false
                ? "В офисе"
                : "Условия уточняются";
        return [
          <>
            <span className="block">
              {href ? (
                <Link href={href} target="_blank" rel="noreferrer">
                  {job.title}<Icon name="external" className="size-4 shrink-0" />
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
          >
            Подробнее
          </Button>,
        ];
      })}
    />
  );
}
export function Pipeline({ state, onInspect, limit }) {
  const [filter, setFilter] = useState("all");
  const filters = [
    ["all", "Все"],
    ["new", "Новые"],
    ["active", "В работе"],
    ["reply", "Ответ получен"],
  ];
  return (
    <section className="flex flex-col gap-4" aria-label="Вакансии"><div className="flex flex-wrap items-center justify-between gap-3"><Typography.Paragraph size="sm" color="muted">{list(state.jobs).length} в вашей истории</Typography.Paragraph></div>
      <div className="sm:hidden"><Select aria-label="Состояние вакансий" value={filter} onChange={(value) => { if (typeof value === "string") setFilter(value); }}>
        <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox>{filters.map(([key, title]) => <ListBox.Item id={key} key={key} textValue={title}>{title}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
      </Select></div>
      <Tabs selectedKey={filter} onSelectionChange={setFilter}>
        <Tabs.ListContainer className="hidden sm:block">
          <Tabs.List aria-label="Состояние вакансий">
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
      <Label htmlFor="agent-goal">Поручение встроенному исполнителю</Label>
      <TextArea
        id="agent-goal"
        ref={context ? undefined : inputRef}
        aria-label="Поручение агенту"
        placeholder="Например: найди работу руководителем в логистике, от 180 000 ₽, без переезда. Изучи компании и сохрани подходящие вакансии."
        rows={3}
        maxLength={16000}
        value={goal}
        onChange={(event) => setGoal(event.target.value)}
        className="w-full"
      />
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3"><strong>Условия поиска</strong><Button variant="ghost" size="sm" onPress={onConditions}>{conditions.length ? "Изменить условия" : "Добавить условия"}</Button></div>
        {conditions.length ? <ul className="flex flex-col gap-2">{conditions.slice(0, 2).map((condition, index) => <li key={index}>{condition}</li>)}</ul> : <Typography.Paragraph size="sm" color="muted">Доход, график и ограничения сохраняются для всех поручений.</Typography.Paragraph>}
        {conditions.length > 2 ? <DetailAccordion title={`Ещё условий: ${conditions.length - 2}`}><ul className="flex flex-col gap-2">{conditions.slice(2).map((condition, index) => <li key={index}>{condition}</li>)}</ul></DetailAccordion> : null}
      </div>
      {context ? <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3"><Label htmlFor="agent-context">Текущее уточнение</Label><Button variant="ghost" size="sm" onPress={() => setContext(null)}>Убрать уточнение</Button></div>
        <TextArea id="agent-context" ref={inputRef} aria-label="Уточнение поручения" rows={3} maxLength={16000} value={context.text} onChange={(event) => setContext({ ...context, text: event.target.value })} />
        <p>Выполнится вместе с основной целью и её ограничениями.</p>
      </div> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          isPending={pending}
          isDisabled={configured !== false && !goal.trim() && !context?.text?.trim()}

        >
          {configured === false ? "Подключить модель исполнителя" : "Запустить поручение"}

        </Button>
        <Typography.Paragraph size="sm" color="muted">Черновик сохраняется локально.</Typography.Paragraph>
      </div>
    </form>
  );
}
export function RunHistory({ runs, onInspect }) {
  if (!runs.length) return null;
  return (
    <Panel title="Запуски агента">
      <DataTable
        headers={["Поручение", "Состояние", "Шаги", "Начало", ""]}
        rows={runs.map((run) => [
          <span className="block">{goalExcerpt(run.goal)}</span>,
          <Status value={run.status} />,
          `${list(run.steps).length} / ${run.max_steps}`,
          <Timestamp value={run.started_at || run.created_at} />,
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect("run", run.id)}
          >
            Журнал
          </Button>,
        ])}
      />
    </Panel>
  );
}
export function ActivityLog({ state, onInspect, limit }) {
  let rows = monitorActivity(state);
  if (limit) rows = rows.slice(0, limit);
  if (!rows.length) return <Empty title="Вызовов MCP пока нет">Дайте поручение в чате вашего агента.</Empty>;
  if (!list(state.tool_calls).length) {
    const hasStatus = rows.some((row) => row.status), hasTarget = rows.some((row) => row.target);
    return <DataTable headers={["Событие", ...(hasStatus ? ["Состояние"] : []), "Время", ...(hasTarget ? [""] : [])]} rows={rows.map((row) => [row.error || row.summary, ...(hasStatus ? [row.status ? <Status value={row.status} /> : "—"] : []), <Timestamp value={row.at} />, ...(hasTarget ? [row.target ? <Button variant="ghost" size="sm" onPress={() => onInspect(row.target.kind, row.target.id)}>Результат</Button> : null] : [])])} />;
  }
  return <DataTable headers={["Инструмент", "Что произошло", "Состояние", "Время", ""]} rows={rows.map((row) => [
    <Typography.Code>{row.tool}</Typography.Code>, row.error || row.summary || "Результат ещё не сохранён", row.status ? <Status value={row.status} /> : "—", <div className="flex flex-col gap-2"><Timestamp value={row.at} />{Number.isFinite(row.duration_seconds) ? <Typography.Paragraph size="sm" color="muted">{row.duration_seconds.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} с</Typography.Paragraph> : null}</div>,
    row.source === "mcp" ? <Button variant="ghost" size="sm" onPress={() => onInspect("tool_call", row.id)}>Подробнее</Button> : row.target ? <Button variant="ghost" size="sm" onPress={() => onInspect(row.target.kind, row.target.id)}>Результат</Button> : null,
  ])} />;
}

function resultName(target, state) {
  if (!target) return null;
  const bucket = { job: "jobs", cv: "cvs", action: "actions", resource: "resources", schedule_run: "schedule_runs" }[target.kind];
  const record = list(bucket ? state[bucket] : state.agent?.runs).find((entry) => entry.id === target.id);
  return record?.name || record?.title || record?.headline || record?.payload?.subject || null;
}

function ActivityFeed({ entries, state, onInspect }) {
  if (!entries.length) return <Empty icon="activity" title="Журнал пока пуст">Здесь появятся действия вашего агента, сохранённые результаты и ход поручений.</Empty>;
  return <div className="flex flex-col" role="list" aria-label="Последние действия">
    {entries.map((entry) => {
      const name = resultName(entry.target, state);
      const icon = { job: "search", cv: "cv", resource: "resources", action: "activity", schedule_run: "schedules" }[entry.target?.kind] || (entry.tool?.includes("search") ? "discover" : entry.tool?.startsWith("resource_") ? "resources" : "activity");
      return <div key={entry.id} role="listitem">
        <div className="flex min-h-36 flex-col gap-4 py-6 xl:flex-row xl:items-start">
          <div className="shrink-0 xl:w-28 xl:pt-3"><Typography.Paragraph size="sm" color="muted"><Timestamp value={entry.at} /></Typography.Paragraph></div>
          <div className="flex min-w-0 flex-1 items-start gap-5">
            <IconCircle name={icon} />
            <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1">
              <h3 className={typographyVariants({ type: "h4", weight: "normal" }).base()}>{entry.summary || entry.tool || "Действие агента"}</h3>
              {name && entry.target ? <Link onPress={() => onInspect(entry.target.kind, entry.target.id)}>{name}<Icon name="next" className="size-4 shrink-0" /></Link> : null}
              {entry.error ? <Typography.Paragraph size="sm" color="muted">{entry.error}</Typography.Paragraph> : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center justify-between gap-3 xl:flex-col xl:items-end xl:pt-1">
            {entry.status ? <Status value={entry.status} /> : null}
            {entry.source === "mcp" ? <Button variant="outline" size="md" onPress={() => onInspect("tool_call", entry.id)}>Подробнее<Icon name="next" /></Button> : entry.target ? <Button variant="outline" size="md" onPress={() => onInspect(entry.target.kind, entry.target.id)}>Подробнее<Icon name="next" /></Button> : null}
          </div>
        </div>
        <Separator />
      </div>;
    })}
  </div>;
}

export function MarketPanel({ state }) {
  const jobs = list(state.jobs), salaryCount = jobs.filter((job) => Number(job.salary_min) > 0 || Number(job.salary_max) > 0).length;
  return <Panel title="Рынок" action={<Typography.Paragraph size="xs" color="muted">Локальные данные</Typography.Paragraph>}>
    <Card variant="secondary" className="gap-4 p-5"><Card.Content className="flex flex-col gap-3">
      <Typography.Paragraph color="muted">Медиана предложений</Typography.Paragraph>
      <p className={typographyVariants({ type: "h4", weight: "normal" }).base()}>Нет сопоставимой выборки</p>
      <Separator />
      <div className="flex items-center justify-between gap-3"><Typography.Paragraph size="sm" color="muted">Вакансий с зарплатой</Typography.Paragraph><Typography.Paragraph weight="medium">{salaryCount}</Typography.Paragraph></div>
    </Card.Content></Card>
    <Link href="#market">Данные рынка<Icon name="next" className="size-4 shrink-0" /></Link>
  </Panel>;
}

export default function Overview({ state, pending, onInspect, onCommand }) {
  const stats = statistics(state), activity = monitorActivity(state), calls = list(state.tool_calls);
  const running = calls.filter((call) => call.status === "running");
  const schedules = list(state.schedules);
  const next = schedules.filter((schedule) => schedule.enabled).sort((a, b) => (a.next_run_at || "").localeCompare(b.next_run_at || ""))[0];
  const saved = [["search", "Сохранённые вакансии", stats.jobs], ["employers", "Компании", employerGroups(state.employers).length], ["resources", "Источники", list(state.resources).length], ...(list(state.cvs).length ? [["cv", "Резюме", list(state.cvs).length]] : [])];
  const activeRuntime = list(state.agent?.runs).find((run) => ["running", "queued", "cancelling"].includes(run.status));
  return <>
    <PageHeading title="Обзор" description="Активность агента, результаты и контекст рынка">{running.length ? <Status value="running">В работе: {running.length}</Status> : null}</PageHeading>
    {activeRuntime ? <Alert><Alert.Content><Alert.Title>Встроенный исполнитель работает</Alert.Title><Alert.Description>{goalExcerpt(activeRuntime.goal)}</Alert.Description><div className="flex flex-wrap gap-2 py-2"><Button variant="secondary" size="sm" onPress={() => onInspect("run", activeRuntime.id)}>Журнал</Button><Button variant="danger-soft" size="sm" isPending={pending === "cancel:" + activeRuntime.id} onPress={() => onCommand("agent_cancel", { run_id: activeRuntime.id }, "cancel:" + activeRuntime.id)}>Остановить</Button></div></Alert.Content></Alert> : null}
    <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
      <section className="min-w-0 flex-1" aria-label="Активность агента">
        <Panel title="Последняя активность" className="xl:min-h-[calc(100dvh-12rem)]" action={activity.length ? <Button variant="outline" size="md" onPress={() => onInspect("activity")}><Icon name="list" />Весь журнал</Button> : null}>
          <ActivityFeed entries={activity.slice(0, 6)} state={state} onInspect={onInspect} />
        </Panel>
      </section>
      <aside className="flex w-full flex-col gap-5 xl:w-90 xl:shrink-0" aria-label="Сводка">
        <MarketPanel state={state} />
        <Panel title="Результаты"><div className="flex flex-col">
          {saved.map(([page, title, count], index) => <div key={page}>{index ? <Separator /> : null}<Button className="min-h-14 justify-start px-1" fullWidth size="lg" variant="ghost" onPress={() => { location.hash = page; }}><Icon name={page} className="size-6 shrink-0" /><span className="flex min-w-0 flex-1 items-center justify-between gap-3"><Typography.Paragraph weight="normal">{title}</Typography.Paragraph><span>{count}</span></span><Icon name="next" className="size-4 shrink-0" /></Button></div>)}
        </div></Panel>
        <Panel title={<span className="flex items-center gap-3"><Icon name="schedules" className="size-6 shrink-0 text-accent" />Следующий запуск</span>} action={<Button isIconOnly variant="ghost" size="sm" aria-label="Открыть расписание" onPress={() => { location.hash = "schedules"; }}><Icon name="next" /></Button>}>
          <div className="flex items-start gap-4"><IconCircle name="schedules" /><div className="flex min-w-0 flex-1 flex-col gap-2">
            <Typography.Paragraph>{next ? next.name : schedules.length ? "Расписание на паузе" : "Запусков пока нет"}</Typography.Paragraph>
            <Typography.Paragraph size="sm" color="muted">{next ? <Timestamp value={next.next_run_at} /> : schedules.length ? `Поручений на паузе: ${schedules.length}` : "Попросите агента настроить."}</Typography.Paragraph>
          </div></div>
          {next ? <div><Button variant="outline" size="sm" isPending={pending === "pause:" + next.id} onPress={() => onCommand("schedule_toggle", { schedule_id: next.id, enabled: false }, "pause:" + next.id)}>Приостановить</Button></div> : null}
        </Panel>
      </aside>
    </div>
    {stats.jobs > 0 ? <Panel title="Сохранённые вакансии" action={<Link href="#search">Все вакансии<Icon name="next" className="size-4 shrink-0" /></Link>}><Typography.Paragraph size="sm" color="muted">Откликов: {stats.applied} · Ответов: {stats.replies}</Typography.Paragraph><Pipeline state={state} onInspect={onInspect} limit={6} /></Panel> : null}
  </>;
}
