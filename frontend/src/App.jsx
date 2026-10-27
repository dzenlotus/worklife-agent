import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Input,
  TextArea,
  Spinner,
  Link,
  Label,
  Typography,
  Alert,
  CloseButton,
  Separator,
  Surface,
  Accordion,
} from "@heroui/react";
import { typographyVariants } from "@heroui/styles";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import {
  SearchBoard,
  MarketBoard,
  ResumeBoard,
  JobDetails,
  CareerEvents,
  SelectField,
} from "./AgencyViews.jsx";
import Overview, {
  ActivityLog,
  GoalComposer,
  RunHistory,
} from "./Overview.jsx";
import ModelConnection from "./ModelConnection.jsx";
import { composeGoal, readDraft, saveDraft } from "./goals.js";
import { documentBlocks } from "./document.js";
import { resultTarget } from "./activity.js";
import {
  Panel,
  PageHeading,
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
  ["cv", "Резюме"],
  ["employers", "Работодатели"],
  ["resources", "Ресурсы"],
  ["accounts", "Аккаунты"],
  ["repositories", "Репозитории"],
  ["tactics", "Тактики"],
  ["settings", "Настройки"],
];
const pageFromHash = () => {
  const page = location.hash.slice(1).split("/")[0];
  return navigation.some(([key]) => key === page) ? page : "overview";
};
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
  if (!run) return <p>Запуск не найден.</p>;
  return (
    <>
      <p>{run.goal}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Status value={run.status} />
        <span>{list(run.steps).length} шагов</span>
        <span>{run.model}</span>
        <Timestamp value={run.started_at || run.created_at} />
      </div>
      {run.error ? <p>{run.error}</p> : null}
      {run.final_answer ? <div>{run.final_answer}</div> : null}
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
        <p>Агент ещё не начал выполнять шаги.</p>
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
    const resource = list(state.resources).find(
      (entry) => entry.id === detail.id,
    );
    if (!resource) return <p>Ресурс не найден.</p>;
    return (
      <>
        <h3
          className={typographyVariants({
            type: "h2",
            weight: "medium",
          }).base()}
        >
          {resource.name}
        </h3>
        {resource.notes ? <p>{resource.notes}</p> : null}
        {safeURL(resource.url) ? (
          <Link href={resource.url} target="_blank" rel="noreferrer">
            Открыть источник
            <Icon name="external" className="size-4 shrink-0" />
          </Link>
        ) : null}
      </>
    );
  }
  if (detail.kind === "tool_call") {
    const call = list(state.tool_calls).find((entry) => entry.id === detail.id);
    if (!call) return <p>Вызов не найден.</p>;
    const target = resultTarget(call.related_id, state);
    return (
      <>
        <h3
          className={typographyVariants({
            type: "h2",
            weight: "medium",
          }).base()}
        >
          {call.tool}
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={call.status} />
          <Timestamp value={call.started_at} />
          {Number.isFinite(call.duration_seconds) ? (
            <span>
              {call.duration_seconds.toLocaleString("ru-RU", {
                maximumFractionDigits: 2,
              })}{" "}
              с
            </span>
          ) : null}
        </div>
        {call.summary ? <p>{call.summary}</p> : null}
        {call.error ? (
          <Alert status="danger">
            <Alert.Content>
              <Alert.Description>{call.error}</Alert.Description>
            </Alert.Content>
          </Alert>
        ) : null}
        {call.finished_at ? (
          <Typography.Paragraph size="sm" color="muted">
            Завершён: <Timestamp value={call.finished_at} />
          </Typography.Paragraph>
        ) : null}
        {target ? (
          <Button
            variant="outline"
            onPress={() => onInspect(target.kind, target.id)}
          >
            Открыть сохранённый результат
          </Button>
        ) : null}
      </>
    );
  }
  if (detail.kind === "cv") {
    const cv = list(state.cvs).find((cv) => cv.id === detail.id);
    if (!cv) return null;
    return (
      <>
        <Typography.Paragraph size="sm" color="muted">
          {cv.name || cv.headline}
          {cv.language ? ` · ${cv.language}` : ""}
        </Typography.Paragraph>
        <Typography.Prose>
          {documentBlocks(cv.markdown).map((block, index) =>
            block.type === "heading" ? (
              <Typography.Heading
                key={index}
                level={Math.min(block.level + 1, 6)}
              >
                {block.text}
              </Typography.Heading>
            ) : block.type === "list" ? (
              <ul key={index}>
                {block.items.map((text, itemIndex) => (
                  <li key={itemIndex}>{text}</li>
                ))}
              </ul>
            ) : (
              <Typography.Paragraph key={index}>
                {block.text}
              </Typography.Paragraph>
            ),
          )}
        </Typography.Prose>
        <DetailAccordion title="Исходный Markdown" id="cv-source">
          <div className="overflow-x-auto">
            <pre>{cv.markdown}</pre>
          </div>
        </DetailAccordion>
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
        <p>{report.experiment.hypothesis}</p>
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
        <p>
          В расчёт входят отправленные отклики с завершённым окном наблюдения.
          Малое количество данных не доказывает эффективность подхода.
        </p>
      </>
    );
  }
  if (detail.kind === "job") {
    const job = list(state.jobs).find((job) => job.id === detail.id);
    if (!job) return null;
    const application = list(state.applications).find(
        (entry) => entry.job_id === job.id,
      ),
      actions = list(state.actions).filter(
        (entry) => entry.payload?._job_id === job.id,
      ),
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
        <h3
          className={typographyVariants({
            type: "h2",
            weight: "medium",
          }).base()}
        >
          {job.title}
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <Status
            value={job.blocked ? "blocked" : application?.stage || "new"}
          />
          <Timestamp value={job.fetched_at} />
        </div>
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
        {application ? (
          <section className="flex flex-col gap-3">
            <Typography.Heading level={3}>Ваш отклик</Typography.Heading>
            {cv ? (
              <Button
                variant="ghost"
                size="sm"
                onPress={() => onInspect("cv", cv.id)}
              >
                CV: {cv.name || cv.headline}
              </Button>
            ) : null}
            {list(application.history).length ? (
              <ol className="flex flex-col gap-3">
                {list(application.history).map((event, index) => (
                  <li className="flex flex-col gap-2" key={index}>
                    <div className="flex flex-wrap items-center gap-3">
                      <Status value={event.stage} />
                      <Timestamp value={event.at} />
                    </div>
                    {event.note ? <p>{event.note}</p> : null}
                  </li>
                ))}
              </ol>
            ) : null}
            {actions.length ? (
              actions.map((action) => (
                <Button
                  variant="outline"
                  size="sm"
                  key={action.id}
                  onPress={() => onInspect("action", action.id)}
                >
                  Открыть действие · {label(action.status)}
                </Button>
              ))
            ) : (
              <Typography.Paragraph size="sm" color="muted">
                Показана сохранённая история отклика. Связанного журнала
                отправки в локальных данных нет; содержание сообщения здесь не
                подтверждено.
              </Typography.Paragraph>
            )}
          </section>
        ) : null}
        {safeURL(job.url) ? (
          <Link href={safeURL(job.url)} target="_blank" rel="noreferrer">
            Открыть источник
            <Icon name="external" className="size-4 shrink-0" />
          </Link>
        ) : null}
      </>
    );
  }
  const bucket = detail.kind === "action" ? "actions" : "schedule_runs",
    record = list(state[bucket]).find((record) => record.id === detail.id);
  if (!record) return null;
  const scheduled =
    detail.kind === "schedule_run" ? scheduleResult(record, state) : null;
  return (
    <>
      {scheduled ? (
        <>
          <p>{scheduled.title}</p>
          <p>{scheduled.text}</p>
          {scheduled.next ? <p>{scheduled.next}</p> : null}
        </>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Status value={record.status} />
        <Timestamp value={record.created_at || record.started_at} />
      </div>
      {detail.kind === "action" ? (
        <>
          <p>
            {record.operation} · {record.connector}
          </p>
          {record.payload?.subject ? (
            <Typography.Heading level={3}>
              {record.payload.subject}
            </Typography.Heading>
          ) : null}
          {record.payload?.body || record.payload?.text ? (
            <p>{record.payload.body || record.payload.text}</p>
          ) : null}
        </>
      ) : null}
      <DetailAccordion title="Технические подробности" id="record-data">
        <pre>{stringify(record)}</pre>
      </DetailAccordion>
    </>
  );
}
function Navigation({
  page,
  onNavigate,
  collapsed = false,
  onExpand,
  id = "sidebar-navigation",
}) {
  const primary = ["overview", "search", "market", "cv", "employers", "schedules"];
  const secondary = [
    "strengths",
    "repositories",
    "resources",
    "accounts",
    "experiments",
    "tactics",
  ];
  const [materialsOpen, setMaterialsOpen] = useState(secondary.includes(page));
  const item = (key) => {
    const title = navigation.find(([id]) => id === key)[1];
    return (
      <button
        key={key}
        className={`nav-item ${page === key ? "selected" : ""}`}
        data-page={key}
        title={collapsed ? title : undefined}
        aria-label={title}
        aria-current={page === key ? "page" : undefined}
        onClick={() => onNavigate(key)}
      >
        <span className={`nav-icon nav-icon-${key}`} aria-hidden="true">
          <Icon name={key} />
        </span>
        <span className="nav-label">{title}</span>
      </button>
    );
  };
  return (
    <nav id={id} className="navigation" aria-label="Разделы Worklife">
      <div className="nav-primary">{primary.map(item)}</div>
      <div className="nav-secondary">
        <button
          className={`nav-item ${materialsOpen && !collapsed ? "expanded" : ""} ${secondary.includes(page) ? "selected" : ""}`}
          data-page="more"
          title={collapsed ? "Ещё разделы" : undefined}
          aria-label="Ещё разделы"
          aria-expanded={materialsOpen && !collapsed}
          aria-controls={`${id}-more`}
          onClick={() => {
            if (collapsed) {
              onExpand?.();
              setMaterialsOpen(true);
            } else {
              setMaterialsOpen(!materialsOpen);
            }
          }}
        >
          <span className="nav-icon nav-icon-more" aria-hidden="true">
            <Icon name="materials" />
          </span>
          <span className="nav-label">Ещё</span>
          <Icon name="next" className="nav-chevron" />
        </button>
        {materialsOpen && !collapsed ? (
          <div id={`${id}-more`} className="nav-submenu">
            {secondary.map(item)}
          </div>
        ) : null}
        {item("settings")}
      </div>
    </nav>
  );
}

export default function App() {
  const [state, setState] = useState(null),
    [error, setError] = useState(""),
    [page, setPage] = useState(pageFromHash),
    [navigationOpen, setNavigationOpen] = useState(false),
    [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
      try {
        return (
          window.localStorage.getItem("worklife.sidebar.collapsed") === "true"
        );
      } catch {
        return false;
      }
    }),
    [draft, setDraft] = useState({ author: "", goal: "", context: null }),
    [modelDialog, setModelDialog] = useState(null),
    [pending, setPending] = useState(""),
    [message, setMessage] = useState(""),
    [updated, setUpdated] = useState(null);
  const [conditionsOpen, setConditionsOpen] = useState(false),
    [conditions, setConditions] = useState(""),
    [targetRoles, setTargetRoles] = useState(""),
    [targetLocations, setTargetLocations] = useState(""),
    [languages, setLanguages] = useState(""),
    [searchRules, setSearchRules] = useState({}),
    [incomeDeadline, setIncomeDeadline] = useState(""),
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
  const setGoal = (value) =>
    setDraft((previous) => ({ ...previous, goal: value }));
  const setContext = (value) =>
    setDraft((previous) => ({ ...previous, context: value }));
  const setSidebar = (collapsed) => {
    setSidebarCollapsed(collapsed);
    try {
      window.localStorage.setItem("worklife.sidebar.collapsed", String(collapsed));
    } catch {}
  };
  useEffect(() => {
    if (!author) return;
    let saved = { goal: "", context: null };
    try {
      saved = readDraft(window.localStorage, author);
    } catch {}
    setDraft({ author, ...saved });
  }, [author]);
  useEffect(() => {
    if (author && draft.author === author) {
      try {
        saveDraft(window.localStorage, author, draft);
      } catch {}
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
      if (location.hash !== "#search/inbox") {
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      }
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
    setModelDialog({
      runAfter: runAfter && Boolean(composeGoal(goal, context)),
    });
  }
  async function runGoal(connected = false) {
    if (!connected && !state.agent?.configured) {
      openModel(true);
      return;
    }
    const text = composeGoal(goal, context);
    if (!text.trim()) return;
    if (text.length > 16000) {
      notify(
        "Поручение слишком длинное. Сократите цель или уточнение до 16 000 знаков вместе.",
      );
      return;
    }
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
    setTargetRoles(list(state?.profile?.target_roles).join(", "));
    setTargetLocations(list(state?.profile?.target_locations).join(", "));
    setLanguages(list(state?.profile?.languages).join(", "));
    setSearchRules(state?.profile?.constraints || {});
    setIncomeDeadline(state?.profile?.income_deadline || "");
    setConditionsOpen(true);
  }
  function openBlock(domain) {
    setBlockDomain(domain);
    setBlockReason("");
    setBlockEvidence("");
    setBlockOpen(true);
  }
  function setRule(key, value) {
    setSearchRules((previous) => {
      const next = { ...previous };
      if (value === "") delete next[key];
      else next[key] = value;
      return next;
    });
  }
  async function saveConditions(event) {
    event.preventDefault();
    try {
      await command(
        "profile_save",
        {
          profile: {
            ...(state.profile || {}),
            constraints: searchRules,
            income_deadline: incomeDeadline || null,
            target_roles: targetRoles
              .split(/[,;\n]/)
              .map((value) => value.trim())
              .filter(Boolean),
            target_locations: targetLocations
              .split(/[,;\n]/)
              .map((value) => value.trim())
              .filter(Boolean),
            languages: languages
              .split(/[,;\n]/)
              .map((value) => value.trim())
              .filter(Boolean),
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
      link.download =
        format === "original"
          ? list(state.cvs).find((cv) => cv.id === id)?.original_filename ||
            "worklife-cv"
          : `worklife-cv.${format}`;
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
    onRefresh: refresh,
    onDownload: downloadCV,
    pending,
    onConditions: openConditions,
    onBlock: openBlock,
    onModel: () => openModel(false),
    runtime: (
      <div className="flex flex-col gap-4">
        <Typography.Paragraph>
          Необязательный автономный исполнитель Worklife. Его подключение не
          требуется для работы через вашего MCP-агента.
        </Typography.Paragraph>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={state?.agent?.configured ? "success" : "planned"}>
            {state?.agent?.configured
              ? "Модель настроена"
              : "Модель не подключена"}
          </Status>
          {state?.agent?.configured ? (
            <Button
              variant="outline"
              size="sm"
              onPress={() => openModel(false)}
            >
              Изменить модель исполнителя
            </Button>
          ) : null}
        </div>
        <GoalComposer
          goal={goal}
          setGoal={setGoal}
          onRun={runGoal}
          pending={pending === "agent"}
          configured={state?.agent?.configured}
          inputRef={inputRef}
          context={context}
          setContext={setContext}
          profile={state?.profile}
          onConditions={openConditions}
        />
        <RunHistory runs={list(state?.agent?.runs)} onInspect={onInspect} />
      </div>
    ),
  };
  const views = {
    market: MarketBoard,
    search: SearchBoard,
    schedules: SchedulesView,
    experiments: ExperimentsView,
    strengths: StrengthsView,
    cv: ResumeBoard,
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
      <Link
        className="sr-only focus:not-sr-only"
        onPress={() => document.getElementById("app-main")?.focus()}
      >
        К содержанию
      </Link>
      <div className={`worklife-app${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
        <aside
          className={`app-sidebar${sidebarCollapsed ? " is-collapsed" : ""}`}
          aria-label="Боковая панель"
        >
          <div className="sidebar-top">
            <div className="brand">
              <a href="#overview" aria-label="Worklife — обзор" title="Worklife — обзор">
                <span className="brand-mark" aria-hidden="true">w</span>
                <span className="brand-name">Worklife</span>
              </a>
            </div>
            <Button
              className="sidebar-toggle"
              variant="ghost"
              size="sm"
              isIconOnly
              aria-label={sidebarCollapsed ? "Развернуть боковую панель" : "Свернуть боковую панель"}
              title={sidebarCollapsed ? "Развернуть боковую панель" : "Свернуть боковую панель"}
              aria-expanded={!sidebarCollapsed}
              aria-controls="sidebar-navigation"
              onPress={() => setSidebar(!sidebarCollapsed)}
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen aria-hidden="true" />
              ) : (
                <PanelLeftClose aria-hidden="true" />
              )}
            </Button>
          </div>
          <div className="navigation-scroll">
            <Navigation
              page={page}
              onNavigate={navigate}
              collapsed={sidebarCollapsed}
              onExpand={() => setSidebar(false)}
            />
          </div>
          <div className="sidebar-footer">
            <button aria-label="Обновить данные" title="Обновить данные" onClick={refresh}>
              <Icon name="refresh" />
              <span className="sidebar-footer-label">Обновить</span>
            </button>
            <time className="sidebar-updated" aria-label="Время обновления данных">
              {error
                ? "Нет связи"
                : updated
                  ? updated.toLocaleTimeString("ru", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"}
            </time>
          </div>
        </aside>
        <div className="app-content">
          <header className="mobile-header">
            <Button
              variant="secondary"
              aria-expanded={navigationOpen}
              onPress={() => setNavigationOpen(true)}
            >
              <Icon name="menu" />
              Разделы
            </Button>
            <Button
              variant="ghost"
              aria-label="Обновить данные"
              onPress={refresh}
            >
              <Icon name="refresh" />
            </Button>
          </header>
          {message ? (
            <Alert>
              <Alert.Content>
                <Alert.Description>{message}</Alert.Description>
              </Alert.Content>
              <CloseButton
                aria-label="Закрыть уведомление"
                onPress={() => setMessage("")}
              />
            </Alert>
          ) : null}
          <main id="app-main" className="app-main" tabIndex={-1}>
            {!state ? (
              <>
                <PageHeading
                  title={page === "overview" ? "Поиск работы" : title}
                />
                {error ? (
                  <>
                    <p>
                      {error} Проверьте, что Worklife запущен на вашем
                      компьютере.
                    </p>
                    <Button variant="outline" onPress={refresh}>
                      Попробовать ещё раз
                    </Button>
                  </>
                ) : (
                  <div role="status" className="flex items-center gap-3">
                    <Spinner size="sm" />
                    <Typography.Paragraph color="muted">
                      Загружаем вашу историю поиска.
                    </Typography.Paragraph>
                  </div>
                )}
              </>
            ) : View ? (
              <>
                <View {...props} />
                {page === "schedules" ? <CareerEvents {...props} /> : null}
              </>
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
        <Dialog
          open={navigationOpen}
          onClose={() => setNavigationOpen(false)}
          title="Разделы Worklife"
        >
          <Navigation id="dialog-navigation" page={page} onNavigate={navigate} />
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
              <form
                id="conditions-form"
                className="flex flex-col gap-3"
                onSubmit={saveConditions}
              >
                <fieldset className="form-section">
                  <legend>Работа</legend>
                  <div className="form-section-fields">
                    <label className="form-field">
                      Желаемые должности
                      <Input
                        value={targetRoles}
                        onChange={(event) => setTargetRoles(event.target.value)}
                        placeholder="Например, frontend-разработчик, руководитель команды"
                      />
                    </label>
                    <div className="detail-grid">
                      <label className="form-field">
                        Города и страны
                        <Input
                          value={targetLocations}
                          onChange={(event) =>
                            setTargetLocations(event.target.value)
                          }
                          placeholder="Москва, удалённо"
                        />
                      </label>
                      <SelectField
                        label="Удалённая работа"
                        value={
                          searchRules.remote === true
                            ? "yes"
                            : searchRules.remote === false
                              ? "no"
                              : ""
                        }
                        onChange={(value) =>
                          setRule("remote", value === "" ? "" : value === "yes")
                        }
                      >
                        <option value="">Не задано</option>
                        <option value="yes">Обязательна</option>
                        <option value="no">Не обязательна</option>
                      </SelectField>
                    </div>
                  </div>
                </fieldset>
                <fieldset className="form-section">
                  <legend>Оплата</legend>
                  <div className="form-section-fields detail-grid">
                    <label className="form-field">
                      Доход от
                      <Input
                        type="number"
                        min="0"
                        value={searchRules.min_salary ?? ""}
                        onChange={(e) =>
                          setRule(
                            "min_salary",
                            e.target.value === "" ? "" : Number(e.target.value),
                          )
                        }
                        placeholder="Не задан"
                      />
                    </label>
                    <SelectField
                      label="Валюта"
                      value={searchRules.currency || ""}
                      onChange={(value) => setRule("currency", value)}
                    >
                      <option value="">Не задана</option>
                      {["RUB", "USD", "EUR"].map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </SelectField>
                    <SelectField
                      label="Период оплаты"
                      value={searchRules.salary_period || ""}
                      onChange={(value) => setRule("salary_period", value)}
                    >
                      <option value="">Не задан</option>
                      <option value="month">Месяц</option>
                      <option value="year">Год</option>
                      <option value="hour">Час</option>
                    </SelectField>
                    <SelectField
                      label="Налоги"
                      value={
                        searchRules.salary_gross === true
                          ? "gross"
                          : searchRules.salary_gross === false
                            ? "net"
                            : ""
                      }
                      onChange={(value) =>
                        setRule(
                          "salary_gross",
                          value === "" ? "" : value === "gross",
                        )
                      }
                    >
                      <option value="">Не задано</option>
                      <option value="gross">До налогов</option>
                      <option value="net">На руки</option>
                    </SelectField>
                  </div>
                </fieldset>
                <DetailAccordion title="Дополнительно" id="conditions-additional">
                  <label className="form-field">
                    Языки работы
                    <Input
                      value={languages}
                      onChange={(event) => setLanguages(event.target.value)}
                      placeholder="Русский, английский"
                    />
                  </label>
                  <div className="detail-grid">
                    <label className="form-field">
                      Часов в неделю, не больше
                      <Input
                        type="number"
                        min="0"
                        value={searchRules.max_hours ?? ""}
                        onChange={(e) =>
                          setRule(
                            "max_hours",
                            e.target.value === "" ? "" : Number(e.target.value),
                          )
                        }
                        placeholder="Не задано"
                      />
                    </label>
                    <label className="form-field">
                      Получить первый доход до
                      <input
                        className="native-input"
                        type="date"
                        value={incomeDeadline}
                        onChange={(e) => setIncomeDeadline(e.target.value)}
                      />
                    </label>
                  </div>
                  <Label>Дополнительные условия</Label>
                  <TextArea
                    aria-label="Условия поиска работы"
                    rows={3}
                    value={conditions}
                    onChange={(event) => setConditions(event.target.value)}
                    placeholder="Хочу работать удалённо, до 40 часов в неделю. Важно…"
                  />
                </DetailAccordion>
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
                <p>
                  Это ваше локальное исключение. Агент учитывает его, когда
                  связь вакансии или контакта с компанией установлена.
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
              {detail?.kind === "job" &&
              list(state.jobs).find((job) => job.id === detail.id) ? (
                <JobDetails
                  key={detail.id}
                  job={list(state.jobs).find((job) => job.id === detail.id)}
                  {...props}
                />
              ) : (
                <DetailContent
                  detail={detail}
                  state={state}
                  onDownload={downloadCV}
                  pending={pending}
                  onInspect={onInspect}
                />
              )}
            </Dialog>
            {modelDialog ? (
              <ModelConnection
                initial={state.agent?.connection}
                runAfter={modelDialog.runAfter}
                onClose={() => setModelDialog(null)}
                onSaved={async (_connection, continueGoal) => {
                  await refresh();
                  setModelDialog(null);
                  if (continueGoal) await runGoal(true);
                  else
                    notify(
                      "Параметры модели сохранены. Теперь можно запустить поручение.",
                    );
                }}
              />
            ) : null}
          </>
        ) : null}
      </div>
    </>
  );
}
