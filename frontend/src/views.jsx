import { t } from "./i18n.js";
import AutomationSettings from "./AutomationSettings.jsx";
import { Button, Link, Typography, Alert, Chip } from "@heroui/react";
import { typographyVariants } from "@heroui/styles";
import {
  Panel,
  PageHeading,
  Status,
  Empty,
  AgentButton,
  PrivateNote,
  DataTable,
  RecordList,
  DetailAccordion,
  Timestamp,
  Icon,
} from "./ui.jsx";
import {
  list,
  label,
  safeURL,
  formatDate,
  employerGroups,
  exchangeSummary,
  employerDatabaseSummary,
  blockConfirmation,
  conditionLabels,
  humanLabel,
  usageMetric,
  observationBasis,
} from "./model.js";
import { Pipeline, MarketPanel } from "./Overview.jsx";

const Source = ({ value, children }) =>
  safeURL(value) ? (
    <Link

      href={safeURL(value)}
      target="_blank"
      rel="noreferrer"
    >
      {children || value}<Icon name="external" className="size-4 shrink-0" />
    </Link>
  ) : value ? (
    <span >{value}</span>
  ) : null;
function EmployerObservation({ entry, confirmations }) {
  const basis = observationBasis(entry);
  return <div className="flex flex-col gap-3 py-3">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-center gap-2"><Chip size="sm" variant="soft">{basis.label}</Chip><Status value={entry.confirmation?.status === "confirmed" ? "confirmed" : "partial"}>{blockConfirmation(entry, confirmations)}</Status>{entry.kind === "retraction" ? <Chip size="sm" variant="soft">{t("Отзыв записи")}</Chip> : null}</div><Typography.Paragraph size="xs" color="muted"><Timestamp value={entry.payload.observed_at} /></Typography.Paragraph></div>
    <Typography.Paragraph>{entry.payload.claim}</Typography.Paragraph>
    <div className="flex flex-wrap items-center gap-4"><Typography.Paragraph size="sm" color="muted">{basis.verification}</Typography.Paragraph>{entry.payload.source_url ? <Source value={entry.payload.source_url}>{t("Источник")}</Source> : <Typography.Paragraph size="sm" color="muted">{t("Источник не указан")}</Typography.Paragraph>}</div>
  </div>;
}
const TopicHeading = ({ title, description }) => <PageHeading title={title} description={description} />;
export function MarketView({ state }) {
  const jobs = list(state.jobs), resources = list(state.resources), companies = employerGroups(state.employers);
  return <>
    <PageHeading title={t("Рынок")} description={t("Источники и фактически собранные данные для сравнения предложений.")} />
    <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
      <section className="flex min-w-0 flex-1 flex-col gap-5" aria-label={t("Собранные данные")}>
        <Panel title={t("Покрытие данных")}><Typography.Paragraph color="muted">{t("Сохранённые предложения отражают вашу историю поиска. Сопоставимая рыночная выборка ещё не сформирована.")}</Typography.Paragraph><DataTable headers={[t("Собрано"), t("Количество"), ""]} rows={[[t("Вакансии"), jobs.length, <Link href="#search">{t("Открыть")}<Icon name="next" className="size-4 shrink-0" /></Link>], [t("Компании"), companies.length, <Link href="#employers">{t("Открыть")}<Icon name="next" className="size-4 shrink-0" /></Link>], [t("Источники"), resources.length, <Link href="#resources">{t("Открыть")}<Icon name="next" className="size-4 shrink-0" /></Link>]]} /></Panel>
        <Panel title={t("Сохранённые источники")}>{resources.length ? <RecordList items={resources} render={(resource) => <><Icon name="resources" className="size-6 shrink-0 text-muted" /><div className="flex min-w-0 flex-1 flex-col gap-2"><h3 className={typographyVariants({ type: "h5", weight: "medium" }).base()}>{resource.name}</h3><Typography.Paragraph size="sm" color="muted">{resource.notes}</Typography.Paragraph><Source value={resource.url}>{t("Открыть источник")}</Source></div></>} /> : <Empty icon="market" title={t("Источников пока нет")}>{t("Агент сохранит источники и предложения по мере поиска.")}</Empty>}</Panel>
      </section>
      <aside className="w-full xl:w-90 xl:shrink-0" aria-label={t("Сравнение предложений")}><MarketPanel state={state} /></aside>
    </div>
  </>;
}
export function SearchView({ state, ask, onInspect }) {
  return (
    <>
      <TopicHeading
        title={t("Вакансии")}
        description={t("Сохранённые предложения, отклики и история переписки.")}
        topic="search"
        ask={ask}
      />
      <Panel title={t("Сохранённые предложения")}><Pipeline state={state} onInspect={onInspect} /></Panel>
      <div className="flex flex-col gap-4">
        <Panel title={t("Переписка и действия")}>
          {list(state.actions).length ? (
            <DataTable
              headers={[t("Действие"), t("Канал"), t("Состояние"), t("Время"), ""]}
              rows={list(state.actions)
                .slice()
                .reverse()
                .map((action) => [
                  <>
                    <span className="block">{action.operation}</span>
                    <span className="block">
                      {action.payload?.subject ||
                        action.payload?.to ||
                        action.payload?.url}
                    </span>
                  </>,
                  action.connector,
                  <Status value={action.status} />,
                  <Timestamp value={action.created_at} />,
                  <Button
                    variant="ghost"
                    size="sm"
                    onPress={() => onInspect("action", action.id)}
                  >{t("Открыть")}</Button>,
                ])}
            />
          ) : (
            <Empty icon="activity" title={t("История действий пока пуста")}>{t("Агент сохранит подготовленные и выполненные действия с их состояниями.")}</Empty>
          )}
        </Panel>
      </div>
    </>
  );
}
export function SchedulesView({ state, ask, onCommand, pending, onInspect, onModel }) {
  return (
    <>
      <TopicHeading
        title={t("Расписание")}
        description={t("Агент организует регулярные поручения. Вы можете приостановить любой запуск.")}
        topic="schedules"
        ask={ask}
      />
      <AutomationSettings state={state} onCommand={onCommand} onModel={onModel} pending={pending} />
      <Panel title={t("Регулярные поручения")}>
        {list(state.schedules).length ? (
          <DataTable
            headers={[
              t("Поручение"),
              t("Повтор"),
              t("Следующий запуск"),
              t("Состояние"),
              "",
            ]}
            rows={list(state.schedules).map((schedule) => [
              <>
                <span className="block">{schedule.name}</span>
                <span className="block">{t("Последний запуск:")}{" "}{formatDate(schedule.last_run_at)}
                </span>
              </>,
              schedule.interval_minutes >= 60 ? t`${schedule.interval_minutes / 60} ч.` : t`${schedule.interval_minutes} мин.`,
              schedule.enabled ? <Timestamp value={schedule.next_run_at} /> : t("После продолжения"),
              <Status value={schedule.enabled ? "active" : "paused"} />,
              <div className="flex flex-wrap gap-2"><Button
                variant="ghost"
                size="sm"
                isDisabled={Boolean(pending)}
                isPending={pending === "schedule:run:" + schedule.id}
                onPress={() => onCommand("schedule_run", { schedule_id: schedule.id }, "schedule:run:" + schedule.id)}
              >{t("Запустить сейчас")}</Button>{schedule.managed_by === "automation:checks" ? <Typography.Paragraph size="sm" color="muted">{t("Настраивается в автопроверках")}</Typography.Paragraph> : <Button
                variant="outline"
                size="sm"
                isPending={pending === "schedule:" + schedule.id}
                onPress={() =>
                  onCommand(
                    "schedule_toggle",
                    { schedule_id: schedule.id, enabled: !schedule.enabled },
                    "schedule:" + schedule.id,
                  )
                }
              >
                {schedule.enabled ? t("Пауза") : t("Продолжить")}
              </Button>}</div>,
            ])}
          />
        ) : (
          <Empty
            icon="schedules"
            title={t("Расписание ещё не задано")}
          >{t("Расскажите агенту, как часто стоит возвращаться к поиску.")}</Empty>
        )}
      </Panel>
      <div className="flex flex-col gap-4">
        <Panel title={t("Следующие действия")}>
          <RecordList
            items={list(state.tasks)}
            empty={t("Агент сохранит следующие шаги и напоминания по мере работы.")}
            render={(task) => (
              <>

                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{task.title}</Typography.Heading>
                  <p>{formatDate(task.due_at)}</p>
                </div>
                <Status value={task.status} />
              </>
            )}
          />
        </Panel>
      </div>
      {list(state.schedule_runs).length ? (
        <div className="flex flex-col gap-4">
          <Panel title={t("История запусков")}>
            <DataTable
              headers={[t("Поручение"), t("Время"), t("Состояние"), ""]}
              rows={list(state.schedule_runs)
                .slice()
                .reverse()
                .slice(0, 20)
                .map((run) => [
                  run.name ||
                    list(state.schedules).find((s) => s.id === run.schedule_id)
                      ?.name ||
                    run.schedule_id,
                  <Timestamp value={run.started_at || run.at} />,
                  <Status value={run.status} />,
                  <Button
                    variant="ghost"
                    size="sm"
                    onPress={() => onInspect("schedule_run", run.id)}
                  >{t("Результат")}</Button>,
                ])}
            />
          </Panel>
        </div>
      ) : null}
    </>
  );
}
export function ExperimentsView({ state, ask, onInspect }) {
  return (
    <>
      <TopicHeading
        title={t("Эксперименты")}
        description={t("Гипотезы, варианты и фактические результаты вашего поиска.")}
        topic="experiments"
        ask={ask}
      />
      <Panel title={t("Гипотезы и результаты")}>
        <RecordList
          items={list(state.experiments)}
          empty={t("Экспериментов пока нет.")}
          render={(experiment) => {
            const report = list(state.experiment_reports).find(
              (r) => r.experiment?.id === experiment.id,
            );
            return (
              <>

                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{experiment.hypothesis}</Typography.Heading>
                  <div className="flex flex-wrap gap-3">
                    <span>{list(experiment.variant_ids).length}{" "}{t("варианта")}</span>
                    <span>{t("Окно:")}{" "}{experiment.horizon_hours}{" "}{t("ч.")}</span>
                    <span>{t("Метрика:")}{" "}{label(experiment.metric)}</span>
                  </div>
                  {report ? <p>{label(report.conclusion)}</p> : null}
                </div>
                <Status value={experiment.status} />
                <Button
                  variant="ghost"
                  size="sm"
                  onPress={() => onInspect("experiment", experiment.id)}
                >{t("Результаты")}</Button>
              </>
            );
          }}
        />
      </Panel>
    </>
  );
}
export function StrengthsView({ state, ask }) {
  return (
    <>
      <TopicHeading
        title={t("Сильные стороны")}
        description={t("Опыт и навыки, для которых агент нашёл подтверждения.")}
        topic="strengths"
        ask={ask}
      />
      <Panel title={t("Факты и подтверждения")}>
        <RecordList
          items={list(state.strengths)}
          empty={t("Агент предложит сильные стороны, когда изучит ваш опыт и проекты.")}
          render={(strength) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{strength.title}</Typography.Heading>
                <p>{strength.description}</p>
                <div className="flex flex-col gap-3">
                  {list(strength.evidence).map((e, index) => (
                    <div key={index}>
                      <Source value={e.source} />
                      {e.excerpt ? <p>{e.excerpt}</p> : null}
                    </div>
                  ))}
                </div>
              </div>
              <Status value={strength.status} />
            </>
          )}
        />
      </Panel>
    </>
  );
}
export function CVView({ state, ask, onInspect }) {
  return (
    <>
      <TopicHeading
        title="CV"
        description={t("Резюме, которые агент собрал из подтверждённых фактов.")}
        topic="cv"
        ask={ask}
      />
      <Panel title={t("Варианты резюме")}>
        <RecordList
          items={list(state.cvs)}
          empty={t("Агент подготовит CV под вашу цель и подходящие вакансии. Поручите ему изучить факты вашего опыта.")}
          render={(cv) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{cv.name || cv.headline}</Typography.Heading>
                <p>{cv.headline}</p>
                <div className="flex flex-wrap gap-3">
                  <span>{cv.language || t("Исходная версия")}</span>
                  <span>{list(cv.facts).length}{" "}{t("фактов")}</span>
                  <span>{formatDate(cv.created_at)}</span>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onPress={() => onInspect("cv", cv.id)}
              >{t("Открыть")}</Button>
            </>
          )}
        />
      </Panel>
    </>
  );
}
export function EmployersView({ state, ask, onBlock, onCommand, pending }) {
  const groups = employerGroups(state.employers),
    blocks = list(state.employer_blocks),
    proposals = list(state.employer_proposals),
    summary = exchangeSummary(state.network),
    database = employerDatabaseSummary(state),
    chain = state.network?.chain || {};
  return (
    <>
      <PageHeading
        title={t("Работодатели")}
        description={t("Наблюдения о компаниях с источниками и подтверждением в блокчейне.")}
      >
        <Button variant="outline" size="sm" isPending={pending === "employer-sync"} onPress={() => onCommand("blockchain_sync", {}, "employer-sync")}><Icon name="refresh" className="size-4 shrink-0" />{t("Обновить обмен")}</Button>
        <Button variant="outline" size="sm" onPress={() => onBlock("")}>{t("Блокировать компанию")}</Button>
      </PageHeading>
      <section className="employer-database-summary" aria-label={t("Состояние базы работодателей")}>
        <dl className="employer-database-counts">
          <div><dt>{t("Компаний")}</dt><dd>{groups.length}</dd></div>
          <div><dt>{t("Подтверждено записей")}</dt><dd>{database.confirmed}</dd></div>
          <div><dt>{t("Ожидают подтверждения")}</dt><dd>{database.pending}</dd></div>
          <div><dt>{t("Блоков в цепочке")}</dt><dd>{database.blocks ?? "—"}</dd></div>
        </dl>
        <Typography.Paragraph>{database.explanation}</Typography.Paragraph>
        {database.pending > 0 && chain.qualified === false ? <Typography.Paragraph size="sm" color="muted">{t("Для включения новых записей в блок нужен квалифицированный узел сети. Одна подпись ещё не добавляет запись в общую базу.")}</Typography.Paragraph> : null}
        <div className="employer-database-actions"><AgentButton onPress={() => ask(t("Разберись с общей базой работодателей: проверь ожидающие записи, состояние блокчейна и доступные подключения. Настрой согласованный обмен, объясни, что нужно для включения записей в блоки. Личные данные и переписку не публикуй."))}>{t("Проверить базу с агентом")}</AgentButton></div>
      </section>
      <div>{summary.status === "healthy" ? <div className="flex flex-wrap items-center gap-3"><Status value="success">{summary.label}</Status><Typography.Paragraph size="sm" color="muted">{t("Синхронизация:")}{" "}<Timestamp value={summary.last_sync} />{summary.employers !== undefined ? t` · Компаний: ${summary.employers}` : ""}</Typography.Paragraph></div> : <Alert status={["attention", "recovering"].includes(summary.status) ? "warning" : "default"}>
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>{summary.label}</Alert.Title>
          <Alert.Description><div className="flex flex-col gap-2">
            <p>{summary.detail}</p>
            <p>{summary.last_sync ? <>{t("Последняя успешная синхронизация:")}{" "}<Timestamp value={summary.last_sync} /></> : t("Успешных синхронизаций ещё не было")}</p>
          </div></Alert.Description>
        </Alert.Content>
      </Alert>}</div>
      {groups.length > 0 || !database.pending ? <Panel title={t("Подтверждённая база")}>
        <RecordList
          items={groups}
          empty={t("Подтверждённых наблюдений пока нет. Здесь будут появляться сведения, принятые в блокчейн.")}
          render={(company) => (
              <div className="flex w-full min-w-0 flex-col gap-3">
                <div className="flex flex-wrap items-start justify-between gap-3"><div className="flex flex-col gap-2"><h2 className={typographyVariants({ type: "h4", weight: "medium" }).base()}>{company.name}</h2><Typography.Paragraph size="sm" color="muted">{company.domain}</Typography.Paragraph></div><Button variant="ghost" size="sm" onPress={() => onBlock(company.domain)}>{t("Блокировать")}</Button></div>
                {company.observations.slice(0, 2).map((entry, index) => (
                  <EmployerObservation key={entry.event_id || index} entry={entry} confirmations={database.confirmations} />
                ))}
                {company.observations.length > 2 ? (
                  <DetailAccordion
                    title={t`Все наблюдения (${company.observations.length})`}
                    id={company.domain}
                  >
                    {company.observations.slice(2).map((entry, index) => (
                      <EmployerObservation key={entry.event_id || index} entry={entry} confirmations={database.confirmations} />
                    ))}
                  </DetailAccordion>
                ) : null}
              </div>
          )}
        />
      </Panel> : null}
      {database.pending > 0 ? <Panel title={t`Ожидают подтверждения · ${database.pending}`}>
        <Typography.Paragraph size="sm" color="muted">{t("Записи из подписанного журнала на этом устройстве. Они сохраняются здесь, пока не получат подтверждение в блокчейне.")}</Typography.Paragraph>
        <RecordList items={proposals} empty={t("Обновите приложение, чтобы увидеть содержимое ожидающих записей.")} render={(entry) => <div className="min-w-0 w-full"><h3 className={typographyVariants({ type: "h4", weight: "medium" }).base()}>{typeof entry.payload?.name === "string" && entry.payload.name ? entry.payload.name : entry.subject}</h3>{typeof entry.payload?.name === "string" && entry.payload.name ? <Typography.Paragraph size="sm" color="muted">{entry.subject}</Typography.Paragraph> : null}<EmployerObservation entry={entry} confirmations={database.confirmations} /></div>} />
      </Panel> : null}
      <DetailAccordion title={t("Как работает блокчейн")} id="employer-blockchain" level={2}>
        <Typography.Paragraph>{t("Подпись связывает наблюдение с автором. Узел включает его в блок, а следующие блоки увеличивают число подтверждений. В основной список попадают только подтверждённые записи.")}</Typography.Paragraph>
        <DataTable headers={[t("Показатель"), t("Состояние")]} rows={[
          [t("Сеть"), chain.profile === "development" ? t("Локальная тестовая сеть") : chain.profile === "public-testnet-v1" ? t("Публичная тестовая сеть") : chain.network || "—"],
          [t("Высота цепочки"), chain.height ?? "—"],
          [t("Нужно подтверждений для записи"), database.confirmations ?? "—"],
          [t("Право создавать блоки"), chain.qualified === true ? t("Квалификация действует") : chain.qualified === false ? t("Требуется квалификация") : "—"],
        ]} />
        <Typography.Paragraph size="sm" color="muted">{t("Подтверждение в блокчейне означает проверку подписи и истории. Достоверность условий работодателя оценивайте по источникам.")}</Typography.Paragraph>
      </DetailAccordion>
      <DetailAccordion title={t("Обмен и защита данных")} id="employer-protection" level={2}>
        <p>{summary.auto ? t("Фоновая синхронизация включена. Результат последней проверки показан выше.") : t("Автоматический обмен отключён.")}</p>
        <p>{t("Подпись защищает запись от подмены. Содержание независимо не проверено — оценивайте его по источнику.")}</p>
        <p>{t("Обмен касается только компаний: вакансий, условий и процесса найма. CV, личные результаты откликов, имена и контакты людей не публикуются. Перед публикацией агент проверяет, что текст касается только работодателя.")}</p>
      </DetailAccordion>
      <div className="flex flex-col gap-4">
        <DetailAccordion title={t`Исключённые компании · ${blocks.filter((block) => block.blocked).length}`} id="employer-exclusions" level={2}>
          <RecordList
            items={blocks.filter((b) => b.blocked)}
            empty={t("Нет заблокированных компаний. Локальные исключения не публикуются в общей базе.")}
            render={(block) => (
              <>
                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{block.domain}</Typography.Heading>
                  <p>{block.reason}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  isPending={pending === "unblock:" + block.domain}
                  onPress={() =>
                    onCommand(
                      "employer_block",
                      {
                        domain: block.domain,
                        reason: block.reason,
                        evidence_url: block.evidence_url || "",
                        blocked: false,
                      },
                      "unblock:" + block.domain,
                    )
                  }
                >{t("Снять блокировку")}</Button>
              </>
            )}
          />
        </DetailAccordion>
      </div>
    </>
  );
}
export function ResourcesView({ state, ask }) {
  const metrics = Object.entries(state.statistics?.metrics_totals || {});
  return (
    <>
      <TopicHeading
        title={t("Ресурсы")}
        description={t("Источники, сервисы и материалы, которые использует агент.")}
        topic="resources"
        ask={ask}
      />
      <Panel>
        <RecordList
          items={list(state.resources)}
          empty={t("Агент выберет полезные источники и ресурсы под вашу задачу.")}
          render={(resource) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <h2 className={typographyVariants({ type: "h3", weight: "medium" }).base()}>{resource.name}</h2>
                <Typography.Paragraph size="sm" color="muted">{resource.notes}</Typography.Paragraph>
                <Source value={resource.url}>{safeURL(resource.url) ? new URL(resource.url).hostname : resource.url}</Source>
                <div className="flex flex-wrap gap-3">
                  <span>{humanLabel(resource.kind)}</span>
                  {resource.budget != null ? (
                    <span>{t("Бюджет:")}{" "}{resource.budget}{resource.currency ? ` ${resource.currency}` : t(" · валюта не указана")}</span>
                  ) : null}
                </div>
              </div>
            </>
          )}
        />
      </Panel>
      {metrics.length ? (
        <div className="flex flex-col gap-4">
          <Panel title={t("Фактическое использование")}>
            <DataTable
              headers={[t("Показатель"), t("Значение")]}
              rows={metrics.map(([key, value]) => usageMetric(key, value))}
            />
          </Panel>
        </div>
      ) : null}
    </>
  );
}
export function AccountsView({ state, ask }) {
  const platforms = new Map(
    list(state.platforms).map((platform) => [platform.id, platform]),
  );
  return (
    <>
      <TopicHeading
        title={t("Аккаунты")}
        description={t("Агент организует доступ к нужным сервисам и отслеживает подтверждения.")}
        topic="accounts"
        ask={ask}
      />
      <Panel title={t("Аккаунты для поиска")}>
        <RecordList
          items={list(state.accounts)}
          empty={t("Агент сам определит, какие аккаунты нужны, и сохранит состояния регистрации и подтверждения почты.")}
          render={(account) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>
                  {platforms.get(account.platform_id)?.name ||
                    account.platform_id}
                </Typography.Heading>
                <p>
                  {account.identifier}
                  {account.email ? " · " + account.email : ""}
                </p>
                {account.notes ? <p>{account.notes}</p> : null}
                {account.status === "verification_required" ? <Typography.Paragraph size="sm" color="muted">{t("Попросите вашего агента проверить, какой шаг подтверждения требуется. Он сообщит, если необходимо ваше участие.")}</Typography.Paragraph> : null}
              </div>
              <Status value={account.status} />
            </>
          )}
        />
      </Panel>
      <div className="flex flex-col gap-4">
        <Panel title={t("Выбранные площадки")}>
          <RecordList
            items={list(state.platforms)}
            empty={t("Агент подбирает площадки под цель, а не по фиксированному списку.")}
            render={(platform) => (
              <>

                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{platform.name}</Typography.Heading>
                  <Source value={platform.url} />
                  <p>{platform.notes}</p>
                  <Typography.Paragraph size="sm" color="muted">{t("Проверку доступа ведёт ваш агент. Если потребуется ваше участие, продолжите в его чате. Открытие ссылки не подтверждает доступ в сеансе агента.")}</Typography.Paragraph>
                  <div className="flex flex-wrap gap-3">
                    {list(platform.capabilities).map((capability) => (
                      <span key={capability}>{humanLabel(capability)}</span>
                    ))}
                  </div>
                </div>
              </>
            )}
          />
        </Panel>
      </div>
    </>
  );
}
export function RepositoriesView({ state, ask }) {
  return (
    <>
      <TopicHeading
        title={t("Репозитории")}
        description={t("Подтверждения опыта, найденные агентом в ваших проектах.")}
        topic="repositories"
        ask={ask}
      />
      <Panel title={t("Изученные проекты")}>
        <RecordList
          items={list(state.repositories)}
          empty={t("Поручите агенту изучить локальный репозиторий и укажите его путь обычным сообщением.")}
          render={(repository) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{repository.name || repository.path}</Typography.Heading>
                <p className="overflow-x-auto">{repository.path}</p>
                <div className="flex flex-wrap gap-3">
                  <span>{repository.scanned_file_count}{" "}{t("изученных файлов")}</span>
                  {Object.keys(repository.languages || {}).map((language) => (
                    <span key={language}>{language}</span>
                  ))}
                  <span>{formatDate(repository.analyzed_at)}</span>
                </div>
                <DetailAccordion title={t("Что нашёл агент")} id={repository.id} level={4}>
                  <p>{repository.readme_excerpt}</p>
                  {list(repository.strength_suggestions).map(
                    (strength, index) => (
                      <div className="flex flex-col gap-2 py-2" key={index}>
                        <Typography.Heading level={4}>{strength.title}</Typography.Heading>
                        <p>{strength.description}</p>
                      </div>
                    ),
                  )}
                  {list(repository.evidence).map((item, index) => (
                    <div className="flex flex-col gap-2 py-2" key={index}>
                      <Source value={item.source} />
                      <pre>{item.excerpt}</pre>
                    </div>
                  ))}
                </DetailAccordion>
              </div>
            </>
          )}
        />
      </Panel>
    </>
  );
}
export function TacticsView({ state, ask }) {
  return (
    <>
      <TopicHeading
        title={t("Тактики")}
        description={t("Подходы к поиску, которые агент предлагает на основе результатов.")}
        topic="tactics"
        ask={ask}
      />
      <Panel title={t("Гипотезы и действия")}>
        <RecordList
          items={list(state.tactics)}
          empty={t("Агент предложит следующий подход, когда изучит вашу цель и результаты поиска.")}
          render={(tactic) => (
            <>

              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{tactic.name}</Typography.Heading>
                <p>{tactic.hypothesis}</p>
                <ol className="flex flex-col gap-2">
                  {list(tactic.actions).map((action, index) => (
                    <li key={index}>{action}</li>
                  ))}
                </ol>
                <p >{t("Признак успеха:")}{" "}{tactic.success_metric}
                </p>
              </div>
              <Status value={tactic.status} />
            </>
          )}
        />
      </Panel>
      {list(state.research).length ? (
        <div className="flex flex-col gap-4">
          <Panel title={t("Исследования агента")}>
            <RecordList
              items={list(state.research)}
              render={(research) => (
                <>

                  <div className="flex min-w-0 flex-1 flex-col gap-3">
                    <Typography.Heading level={3}>{research.title}</Typography.Heading>
                    <p>{research.hypothesis}</p>
                    <p >{t("Следующий шаг:")}{" "}{research.next_step}
                    </p>
                    <DetailAccordion title={t("Подтверждения")} id={research.id} level={4}>
                      {list(research.evidence).map((evidence, index) => (
                        <div className="flex flex-col gap-2 py-2" key={index}>
                          <Source value={evidence.source || evidence.url} />
                          <p>
                            {evidence.text ||
                              evidence.excerpt ||
                              evidence.claim}
                          </p>
                        </div>
                      ))}
                    </DetailAccordion>
                  </div>
                </>
              )}
            />
          </Panel>
        </div>
      ) : null}
    </>
  );
}
export function SettingsView({ state, onConditions, runtime }) {
  const profile = state.profile || {};
  return (
    <>
      <PageHeading
        title={t("Настройки")}
        description={t("Условия поиска и дополнительные параметры Worklife.")}
      />
      {state.release?.installed_version ? <Panel title={t("Версия Worklife")}>
        <div className="flex flex-col gap-3">
          <p>{t`Установлена версия ${state.release.installed_version}.`}</p>
          {state.release.latest_version ? <p>{t`Последняя опубликованная версия: ${state.release.latest_version}.`}</p> : null}
          {state.release.status !== "checked" ? <Typography.Paragraph color="muted">{t("Проверка обновлений сейчас недоступна.")}</Typography.Paragraph> : null}
          <Link href={safeURL(state.release.release_url)} target="_blank" rel="noopener noreferrer">{t("Открыть релиз")}<Icon name="external" className="size-4 shrink-0" /></Link>
        </div>
      </Panel> : null}
      <Panel title={t("Что важно в работе")}>
        <div className="flex flex-col gap-4">
          {list(profile.life_preferences).length ? (
            <ul>
              {profile.life_preferences.map((preference, index) => (
                <li key={index}>{preference}</li>
              ))}
            </ul>
          ) : (
            <p>{t("Расскажите, какую работу вы ищете: график, место, доход и другие важные условия.")}</p>
          )}
          {Object.keys(profile.constraints || {}).length ? (
            <DetailAccordion
              title={t("Условия, уточнённые агентом")}
              id="constraints"
            >
              <dl className="grid gap-3">
                {Object.entries(profile.constraints).map(([key, value]) => (
                  <div key={key}>
                    <dt>{conditionLabels[key] ? t(conditionLabels[key]) : key}</dt>
                    <dd>
                      {typeof value === "boolean"
                        ? value
                          ? t("Да")
                          : t("Нет")
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </DetailAccordion>
          ) : null}
          <Button variant="outline" size="sm" onPress={onConditions}>{t("Уточнить условия")}</Button>
        </div>
      </Panel>
      <DetailAccordion title={t("Дополнительно: встроенный исполнитель")} id="embedded-runtime" level={2}>{runtime}</DetailAccordion>
      <div className="flex flex-col gap-4">
        <Panel title={t("Данные и подключения")}>
          <div className="flex flex-col gap-4">
            <PrivateNote />
            <DetailAccordion
              title={t("Факты, которые использует агент")}
              id="profile-facts"
            >
              {list(profile.facts).length ? (
                profile.facts.map((fact, index) => (
                  <div className="flex flex-col gap-2 py-2" key={fact.id || index}>
                    <p>{fact.text}</p>
                    <Source value={fact.source} />
                  </div>
                ))
              ) : (
                <p>{t("Агент ещё не сохранил факты опыта.")}</p>
              )}
            </DetailAccordion>
            <DetailAccordion title={t("Технические подключения")} id="connections">
              {!list(state.connectors).length ? <p>{t("Дополнительные сервисы пока не подключены. Агент определит, какие нужны для вашей цели, и поможет настроить доступ; если потребуется ваше участие, сообщит об этом.")}</p> : null}
              {list(state.connectors).map((connector) => (
                <div className="flex flex-col gap-2 py-2" key={connector.name}>
                  <Typography.Heading level={4}>{connector.name}</Typography.Heading>
                  <p>{t("Чтение:")}{" "}{list(connector.read).join(", ") || "—"}</p>
                  <p>{t("Действия:")}{" "}{list(connector.write).join(", ") || "—"}</p>
                  {Object.entries(connector.credentials || {}).map(
                    ([key, value]) => (
                      <p key={key}>
                        {key}: {value.set ? t("настроено") : t("не настроено")}{" "}
                        <span >({value.env})</span>
                      </p>
                    ),
                  )}
                </div>
              ))}
            </DetailAccordion>
          </div>
        </Panel>
      </div>
    </>
  );
}
