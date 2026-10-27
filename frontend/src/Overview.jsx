import { useState } from "react";
import { Button, TextArea, Tabs, Link, Label, Typography } from "@heroui/react";
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
import { list, statistics, filterJobs, formatDate, safeURL, currentConditions, activitySummary, goalExcerpt } from "./model.js";

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
    <Panel title="Конвейер вакансий" >
      <Tabs
        selectedKey={filter}
        onSelectionChange={setFilter}

      >
        <Tabs.ListContainer>
          <Tabs.List aria-label="Состояние вакансий">
            {filters.map(([key, title]) => (
              <Tabs.Tab id={key} key={key}>
                {title}
                {key === "all" ? (
                  <span >
                    {list(state.jobs).length}
                  </span>
                ) : null}
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
    </Panel>
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
      <div className="flex flex-wrap items-center justify-between gap-3">

        <Label htmlFor="agent-goal">Основная цель поиска</Label>
        <span>ПОИСК РАБОТЫ</span>
      </div>
      <TextArea
        id="agent-goal"
        ref={inputRef}
        aria-label="Поручение агенту"
        placeholder="Найди удалённую работу под мои условия. Изучи подходящие компании и подготовь следующие шаги…"
        rows={3}
        maxLength={16000}
        value={goal}
        onChange={(event) => setGoal(event.target.value)}
        className="w-full"
      />
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3"><strong>Учитывать в каждом поручении</strong><Button variant="ghost" size="sm" onPress={onConditions}>{conditions.length ? "Изменить условия" : "Добавить условия"}</Button></div>
        {conditions.length ? <ul className="flex flex-col gap-2">{conditions.slice(0, 3).map((condition, index) => <li key={index}>{condition}</li>)}</ul> : <p>Укажите доход, график и ограничения, которые важны для вас.</p>}
        {conditions.length > 3 ? <DetailAccordion title={`Все условия (${conditions.length})`}><ul className="flex flex-col gap-2">{conditions.slice(3).map((condition, index) => <li key={index}>{condition}</li>)}</ul></DetailAccordion> : null}
      </div>
      {context ? <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3"><Label htmlFor="agent-context">Текущее уточнение</Label><Button variant="ghost" size="sm" onPress={() => setContext(null)}>Убрать уточнение</Button></div>
        <TextArea id="agent-context" aria-label="Уточнение поручения" rows={3} maxLength={16000} value={context.text} onChange={(event) => setContext({ ...context, text: event.target.value })} />
        <p>Выполнится вместе с основной целью и её ограничениями.</p>
      </div> : null}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p>
          Цель и уточнение сохраняются на этом устройстве. Агент сам организует источники и сохраняет ход работы.
        </p>
        <Button
          type="submit"
          isPending={pending}
          isDisabled={configured !== false && !goal.trim() && !context?.text?.trim()}

        >
          {configured === false ? "Подключить модель" : "Запустить поручение"}

        </Button>
      </div>
      {configured === false ? (
        <p >
          Перед первым запуском укажите сервис и модель. Поручение сохранится.
        </p>
      ) : null}
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
export default function Overview({
  state,
  goal,
  setGoal,
  onRun,
  pending,
  onInspect,
  onConditions,
  onCommand,
  inputRef,
  context,
  setContext,
}) {
  const stats = statistics(state),
    runs = list(state.agent?.runs),
    active = runs.find((run) =>
      ["running", "queued", "cancelling"].includes(run.status),
    );
  const activity = list(state.activity)
    .slice()
    .sort((a, b) => (b.at || "").localeCompare(a.at || ""))
    .slice(0, 5);
  const schedules = list(state.schedules),
    paused = schedules.filter((s) => !s.enabled),
    next = schedules
      .filter((s) => s.enabled)
      .sort((a, b) =>
        (a.next_run_at || "").localeCompare(b.next_run_at || ""),
      )[0];
  const hasStatistics = stats.jobs > 0 || stats.applied > 0 || stats.replies > 0,
    firstUse = !runs.length && !activity.length && !schedules.length && !hasStatistics;
  return (
    <>
      <PageHeading
        title="Обзор"
        description="Ваша цель, действия агента и результаты поиска."
      >
        <Button variant="outline" size="sm" onPress={onConditions}>
          Мои условия
        </Button>
      </PageHeading>
      <GoalComposer
        goal={goal}
        setGoal={setGoal}
        onRun={onRun}
        pending={pending === "agent"}
        configured={state.agent?.configured}
        inputRef={inputRef}
        context={context}
        setContext={setContext}
        profile={state.profile}
        onConditions={onConditions}
      />
      {active ? (
        <div className="flex flex-wrap items-center gap-3">
          <Status value={active.status} />
          <span>{goalExcerpt(active.goal)}</span>
          <Button
            variant="ghost"
            size="sm"
            onPress={() => onInspect("run", active.id)}
          >
            Ход работы
          </Button>
          <Button
            variant="danger-soft"
            size="sm"
            isPending={pending === "cancel:" + active.id}
            onPress={() =>
              onCommand(
                "agent_cancel",
                { run_id: active.id },
                "cancel:" + active.id,
              )
            }
          >
            Остановить
          </Button>
        </div>
      ) : null}
      {firstUse ? <div className="flex flex-col gap-3 py-4">

        <div><Typography.Heading level={2}>Поручений пока не было</Typography.Heading><p>{state.agent?.configured ? "Запустите цель выше. Здесь появятся действия агента и фактические результаты." : "Подключите модель, чтобы начать. Ваша цель и условия останутся на месте."}</p></div>
      </div> : <div className={!hasStatistics && !schedules.length ? "flex flex-col gap-6" : "grid gap-6 lg:grid-cols-2"}>
        <Panel
          title="Активность агента"

          action={
            <Button
              variant="ghost"
              size="sm"
              onPress={() => onInspect("activity")}
            >
              Все события ↗
            </Button>
          }
        >
          {activity.length ? (
            <ol className="flex flex-col gap-4">
              {activity.map((event) => (
                <li key={event.id}>
                  <time>{formatDate(event.at, true)}</time>
                  <span >

                  </span>
                  <div>
                    <strong>{activitySummary(event, state).text}</strong>
                    {activitySummary(event, state).target ? <Button variant="ghost" size="sm" onPress={() => {
                      const target = activitySummary(event, state).target;
                      onInspect(target.kind, target.id);
                    }}>Открыть результат</Button> : null}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <Empty icon="activity" title="Агент ещё не запускался">
              Задайте цель. Здесь появятся его действия и фактические
              результаты.
            </Empty>
          )}
        </Panel>
        {hasStatistics || schedules.length ? <div className="flex flex-col gap-4">
          {hasStatistics ? <Panel
            title="Статистика поиска"
            action={<span >Ваша история</span>}
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="flex flex-col gap-2">
                <span>Найдено вакансий</span>
                <strong>{stats.jobs}</strong>
              </div>
              <div className="flex flex-col gap-2">
                <span>Отправлено откликов</span>
                <strong>{stats.applied}</strong>
              </div>
              <div className="flex flex-col gap-2">
                <span>Получено ответов</span>
                <strong>{stats.replies}</strong>
              </div>
            </div>
          </Panel> : null}
          {schedules.length ? <Panel >

            <div>
              <Typography.Heading level={2}>Следующий запуск</Typography.Heading>
              <p>
                {next
                  ? formatDate(next.next_run_at)
                  : "Расписание на паузе"}
              </p>
              <span>
                {next ? next.name : `Заданий на паузе: ${paused.length}. Можно продолжить в расписании.`}
              </span>
            </div>
            {next ? (
              <Button
                variant="ghost"
                size="sm"
                onPress={() =>
                  onCommand(
                    "schedule_toggle",
                    { schedule_id: next.id, enabled: false },
                    "pause:" + next.id,
                  )
                }
              >
                Пауза
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onPress={() => {
                  location.hash = "schedules";
                }}
              >
                Расписание ↗
              </Button>
            )}
          </Panel> : null}
        </div> : null}
      </div>}
      {hasStatistics ? <Pipeline state={state} onInspect={onInspect} limit={6} /> : null}
      <div className="flex flex-col gap-4">
        <RunHistory runs={runs} onInspect={onInspect} />
      </div>
    </>
  );
}
