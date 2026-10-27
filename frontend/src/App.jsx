import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Input, TextArea, Spinner, Link, Label, Typography, Alert, CloseButton, Separator, Surface, Accordion } from "@heroui/react";
import { typographyVariants } from "@heroui/styles";
import Overview, { ActivityLog, GoalComposer, RunHistory } from "./Overview.jsx";
import ModelConnection from "./ModelConnection.jsx";
import { composeGoal, readDraft, saveDraft } from "./goals.js";
import { documentBlocks } from "./document.js";
import { resultTarget } from "./activity.js";
import {
  Panel,
  Status,
  DataTable,
  DetailAccordion,
  Timestamp,
  Dialog,
  Icon,
} from "./ui.jsx";
import { list, label, formatDate, safeURL, scheduleResult } from "./model.js";
import {
  SearchView,
  MarketView,
  SchedulesView,
  ExperimentsView,
  StrengthsView,
  CVView,
  EmployersView,
  ResourcesView,
  AccountsView,
  RepositoriesView,
  TacticsView,
  SettingsView,
} from "./views.jsx";

const navigation = [
  ["overview", "Обзор"],
  ["market", "Рынок"],
  ["search", "Вакансии"],
  ["schedules", "Расписание"],
  ["experiments", "Эксперименты"],
  ["strengths", "Сильные стороны"],
  ["cv", "CV"],
  ["employers", "Работодатели"],
  ["resources", "Ресурсы"],
  ["accounts", "Аккаунты"],
  ["repositories", "Репозитории"],
  ["tactics", "Тактики"],
  ["settings", "Настройки"],
];
const pageFromHash = () =>
  navigation.some(([key]) => key === location.hash.slice(1))
    ? location.hash.slice(1)
    : "overview";
const stringify = (value) => JSON.stringify(value, null, 2);
function errorText(error) {
  const text = error?.message || String(error);
  if (text.includes("Agent not configured"))
    return "Модель агента ещё не подключена. Откройте настройки и инструкцию по подключению.";
  return text;
}
async function invoke(name, args) {
  const response = await fetch(`/api/tools/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Worklife-Client": "local",
    },
    body: JSON.stringify(args),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error("Не удалось прочитать ответ локального приложения.");
  }
  if (!response.ok || result.ok === false)
    throw new Error(
      typeof result.error === "string"
        ? result.error
        : "Не удалось выполнить поручение.",
    );
  return result.result;
}
function RunDetails({ run }) {
  if (!run) return <p >Запуск не найден.</p>;
  return (
    <>
      <p >{run.goal}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Status value={run.status} />
        <span>{list(run.steps).length} шагов</span>
        <span>{run.model}</span>
        <Timestamp value={run.started_at || run.created_at} />
      </div>
      {run.error ? <p >{run.error}</p> : null}
      {run.final_answer ? (
        <div >{run.final_answer}</div>
      ) : null}
      {list(run.steps).length ? (
        list(run.steps).map((step) => (
          <section className="flex flex-col gap-3 py-3" key={step.index}>
            <Typography.Heading level={3}>
              <span>Шаг {step.index}</span>
              <time>{formatDate(step.started_at, true)}</time>
            </Typography.Heading>
            {step.assistant?.content ? <p>{step.assistant.content}</p> : null}
            {list(step.assistant?.tool_calls).map((call, index) => (
              <DetailAccordion
                key={call.id || index}
                id={call.id || `call-${index}`}
                title={call.function?.name || "Действие агента"}
              >
                <pre>{call.function?.arguments}</pre>
              </DetailAccordion>
            ))}
            {list(step.tool_results).length ? (
              <DetailAccordion
                id={`results-${step.index}`}
                title="Результаты действий"
              >
                <pre>{stringify(step.tool_results)}</pre>
              </DetailAccordion>
            ) : null}
          </section>
        ))
      ) : (
        <p >Агент ещё не начал выполнять шаги.</p>
      )}
    </>
  );
}
function DetailContent({ detail, state, onDownload, pending, onInspect }) {
  if (!detail) return null;
  if (detail.kind === "run")
    return (
      <RunDetails
        run={list(state.agent?.runs).find((run) => run.id === detail.id)}
      />
    );
  if (detail.kind === "activity")
    return <ActivityLog state={state} onInspect={onInspect} />;
  if (detail.kind === "resource") {
    const resource = list(state.resources).find((entry) => entry.id === detail.id);
    if (!resource) return <p>Ресурс не найден.</p>;
    return <>
      <h3 className={typographyVariants({ type: "h2", weight: "medium" }).base()}>{resource.name}</h3>
      {resource.notes ? <p>{resource.notes}</p> : null}
      {safeURL(resource.url) ? <Link href={resource.url} target="_blank" rel="noreferrer">Открыть источник<Icon name="external" className="size-4 shrink-0" /></Link> : null}
    </>;
  }
  if (detail.kind === "tool_call") {
    const call = list(state.tool_calls).find((entry) => entry.id === detail.id);
    if (!call) return <p>Вызов не найден.</p>;
    const target = resultTarget(call.related_id, state);
    return <>
      <h3 className={typographyVariants({ type: "h2", weight: "medium" }).base()}>{call.tool}</h3>
      <div className="flex flex-wrap items-center gap-3"><Status value={call.status} /><Timestamp value={call.started_at} />{Number.isFinite(call.duration_seconds) ? <span>{call.duration_seconds.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} с</span> : null}</div>
      {call.summary ? <p>{call.summary}</p> : null}
      {call.error ? <Alert status="danger"><Alert.Content><Alert.Description>{call.error}</Alert.Description></Alert.Content></Alert> : null}
      {call.finished_at ? <Typography.Paragraph size="sm" color="muted">Завершён: <Timestamp value={call.finished_at} /></Typography.Paragraph> : null}
      {target ? <Button variant="outline" onPress={() => onInspect(target.kind, target.id)}>Открыть сохранённый результат</Button> : null}
    </>;
  }
  if (detail.kind === "cv") {
    const cv = list(state.cvs).find((cv) => cv.id === detail.id);
    if (!cv) return null;
    return (
      <>
        <Typography.Paragraph size="sm" color="muted">{cv.name || cv.headline}{cv.language ? ` · ${cv.language}` : ""}</Typography.Paragraph>
        <Typography.Prose>{documentBlocks(cv.markdown).map((block, index) => block.type === "heading" ? <Typography.Heading key={index} level={Math.min(block.level + 1, 6)}>{block.text}</Typography.Heading> : block.type === "list" ? <ul key={index}>{block.items.map((text, itemIndex) => <li key={itemIndex}>{text}</li>)}</ul> : <Typography.Paragraph key={index}>{block.text}</Typography.Paragraph>)}</Typography.Prose>
        <DetailAccordion title="Исходный Markdown" id="cv-source"><div className="overflow-x-auto"><pre>{cv.markdown}</pre></div></DetailAccordion>
        <div className="flex flex-wrap gap-2">
          {["pdf", "md", "html"].map((format) => (
            <Button
              variant="outline"
              size="sm"
              key={format}
              isPending={pending === `download:${format}`}
              onPress={() => onDownload(cv.id, format)}
            >
              Скачать {format.toUpperCase()}
            </Button>
          ))}
        </div>
      </>
    );
  }
  if (detail.kind === "experiment") {
    const report = list(state.experiment_reports).find(
      (report) => report.experiment?.id === detail.id,
    );
    if (!report) return <p>Результат ещё не рассчитан.</p>;
    return (
      <>
        <p >{report.experiment.hypothesis}</p>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={report.conclusion} />
          <span>Окно: {report.experiment.horizon_hours} ч.</span>
        </div>
        <DataTable
          headers={[
            "CV",
            "Назначено",
            "Отправлено",
            "Созрело",
            "Успехи",
            "Доля",
          ]}
          rows={list(report.variants).map((variant) => [
            list(state.cvs).find((cv) => cv.id === variant.variant_id)?.name ||
              variant.variant_id,
            variant.assigned,
            variant.exposed,
            variant.mature,
            variant.successes,
            variant.rate == null ? "—" : `${Math.round(variant.rate * 100)}%`,
          ])}
        />
        <p >
          В расчёт входят отправленные отклики с завершённым окном наблюдения.
          Малое количество данных не доказывает эффективность подхода.
        </p>
      </>
    );
  }
  if (detail.kind === "job") {
    const job = list(state.jobs).find((job) => job.id === detail.id);
    if (!job) return null;
    const application = list(state.applications).find((entry) => entry.job_id === job.id),
      actions = list(state.actions).filter((entry) => entry.payload?._job_id === job.id),
      cv = list(state.cvs).find((entry) => entry.id === application?.cv_id);
    const fields = {
      employer: "Компания",
      remote: "Удалённо",
      salary_min: "Зарплата от",
      salary_max: "Зарплата до",
      currency: "Валюта",
      salary_period: "Период оплаты",
      hours: "Часов в неделю",
      hiring_stages: "Этапов найма",
      test_hours: "Объём тестового, часов",
      employer_domain: "Домен компании",
      notes: "Заметки",
    };
    return (
      <>
        <h3 className={typographyVariants({ type: "h2", weight: "medium" }).base()}>{job.title}</h3>
        <div className="flex flex-wrap items-center gap-3"><Status value={job.blocked ? "blocked" : application?.stage || "new"} /><Timestamp value={job.fetched_at} /></div>
        {job.description ? <p>{job.description}</p> : null}
        <dl className="grid gap-3">
          {Object.entries(fields)
            .filter(([key]) => job[key] != null)
            .map(([key, title]) => (
              <div key={key}>
                <dt>{title}</dt>
                <dd>
                  {typeof job[key] === "boolean"
                    ? job[key]
                      ? "Да"
                      : "Нет"
                    : typeof job[key] === "object"
                      ? job[key].name
                      : String(job[key])}
                </dd>
              </div>
            ))}
        </dl>
        {application ? <section className="flex flex-col gap-3"><Typography.Heading level={3}>Ваш отклик</Typography.Heading>
          {cv ? <Button variant="ghost" size="sm" onPress={() => onInspect("cv", cv.id)}>CV: {cv.name || cv.headline}</Button> : null}
          {list(application.history).length ? <ol className="flex flex-col gap-3">{list(application.history).map((event, index) => <li className="flex flex-col gap-2" key={index}><div className="flex flex-wrap items-center gap-3"><Status value={event.stage} /><Timestamp value={event.at} /></div>{event.note ? <p>{event.note}</p> : null}</li>)}</ol> : null}
          {actions.length ? actions.map((action) => <Button variant="outline" size="sm" key={action.id} onPress={() => onInspect("action", action.id)}>Открыть действие · {label(action.status)}</Button>) : <Typography.Paragraph size="sm" color="muted">Показана сохранённая история отклика. Связанного журнала отправки в локальных данных нет; содержание сообщения здесь не подтверждено.</Typography.Paragraph>}
        </section> : null}
        {safeURL(job.url) ? (
          <Link

            href={safeURL(job.url)}
            target="_blank"
            rel="noreferrer"
          >
            Открыть источник<Icon name="external" className="size-4 shrink-0" />
          </Link>
        ) : null}
      </>
    );
  }
  const bucket = detail.kind === "action" ? "actions" : "schedule_runs",
    record = list(state[bucket]).find((record) => record.id === detail.id);
  if (!record) return null;
  const scheduled = detail.kind === "schedule_run" ? scheduleResult(record, state) : null;
  return (
    <>
      {scheduled ? <>
        <p >{scheduled.title}</p>
        <p >{scheduled.text}</p>
        {scheduled.next ? <p >{scheduled.next}</p> : null}
      </> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Status value={record.status} />
        <Timestamp value={record.created_at || record.started_at} />
      </div>
      {detail.kind === "action" ? (
        <>
          <p >
            {record.operation} · {record.connector}
          </p>
          {record.payload?.subject ? <Typography.Heading level={3}>{record.payload.subject}</Typography.Heading> : null}
          {record.payload?.body || record.payload?.text ? (
            <p >
              {record.payload.body || record.payload.text}
            </p>
          ) : null}
        </>
      ) : null}
      <DetailAccordion title="Технические подробности" id="record-data">
        <pre>{stringify(record)}</pre>
      </DetailAccordion>
    </>
  );
}
function Navigation({ page, onNavigate }) {
  const primary = ["overview", "market", "search", "employers", "schedules"];
  const groups = [
    ["materials", "Материалы", ["cv", "strengths", "repositories"]],
    ["tools", "Инструменты", ["resources", "accounts", "experiments", "tactics"]],
  ];
  const activeGroup = groups.find(([, , keys]) => keys.includes(page))?.[0];
  const item = (key) => <Button key={key} className="min-h-12 justify-start gap-5" fullWidth size="lg" variant={page === key ? "secondary" : "ghost"} aria-current={page === key ? "page" : undefined} onPress={() => onNavigate(key)}>
    <Icon name={key} className="size-6 shrink-0" /><span>{navigation.find(([id]) => id === key)[1]}</span>
  </Button>;
  return <nav className="flex flex-col gap-5" aria-label="Разделы Worklife">
    <div className="flex flex-col gap-2">{primary.map(item)}</div>
    <Separator />
    <Accordion key={activeGroup || "main"} defaultExpandedKeys={activeGroup ? [activeGroup] : []} hideSeparator>
      {groups.map(([id, title, keys]) => <Accordion.Item id={id} key={id}>
        <div className="flex"><Accordion.Trigger className="min-h-14 px-4"><span className="flex items-center gap-5"><Icon name={id} className="size-6 shrink-0" /><Typography.Paragraph>{title}</Typography.Paragraph></span><Accordion.Indicator /></Accordion.Trigger></div>
        <Accordion.Panel><Accordion.Body><div className="flex flex-col gap-1">{keys.map(item)}</div></Accordion.Body></Accordion.Panel>
      </Accordion.Item>)}
    </Accordion>
    {item("settings")}
  </nav>;
}
export default function App() {
  const [state, setState] = useState(null),
    [error, setError] = useState(""),
    [page, setPage] = useState(pageFromHash),
    [navigationOpen, setNavigationOpen] = useState(false),
    [draft, setDraft] = useState({ author: "", goal: "", context: null }),
    [modelDialog, setModelDialog] = useState(null),
    [pending, setPending] = useState(""),
    [message, setMessage] = useState(""),
    [updated, setUpdated] = useState(null);
  const [conditionsOpen, setConditionsOpen] = useState(false),
    [conditions, setConditions] = useState(""),
    [blockOpen, setBlockOpen] = useState(false),
    [blockDomain, setBlockDomain] = useState(""),
    [blockReason, setBlockReason] = useState(""),
    [blockEvidence, setBlockEvidence] = useState(""),
    [detail, setDetail] = useState(null);
  const inputRef = useRef(null),
    timer = useRef(null);
  const author = state?.network?.author,
    goal = draft.goal,
    context = draft.context;
  const setGoal = (value) => setDraft((previous) => ({ ...previous, goal: value }));
  const setContext = (value) => setDraft((previous) => ({ ...previous, context: value }));
  useEffect(() => {
    if (!author) return;
    let saved = { goal: "", context: null };
    try { saved = readDraft(window.localStorage, author); } catch {}
    setDraft({ author, ...saved });
  }, [author]);
  useEffect(() => {
    if (author && draft.author === author) {
      try { saveDraft(window.localStorage, author, draft); } catch {}
    }
  }, [author, draft]);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) throw new Error("Локальное приложение недоступно.");
      const value = await response.json();
      if (value.ok === false)
        throw new Error(value.error || "Не удалось загрузить данные.");
      setState(value.result || value);
      setError("");
      setUpdated(new Date());
      return value.result || value;
    } catch (error) {
      setError(errorText(error));
      return null;
    }
  }, []);
  useEffect(() => {
    refresh();
    const poll = setInterval(() => {
      if (!document.hidden) refresh();
    }, 10000);
    return () => clearInterval(poll);
  }, [refresh]);
  useEffect(() => {
    const change = () => {
      setPage(pageFromHash());
      setNavigationOpen(false);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  const notify = useCallback((text) => {
    setMessage(text);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setMessage(""), 8000);
  }, []);
  async function command(name, args, key = name) {
    setPending(key);
    try {
      const result = await invoke(name, args);
      await refresh();
      notify(
        name === "agent_cancel"
          ? "Остановка запрошена."
          : name === "schedule_toggle"
            ? args.enabled
              ? "Поиск по расписанию продолжится."
              : "Поиск по расписанию на паузе."
            : name === "employer_block"
              ? args.blocked
                ? "Компания исключена из вашего поиска."
                : "Блокировка снята."
              : "Сохранено.",
      );
      return result;
    } catch (error) {
      notify(errorText(error));
      throw error;
    } finally {
      setPending("");
    }
  }
  const safeCommand = (...args) => command(...args).catch(() => {});
  function openModel(runAfter = false) {
    setDetail(null);
    setModelDialog({ runAfter: runAfter && Boolean(composeGoal(goal, context)) });
  }
  async function runGoal(connected = false) {
    if (!connected && !state.agent?.configured) { openModel(true); return; }
    const text = composeGoal(goal, context);
    if (!text.trim()) return;
    if (text.length > 16000) { notify("Поручение слишком длинное. Сократите цель или уточнение до 16 000 знаков вместе."); return; }
    setPending("agent");
    try {
      await invoke("agent_run", { goal: text.trim(), max_steps: 8 });
      await refresh();
      setContext(null);
      notify("Агент принял поручение. Ход работы появится ниже.");
    } catch (error) {
      notify(errorText(error));
    } finally {
      setPending("");
    }
  }
  function openConditions() {
    setConditions(list(state?.profile?.life_preferences).join("\n"));
    setConditionsOpen(true);
  }
  function openBlock(domain) {
    setBlockDomain(domain);
    setBlockReason("");
    setBlockEvidence("");
    setBlockOpen(true);
  }
  async function saveConditions(event) {
    event.preventDefault();
    try {
      await command(
        "profile_save",
        {
          profile: {
            ...(state.profile || {}),
            life_preferences: conditions
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean),
          },
        },
        "conditions",
      );
      setConditionsOpen(false);
    } catch {}
  }
  async function saveBlock(event) {
    event.preventDefault();
    try {
      await command(
        "employer_block",
        {
          domain: blockDomain.trim(),
          reason: blockReason.trim(),
          evidence_url: blockEvidence.trim(),
          blocked: true,
        },
        "block",
      );
      setBlockOpen(false);
    } catch {}
  }
  async function downloadCV(id, format) {
    setPending(`download:${format}`);
    try {
      const response = await fetch(
        `/api/cv/${encodeURIComponent(id)}/download?format=${format}`,
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Не удалось сформировать файл.");
      }
      const objectURL = URL.createObjectURL(await response.blob()),
        link = document.createElement("a");
      link.href = objectURL;
      link.download = `worklife-cv.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
    } catch (error) {
      notify(errorText(error));
    } finally {
      setPending("");
    }
  }
  const onInspect = (kind, id) => setDetail({ kind, id });
  const props = {
    state,
    onInspect,
    onCommand: safeCommand,
    pending,
    onConditions: openConditions,
    onBlock: openBlock,
    onModel: () => openModel(false),
    runtime: <div className="flex flex-col gap-4">
      <Typography.Paragraph>Необязательный автономный исполнитель Worklife. Его подключение не требуется для работы через вашего MCP-агента.</Typography.Paragraph>
      <div className="flex flex-wrap items-center gap-3"><Status value={state?.agent?.configured ? "success" : "planned"}>{state?.agent?.configured ? "Модель настроена" : "Модель не подключена"}</Status>{state?.agent?.configured ? <Button variant="outline" size="sm" onPress={() => openModel(false)}>Изменить модель исполнителя</Button> : null}</div>
      <GoalComposer goal={goal} setGoal={setGoal} onRun={runGoal} pending={pending === "agent"} configured={state?.agent?.configured} inputRef={inputRef} context={context} setContext={setContext} profile={state?.profile} onConditions={openConditions} />
      <RunHistory runs={list(state?.agent?.runs)} onInspect={onInspect} />
    </div>,
  };
  const views = {
    market: MarketView,
    search: SearchView,
    schedules: SchedulesView,
    experiments: ExperimentsView,
    strengths: StrengthsView,
    cv: CVView,
    employers: EmployersView,
    resources: ResourcesView,
    accounts: AccountsView,
    repositories: RepositoriesView,
    tactics: TacticsView,
    settings: SettingsView,
  };
  const View = views[page];
  const title = navigation.find(([key]) => key === page)?.[1] || "Обзор";
  const navigate = (key) => {
    location.hash = key;
    setPage(key);
    setNavigationOpen(false);
  };
  const detailTitle =
    detail?.kind === "run"
      ? "Ход работы агента"
      : detail?.kind === "cv"
        ? "Ваше CV"
        : detail?.kind === "job"
          ? "Условия вакансии"
          : detail?.kind === "experiment"
            ? "Результаты эксперимента"
            : detail?.kind === "activity"
              ? "Журнал работы"
              : detail?.kind === "tool_call"
                ? "Вызов MCP"
              : "Подробности действия";
  return (
    <>
    <Link className="sr-only focus:not-sr-only" onPress={() => document.getElementById("app-main")?.focus()}>К содержанию</Link>
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="hidden md:sticky md:top-0 md:flex md:h-dvh md:w-60 md:shrink-0">
        <Surface className="flex min-h-0 w-full flex-col gap-8 p-4">
          <div className="flex shrink-0 flex-col gap-1 px-3 py-2">
            <Link href="#overview" aria-label="Worklife — обзор"><p className={typographyVariants({ type: "h3", weight: "medium" }).base()}>Worklife</p></Link>
            <Typography.Paragraph size="sm" color="muted">MCP-инструменты</Typography.Paragraph>
          </div>
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto"><Navigation page={page} onNavigate={navigate} /></div>
          <div className="mt-auto flex shrink-0 flex-col gap-3 px-3 py-3">
            <Separator />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Button variant="ghost" size="sm" aria-label="Обновить данные" onPress={refresh}><Icon name="refresh" />Обновить</Button>
              <Typography.Paragraph size="xs" color="muted" aria-label="Время обновления данных">{error ? "Нет связи" : updated ? updated.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }) : "Загрузка…"}</Typography.Paragraph>
            </div>
          </div>
        </Surface>
      </aside>
      <div className="flex w-full min-w-0 flex-1 flex-col gap-6 p-5 md:p-8 md:py-6">
        <header className="flex items-center justify-between md:hidden">
          <Button variant="secondary" aria-expanded={navigationOpen} onPress={() => setNavigationOpen(true)}><Icon name="menu" />Разделы</Button>
          <Button variant="ghost" size="sm" aria-label="Обновить данные" onPress={refresh}><Icon name="refresh" />Обновить</Button>
        </header>
        {message ? <Alert><Alert.Content><Alert.Description>{message}</Alert.Description></Alert.Content><CloseButton aria-label="Закрыть уведомление" onPress={() => setMessage("")} /></Alert> : null}
        <main id="app-main" className="flex flex-col gap-6" tabIndex={-1}>
          {!state ? (
            <div className="flex flex-col gap-4 py-8">
              {error ? (
                <>

                  <Typography.Heading level={1}>Не удалось подключиться</Typography.Heading>
                  <p>
                    {error} Проверьте, что Worklife запущен на вашем компьютере.
                  </p>
                  <Button variant="outline" onPress={refresh}>
                    Попробовать ещё раз
                  </Button>
                </>
              ) : (
                <>
                  <Spinner />
                  <Typography.Heading level={1}>Открываем Worklife</Typography.Heading>
                  <p>Загружаем вашу историю поиска.</p>
                </>
              )}
            </div>
          ) : View ? (
            <View {...props} />
          ) : (
            <Overview
              {...props}
              goal={goal}
              setGoal={setGoal}
              context={context}
              setContext={setContext}
              onRun={runGoal}
              inputRef={inputRef}
            />
          )}
        </main>
      </div>
      <Dialog open={navigationOpen} onClose={() => setNavigationOpen(false)} title="Разделы Worklife">
        <Navigation state={state} page={page} onNavigate={navigate} />
      </Dialog>
      {state ? (
        <>
          <Dialog
            open={conditionsOpen}
            onClose={() => setConditionsOpen(false)}
            title="Мои условия"
            footer={
              <>
                <Button
                  variant="ghost"
                  onPress={() => setConditionsOpen(false)}
                >
                  Отмена
                </Button>
                <Button
                  type="submit"
                  form="conditions-form"
                  isPending={pending === "conditions"}
                >
                  Сохранить условия
                </Button>
              </>
            }
          >
            <form id="conditions-form" className="flex flex-col gap-3" onSubmit={saveConditions}>
              <p >
                Опишите обычными словами, какую работу вы ищете: доход, график,
                место и то, что для вас важно.
              </p>
              <TextArea
                aria-label="Условия поиска работы"
                rows={7}
                value={conditions}
                onChange={(event) => setConditions(event.target.value)}
                placeholder="Хочу работать удалённо, до 40 часов в неделю. Важно…"
              />
              <p >
                Агент учтёт эти условия в следующих поручениях. Факты опыта и
                готовые CV сохранятся.
              </p>
            </form>
          </Dialog>
          <Dialog
            open={blockOpen}
            onClose={() => setBlockOpen(false)}
            title="Блокировать компанию"
            footer={
              <>
                <Button variant="ghost" onPress={() => setBlockOpen(false)}>
                  Отмена
                </Button>
                <Button
                  variant="danger"
                  type="submit"
                  form="block-form"
                  isPending={pending === "block"}
                >
                  Блокировать
                </Button>
              </>
            }
          >
            <form
              id="block-form"
              className="flex flex-col gap-3"
              onSubmit={saveBlock}
            >
              <p >
                Это ваше локальное исключение. Агент учитывает его, когда связь
                вакансии или контакта с компанией установлена.
              </p>
              <Label htmlFor="block-domain">Домен компании</Label>
              <Input
                id="block-domain"
                value={blockDomain}
                onChange={(event) => setBlockDomain(event.target.value)}
                placeholder="company.example"
                required
              />
              <Label htmlFor="block-reason">Причина</Label>
              <TextArea
                id="block-reason"
                rows={3}
                value={blockReason}
                onChange={(event) => setBlockReason(event.target.value)}
                required
              />
              <Label htmlFor="block-evidence">
                Ссылка на источник · необязательно
              </Label>
              <Input
                id="block-evidence"
                type="url"
                value={blockEvidence}
                onChange={(event) => setBlockEvidence(event.target.value)}
              />
            </form>
          </Dialog>
          <Dialog
            open={!!detail}
            onClose={() => setDetail(null)}
            title={detailTitle}
          >
            <DetailContent
              detail={detail}
              state={state}
              onDownload={downloadCV}
              pending={pending}
              onInspect={onInspect}
            />
          </Dialog>
          {modelDialog ? <ModelConnection
            initial={state.agent?.connection}
            runAfter={modelDialog.runAfter}
            onClose={() => setModelDialog(null)}
            onSaved={async (_connection, continueGoal) => {
              await refresh();
              setModelDialog(null);
              if (continueGoal) await runGoal(true);
              else notify("Параметры модели сохранены. Теперь можно запустить поручение.");
            }}
          /> : null}
        </>
      ) : null}
    </div>
    </>
  );
}
