import { t, getLocale, useLocale } from "./i18n.js";
import LanguageSelect from "./LanguageSelect.jsx";
import ProjectActions, { ProjectStarLink } from "./ProjectActions.jsx";
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
  ConversationBoard,
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
import { readDismissedRelease, saveDismissedRelease, shouldShowReleaseNotice } from "./release-notice.js";
import { documentBlocks } from "./document.js";
import { callSummary, resultTarget } from "./activity.js";
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
  ["messages", "Переписка"],
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
  if (location.hash === "#search/inbox") return "messages";
  const page = location.hash.slice(1).split("/")[0];
  return navigation.some(([key]) => key === page) ? page : "overview";
};
const stringify = (value) => JSON.stringify(value, null, 2);
function ReleaseNotice({ release }) {
  const [dismissed, setDismissed] = useState(() => {
    try { return readDismissedRelease(window.localStorage); } catch { return ""; }
  });
  const [copyState, setCopyState] = useState("");
  if (!shouldShowReleaseNotice(release, dismissed)) return null;
  const request = t`Обнови Worklife до ${release.latest_version}. Проверь текущий способ установки и настройки запуска MCP, сохрани личную базу, подключения и нативные скиллы.`;
  const dismiss = () => {
    setDismissed(release.latest_version);
    try { saveDismissedRelease(window.localStorage, release.latest_version); } catch {}
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(request);
      setCopyState("copied");
    } catch { setCopyState("manual"); }
  };
  return <Alert>
    <Alert.Content>
      <Alert.Title>{t`Доступен Worklife ${release.latest_version}`}</Alert.Title>
      <Alert.Description>{t`Установлена версия ${release.installed_version}.`}</Alert.Description>
      <div className="flex flex-wrap items-center gap-3">
        <Link href={safeURL(release.release_url)} target="_blank" rel="noopener noreferrer">{t("Открыть релиз")}<Icon name="external" className="size-4 shrink-0" /></Link>
        <Button size="sm" variant="ghost" onPress={copy}>{copyState === "copied" ? t("Поручение скопировано") : t("Скопировать поручение агенту")}</Button>
      </div>
      {copyState === "manual" ? <div className="flex flex-col gap-2">
        <p>{t("Не удалось скопировать поручение. Выделите его и скопируйте вручную.")}</p>
        <Input aria-label={t("Поручение для обновления Worklife")} value={request} readOnly onFocus={(event) => event.target.select()} />
      </div> : null}
    </Alert.Content>
    <CloseButton aria-label={t("Скрыть уведомление об этой версии")} onPress={dismiss} />
  </Alert>;
}
function errorText(error) {
  const text = error?.message || String(error);
  if (text.includes("Agent not configured"))
    return t("Модель агента ещё не подключена. Откройте настройки и инструкцию по подключению.");
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
    throw new Error(t("Не удалось прочитать ответ локального приложения."));
  }
  if (!response.ok || result.ok === false)
    throw new Error(
      typeof result.error === "string"
        ? result.error
        : t("Не удалось выполнить поручение."),
    );
  return result.result;
}
function RunDetails({ run }) {
  if (!run) return <p>{t("Запуск не найден.")}</p>;
  return (
    <>
      <p>{run.goal}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Status value={run.status} />
        <span>{list(run.steps).length}{t(" шагов")}</span>
        <span>{run.model}</span>
        <Timestamp value={run.started_at || run.created_at} />
      </div>
      {run.error ? <p>{run.error}</p> : null}
      {run.final_answer ? <div>{run.final_answer}</div> : null}
      {list(run.steps).length ? (
        list(run.steps).map((step) => (
          <section className="flex flex-col gap-3 py-3" key={step.index}>
            <Typography.Heading level={3}>
              <span>{t("Шаг ")}{step.index}</span>
              <time>{formatDate(step.started_at, true)}</time>
            </Typography.Heading>
            {step.assistant?.content ? <p>{step.assistant.content}</p> : null}
            {list(step.assistant?.tool_calls).map((call, index) => (
              <DetailAccordion
                key={call.id || index}
                id={call.id || `call-${index}`}
                title={call.function?.name || t("Действие агента")}
              >
                <pre>{call.function?.arguments}</pre>
              </DetailAccordion>
            ))}
            {list(step.tool_results).length ? (
              <DetailAccordion
                id={`results-${step.index}`}
                title={t("Результаты действий")}
              >
                <pre>{stringify(step.tool_results)}</pre>
              </DetailAccordion>
            ) : null}
          </section>
        ))
      ) : (
        <p>{t("Агент ещё не начал выполнять шаги.")}</p>
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
    if (!resource) return <p>{t("Ресурс не найден.")}</p>;
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
          <Link href={resource.url} target="_blank" rel="noreferrer">{t("Открыть источник")}<Icon name="external" className="size-4 shrink-0" />
          </Link>
        ) : null}
      </>
    );
  }
  if (detail.kind === "tool_call") {
    const call = list(state.tool_calls).find((entry) => entry.id === detail.id);
    if (!call) return <p>{t("Вызов не найден.")}</p>;
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
              {call.duration_seconds.toLocaleString(getLocale(), {
                maximumFractionDigits: 2,
              })}{" "}{t("с")}</span>
          ) : null}
        </div>
        {call.summary ? <p>{callSummary(call.summary)}</p> : null}
        {call.error ? (
          <Alert status="danger">
            <Alert.Content>
              <Alert.Description>{call.error}</Alert.Description>
            </Alert.Content>
          </Alert>
        ) : null}
        {call.finished_at ? (
          <Typography.Paragraph size="sm" color="muted">{t("Завершён: ")}<Timestamp value={call.finished_at} />
          </Typography.Paragraph>
        ) : null}
        {target ? (
          <Button
            variant="outline"
            onPress={() => onInspect(target.kind, target.id)}
          >{t("Открыть сохранённый результат")}</Button>
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
        <DetailAccordion title={t("Исходный Markdown")} id="cv-source">
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
            >{t("Скачать ")}{format.toUpperCase()}
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
    if (!report) return <p>{t("Результат ещё не рассчитан.")}</p>;
    return (
      <>
        <p>{report.experiment.hypothesis}</p>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={report.conclusion} />
          <span>{t("Окно: ")}{report.experiment.horizon_hours}{t(" ч.")}</span>
        </div>
        <DataTable
          headers={[
            "CV",
            t("Назначено"),
            t("Отправлено"),
            t("Созрело"),
            t("Успехи"),
            t("Доля"),
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
        <p>{t("В расчёт входят отправленные отклики с завершённым окном наблюдения. Малое количество данных не доказывает эффективность подхода.")}</p>
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
      employer: t("Компания"),
      remote: t("Удалённо"),
      salary_min: t("Зарплата от"),
      salary_max: t("Зарплата до"),
      currency: t("Валюта"),
      salary_period: t("Период оплаты"),
      hours: t("Часов в неделю"),
      hiring_stages: t("Этапов найма"),
      test_hours: t("Объём тестового, часов"),
      employer_domain: t("Домен компании"),
      notes: t("Заметки"),
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
                      ? t("Да")
                      : t("Нет")
                    : typeof job[key] === "object"
                      ? job[key].name
                      : String(job[key])}
                </dd>
              </div>
            ))}
        </dl>
        {application ? (
          <section className="flex flex-col gap-3">
            <Typography.Heading level={3}>{t("Ваш отклик")}</Typography.Heading>
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
                >{t("Открыть действие · ")}{label(action.status)}
                </Button>
              ))
            ) : (
              <Typography.Paragraph size="sm" color="muted">{t("Показана сохранённая история отклика. Связанного журнала отправки в локальных данных нет; содержание сообщения здесь не подтверждено.")}</Typography.Paragraph>
            )}
          </section>
        ) : null}
        {safeURL(job.url) ? (
          <Link href={safeURL(job.url)} target="_blank" rel="noreferrer">{t("Открыть источник")}<Icon name="external" className="size-4 shrink-0" />
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
      <DetailAccordion title={t("Технические подробности")} id="record-data">
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
  const primary = ["overview", "search", "messages", "market", "cv", "employers", "schedules"];
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
    const title = t(navigation.find(([id]) => id === key)[1]);
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
    <nav id={id} className="navigation" aria-label={t("Разделы Worklife")}>
      <div className="nav-primary">{primary.map(item)}</div>
      <div className="nav-secondary">
        <button
          className={`nav-item ${materialsOpen && !collapsed ? "expanded" : ""} ${secondary.includes(page) ? "selected" : ""}`}
          data-page="more"
          title={collapsed ? t("Ещё разделы") : undefined}
          aria-label={t("Ещё разделы")}
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
          <span className="nav-label">{t("Ещё")}</span>
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
  const [locale] = useLocale();
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
    [searchLanguages, setSearchLanguages] = useState([]),
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
      if (!response.ok) throw new Error(t("Локальное приложение недоступно."));
      const value = await response.json();
      if (value.ok === false)
        throw new Error(value.error || t("Не удалось загрузить данные."));
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
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
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
          ? t("Остановка запрошена.")
          : name === "blockchain_sync"
            ? result.status === "healthy" ? t("Обмен завершён. Состояние базы обновлено.")
              : result.status === "local_only" ? t("Обмен не настроен. Подключите общую базу с агентом.")
                : t("Обмен требует внимания. Причина показана в разделе работодателей.")
          : name === "automation_configure"
            ? args.enabled ? t("Автопроверки сохранены и включены.") : t("Настройки сохранены. Автопроверки выключены.")
          : name === "automation_run"
            ? result.status === "success" ? t("Проверки запущены. Результаты — в истории запусков.") : t("Часть проверок требует внимания. Посмотрите результат в расписании.")
          : name === "schedule_run"
            ? result.status === "success" ? t("Проверка выполнена.") : t("Проверка требует внимания. Посмотрите результат в истории запусков.")
          : name === "schedule_toggle"
            ? args.enabled
              ? t("Поиск по расписанию продолжится.")
              : t("Поиск по расписанию на паузе.")
            : name === "employer_block"
              ? args.blocked
                ? t("Компания исключена из вашего поиска.")
                : t("Блокировка снята.")
              : t("Сохранено."),
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
        t("Поручение слишком длинное. Сократите цель или уточнение до 16 000 знаков вместе."),
      );
      return;
    }
    setPending("agent");
    try {
      if (state.profile?.interface_language !== locale) {
        await invoke("profile_save", { profile: { ...(state.profile || {}), interface_language: locale } });
      }
      await invoke("agent_run", { goal: text.trim(), max_steps: 8 });
      await refresh();
      setContext(null);
      notify(t("Агент принял поручение. Ход работы появится ниже."));
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
    setSearchLanguages(list(state?.profile?.search_languages));
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
            interface_language: locale,
            search_languages: searchLanguages,
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
        throw new Error(error.error || t("Не удалось сформировать файл."));
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
        <Typography.Paragraph>{t("Необязательный автономный исполнитель Worklife. Его подключение не требуется для работы через вашего MCP-агента.")}</Typography.Paragraph>
        <div className="flex flex-wrap items-center gap-3">
          <Status value={state?.agent?.configured ? "success" : "planned"}>
            {state?.agent?.configured
              ? t("Модель настроена")
              : t("Модель не подключена")}
          </Status>
          {state?.agent?.configured ? (
            <Button
              variant="outline"
              size="sm"
              onPress={() => openModel(false)}
            >{t("Изменить модель исполнителя")}</Button>
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
    messages: ConversationBoard,
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
  const title = t(navigation.find(([key]) => key === page)?.[1] || "Обзор");
  const navigate = (key) => {
    location.hash = key;
    setPage(key);
    setNavigationOpen(false);
  };
  const detailTitle =
    detail?.kind === "run"
      ? t("Ход работы агента")
      : detail?.kind === "cv"
        ? t("Ваше CV")
        : detail?.kind === "job"
          ? t("Условия вакансии")
          : detail?.kind === "experiment"
            ? t("Результаты эксперимента")
            : detail?.kind === "activity"
              ? t("Журнал работы")
              : detail?.kind === "tool_call"
                ? t("Вызов MCP")
                : t("Подробности действия");
  return (
    <>
      <Link
        className="app-skip sr-only focus:not-sr-only"
        onPress={() => document.getElementById("app-main")?.focus()}
      >{t("К содержанию")}</Link>
      <ProjectStarLink />
      <div className={`worklife-app${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
        <aside
          className={`app-sidebar${sidebarCollapsed ? " is-collapsed" : ""}`}
          aria-label={t("Боковая панель")}
        >
          <div className="sidebar-top">
            <div className="brand">
              <a href="#overview" aria-label={t("Worklife — обзор")} title={t("Worklife — обзор")}>
                <span className="brand-mark" aria-hidden="true">w</span>
                <span className="brand-name">Worklife</span>
              </a>
            </div>
            <Button
              className="sidebar-toggle"
              variant="ghost"
              size="sm"
              isIconOnly
              aria-label={sidebarCollapsed ? t("Развернуть боковую панель") : t("Свернуть боковую панель")}
              title={sidebarCollapsed ? t("Развернуть боковую панель") : t("Свернуть боковую панель")}
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
          <ProjectActions placement="sidebar" />
          <div className="sidebar-footer">
            <LanguageSelect onChange={(value) => state && safeCommand("profile_save", { profile: { ...(state.profile || {}), interface_language: value } })} />
            <button aria-label={t("Обновить данные")} title={t("Обновить данные")} onClick={refresh}>
              <Icon name="refresh" />
              <span className="sidebar-footer-label">{t("Обновить")}</span>
            </button>
            <time className="sidebar-updated" aria-label={t("Время обновления данных")}>
              {error
                ? t("Нет связи")
                : updated
                  ? updated.toLocaleTimeString(getLocale(), {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"}
            </time>
          </div>
        </aside>
        <div className="app-content">
          {state?.demo ? (
            <div className="demo-notice" role="note">
              <span>{t("Демонстрация")}</span>{t("Вымышленные вакансии и переписка · отдельная база")}</div>
          ) : null}
          <header className="mobile-header">
            <LanguageSelect onChange={(value) => state && safeCommand("profile_save", { profile: { ...(state.profile || {}), interface_language: value } })} />
            <Button
              variant="secondary"
              aria-expanded={navigationOpen}
              onPress={() => setNavigationOpen(true)}
            >
              <Icon name="menu" />{t("Разделы")}</Button>
            <Button
              variant="ghost"
              aria-label={t("Обновить данные")}
              onPress={refresh}
            >
              <Icon name="refresh" />
            </Button>
          </header>
          <ReleaseNotice key={state?.release?.latest_version || "none"} release={state?.release} />
          {message ? (
            <Alert>
              <Alert.Content>
                <Alert.Description>{message}</Alert.Description>
              </Alert.Content>
              <CloseButton
                aria-label={t("Закрыть уведомление")}
                onPress={() => setMessage("")}
              />
            </Alert>
          ) : null}
          <main id="app-main" className="app-main" tabIndex={-1}>
            {!state ? (
              <>
                <PageHeading
                  title={page === "overview" ? t("Поиск работы") : title}
                />
                {error ? (
                  <>
                    <p>
                      {error}{t(" Проверьте, что Worklife запущен на вашем компьютере.")}</p>
                    <Button variant="outline" onPress={refresh}>{t("Попробовать ещё раз")}</Button>
                  </>
                ) : (
                  <div role="status" className="flex items-center gap-3">
                    <Spinner size="sm" />
                    <Typography.Paragraph color="muted">{t("Загружаем вашу историю поиска.")}</Typography.Paragraph>
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
          title={t("Разделы Worklife")}
        >
          <Navigation id="dialog-navigation" page={page} onNavigate={navigate} />
          <ProjectActions placement="menu" />
        </Dialog>
        {state ? (
          <>
            <Dialog
              open={conditionsOpen}
              onClose={() => setConditionsOpen(false)}
              title={t("Мои условия")}
              footer={
                <>
                  <Button
                    variant="ghost"
                    onPress={() => setConditionsOpen(false)}
                  >{t("Отмена")}</Button>
                  <Button
                    type="submit"
                    form="conditions-form"
                    isPending={pending === "conditions"}
                  >{t("Сохранить условия")}</Button>
                </>
              }
            >
              <form
                id="conditions-form"
                className="flex flex-col gap-3"
                onSubmit={saveConditions}
              >
                <fieldset className="form-section">
                  <legend>{t("Работа")}</legend>
                  <div className="form-section-fields">
                    <label className="form-field">{t("Желаемые должности")}<Input
                        value={targetRoles}
                        onChange={(event) => setTargetRoles(event.target.value)}
                        placeholder={t("Например, frontend-разработчик, руководитель команды")}
                      />
                    </label>
                    <div className="detail-grid">
                      <label className="form-field">{t("Города и страны")}<Input
                          value={targetLocations}
                          onChange={(event) =>
                            setTargetLocations(event.target.value)
                          }
                          placeholder={t("Москва, удалённо")}
                        />
                      </label>
                      <SelectField
                        label={t("Удалённая работа")}
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
                        <option value="">{t("Не задано")}</option>
                        <option value="yes">{t("Обязательна")}</option>
                        <option value="no">{t("Не обязательна")}</option>
                      </SelectField>
                    </div>
                  </div>
                </fieldset>
                <fieldset className="form-section">
                  <legend>{t("Оплата")}</legend>
                  <div className="form-section-fields detail-grid">
                    <label className="form-field">{t("Доход от")}<Input
                        type="number"
                        min="0"
                        value={searchRules.min_salary ?? ""}
                        onChange={(e) =>
                          setRule(
                            "min_salary",
                            e.target.value === "" ? "" : Number(e.target.value),
                          )
                        }
                        placeholder={t("Не задан")}
                      />
                    </label>
                    <SelectField
                      label={t("Валюта")}
                      value={searchRules.currency || ""}
                      onChange={(value) => setRule("currency", value)}
                    >
                      <option value="">{t("Не задана")}</option>
                      {["RUB", "USD", "EUR"].map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </SelectField>
                    <SelectField
                      label={t("Период оплаты")}
                      value={searchRules.salary_period || ""}
                      onChange={(value) => setRule("salary_period", value)}
                    >
                      <option value="">{t("Не задан")}</option>
                      <option value="month">{t("Месяц")}</option>
                      <option value="year">{t("Год")}</option>
                      <option value="hour">{t("Час")}</option>
                    </SelectField>
                    <SelectField
                      label={t("Налоги")}
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
                      <option value="">{t("Не задано")}</option>
                      <option value="gross">{t("До налогов")}</option>
                      <option value="net">{t("На руки")}</option>
                    </SelectField>
                  </div>
                </fieldset>
                <DetailAccordion title={t("Дополнительно")} id="conditions-additional">
                  <fieldset className="search-language-options">
                    <legend>{t("Языки поиска")}</legend>
                    <p className="muted">{t("Агент будет искать вакансии на выбранных языках. Если ничего не выбрано, ограничений по языку нет.")}</p>
                    <div>
                      {[["ru", "Русский"], ["en", "Английский"], ["de", "Немецкий"], ["es", "Испанский"], ["fr", "Французский"], ["it", "Итальянский"], ["pt", "Португальский"], ["zh", "Китайский"], ["ja", "Японский"], ["ar", "Арабский"]]
                        .concat(searchLanguages.filter((code) => !["ru", "en", "de", "es", "fr", "it", "pt", "zh", "ja", "ar"].includes(code)).map((code) => [code, code]))
                        .map(([code, name]) => (
                        <label key={code}>
                          <input type="checkbox" checked={searchLanguages.includes(code)} onChange={(event) => setSearchLanguages((previous) => event.target.checked ? [...previous, code] : previous.filter((language) => language !== code))} />
                          {t(name)}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <label className="form-field">{t("Языки работы")}<Input
                      value={languages}
                      onChange={(event) => setLanguages(event.target.value)}
                      placeholder={t("Русский, английский")}
                    />
                  </label>
                  <div className="detail-grid">
                    <label className="form-field">{t("Часов в неделю, не больше")}<Input
                        type="number"
                        min="0"
                        value={searchRules.max_hours ?? ""}
                        onChange={(e) =>
                          setRule(
                            "max_hours",
                            e.target.value === "" ? "" : Number(e.target.value),
                          )
                        }
                        placeholder={t("Не задано")}
                      />
                    </label>
                    <label className="form-field">{t("Получить первый доход до")}<input
                        className="native-input"
                        type="date"
                        value={incomeDeadline}
                        onChange={(e) => setIncomeDeadline(e.target.value)}
                      />
                    </label>
                  </div>
                  <Label>{t("Дополнительные условия")}</Label>
                  <TextArea
                    aria-label={t("Условия поиска работы")}
                    rows={3}
                    value={conditions}
                    onChange={(event) => setConditions(event.target.value)}
                    placeholder={t("Хочу работать удалённо, до 40 часов в неделю. Важно…")}
                  />
                </DetailAccordion>
              </form>
            </Dialog>
            <Dialog
              open={blockOpen}
              onClose={() => setBlockOpen(false)}
              title={t("Блокировать компанию")}
              footer={
                <>
                  <Button variant="ghost" onPress={() => setBlockOpen(false)}>{t("Отмена")}</Button>
                  <Button
                    variant="danger"
                    type="submit"
                    form="block-form"
                    isPending={pending === "block"}
                  >{t("Блокировать")}</Button>
                </>
              }
            >
              <form
                id="block-form"
                className="flex flex-col gap-3"
                onSubmit={saveBlock}
              >
                <p>{t("Это ваше локальное исключение. Агент учитывает его, когда связь вакансии или контакта с компанией установлена.")}</p>
                <Label htmlFor="block-domain">{t("Домен компании")}</Label>
                <Input
                  id="block-domain"
                  value={blockDomain}
                  onChange={(event) => setBlockDomain(event.target.value)}
                  placeholder="company.example"
                  required
                />
                <Label htmlFor="block-reason">{t("Причина")}</Label>
                <TextArea
                  id="block-reason"
                  rows={3}
                  value={blockReason}
                  onChange={(event) => setBlockReason(event.target.value)}
                  required
                />
                <Label htmlFor="block-evidence">{t("Ссылка на источник · необязательно")}</Label>
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
                      t("Параметры модели сохранены. Теперь можно запустить поручение."),
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
