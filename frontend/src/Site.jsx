import { useState } from "react";
import { Accordion, Button, Card, Chip, Link, Separator, Tabs, Typography, buttonVariants } from "@heroui/react";
import { typographyVariants } from "@heroui/styles";
import { Icon } from "./ui.jsx";

const github = "https://github.com/dzenlotus/worklife-agent";
const mcpCommand = "uv run --env-file .env worklife --config config.toml mcp";
const monitorCommand = "uv run --env-file .env worklife --config config.toml app";
const setupCommands = ["git clone https://github.com/dzenlotus/worklife-agent.git", "cd worklife-agent", "uv sync --extra dev --extra browser", "uv run playwright install chromium", "cp config.example.toml config.toml", "cp .env.example .env", "uv run --env-file .env worklife --config config.toml init"];
const mcpConfig = JSON.stringify({ mcpServers: { worklife: { command: "uv", args: ["run", "--directory", "/absolute/path/to/worklife-agent", "--env-file", "/absolute/path/to/worklife-agent/.env", "worklife", "--config", "/absolute/path/to/worklife-agent/config.toml", "mcp"] } } }, null, 2);
const examples = [
  { id: "logistics", label: "Логистика", goal: "Найди работу руководителем в логистике, от 180 000 ₽, без переезда. Выясни график и размер команды.", jobs: [["Руководитель отдела логистики", "Пример: Север", "От 180 000 ₽, нужный город. График ещё нужно уточнить.", "Новая"], ["Менеджер цепей поставок", "Пример: Маршрут", "От 200 000 ₽. Размер команды пока неизвестен.", "Сохранена"]] },
  { id: "marketing", label: "Маркетинг", goal: "Найди удалённую работу в контент-маркетинге, от 120 000 ₽. Без неоплачиваемого тестового дольше двух часов.", jobs: [["Контент-маркетолог", "Пример: Студия", "Удалённо, от 120 000 ₽. Объём тестового пока неизвестен.", "Новая"], ["Редактор бренд-медиа", "Пример: Редакция", "Удалённо, от 140 000 ₽. Условия тестового уточняются.", "Сохранена"]] },
  { id: "accounting", label: "Бухгалтерия", goal: "Найди работу бухгалтером на полный день, от 100 000 ₽, с гибридным графиком. Проверь условия в объявлении.", jobs: [["Бухгалтер", "Пример: Баланс", "Гибрид, от 100 000 ₽. Указанные условия соответствуют цели.", "Новая"], ["Ведущий бухгалтер", "Пример: Контур", "От 130 000 ₽. Число дней в офисе нужно подтвердить.", "Сохранена"]] },
];
const SiteLink = ({ href, children, primary = false }) => <Link href={href} className={buttonVariants({ variant: primary ? "primary" : "outline" })}>{children}</Link>;

export default function Site() {
  const [copied, setCopied] = useState(""), [exampleId, setExampleId] = useState("logistics");
  async function copy(text, message) {
    try { await navigator.clipboard.writeText(text); setCopied(message); }
    catch { setCopied("Выделите и скопируйте текст ниже."); }
  }
  return <div className="mx-auto flex w-full max-w-7xl flex-col gap-12 p-5 md:p-8 lg:p-10">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Link href="#top" aria-label="Worklife — начало"><p className={typographyVariants({ type: "h3", weight: "medium" }).base()}>Worklife</p></Link>
      <nav aria-label="Основная навигация" className="flex items-center gap-6">
        <Link href="#network" className="hidden sm:block">Работодатели</Link>
        <Link href="#start">Подключение</Link>
        <Link href={github}>GitHub<Icon name="external" className="size-4 shrink-0" /></Link>
      </nav>
    </header>
    <main id="top" className="flex flex-col gap-16">
      <section className="flex flex-col gap-10 py-4 lg:flex-row lg:items-center lg:gap-16 lg:py-8" aria-labelledby="product-promise">
        <div className="flex w-full flex-col gap-6 lg:w-96 lg:shrink-0">
          <div><Chip variant="soft" size="sm">Инструменты для MCP-агента</Chip></div>
          <Typography.Heading id="product-promise" level={1} weight="medium">Поиск работы.<br />В вашем чате.</Typography.Heading>
          <Typography.Paragraph color="muted">Поручите агенту искать вакансии, готовить CV и вести переписку. Worklife даст ему инструменты, а вам — понятную историю поиска.</Typography.Paragraph>
          <div><SiteLink href="#start" primary>Подключить к агенту</SiteLink></div>
          <Typography.Paragraph size="sm" color="muted">Модель — в вашем агенте. Результаты — под рукой.</Typography.Paragraph>
        </div>
        <div id="application" className="min-w-0 flex-1">
          <Card className="gap-5 p-6">
            <Card.Header className="flex flex-row items-center justify-between gap-3"><h2 className={typographyVariants({ type: "h4", weight: "medium" }).base()}>Результаты поиска</h2><Chip size="sm" variant="soft">Демо</Chip></Card.Header>
            <Separator />
            <Card.Content className="flex flex-col gap-5">
              <Tabs selectedKey={exampleId} onSelectionChange={(key) => setExampleId(String(key))}>
                <Tabs.ListContainer><Tabs.List aria-label="Пример поиска">{examples.map((item) => <Tabs.Tab id={item.id} key={item.id}>{item.label}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
                {examples.map((item) => <Tabs.Panel id={item.id} key={item.id}><div className="flex flex-col gap-4 py-4">
                  <div className="flex flex-col gap-5">{item.jobs.map(([role, company, reason, status], index) => <div key={role} className="flex flex-col gap-5">
                    {index ? <Separator /> : null}
                    <div className="flex items-start justify-between gap-4">
                      <Icon name="search" className="size-6 shrink-0 text-accent" />
                      <div className="flex min-w-0 flex-1 flex-col gap-2"><Typography.Paragraph weight="semibold">{role}</Typography.Paragraph><Typography.Paragraph size="xs" color="muted">{company.replace("Пример: ", "")}</Typography.Paragraph><Typography.Paragraph size="sm" color="muted">{reason}</Typography.Paragraph></div>
                      <Chip size="sm" variant="soft">{status}</Chip>
                    </div>
                  </div>)}</div>
                  <Accordion hideSeparator><Accordion.Item id={`goal-${item.id}`}><Accordion.Heading><Accordion.Trigger>Условия этого поиска<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph size="sm" color="muted">{item.goal}</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
                </div></Tabs.Panel>)}
              </Tabs>
            </Card.Content>
            <Card.Footer><Typography.Paragraph size="xs" color="muted">Компании и вакансии в этом примере вымышлены.</Typography.Paragraph></Card.Footer>
          </Card>
        </div>
      </section>

      <section className="grid gap-8 md:grid-cols-3" aria-label="Возможности">
        {[["Поиск и переписка", "Источники вакансий, отклики и ответы в одной истории."], ["CV на разных языках", "Варианты резюме из ваших подтверждённых фактов и опыта."], ["Гипотезы и результаты", "Эксперименты, статистика и расписания для следующего шага."]].map(([title, text]) => <div className="flex flex-col gap-3" key={title}><h2 className={typographyVariants({ type: "h4", weight: "medium" }).base()}>{title}</h2><Typography.Paragraph size="sm" color="muted">{text}</Typography.Paragraph></div>)}
      </section>
      <Separator />

      <section id="start" className="flex flex-col gap-8 lg:flex-row lg:gap-16" aria-labelledby="start-heading">
        <div className="flex w-full flex-col gap-4 lg:w-80 lg:shrink-0">
          <Typography.Heading id="start-heading" level={2}>Подключение</Typography.Heading>
          <Typography.Paragraph color="muted">Установите Worklife и добавьте его в вашего MCP-агента.</Typography.Paragraph>
          <Typography.Paragraph size="sm" color="muted">Python 3.12+, uv и клиент с поддержкой stdio. Отдельный ключ модели для Worklife не нужен.</Typography.Paragraph>
          <Link href={`${github}#подключить-к-агенту`}>Полная инструкция<Icon name="external" className="size-4 shrink-0" /></Link>
        </div>
        <div className="min-w-0 flex-1"><Card className="gap-5 p-6"><Card.Content className="flex min-w-0 flex-col gap-4">
          <Tabs defaultSelectedKey="install">
            <Tabs.ListContainer><Tabs.List aria-label="Шаги подключения"><Tabs.Tab id="install">1. Установка<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="connect">2. MCP<Tabs.Indicator /></Tabs.Tab><Tabs.Tab id="goal">3. Поручение<Tabs.Indicator /></Tabs.Tab></Tabs.List></Tabs.ListContainer>
            <Tabs.Panel id="install"><div className="flex min-w-0 flex-col gap-4 py-4">
              <div className="flex flex-wrap gap-4"><Link href="https://git-scm.com/downloads" target="_blank" rel="noreferrer">Git<Icon name="external" className="size-4 shrink-0" /></Link><Link href="https://docs.astral.sh/uv/getting-started/installation/" target="_blank" rel="noreferrer">Установить uv<Icon name="external" className="size-4 shrink-0" /></Link></div>
              <Typography.Prose><pre>{setupCommands.join("\n")}</pre></Typography.Prose>
              <Typography.Paragraph size="xs" color="muted">Команды для macOS/Linux. На Windows создайте копии файлов конфигурации вручную.</Typography.Paragraph>
              <div><Button variant="secondary" size="sm" onPress={() => copy(setupCommands.join("\n"), "Команды скопированы")}>Скопировать команды</Button></div>
            </div></Tabs.Panel>
            <Tabs.Panel id="connect"><div className="flex min-w-0 flex-col gap-4 py-4">
              <Typography.Paragraph size="sm" color="muted">Добавьте локальный stdio-сервер в настройках агента. Команда из папки проекта:</Typography.Paragraph>
              <Typography.Prose><pre>{mcpCommand}</pre></Typography.Prose>
              <Accordion><Accordion.Item id="mcp-config"><Accordion.Heading><Accordion.Trigger>JSON конфигурации<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex min-w-0 flex-col gap-4"><Typography.Paragraph size="sm" color="muted">Замените /absolute/path/to/worklife-agent на полный путь к проекту.</Typography.Paragraph><Typography.Prose><pre>{mcpConfig}</pre></Typography.Prose><div><Button variant="secondary" size="sm" onPress={() => copy(mcpConfig, "JSON скопирован")}>Скопировать JSON</Button></div></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
            </div></Tabs.Panel>
            <Tabs.Panel id="goal"><div className="flex flex-col gap-4 py-4">
              <Typography.Paragraph size="sm" color="muted">Дайте поручение в чате вашего агента, например:</Typography.Paragraph>
              <Typography.Paragraph>Используй Worklife для поиска работы. Начни с agent_brief, уточни мои условия, найди подходящие вакансии и сохрани результаты.</Typography.Paragraph>
              <Typography.Paragraph size="sm" color="muted">Доступы к площадкам агент уточнит по мере необходимости.</Typography.Paragraph>
            </div></Tabs.Panel>
          </Tabs>
          {copied ? <Typography.Paragraph size="sm" role="status">{copied}</Typography.Paragraph> : null}
          <Separator />
          <Accordion hideSeparator><Accordion.Item id="monitor-start"><Accordion.Heading><Accordion.Trigger>Открыть локальное приложение<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex min-w-0 flex-col gap-3"><Typography.Paragraph size="sm" color="muted">Запустите с тем же config.toml, что и MCP-сервер.</Typography.Paragraph><Typography.Prose><pre>{monitorCommand}</pre></Typography.Prose><Link href="http://127.0.0.1:8877/">Открыть приложение<Icon name="external" className="size-4 shrink-0" /></Link></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
        </Card.Content></Card></div>
      </section>
      <Separator />

      <section id="network" className="flex flex-col gap-8 lg:flex-row lg:gap-16" aria-labelledby="network-heading">
        <div className="flex w-full flex-col gap-4 lg:w-80 lg:shrink-0"><Typography.Heading id="network-heading" level={2}>Общая база работодателей</Typography.Heading><Link href="https://github.com/dzenlotus/worklife-employers">Открыть общую базу<Icon name="external" className="size-4 shrink-0" /></Link></div>
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          <Typography.Paragraph>Агенты обмениваются наблюдениями о компаниях. Записи подписываются и синхронизируются; каждая копия проверяет их целостность.</Typography.Paragraph>
          <Accordion>
            <Accordion.Item id="shared-data"><Accordion.Heading><Accordion.Trigger>Что хранится в общей базе?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph size="sm">Вакансии, условия и процесс найма с источниками. CV, переписка и личные результаты остаются локальными. Подпись подтверждает происхождение записи, но не правдивость её содержания.</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item>
            <Accordion.Item id="privacy"><Accordion.Heading><Accordion.Trigger>Какие данные получает модель?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph size="sm">Ваш MCP-агент получает данные для поручения и обрабатывает их по правилам своего поставщика модели. Его модель и стоимость выбираются в вашем клиенте.</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item>
          </Accordion>
        </div>
      </section>
    </main>
    <Separator /><footer className="flex flex-wrap items-center justify-between gap-4 pb-4"><Typography.Paragraph size="sm" color="muted">Worklife</Typography.Paragraph><Link href={github}>Код и документация<Icon name="external" className="size-4 shrink-0" /></Link></footer>
  </div>;
}
