import { useState } from "react";
import { Accordion, Button, Card, Chip, Link, Separator, Surface, Tabs, Typography, Select, ListBox, buttonVariants } from "@heroui/react";
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
const SiteLink = ({ href, children, primary = false }) => <Link href={href} className={buttonVariants({ variant: primary ? "primary" : "outline" })}>{children}</Link>;

export default function Site() {
  const [copied, setCopied] = useState(""), [exampleId, setExampleId] = useState("logistics");
  async function copy(text, message) {
    try { await navigator.clipboard.writeText(text); setCopied(message); }
    catch { setCopied("Выделите и скопируйте текст ниже."); }
  }
  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 p-4 md:p-8">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Link href="#top" aria-label="Worklife — начало">Worklife</Link>
      <nav aria-label="Основная навигация" className="flex items-center gap-4">
        <Link href="#application" className="hidden sm:block">Монитор</Link>
        <Link href="#start">Подключение</Link>
        <Link href={github}>GitHub ↗</Link>
      </nav>
    </header>
    <Separator />
    <main id="top" className="flex flex-col gap-16">
      <section className="flex flex-col gap-10 py-4 lg:flex-row lg:items-start lg:gap-16 md:py-8" aria-labelledby="product-promise">
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <div className="flex max-w-xl flex-col gap-4">
            <Typography.Paragraph size="sm" color="muted">Worklife · MCP-инструменты для поиска работы</Typography.Paragraph>
            <Typography.Heading id="product-promise" level={1}>Поиск работы в вашем привычном чате.</Typography.Heading>
            <Typography.Paragraph>Поручите агенту найти вакансии, подготовить CV и вести отклики. Worklife даёт ему инструменты, а вам — возможность видеть, что сделано и что найдено.</Typography.Paragraph>
          </div>
          <div className="flex flex-wrap gap-3">
            <SiteLink href="#start" primary>Подключить к агенту</SiteLink>
            <SiteLink href="#application">Посмотреть монитор</SiteLink>
          </div>
          <Typography.Paragraph size="sm" color="muted">Локальный Python MCP-сервер. Модель и диалог — в вашем агенте.</Typography.Paragraph>
        </div>
        <aside className="flex w-full flex-col gap-5 lg:w-80 lg:shrink-0" aria-label="Как работает Worklife">
          <Typography.Paragraph size="sm" color="muted">От поручения к результату</Typography.Paragraph>
          <ol className="flex flex-col gap-5">
            <li className="flex flex-col gap-5">
              <div className="flex gap-4"><Typography.Paragraph size="sm" color="muted">01</Typography.Paragraph><div className="flex flex-col gap-1"><Typography.Paragraph weight="semibold">Вы задаёте условия</Typography.Paragraph><Typography.Paragraph size="sm" color="muted">В чате агента: роль, зарплата, график и важные ограничения.</Typography.Paragraph></div></div>
              <Separator />
            </li>
            <li className="flex flex-col gap-5">
              <div className="flex gap-4"><Typography.Paragraph size="sm" color="muted">02</Typography.Paragraph><div className="flex flex-col gap-1"><Typography.Paragraph weight="semibold">Агент использует Worklife</Typography.Paragraph><Typography.Paragraph size="sm" color="muted">Ищет вакансии, работает с CV, сохраняет результаты и отклики.</Typography.Paragraph></div></div>
              <Separator />
            </li>
            <li className="flex gap-4">
              <Typography.Paragraph size="sm" color="muted">03</Typography.Paragraph>
              <div className="flex flex-col gap-1"><Typography.Paragraph weight="semibold">Вы видите ход работы</Typography.Paragraph><Typography.Paragraph size="sm" color="muted">В браузере — реальные вызовы инструментов и полученные данные.</Typography.Paragraph></div>
            </li>
          </ol>
        </aside>
      </section>

      <section id="application" className="flex flex-col gap-6" aria-labelledby="preview-heading">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex max-w-2xl flex-col gap-2"><Typography.Heading id="preview-heading" level={2}>Проверьте, что сделал агент.</Typography.Heading><Typography.Paragraph color="muted">Монитор собирает действия, вакансии и неизвестные условия в одном месте.</Typography.Paragraph></div>
        </div>
        <Card>
          <Card.Header className="flex flex-row flex-wrap items-center justify-between gap-3">
            <Card.Title>Worklife / Монитор</Card.Title>
            <Chip size="sm" variant="soft">Все данные вымышлены</Chip>
          </Card.Header>
          <Card.Content className="flex flex-col gap-4">
            <div className="sm:hidden"><Select aria-label="Пример профессии" value={exampleId} onChange={(value) => { if (typeof value === "string") setExampleId(value); }}><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>{examples.map((example) => <ListBox.Item id={example.id} key={example.id} textValue={example.label}>{example.label}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover></Select></div>
            <Tabs selectedKey={exampleId} onSelectionChange={setExampleId}>
              <Tabs.ListContainer className="hidden sm:block"><Tabs.List aria-label="Пример профессии">{examples.map((example) => <Tabs.Tab id={example.id} key={example.id}>{example.label}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
              {examples.map((example) => <Tabs.Panel id={example.id} key={example.id}>
                <div className="flex flex-col gap-6 py-4">
                  <Surface variant="secondary" className="flex flex-col gap-2 p-4">
                    <Typography.Paragraph size="sm" color="muted">Поручение в чате агента</Typography.Paragraph>
                    <Typography.Paragraph>{example.goal}</Typography.Paragraph>
                  </Surface>
                  <div className="flex flex-col gap-6 lg:flex-row lg:gap-8">
                    <div className="flex w-full flex-col gap-5 lg:w-64 lg:shrink-0">
                      <Typography.Paragraph weight="semibold">Действия агента</Typography.Paragraph>
                      <div className="flex flex-col gap-2"><div className="flex flex-wrap items-center justify-between gap-2"><Typography.Code>jobs_search</Typography.Code><Chip size="sm" color="success" variant="soft">Завершён</Chip></div><Typography.Paragraph size="sm" color="muted">Проверен подключённый источник вакансий.</Typography.Paragraph></div>
                      <Separator />
                      <div className="flex flex-col gap-2"><div className="flex flex-wrap items-center justify-between gap-2"><Typography.Code>job_save</Typography.Code><Chip size="sm" color="success" variant="soft">Завершён</Chip></div><Typography.Paragraph size="sm" color="muted">Варианты сохранены вместе с известными условиями.</Typography.Paragraph></div>
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-4">
                      <Typography.Paragraph weight="semibold">Найденные вакансии</Typography.Paragraph>
                      <DataTable headers={["Вакансия", "Условия и неизвестное", "Состояние"]} rows={example.jobs.map(([role, company, reason, status]) => [<div className="flex flex-col gap-1"><Typography.Paragraph weight="medium">{role}</Typography.Paragraph><Typography.Paragraph size="sm" color="muted">{company}</Typography.Paragraph></div>, reason, <Chip size="sm">{status}</Chip>])} />
                    </div>
                  </div>
                </div>
              </Tabs.Panel>)}
            </Tabs>
          </Card.Content>
          <Card.Footer><Typography.Paragraph size="sm" color="muted">Образец интерфейса. Неизвестные условия остаются вопросами.</Typography.Paragraph></Card.Footer>
        </Card>
      </section>

      <Separator />
      <section id="start" className="flex flex-col gap-8 lg:flex-row lg:gap-16" aria-labelledby="start-heading">
        <div className="flex w-full flex-col gap-4 lg:w-80 lg:shrink-0">
          <Typography.Heading id="start-heading" level={2}>Подключите один раз. Продолжайте в чате.</Typography.Heading>
          <Typography.Paragraph color="muted">Нужны компьютер, Python 3.12+, uv и MCP-клиент с поддержкой локального stdio-сервера.</Typography.Paragraph>
          <Typography.Paragraph size="sm" color="muted">Отдельная модель или API-ключ для Worklife не требуются: агент использует своё подключение.</Typography.Paragraph>
          <div><Link href={`${github}#подключить-к-агенту`}>Документация MCP ↗</Link></div>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-6">
          <ol className="flex flex-col gap-8">
            <li className="flex flex-col gap-3">
              <Typography.Paragraph weight="semibold">1. Установите проект</Typography.Paragraph>
              <div className="flex flex-wrap gap-4"><Link href="https://git-scm.com/downloads" target="_blank" rel="noreferrer">Git ↗</Link><Link href="https://docs.astral.sh/uv/getting-started/installation/" target="_blank" rel="noreferrer">Установка uv ↗</Link><Link href="https://docs.astral.sh/uv/guides/install-python/" target="_blank" rel="noreferrer">Python через uv ↗</Link></div>
              <Accordion><Accordion.Item id="installation"><Accordion.Heading><Accordion.Trigger>Команды установки с нуля<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex min-w-0 flex-col gap-4"><Typography.Paragraph size="sm" color="muted">Выполните в терминале. Команды копирования показаны для macOS/Linux; на Windows создайте копии двух файлов конфигурации.</Typography.Paragraph><Typography.Prose><pre>{setupCommands.join("\n")}</pre></Typography.Prose><div><Button variant="secondary" size="sm" onPress={() => copy(setupCommands.join("\n"), "Команды установки скопированы")}>Скопировать команды</Button></div></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
            </li>
            <li className="flex flex-col gap-3">
              <Typography.Paragraph weight="semibold">2. Добавьте локальный MCP-сервер</Typography.Paragraph>
              <Typography.Paragraph>В настройках MCP вашего агента укажите запуск Worklife через stdio. Из папки проекта команда выглядит так:</Typography.Paragraph>
              <Typography.Prose><pre>{mcpCommand}</pre></Typography.Prose>
              <Accordion><Accordion.Item id="mcp-config"><Accordion.Heading><Accordion.Trigger>JSON для совместимого MCP-клиента<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex min-w-0 flex-col gap-4"><Typography.Paragraph size="sm" color="muted">Замените /absolute/path/to/worklife-agent на полный путь к проекту. Конкретный формат настроек зависит от вашего MCP-клиента.</Typography.Paragraph><Typography.Prose><pre>{mcpConfig}</pre></Typography.Prose><div className="flex flex-wrap items-center gap-4"><Button variant="secondary" size="sm" onPress={() => copy(mcpConfig, "Пример MCP-конфигурации скопирован")}>Скопировать JSON</Button><Link href={`${github}/blob/main/examples/mcp.json`}>Файл примера ↗</Link></div></div></Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
            </li>
            <li className="flex flex-col gap-3">
              <Typography.Paragraph weight="semibold">3. Дайте поручение в чате</Typography.Paragraph>
              <Typography.Paragraph>Попросите агента начать с <Typography.Code>agent_brief</Typography.Code>, уточнить ваши условия и использовать Worklife для поиска. Аккаунты и доступ к внешним источникам настраиваются по мере необходимости.</Typography.Paragraph>
            </li>
          </ol>
          {copied ? <p role="status">{copied}</p> : null}
        </div>
      </section>

      <Separator />
      <section className="flex flex-col gap-8 lg:flex-row lg:gap-16" aria-labelledby="details-heading">
        <div className="flex w-full flex-col gap-3 lg:w-80 lg:shrink-0"><Typography.Heading id="details-heading" level={3}>Полезно знать до начала</Typography.Heading><Typography.Paragraph size="sm" color="muted">Модель, данные и запуск локального монитора.</Typography.Paragraph></div>
        <div className="min-w-0 flex-1">
          <Accordion>
            <Accordion.Item id="model-and-cost"><Accordion.Heading><Accordion.Trigger>Где выбрать модель и сколько это стоит?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph>Модель выбирается в вашем агенте; расходы зависят от его клиента и поставщика. Дополнительные источники могут требовать своих аккаунтов и ключей. Worklife не подключает платный сервис автоматически.</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item>
            <Accordion.Item id="personal-data"><Accordion.Heading><Accordion.Trigger>Где хранятся CV и личные результаты?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph>CV и личные результаты хранятся локально, но MCP-агент получает данные, нужные для поручения, и использует их по правилам своего поставщика модели.</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item>
            <Accordion.Item id="shared-data"><Accordion.Heading><Accordion.Trigger>Что попадает в общую базу?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><Typography.Paragraph>Только наблюдения о работодателях с источниками. Подпись защищает запись от подмены, а не подтверждает её правдивость.</Typography.Paragraph></Accordion.Body></Accordion.Panel></Accordion.Item>
            <Accordion.Item id="monitor-start"><Accordion.Heading><Accordion.Trigger>Как открыть локальный монитор?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex min-w-0 flex-col gap-3"><Typography.Paragraph>Запустите монитор с тем же config.toml, который использует MCP-сервер.</Typography.Paragraph><Typography.Prose><pre>{monitorCommand}</pre></Typography.Prose><Link href="http://127.0.0.1:8877/">Открыть 127.0.0.1:8877 ↗</Link></div></Accordion.Body></Accordion.Panel></Accordion.Item>
          </Accordion>
        </div>
      </section>
    </main>
    <Separator />
    <footer className="flex flex-wrap items-center justify-between gap-4 py-4"><Typography.Paragraph size="sm" color="muted">Worklife · локальные инструменты для вашего агента</Typography.Paragraph><Link href={github}>Открытый код и документация ↗</Link></footer>
  </div>;
}
