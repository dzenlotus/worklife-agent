import { useState } from "react";
import { Accordion, Button, Card, Chip, Link, Separator, Tabs, Typography, Select, ListBox } from "@heroui/react";
import { DataTable } from "./ui.jsx";

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
const SiteLink = ({ href, children, primary = false }) => <Button variant={primary ? "primary" : "outline"} render={(props) => <a {...props} href={href} />}>{children}</Button>;

export default function Site() {
  const [copied, setCopied] = useState(""), [exampleId, setExampleId] = useState("logistics");
  async function copy(text, message) {
    try { await navigator.clipboard.writeText(text); setCopied(message); }
    catch { setCopied("Выделите и скопируйте текст ниже."); }
  }
  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 p-4 md:p-8">
    <header className="flex items-center justify-between gap-4"><Link href="#top" aria-label="Worklife — начало">Worklife</Link><nav aria-label="Основная навигация" className="flex items-center gap-4"><Link href="#application" className="hidden sm:block">Монитор</Link><Link href="#start">Подключение</Link><Link href={github}>GitHub ↗</Link></nav></header>
    <Separator />
    <main id="top" className="flex flex-col gap-12">
      <section className="flex flex-col gap-6 py-4 md:py-8" aria-labelledby="product-name">
        <div className="flex max-w-3xl flex-col gap-4"><Typography.Heading id="product-name" level={1}>Worklife</Typography.Heading><Typography.Heading level={2}>MCP-инструменты для поиска работы через вашего агента</Typography.Heading><Typography.Paragraph>Обсуждайте цели в привычном чате. Агент использует Worklife для поиска вакансий, работы с CV и ведения откликов. Браузер показывает фактические действия и результаты.</Typography.Paragraph></div>
        <div className="flex flex-wrap gap-3"><SiteLink href="#start" primary>Подключить к агенту</SiteLink><SiteLink href="#application">Посмотреть монитор</SiteLink></div>
        <Typography.Paragraph size="sm" color="muted">Локальный MCP-сервер. Модель и диалог остаются в вашем агенте.</Typography.Paragraph>
      </section>

      <section id="application" className="flex flex-col gap-4" aria-label="Пример монитора Worklife">
        <div className="flex flex-col gap-2"><Typography.Heading level={2}>В чате — поручение. В мониторе — ход работы.</Typography.Heading><Typography.Paragraph color="muted">Пример интерфейса: все вызовы, компании и вакансии ниже вымышлены.</Typography.Paragraph></div>
        <Card><Card.Header className="flex flex-row flex-wrap items-center justify-between gap-3"><Card.Title>Монитор Worklife</Card.Title><Chip size="sm">Демонстрация</Chip></Card.Header><Card.Content>
          <div className="sm:hidden"><Select aria-label="Пример профессии" value={exampleId} onChange={(value) => { if (typeof value === "string") setExampleId(value); }}><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>{examples.map((example) => <ListBox.Item id={example.id} key={example.id} textValue={example.label}>{example.label}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover></Select></div>
          <Tabs selectedKey={exampleId} onSelectionChange={setExampleId}><Tabs.ListContainer className="hidden sm:block"><Tabs.List aria-label="Пример профессии">{examples.map((example) => <Tabs.Tab id={example.id} key={example.id}>{example.label}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>{examples.map((example) => <Tabs.Panel id={example.id} key={example.id}><div className="flex flex-col gap-6 py-4">
            <div className="flex max-w-3xl flex-col gap-2"><Typography.Paragraph size="sm" color="muted">Поручение в чате агента</Typography.Paragraph><Typography.Paragraph>{example.goal}</Typography.Paragraph></div><Separator />
            <DataTable headers={["Вызов MCP", "Что произошло", "Состояние"]} rows={[[<Typography.Code>jobs_search</Typography.Code>, "Проверен подключённый источник вакансий", <Chip size="sm" color="success" variant="soft">Завершён</Chip>], [<Typography.Code>job_save</Typography.Code>, "Варианты сохранены вместе с известными условиями", <Chip size="sm" color="success" variant="soft">Завершён</Chip>]]} />
            <DataTable headers={["Вакансия", "Условия и неизвестное", "Состояние"]} rows={example.jobs.map(([role, company, reason, status]) => [<div className="flex flex-col gap-2"><strong>{role}</strong><Typography.Paragraph size="sm" color="muted">{company}</Typography.Paragraph></div>, reason, <Chip size="sm">{status}</Chip>])} />
          </div></Tabs.Panel>)}</Tabs>
        </Card.Content><Card.Footer><Typography.Paragraph size="sm" color="muted">Неизвестные условия остаются вопросами.</Typography.Paragraph></Card.Footer></Card>
      </section>


      <Separator />
      <section id="start" className="flex flex-col gap-6" aria-labelledby="start-heading">
        <div className="flex max-w-3xl flex-col gap-3"><Typography.Heading id="start-heading" level={2}>Подключить Worklife к вашему агенту</Typography.Heading><Typography.Paragraph>Нужны компьютер, Python 3.12+, uv и MCP-клиент с поддержкой локального stdio-сервера. Отдельная модель или API-ключ для Worklife не требуются: агент использует своё подключение.</Typography.Paragraph></div>
        <ol className="flex flex-col gap-6">
          <li className="flex flex-col gap-3"><Typography.Heading level={3}>1. Установите проект</Typography.Heading><div className="flex flex-wrap gap-4"><Link href="https://git-scm.com/downloads" target="_blank" rel="noreferrer">Git ↗</Link><Link href="https://docs.astral.sh/uv/getting-started/installation/" target="_blank" rel="noreferrer">Установка uv ↗</Link><Link href="https://docs.astral.sh/uv/guides/install-python/" target="_blank" rel="noreferrer">Python через uv ↗</Link></div><Accordion><Accordion.Item id="installation"><Accordion.Heading><Accordion.Trigger>Команды установки с нуля<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex flex-col gap-4"><Typography.Paragraph size="sm" color="muted">Выполните в терминале. Команды копирования показаны для macOS/Linux; на Windows создайте копии двух файлов конфигурации.</Typography.Paragraph><div className="overflow-x-auto"><pre>{setupCommands.join("\n")}</pre></div><div><Button variant="secondary" size="sm" onPress={() => copy(setupCommands.join("\n"), "Команды установки скопированы")}>Скопировать команды</Button></div></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion></li>
          <li className="flex flex-col gap-3"><Typography.Heading level={3}>2. Добавьте локальный MCP-сервер</Typography.Heading><Typography.Paragraph>В настройках MCP вашего агента укажите запуск Worklife через stdio. Из папки проекта команда выглядит так:</Typography.Paragraph><div className="overflow-x-auto"><pre>{mcpCommand}</pre></div><Accordion><Accordion.Item id="mcp-config"><Accordion.Heading><Accordion.Trigger>Пример JSON для совместимого MCP-клиента<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex flex-col gap-4"><Typography.Paragraph size="sm" color="muted">Замените /absolute/path/to/worklife-agent на полный путь к проекту. Конкретный формат настроек зависит от вашего MCP-клиента.</Typography.Paragraph><div className="overflow-x-auto"><pre>{mcpConfig}</pre></div><div><Button variant="secondary" size="sm" onPress={() => copy(mcpConfig, "Пример MCP-конфигурации скопирован")}>Скопировать JSON</Button></div></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion></li>
          <li className="flex flex-col gap-3"><Typography.Heading level={3}>3. Дайте поручение в чате</Typography.Heading><Typography.Paragraph>Попросите агента начать с agent_brief, уточнить ваши условия и использовать Worklife для поиска. Аккаунты и доступ к внешним источникам настраиваются по мере необходимости.</Typography.Paragraph></li>
        </ol>
        {copied ? <p role="status">{copied}</p> : null}
        <div className="flex flex-wrap gap-3"><SiteLink href={`${github}#подключить-к-агенту`}>Документация MCP на GitHub</SiteLink><Link href={`${github}/blob/main/examples/mcp.json`}>Пример конфигурации ↗</Link></div>
      </section>

      <section className="flex flex-col gap-4" aria-labelledby="monitor-heading"><Typography.Heading id="monitor-heading" level={2}>Локальный монитор</Typography.Heading><Accordion><Accordion.Item id="monitor-start"><Accordion.Heading><Accordion.Trigger>Открыть локальный монитор<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex flex-col gap-3"><Typography.Paragraph>Запустите монитор с тем же config.toml, который использует MCP-сервер.</Typography.Paragraph><div className="overflow-x-auto"><pre>{monitorCommand}</pre></div><Link href="http://127.0.0.1:8877/">Открыть 127.0.0.1:8877 ↗</Link></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion></section>
      <section className="flex flex-col gap-4"><Typography.Heading level={2}>Модель, расходы и общая база</Typography.Heading><Typography.Paragraph>Модель выбирается в вашем агенте; расходы зависят от его клиента и поставщика. Дополнительные источники могут требовать своих аккаунтов и ключей. Worklife не подключает платный сервис автоматически.</Typography.Paragraph><Typography.Paragraph color="muted">CV и личные результаты хранятся локально, но MCP-агент получает данные, нужные для поручения, и использует их по правилам своего поставщика модели. В общей базе — только наблюдения о работодателях с источниками. Подпись защищает запись от подмены, а не подтверждает её правдивость.</Typography.Paragraph></section>
      <div><SiteLink href="#start" primary>Подключить к агенту</SiteLink></div>
    </main>
    <Separator /><footer className="flex flex-wrap justify-between gap-4"><p>Worklife</p><Link href={github}>Открытый код и документация ↗</Link></footer>
  </div>;
}
