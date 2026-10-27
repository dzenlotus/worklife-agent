import { useState } from "react";
import { Alert, Button, Card, TextArea, Tabs, Link, Label, Typography, Select, ListBox, Separator } from "@heroui/react";
import {
  Panel,
  PageHeading,
  Status,
  Empty,
  DataTable,
  AgentButton,
  Timestamp,
  DetailAccordion,
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
                  {job.title} ↗
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
    <section className="flex flex-col gap-4" aria-label="Вакансии"><div className="flex flex-wrap items-center justify-between gap-3"><Typography.Heading level={3}>Вакансии</Typography.Heading><Typography.Paragraph size="sm" color="muted">{list(state.jobs).length} в вашей истории</Typography.Paragraph></div>
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

function LatestActivity({ entry, state, onInspect }) {
  if (!entry) return <Card><Card.Content className="flex flex-col gap-4 py-6">
    <Typography.Heading level={2}>Вызовов MCP пока нет</Typography.Heading>
    <Typography.Paragraph color="muted">Дайте поручение в чате вашего агента. Здесь появятся вызовы MCP и сохранённые результаты.</Typography.Paragraph>
  </Card.Content></Card>;
  const name = resultName(entry.target, state);
  return <Card>
    <Card.Header className="flex flex-col gap-4">
      <div className="flex w-full flex-wrap items-center justify-between gap-3">
        <Typography.Paragraph size="sm" color="muted">Последнее действие</Typography.Paragraph>
        {entry.status ? <Status value={entry.status} /> : null}
      </div>
      {entry.source === "mcp" ? <Typography.Heading level={2}>{entry.summary || (entry.status === "running" ? "Выполняется вызов MCP" : "Вызов MCP записан")}</Typography.Heading> : <Typography.Paragraph weight="medium">{entry.summary || entry.tool}</Typography.Paragraph>}
    </Card.Header>
    <Card.Content className="flex flex-col gap-4">
      {name ? <Typography.Paragraph>{name}</Typography.Paragraph> : null}
      {entry.error ? <Alert status="danger"><Alert.Content><Alert.Description>{entry.error}</Alert.Description></Alert.Content></Alert> : null}
      <div className="flex flex-wrap items-center gap-3">
        {entry.source === "mcp" ? <Typography.Code>{entry.tool}</Typography.Code> : null}
        <Typography.Paragraph size="sm" color="muted"><Timestamp value={entry.at} /></Typography.Paragraph>
        {Number.isFinite(entry.duration_seconds) ? <Typography.Paragraph size="sm" color="muted">{entry.duration_seconds.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} с</Typography.Paragraph> : null}
      </div>
    </Card.Content>
    {entry.target || entry.source === "mcp" ? <Card.Footer className="flex flex-wrap gap-2">
      {entry.target ? <Button variant="secondary" size="sm" onPress={() => onInspect(entry.target.kind, entry.target.id)}>Открыть результат</Button> : null}
      {entry.source === "mcp" ? <Button variant="ghost" size="sm" onPress={() => onInspect("tool_call", entry.id)}>Подробнее о вызове</Button> : null}
    </Card.Footer> : null}
  </Card>;
}

function EarlierActivity({ entries, onInspect }) {
  if (!entries.length) return null;
  return <section className="flex flex-col gap-3" aria-label="Предыдущие действия">
    <Typography.Paragraph size="sm" color="muted">Ранее</Typography.Paragraph>
    <div className="flex flex-col gap-4">{entries.map((entry, index) => <div className="flex flex-col gap-4" key={entry.id}>
      {index ? <Separator /> : null}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <Typography.Paragraph weight="medium">{entry.error || entry.summary || entry.tool}</Typography.Paragraph>
          <div className="flex flex-wrap items-center gap-3">
            {entry.source === "mcp" ? <Typography.Code>{entry.tool}</Typography.Code> : null}
            <Typography.Paragraph size="sm" color="muted"><Timestamp value={entry.at} /></Typography.Paragraph>
            {entry.status ? <Status value={entry.status} /> : null}
          </div>
        </div>
        {entry.source === "mcp" ? <Button variant="ghost" size="sm" onPress={() => onInspect("tool_call", entry.id)}>Подробнее</Button> : entry.target ? <Button variant="ghost" size="sm" onPress={() => onInspect(entry.target.kind, entry.target.id)}>Результат</Button> : null}
      </div>
    </div>)}</div>
  </section>;
}

export default function Overview({ state, pending, onInspect, onCommand }) {
  const stats = statistics(state), activity = monitorActivity(state), calls = list(state.tool_calls);
  const running = calls.filter((call) => call.status === "running");
  const schedules = list(state.schedules), enabled = schedules.filter((schedule) => schedule.enabled);
  const next = enabled.slice().sort((a, b) => (a.next_run_at || "").localeCompare(b.next_run_at || ""))[0];
  const saved = [["resources", "Ресурсы", list(state.resources).length], ["cv", "CV", list(state.cvs).length], ["employers", "Работодатели", employerGroups(state.employers).length], ["strengths", "Сильные стороны", list(state.strengths).length]].filter(([, , count]) => count);
  const activeRuntime = list(state.agent?.runs).find((run) => ["running", "queued", "cancelling"].includes(run.status));
  return <>
    <PageHeading title="Работа агента">
      {running.length ? <Status value="running">В работе: {running.length}</Status> : null}
    </PageHeading>
    {activeRuntime ? <Alert><Alert.Content><Alert.Title>Встроенный исполнитель работает</Alert.Title><Alert.Description>{goalExcerpt(activeRuntime.goal)}</Alert.Description><div className="flex flex-wrap gap-2 py-2"><Button variant="secondary" size="sm" onPress={() => onInspect("run", activeRuntime.id)}>Журнал</Button><Button variant="danger-soft" size="sm" isPending={pending === "cancel:" + activeRuntime.id} onPress={() => onCommand("agent_cancel", { run_id: activeRuntime.id }, "cancel:" + activeRuntime.id)}>Остановить</Button></div></Alert.Content></Alert> : null}
    <div className="flex flex-col gap-8 xl:flex-row">
      <section className="flex min-w-0 flex-1 flex-col gap-6" aria-label="Журнал работы">
        <LatestActivity entry={activity[0]} state={state} onInspect={onInspect} />
        <EarlierActivity entries={activity.slice(1, 5)} onInspect={onInspect} />
        {activity.length ? <div className="flex flex-wrap items-center justify-between gap-3"><Typography.Paragraph size="sm" color="muted">{calls.length ? `Вызовов MCP в журнале: ${calls.length}` : `Событий в журнале: ${activity.length}`}</Typography.Paragraph><Button variant="ghost" size="sm" onPress={() => onInspect("activity")}>Весь журнал</Button></div> : null}
      </section>
      {saved.length || schedules.length ? <aside className="flex w-full flex-col gap-6 xl:w-64 xl:shrink-0" aria-label="Сводка работы">
        {saved.length ? <section className="flex flex-col gap-4" aria-labelledby="saved-heading">
          <Typography.Heading level={4} id="saved-heading">Сохранено</Typography.Heading>
          <dl className="flex flex-col gap-3">{saved.map(([page, title, count]) => <div className="flex items-center justify-between gap-3" key={page}><dt><Link href={`#${page}`}>{title}</Link></dt><dd>{count}</dd></div>)}</dl>
        </section> : null}
        {saved.length && schedules.length ? <Separator /> : null}
        {schedules.length ? <section className="flex flex-col gap-3" aria-labelledby="schedule-heading">
          <div className="flex flex-wrap items-center justify-between gap-3"><Typography.Heading level={4} id="schedule-heading">Расписание</Typography.Heading>{schedules.length ? <Status value={next ? "planned" : "paused"} /> : null}</div>
          {next ? <><Typography.Paragraph size="sm">{next.name}</Typography.Paragraph><Typography.Paragraph size="sm" color="muted"><Timestamp value={next.next_run_at} /></Typography.Paragraph><div><Button variant="outline" size="sm" isPending={pending === "pause:" + next.id} onPress={() => onCommand("schedule_toggle", { schedule_id: next.id, enabled: false }, "pause:" + next.id)}>Приостановить</Button></div></> : <Typography.Paragraph size="sm" color="muted">Заданий на паузе: {schedules.length}</Typography.Paragraph>}
          <Link href="#schedules">Открыть расписание</Link>
        </section> : null}
      </aside> : null}
    </div>
    {stats.jobs > 0 ? <><Separator /><div className="flex flex-wrap items-center justify-between gap-3"><Typography.Paragraph size="sm" color="muted">Откликов: {stats.applied} · Ответов: {stats.replies}</Typography.Paragraph><Link href="#search">Открыть поиск</Link></div><Pipeline state={state} onInspect={onInspect} limit={6} /></> : null}
  </>;
}
