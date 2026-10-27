import { useState } from "react";
import { Button, Card, Chip, Link, Separator, Tabs, Typography } from "@heroui/react";
import { DataTable } from "./ui.jsx";

const github = "https://github.com/dzenlotus/worklife-agent";
const launchCommand = "uv run --env-file .env worklife --config config.toml app";
const demoJobs = [
  { role: "Backend-разработчик", company: "Демонстрационная компания", state: "Новая", group: "new" },
  { role: "Fullstack-разработчик", company: "Демонстрационная компания", state: "В работе", group: "active" },
  { role: "Инженер данных", company: "Демонстрационная компания", state: "Ответ получен", group: "reply" },
];
const views = [["all", "Все"], ["active", "В работе"], ["reply", "Ответ получен"]];
const SiteLink = ({ href, children, primary = false }) => <Button variant={primary ? "primary" : "outline"} render={(props) => <a {...props} href={href} />}>{children}</Button>;

export default function Site() {
  const [copied, setCopied] = useState("");
  async function copyCommand() {
    try { await navigator.clipboard.writeText(launchCommand); setCopied("Команда скопирована"); }
    catch { setCopied("Выделите и скопируйте команду ниже."); }
  }
  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 p-4 md:p-8">
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Link href="#top">Worklife</Link>
      <nav aria-label="Основная навигация" className="flex flex-wrap gap-4">
        <Link href="#possibilities">Возможности</Link><Link href="#application">Приложение</Link><Link href="#employers">База работодателей</Link>
      </nav>
      <SiteLink href={github}>GitHub</SiteLink>
    </header>
    <Separator />
    <main id="top" className="flex flex-col gap-8">
      <section id="possibilities" className="flex flex-col gap-4">
        <Typography.Heading level={1}>Worklife — агент поиска работы</Typography.Heading>
        <p>Задайте цель и условия. Агент выбирает источники, изучает вакансии и сохраняет ход работы.</p>
        <div className="flex flex-wrap gap-3"><SiteLink href="#start" primary>Запустить локально</SiteLink><SiteLink href={github}>Открыть проект</SiteLink></div>
      </section>
      <section id="application" className="flex flex-col gap-4" aria-label="Демонстрация Worklife">
        <div className="flex flex-wrap items-center gap-3"><Typography.Heading level={2}>Поручения и результаты</Typography.Heading><Chip>Демонстрационные данные</Chip></div>
        <Card><Card.Header><Card.Title>Пример цели</Card.Title></Card.Header><Card.Content><p>Backend / Python, удалённо, от 250 000 ₽, без длинных тестовых.</p></Card.Content></Card>
        <Card><Card.Header><Card.Title>Пример списка вакансий</Card.Title></Card.Header><Card.Content>
          <Tabs defaultSelectedKey="all">
            <Tabs.ListContainer><Tabs.List aria-label="Фильтр демонстрационных вакансий">{views.map(([id, text]) => <Tabs.Tab id={id} key={id}>{text}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
            {views.map(([id]) => <Tabs.Panel id={id} key={id}><DataTable headers={["Вакансия", "Компания", "Состояние"]} rows={demoJobs.filter((job) => id === "all" || job.group === id).map((job) => [job.role, job.company, <Chip size="sm" key={job.role}>{job.state}</Chip>])} /></Tabs.Panel>)}
          </Tabs>
        </Card.Content></Card>
        <p>Это примеры интерфейса. В локальном приложении отображаются только ваши сохранённые данные и фактические действия.</p>
      </section>
      <section className="grid gap-4 md:grid-cols-3" aria-label="Возможности агента">
        {[['Поиск', 'Агрегаторы вакансий, карьерные сайты компаний и другие подходящие источники.'], ['Процесс', 'Аккаунты, подтверждения почты, резюме и следующие действия в рамках ваших поручений.'], ['Эксперименты', 'Сравнение вариантов CV и тактик по сохранённым фактическим результатам.']].map(([title, description]) => <Card key={title}><Card.Header><Card.Title>{title}</Card.Title></Card.Header><Card.Content><p>{description}</p></Card.Content></Card>)}
      </section>
      <section id="employers" className="flex flex-col gap-4">
        <Typography.Heading level={2}>Общая база работодателей</Typography.Heading>
        <p>В общей базе — компании, вакансии, условия и наблюдения с источниками. Подпись защищает запись от подмены и не подтверждает правдивость её содержания.</p>
        <p>CV, личная статистика, эксперименты, сильные стороны и анализ репозиториев хранятся локально. Профили работников, имена и контакты людей не публикуются.</p>
      </section>
      <Card id="start"><Card.Header><Card.Title>Запустить на своём компьютере</Card.Title></Card.Header><Card.Content className="flex flex-col gap-4">
        <p>Установите проект, откройте локальное приложение и подключите модель. Инструкция описывает необходимые настройки.</p>
        <div className="overflow-x-auto"><code>{launchCommand}</code></div>
        <div className="flex flex-wrap gap-3"><Button variant="secondary" onPress={copyCommand}>Скопировать команду</Button><SiteLink href={`${github}#быстрый-запуск`}>Инструкция на GitHub</SiteLink></div>
        {copied ? <p role="status">{copied}</p> : null}
      </Card.Content></Card>
    </main>
    <Separator />
    <footer className="flex flex-wrap justify-between gap-4"><p>Worklife</p><Link href={github}>Открытый код</Link></footer>
  </div>;
}
