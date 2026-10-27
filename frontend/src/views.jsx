import { Button, Link, Typography, Alert } from "@heroui/react";
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
} from "./ui.jsx";
import {
  list,
  label,
  safeURL,
  formatDate,
  employerGroups,
  exchangeSummary,
  conditionLabels,
  humanLabel,
  usageMetric,
  observationBasis,
} from "./model.js";
import { Pipeline } from "./Overview.jsx";

const Source = ({ value, children }) =>
  safeURL(value) ? (
    <Link
      
      href={safeURL(value)}
      target="_blank"
      rel="noreferrer"
    >
      {children || value} ↗
    </Link>
  ) : value ? (
    <span >{value}</span>
  ) : null;
function EmployerObservation({ entry }) {
  const basis = observationBasis(entry);
  return <div className="flex flex-col gap-3 py-3">
    <span >{basis.label}</span>
    <p>{entry.payload.claim}</p>
    <p >{basis.verification}</p>
    <div className="flex flex-wrap gap-3">
      {entry.payload.source_url ? <Source value={entry.payload.source_url}>Источник</Source> : <span>Источник не указан</span>}
      <span>Наблюдение: {formatDate(entry.payload.observed_at)}</span>
    </div>
  </div>;
}
const TopicHeading = ({ title, description, topic, ask }) => (
  <PageHeading title={title} description={description}>
    <AgentButton onPress={() => ask(topic)} />
  </PageHeading>
);
export function SearchView({ state, ask, onInspect }) {
  return (
    <>
      <TopicHeading
        title="Поиск"
        description="Предложения, которые изучил агент, и ход ваших откликов."
        topic="search"
        ask={ask}
      />
      <Pipeline state={state} onInspect={onInspect} />
      <div className="flex flex-col gap-4">
        <Panel title="Переписка и действия">
          {list(state.actions).length ? (
            <DataTable
              headers={["Действие", "Канал", "Состояние", "Время", ""]}
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
                  >
                    Открыть
                  </Button>,
                ])}
            />
          ) : (
            <Empty icon="activity" title="История действий пока пуста">
              Агент сохранит подготовленные и выполненные действия с их
              состояниями.
            </Empty>
          )}
        </Panel>
      </div>
    </>
  );
}
export function SchedulesView({ state, ask, onCommand, pending, onInspect }) {
  return (
    <>
      <TopicHeading
        title="Расписание"
        description="Агент организует регулярные поручения. Вы можете приостановить любой запуск."
        topic="schedules"
        ask={ask}
      />
      <Panel title="Регулярные поручения">
        {list(state.schedules).length ? (
          <DataTable
            headers={[
              "Поручение",
              "Повтор",
              "Следующий запуск",
              "Состояние",
              "",
            ]}
            rows={list(state.schedules).map((schedule) => [
              <>
                <span className="block">{schedule.name}</span>
                <span className="block">
                  Последний запуск: {formatDate(schedule.last_run_at)}
                </span>
              </>,
              schedule.interval_minutes >= 60 ? `${schedule.interval_minutes / 60} ч.` : `${schedule.interval_minutes} мин.`,
              schedule.enabled ? <Timestamp value={schedule.next_run_at} /> : "После продолжения",
              <Status value={schedule.enabled ? "active" : "paused"} />,
              <Button
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
                {schedule.enabled ? "Пауза" : "Продолжить"}
              </Button>,
            ])}
          />
        ) : (
          <Empty
            icon="schedules"
            title="Расписание ещё не задано"
            action={
              <AgentButton onPress={() => ask("schedules")}>
                Поручить организовать расписание
              </AgentButton>
            }
          >
            Расскажите агенту, как часто стоит возвращаться к поиску.
          </Empty>
        )}
      </Panel>
      <div className="flex flex-col gap-4">
        <Panel title="Следующие действия">
          <RecordList
            items={list(state.tasks)}
            empty="Агент сохранит следующие шаги и напоминания по мере работы."
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
          <Panel title="История запусков">
            <DataTable
              headers={["Поручение", "Время", "Состояние", ""]}
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
                  >
                    Результат
                  </Button>,
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
        title="Эксперименты"
        description="Гипотезы, варианты и фактические результаты вашего поиска."
        topic="experiments"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Гипотезы и результаты">
        <RecordList
          items={list(state.experiments)}
          empty="Пока нет экспериментов. Агент может сравнить варианты CV или подходы к поиску и заранее задать метрику."
          render={(experiment) => {
            const report = list(state.experiment_reports).find(
              (r) => r.experiment?.id === experiment.id,
            );
            return (
              <>
                
                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{experiment.hypothesis}</Typography.Heading>
                  <div className="flex flex-wrap gap-3">
                    <span>{list(experiment.variant_ids).length} варианта</span>
                    <span>Окно: {experiment.horizon_hours} ч.</span>
                    <span>Метрика: {label(experiment.metric)}</span>
                  </div>
                  {report ? <p>{label(report.conclusion)}</p> : null}
                </div>
                <Status value={experiment.status} />
                <Button
                  variant="ghost"
                  size="sm"
                  onPress={() => onInspect("experiment", experiment.id)}
                >
                  Результаты
                </Button>
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
        title="Сильные стороны"
        description="Опыт и навыки, для которых агент нашёл подтверждения."
        topic="strengths"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Факты и подтверждения">
        <RecordList
          items={list(state.strengths)}
          empty="Агент предложит сильные стороны, когда изучит ваш опыт и проекты."
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
        description="Резюме, которые агент собрал из подтверждённых фактов."
        topic="cv"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Варианты резюме">
        <RecordList
          items={list(state.cvs)}
          empty="Агент подготовит CV под вашу цель и подходящие вакансии. Поручите ему изучить факты вашего опыта."
          render={(cv) => (
            <>
              
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{cv.name || cv.headline}</Typography.Heading>
                <p>{cv.headline}</p>
                <div className="flex flex-wrap gap-3">
                  <span>{cv.language || "Исходная версия"}</span>
                  <span>{list(cv.facts).length} фактов</span>
                  <span>{formatDate(cv.created_at)}</span>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onPress={() => onInspect("cv", cv.id)}
              >
                Открыть
              </Button>
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
    summary = exchangeSummary(state.network);
  return (
    <>
      <PageHeading
        title="Работодатели"
        description="Компании, их вакансии и условия. Общая база не содержит профилей работников."
      >
        <Button variant="outline" size="sm" onPress={() => onBlock("")}>
          Блокировать компанию
        </Button>
        <AgentButton onPress={() => ask("employers")} />
      </PageHeading>
      <Alert status={summary.status === "healthy" ? "success" : ["attention", "recovering"].includes(summary.status) ? "warning" : "default"}>
        <Alert.Indicator />
        <Alert.Content>
          <Alert.Title>{summary.label}</Alert.Title>
          <Alert.Description><div className="flex flex-col gap-2">
            <p>{summary.detail}</p>
            <p>{summary.last_sync ? <>Последняя успешная синхронизация: <Timestamp value={summary.last_sync} /></> : "Успешных синхронизаций ещё не было"}</p>
            <p>Подпись защищает запись от подмены. Содержание независимо не проверено — оценивайте его по источнику.</p>
            <p>{summary.auto ? "Обмен работает автоматически." : "Автоматический обмен отключён."}{summary.employers !== undefined ? ` Компаний в базе: ${summary.employers}.` : ""}</p>
          </div></Alert.Description>
        </Alert.Content>
      </Alert>
      <Panel title="Компании и наблюдения">
        <RecordList
          items={groups}
          empty="Общая база пока пуста. Агент будет собирать наблюдения о работодателях и обновлять их автоматически."
          render={(company) => (
            <>
              
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{company.name}</Typography.Heading>
                <span className="block">{company.domain}</span>
                {company.observations.slice(0, 2).map((entry, index) => (
                  <EmployerObservation key={entry.event_id || index} entry={entry} />
                ))}
                {company.observations.length > 2 ? (
                  <DetailAccordion
                    title={`Все наблюдения (${company.observations.length})`}
                    id={company.domain}
                  >
                    {company.observations.slice(2).map((entry, index) => (
                      <EmployerObservation key={entry.event_id || index} entry={entry} />
                    ))}
                  </DetailAccordion>
                ) : null}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onPress={() => onBlock(company.domain)}
              >
                Блокировать
              </Button>
            </>
          )}
        />
      </Panel>
      <p >
        Обмен касается только компаний: вакансий, условий, этапов найма и
        поведения работодателя. CV, личные результаты откликов, имена и контакты
        людей не публикуются. Перед публикацией агент проверяет, что текст касается только работодателя.
      </p>
      <div className="flex flex-col gap-4">
        <Panel title="Ваши исключения">
          <RecordList
            items={blocks.filter((b) => b.blocked)}
            empty="Нет заблокированных компаний. Локальные исключения не публикуются в общей базе."
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
                >
                  Снять блокировку
                </Button>
              </>
            )}
          />
        </Panel>
      </div>
    </>
  );
}
export function ResourcesView({ state, ask }) {
  const metrics = Object.entries(state.statistics?.metrics_totals || {});
  return (
    <>
      <TopicHeading
        title="Ресурсы"
        description="Источники, сервисы и материалы, которые использует агент."
        topic="resources"
        ask={ask}
      />
      <Panel title="Что использует агент">
        <RecordList
          items={list(state.resources)}
          empty="Агент выберет полезные источники и ресурсы под вашу задачу."
          render={(resource) => (
            <>
              
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{resource.name}</Typography.Heading>
                <p>{resource.notes}</p>
                <Source value={resource.url} />
                <div className="flex flex-wrap gap-3">
                  <span>{humanLabel(resource.kind)}</span>
                  {resource.budget != null ? (
                    <span>Бюджет: {resource.budget}{resource.currency ? ` ${resource.currency}` : " · валюта не указана"}</span>
                  ) : null}
                </div>
                <Button variant="ghost" size="sm" onPress={() => ask("resources", `Используй ресурс «${resource.name}» (${resource.url || "без ссылки"}) для моей цели. Учитывай его заметки, бюджет и мои ограничения.`, { kind: "resource", id: resource.id })}>Поручить по этому ресурсу</Button>
              </div>
            </>
          )}
        />
      </Panel>
      {metrics.length ? (
        <div className="flex flex-col gap-4">
          <Panel title="Фактическое использование">
            <DataTable
              headers={["Показатель", "Значение"]}
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
        title="Аккаунты"
        description="Агент организует доступ к нужным сервисам и отслеживает подтверждения."
        topic="accounts"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Аккаунты для поиска">
        <RecordList
          items={list(state.accounts)}
          empty="Агент сам определит, какие аккаунты нужны, и сохранит состояния регистрации и подтверждения почты."
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
                <Button variant="ghost" size="sm" onPress={() => ask("accounts", `Продолжи работу с аккаунтом «${account.identifier}» на площадке «${platforms.get(account.platform_id)?.name || "выбранная площадка"}». Текущее состояние: ${label(account.status)}. Разберись, что требуется для продолжения, и сообщи, если нужно моё действие.`, { kind: "account", id: account.id, status: account.status })}>{account.status === "verification_required" ? "Продолжить подтверждение" : "Поручить по этому аккаунту"}</Button>
              </div>
              <Status value={account.status} />
            </>
          )}
        />
      </Panel>
      <div className="flex flex-col gap-4">
        <Panel title="Выбранные площадки">
          <RecordList
            items={list(state.platforms)}
            empty="Агент подбирает площадки под цель, а не по фиксированному списку."
            render={(platform) => (
              <>
                
                <div className="flex min-w-0 flex-1 flex-col gap-3">
                  <Typography.Heading level={3}>{platform.name}</Typography.Heading>
                  <Source value={platform.url} />
                  <p>{platform.notes}</p>
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
        title="Репозитории"
        description="Подтверждения опыта, найденные агентом в ваших проектах."
        topic="repositories"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Изученные проекты">
        <RecordList
          items={list(state.repositories)}
          empty="Поручите агенту изучить локальный репозиторий и укажите его путь обычным сообщением."
          render={(repository) => (
            <>
              
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <Typography.Heading level={3}>{repository.name || repository.path}</Typography.Heading>
                <p className="overflow-x-auto">{repository.path}</p>
                <div className="flex flex-wrap gap-3">
                  <span>{repository.scanned_file_count} изученных файлов</span>
                  {Object.keys(repository.languages || {}).map((language) => (
                    <span key={language}>{language}</span>
                  ))}
                  <span>{formatDate(repository.analyzed_at)}</span>
                </div>
                <DetailAccordion title="Что нашёл агент" id={repository.id}>
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
                <Button variant="ghost" size="sm" onPress={() => ask("repositories", `Продолжи разбор проекта «${repository.name || repository.path}» по пути ${repository.path}. Уточни мою роль и результаты, сохрани только подтверждённые сильные стороны.`, { kind: "repository", id: repository.id })}>Разобрать с агентом</Button>
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
        title="Тактики"
        description="Подходы к поиску, которые агент предлагает на основе результатов."
        topic="tactics"
        ask={ask}
      />
      <PrivateNote />
      <Panel title="Гипотезы и действия">
        <RecordList
          items={list(state.tactics)}
          empty="Агент предложит следующий подход, когда изучит вашу цель и результаты поиска."
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
                <p >
                  Признак успеха: {tactic.success_metric}
                </p>
                <Button variant="ghost" size="sm" onPress={() => ask("tactics", `Оцени и продолжи тактику «${tactic.name}». Проверь её действия и фактические результаты по метрике «${tactic.success_metric}», сохраняя мою цель и ограничения.`, { kind: "tactic", id: tactic.id, status: tactic.status })}>Продолжить тактику</Button>
              </div>
              <Status value={tactic.status} />
            </>
          )}
        />
      </Panel>
      {list(state.research).length ? (
        <div className="flex flex-col gap-4">
          <Panel title="Исследования агента">
            <RecordList
              items={list(state.research)}
              render={(research) => (
                <>
                  
                  <div className="flex min-w-0 flex-1 flex-col gap-3">
                    <Typography.Heading level={3}>{research.title}</Typography.Heading>
                    <p>{research.hypothesis}</p>
                    <p >
                      Следующий шаг: {research.next_step}
                    </p>
                    <DetailAccordion title="Подтверждения" id={research.id}>
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
export function SettingsView({ state, onConditions, ask, onModel }) {
  const profile = state.profile || {},
    configured = state.agent?.configured;
  return (
    <>
      <PageHeading
        title="Настройки"
        description="Ваши условия и подключение агента."
      >
        <Button variant="outline" size="sm" onPress={onConditions}>
          Мои условия
        </Button>
      </PageHeading>
      <Panel title="Что важно в работе">
        <div className="flex flex-col gap-4">
          {list(profile.life_preferences).length ? (
            <ul>
              {profile.life_preferences.map((preference, index) => (
                <li key={index}>{preference}</li>
              ))}
            </ul>
          ) : (
            <p>
              Расскажите, какую работу вы ищете: график, место, доход и другие
              важные условия.
            </p>
          )}
          {Object.keys(profile.constraints || {}).length ? (
            <DetailAccordion
              title="Условия, уточнённые агентом"
              id="constraints"
            >
              <dl className="grid gap-3">
                {Object.entries(profile.constraints).map(([key, value]) => (
                  <div key={key}>
                    <dt>{conditionLabels[key] || key}</dt>
                    <dd>
                      {typeof value === "boolean"
                        ? value
                          ? "Да"
                          : "Нет"
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
              <AgentButton
                onPress={() =>
                  ask(
                    "search",
                    "Уточни мои условия поиска. Сопоставь мои последние предпочтения с ранее сохранёнными условиями, задай нужные вопросы и обнови профиль.",
                  )
                }
              >
                Поручить уточнение агенту
              </AgentButton>
            </DetailAccordion>
          ) : null}
          <Button variant="outline" size="sm" onPress={onConditions}>
            Уточнить условия
          </Button>
        </div>
      </Panel>
      <div className="flex flex-col gap-4">
        <Panel
          title="Модель агента"
          action={
            <Status value={configured ? "success" : "planned"}>
              {configured ? "Настроена" : "Не подключена"}
            </Status>
          }
        >
          <div className="flex flex-col gap-4">
            <p>
              {configured
                ? `Модель ${state.agent?.connection?.model || ""} настроена. Запуски и доступность сервиса видны в журнале поручений.`
                : "Подключите модель один раз, чтобы агент мог самостоятельно искать, общаться и проверять гипотезы."}
            </p>
            <Button variant="outline" onPress={onModel}>{configured ? "Изменить подключение" : "Подключить модель"}</Button>
          </div>
        </Panel>
      </div>
      <div className="flex flex-col gap-4">
        <Panel title="Данные и подключения">
          <div className="flex flex-col gap-4">
            <PrivateNote />
            <DetailAccordion
              title="Факты, которые использует агент"
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
                <p>Агент ещё не сохранил факты опыта.</p>
              )}
            </DetailAccordion>
            <DetailAccordion title="Технические подключения" id="connections">
              {!list(state.connectors).length ? <p>Дополнительные сервисы пока не подключены. Агент определит, какие нужны для вашей цели, и поможет настроить доступ; если потребуется ваше участие, сообщит об этом.</p> : null}
              {list(state.connectors).map((connector) => (
                <div className="flex flex-col gap-2 py-2" key={connector.name}>
                  <Typography.Heading level={4}>{connector.name}</Typography.Heading>
                  <p>Чтение: {list(connector.read).join(", ") || "—"}</p>
                  <p>Действия: {list(connector.write).join(", ") || "—"}</p>
                  {Object.entries(connector.credentials || {}).map(
                    ([key, value]) => (
                      <p key={key}>
                        {key}: {value.set ? "настроено" : "не настроено"}{" "}
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
