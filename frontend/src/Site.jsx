import { useRef, useState } from "react";
import { Tabs } from "@heroui/react";
import { ArrowDown, ArrowRight, ArrowUpRight, Copy, GitBranch, Code2, Globe2, LockKeyhole, Search, Terminal as TerminalIcon, UserRound, FileText, MessageSquare, Target, Waves } from "lucide-react";
import { BlurFade, NumberTicker } from "./magicui.jsx";
import { ShimmerLink, Terminal, AnimatedSpan, TypingAnimation, TextAnimate, AnimatedShinyText, Marquee, ScrollProgress, AnimatedBeam, OrbitingCircles, MagicCard, WordRotate, LineShadowText } from "./site-magicui.jsx";
import heroImage from "./site-assets/worklife-horizon.jpg";
import manifestoImage from "./site-assets/worklife-coast.jpg";
import jobsScreenshot from "./site-assets/worklife-jobs.png";
import messagesScreenshot from "./site-assets/worklife-messages.png";
import "./site.css";

const github = "https://github.com/dzenlotus/worklife-agent";
const pypiPublished = true;
const installClients = [["codex", "Codex"], ["claude-code", "Claude Code"], ["cursor", "Cursor"], ["opencode", "OpenCode"], ["generic", "Другой MCP-клиент"]];
const firstGoal = "Помоги найти работу. Разберись в моём опыте, уточни условия и займись поиском работодателей, резюме и перепиской.";
const questions = [
  ["С чего начать?", "Расскажите агенту, чем занимались и какую работу хотите. Он уточнит недостающее, разберётся в вашем опыте и предложит план поиска."],
  ["Нужно самому готовить резюме и отклики?", "Это работа агента. Он подготовит резюме из ваших реальных навыков и опыта, адаптирует отклики под компании и будет вести переписку в рамках вашего поручения."],
  ["А настройка и локальное приложение?", "Поручите их агенту: он проверит окружение, подготовит подключение и запустит приложение, когда оно понадобится. Если потребуется ваш вход или разрешение, он объяснит конкретный шаг."],
  ["Что остаётся за мной?", "Рассказать о себе, задать условия поиска и предоставить нужные доступы. Вы выбираете, с кем разговаривать и какое предложение принять. Рутину ведёт агент."],
];
const screenshots = [
  { id: "jobs", label: "Вакансии", image: jobsScreenshot, alt: "Worklife: четыре вымышленные вакансии с зарплатами, этапами поиска и основаниями подбора.", caption: "Карточки компаний, зарплаты и основания подбора — рядом с текущим этапом поиска." },
  { id: "messages", label: "Переписка", image: messagesScreenshot, alt: "Worklife: непрочитанные сообщения от вымышленных работодателей с отправителями, темами и текстом.", caption: "Входящие собраны отдельно: видны отправитель, тема, содержание и отметка прочтения." },
];
const principles = [
  ["Человек в центре.", "Поиск начинается с ваших способностей, интересов и жизненных условий. Задача — найти достойное применение вашему опыту и получать за него деньги."],
  ["Ваш опыт шире названия должности.", "Работа, учёба, свои проекты, забота о близких, смена профессии. За каждой историей могут стоять полезные навыки. Их нужно увидеть и понять, кому они нужны."],
  ["Вы предлагаете профессиональные услуги.", "У вас есть знания, время и способность решать задачи. Вы предлагаете эту работу за деньги и имеете право обсуждать стоимость, нагрузку и условия."],
  ["Работодатель тоже проходит отбор.", "У компании есть задачи, у вас — способы их решить. Вы выбираете, кому предложить свои услуги, чьи условия принять и с кем отказаться работать."],
  ["Автоматизация должна работать на обе стороны.", "Компании уже используют ИИ для поиска, отбора резюме и организации интервью. У человека тоже должен быть агент, который ищет подходящих работодателей и представляет его интересы."],
  ["Больше откликов — ещё не стратегия.", "Важны подходящие компании, подтверждённые сильные стороны, содержательные обращения и ответы. Агент помогает делать больше полезной работы: искать шире, уточнять условия, вести переписку и проверять подходы."],
  ["Вы определяете полномочия агента.", "Цели, границы и решения остаются вашими. Агент действует в пределах поручения, сохраняет историю и показывает следующий шаг. Личные CV и переписка не входят в общую базу работодателей."],
  ["Каждый шаг должен давать ясность.", "Что сделано? Где есть ответ? Что стоит изменить? Отказ — повод пересмотреть конкретный подход, а не приговор вашей ценности. Ваш поиск должен становиться понятнее с каждым циклом."],
];
const research = [
  {value:37, suffix:"%", text:"соискателей говорят: откликов больше, ответов меньше", scope:"Международный опрос LinkedIn · январь 2025", href:"https://news.linkedin.com/2025/talent-campaign-b2b-press-release"},
  {value:2, suffix:"×", text:"кандидатов на открытую роль в США по сравнению с весной 2022 года", scope:"Данные LinkedIn · январь 2026", href:"https://news.linkedin.com/2026/LinkedIn-Research-Talent-2026"},
  {value:27, suffix:"%", text:"организаций в исследовании SHRM применяют ИИ в подборе", scope:"Исследование SHRM · апрель 2026", href:"https://www.shrm.org/topics-tools/news/ai-hr-2026-from-hype-to-measured-human-centered-impact"},
];

function Brand({ large = false }) {
  return <span className={large ? "wl-wordmark" : "wl-brand"}>{!large && <Waves aria-hidden="true" />}Worklife<span className="wl-brand-dot">.</span></span>;
}

function HumanCentre() {
  const container = useRef(null), human = useRef(null), agent = useRef(null), employers = useRef(null), evidence = useRef(null);
  return <div className="wl-human-scene" ref={container} role="img" aria-label="Вы и ваш опыт в центре: агент помогает искать работодателей, вести переговоры и сохранять результаты.">
    <div className="wl-orbit-decoration" aria-hidden="true"><OrbitingCircles radius={112} iconSize={30} duration={40}><span><Search /></span><span><FileText /></span><span><MessageSquare /></span></OrbitingCircles></div>
    <div className="wl-human-node wl-human-self" ref={human}><UserRound aria-hidden="true" /><strong>Вы</strong><span>Ваш опыт и условия</span></div>
    <div className="wl-human-node wl-human-agent" ref={agent}><Waves aria-hidden="true" /><strong>Ваш агент</strong></div>
    <div className="wl-human-node wl-human-employers" ref={employers}><Search aria-hidden="true" /><strong>Работодатели</strong></div>
    <div className="wl-human-node wl-human-evidence" ref={evidence}><Target aria-hidden="true" /><strong>Ваш следующий шаг</strong></div>
    <AnimatedBeam containerRef={container} fromRef={human} toRef={agent} reverse curvature={35} />
    <AnimatedBeam containerRef={container} fromRef={human} toRef={employers} curvature={-40} delay={1} />
    <AnimatedBeam containerRef={container} fromRef={human} toRef={evidence} curvature={45} delay={2} />
  </div>;
}

export default function Site() {
  const [copied, setCopied] = useState("");
  const [goalCopyStatus, setGoalCopyStatus] = useState("");
  const [installTarget, setInstallTarget] = useState("codex");
  const installCommand = `uvx --python 3.12 worklife-agent --target ${installTarget}`;
  async function copy(value, message, setFeedback = setCopied) {
    try { await navigator.clipboard.writeText(value); setFeedback(message); }
    catch { setFeedback("Не удалось скопировать автоматически. Выделите и скопируйте текст в блоке."); }
  }
  return <div className="worklife-site" id="top">
    <ScrollProgress />
    <a className="wl-skip" href="#main">К содержанию</a>
    <header className="wl-header wl-container">
      <a href="#top" aria-label="Worklife — начало"><Brand /></a>
      <nav aria-label="Основная навигация">
        <a href="#how">Как это работает</a><a href="#manifesto">Манифест</a>
        <a className="wl-nav-github" href={github} aria-label="Worklife на GitHub"><Code2 aria-hidden="true" /><span>GitHub</span></a>
        <a className="wl-nav-start" href="#start">Подключить <ArrowUpRight aria-hidden="true" /></a>
      </nav>
    </header>
    <main id="main">
      <section className="wl-hero" aria-labelledby="hero-heading">
        <img className="wl-hero-image" src={heroImage} alt="" fetchPriority="high" width="1672" height="941" />
        <div className="wl-hero-shade" />
        <div className="wl-hero-content wl-container">
          <BlurFade delay={0.04}><p className="wl-eyebrow"><span className="wl-live-dot" /><AnimatedShinyText>ИИ-агент на вашей стороне</AnimatedShinyText></p></BlurFade>
          <BlurFade delay={0.12}><h1 id="hero-heading"><Brand large /></h1></BlurFade>
          <TextAnimate as="p" by="line" animation="blurInUp" startOnView={false} delay={0.2} className="wl-hero-heading">{"Сколько ещё\nотказов?"}</TextAnimate>
          <BlurFade delay={0.32}><p className="wl-hero-description">Компании автоматизируют найм. Вы снова заполняете анкеты и ждёте ответа.<br className="wl-desktop-break" /> Пора дать человеку своего агента — и вернуть контроль над поиском.</p></BlurFade>
          <BlurFade delay={0.42} className="wl-hero-actions"><ShimmerLink href="#manifesto">Меняем правила поиска <ArrowUpRight aria-hidden="true" /></ShimmerLink><a className="wl-text-link" href="#start">Подключить Worklife <ArrowRight aria-hidden="true" /></a></BlurFade>
        </div>
        <div className="wl-hero-bottom wl-container"><span>В центре — <WordRotate words={["ваш опыт", "ваши условия", "ваш выбор"]} accessibleLabel="Ваш опыт, ваши условия и ваш выбор" /></span><a href="#story">Почему привычная схема перестала помогать <ArrowDown aria-hidden="true" /></a></div>
      </section>

      <section id="story" className="wl-story wl-container" aria-label="От проблемы к решению">
        {[["01 / Проблема", "Снова отклик.\nСнова тишина.", "Вакансии есть. Вы меняете CV, заполняете те же анкеты, отправляете ещё десяток откликов. Получаете отказ — без понимания, что именно менять."], ["02 / Что это вызывает", "Руки опускаются.\nВы теряете опору.", "Фрустрация, разочарование, чувство безнадёжности. Усилий всё больше, ясности всё меньше. Кажется, что от вас уже ничего не зависит."], ["03 / Что нужно менять", "Саму модель\nпоиска работы.", "Вы предлагаете свой опыт за деньги и выбираете работодателя. Ваш агент помогает искать, сравнивать, вести переписку и проверять стратегии — в ваших интересах."]].map(([label, title, text], index) => <MagicCard as="article" className="wl-story-card" contentClassName="wl-story-card-content" style={{"--magic-card-bg":"#1b2229"}} key={label}><BlurFade inView delay={index * 0.08}><p className="wl-eyebrow">{label}</p><TextAnimate as="h2" by="line" animation="blurInUp">{title}</TextAnimate><p className="wl-story-copy">{text}</p>{index === 2 && <a className="wl-text-link" href="#manifesto">Наш манифест <ArrowDown aria-hidden="true" /></a>}</BlurFade></MagicCard>)}
      </section>

      <section className="wl-market-proof wl-container" aria-labelledby="market-proof-heading">
        <BlurFade inView className="wl-proof-intro"><p className="wl-eyebrow">Это шире одного неудачного отклика</p><TextAnimate as="h2" by="line" animation="blurInUp" id="market-proof-heading">{"Больше откликов.\nМеньше ответов."}</TextAnimate><p>Ниже — данные конкретных исследований, а не оценка вашей ценности или обещание результата.</p></BlurFade>
        <div className="wl-proof-grid">{research.map(item => <div className="wl-proof-item" key={item.href}><p className="wl-proof-number"><NumberTicker value={item.value} /><span>{item.suffix}</span></p><p>{item.text}</p><a href={item.href} target="_blank" rel="noreferrer">{item.scope}<ArrowUpRight aria-hidden="true" /></a></div>)}</div>
      </section>

      <section className="wl-paradigm wl-container" aria-labelledby="paradigm-heading"><BlurFade inView><p className="wl-eyebrow">Парадигма должна измениться</p><h2 id="paradigm-heading">Компаниям помогают системы.<br /><span>Вам нужен свой агент.</span></h2><p>Не больше часов перед формой отклика. Больше полезных действий: найти подходящие компании, увидеть ценность опыта, уточнить условия и сохранить нить разговора.</p><p>Работодатель — другая сторона сделки. Вы тоже выбираете.</p></BlurFade><HumanCentre /></section>
      <div className="wl-experience-strip"><p>Ваш опыт имеет значение в любой сфере.</p><Marquee duration={45} tabIndex={0} aria-label="Сферы профессионального опыта">{["Логистика", "Бухгалтерия", "Ремонт", "Обучение", "Продажи", "Производство", "Разработка", "Забота о людях"].map(item => <span key={item}>{item}<span aria-hidden="true">✦</span></span>)}</Marquee></div>

      <section id="how" className="wl-section wl-container wl-product-gallery" aria-labelledby="how-heading">
        <BlurFade inView className="wl-section-heading wl-gallery-heading"><p className="wl-eyebrow">01 / От поручения к результату</p><h2 id="how-heading">Скажите, что<br /><span>вам подходит.</span></h2><p>Агент ведёт поиск, а приложение показывает результат: вакансии, основания подбора и переписку. Ниже — снимки работающего интерфейса.</p></BlurFade>
        <BlurFade inView delay={0.08} className="wl-demo wl-screenshot-demo">
          <Tabs defaultSelectedKey="jobs" className="wl-example-tabs">
            <Tabs.ListContainer><Tabs.List aria-label="Экраны приложения">{screenshots.map(item => <Tabs.Tab id={item.id} key={item.id}>{item.label}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
            {screenshots.map(item => <Tabs.Panel id={item.id} key={item.id}>
              <figure className="wl-product-shot">
                <a className="wl-screenshot-link" href={item.image} target="_blank" rel="noreferrer" aria-label={`Открыть снимок «${item.label}» в полном размере`}>
                  <img src={item.image} alt={item.alt} width="1440" height="1080" loading="lazy" decoding="async" />
                </a>
                <figcaption><p>{item.caption}</p><a href={item.image} target="_blank" rel="noreferrer">Открыть в полном размере<ArrowUpRight aria-hidden="true" /></a></figcaption>
              </figure>
            </Tabs.Panel>)}
          </Tabs>
          <p className="wl-demo-footer">Компании, вакансии и сообщения в примере вымышлены.</p>
        </BlurFade>
        <div className="wl-capabilities">{[[Search, "Ищет и уточняет", "Вакансии и условия — с источниками и вопросами к работодателю."], [TerminalIcon, "Готовит и помнит", "CV из подтверждённого опыта. Отклики, ответы и следующий шаг — в истории."], [GitBranch, "Проверяет подходы", "Гипотезы, эксперименты и расписания, чтобы двигаться дальше."]].map(([Glyph, title, text], index) => <BlurFade inView delay={index * 0.06} key={title}><Glyph aria-hidden="true" /><h3>{title}</h3><p>{text}</p></BlurFade>)}</div>
      </section>

      <section id="manifesto" className="wl-manifesto" aria-labelledby="manifesto-heading">
        <div className="wl-manifesto-opening wl-container"><p className="wl-eyebrow">Манифест Worklife</p><TextAnimate as="p" by="word" animation="blurInUp" className="wl-manifesto-question">Сколько отказов нужно получить, чтобы начать сомневаться в себе?</TextAnimate><p>Привычная схема предлагает снова переписать резюме, отправить больше откликов и ждать. Но повторять одно и то же всё быстрее — ещё не значит управлять поиском.</p><p>На стороне компаний уже работают базы кандидатов, автоматический отбор и ИИ. Когда человек отвечает на эту систему только своим временем, возникает дисбаланс. Его нельзя исправить одним «идеальным» CV.</p><p className="wl-manifesto-declaration">Пора менять саму схему.<br />Человеку тоже нужен агент на его стороне.</p></div>
        <div className="wl-manifesto-body wl-container">
          <BlurFade inView className="wl-manifesto-intro"><p className="wl-eyebrow">Наши принципы</p><h2 id="manifesto-heading">В центре —<br /><LineShadowText>человек.</LineShadowText></h2><p>Его опыт. Его интересы.<br />Его право выбирать, кому и на каких условиях предлагать свою работу.</p><a className="wl-text-link" href="#start">Вернуть контроль <ArrowRight aria-hidden="true" /></a></BlurFade>
          <div className="wl-principles">{principles.map(([title, text], index) => <BlurFade inView delay={0.04} key={title} className="wl-principle"><span className="wl-index">0{index + 1}</span><div><h3>{title}</h3><p>{text}</p></div></BlurFade>)}</div>
        </div>
        <div className="wl-manifesto-photo"><img src={manifestoImage} alt="Тропа вдоль тихого морского побережья в рассветном тумане" loading="lazy" width="1672" height="941" /><div className="wl-photo-caption wl-container"><span>Ваш опыт имеет ценность.</span><span>Ваш поиск должен работать на вас.</span></div></div>
      </section>

      <section id="network" className="wl-network wl-section wl-container" aria-labelledby="network-heading">
        <BlurFade inView><p className="wl-eyebrow">03 / Знание, которым можно делиться</p><h2 id="network-heading">Ваш опыт полезен.<br /><span>И другим тоже.</span></h2><p className="wl-network-description">Условия, этапы найма, наблюдения о компаниях — с источниками. Общая база работодателей помогает следующему человеку задавать правильные вопросы.</p><a className="wl-text-link" href="https://github.com/dzenlotus/worklife-employers">Общая база работодателей <ArrowUpRight aria-hidden="true" /></a></BlurFade>
        <div className="wl-network-details"><div><Globe2 aria-hidden="true" /><h3>Общее — о работодателях</h3><p>Участники обмениваются подписанными наблюдениями. Подпись подтверждает происхождение записи, а не правдивость содержания.</p></div><div><LockKeyhole aria-hidden="true" /><h3>Личное — в вашем пространстве</h3><p>CV, переписка и результаты поиска не входят в общую базу. Ваш MCP-агент обрабатывает данные поручения по правилам своего поставщика модели.</p></div></div>
      </section>

      <section id="start" className="wl-start wl-container" aria-labelledby="start-heading">
        <BlurFade inView className="wl-start-heading"><p className="wl-eyebrow">Подготовку тоже можно поручить</p><h2 id="start-heading">Агент настроит<br /><span>Worklife.</span></h2><p>Выберите свой AI-клиент и передайте агенту команду. Он подготовит окружение и подключение, чтобы вы могли продолжить в привычном чате.</p>{pypiPublished && <a className="wl-text-link" href="https://pypi.org/project/worklife-agent/">Пакет в PyPI <ArrowUpRight aria-hidden="true" /></a>}</BlurFade>
        <div className="wl-setup-terminal">
          <div className="wl-install-client"><label htmlFor="install-client">Ваш AI-клиент</label><select id="install-client" value={installTarget} onChange={(event) => { setInstallTarget(event.target.value); setCopied(""); }}>{installClients.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div>
          <Terminal key={installTarget} title="worklife / установка" label="uv · PyPI" actions={<button className="wl-terminal-copy" type="button" aria-label="Скопировать команду установки" onClick={() => copy(installCommand, "Команда установки скопирована")}><Copy aria-hidden="true" /><span>Копировать</span></button>}>
            <TypingAnimation duration={18}>{`$ ${installCommand}`}</TypingAnimation>
            <AnimatedSpan className="wl-terminal-comment"># Подготовку выполнит агент</AnimatedSpan>
            <AnimatedSpan className="wl-terminal-plan">→ Установит Worklife</AnimatedSpan>
            <AnimatedSpan className="wl-terminal-plan">→ Подготовит личное рабочее пространство</AnimatedSpan>
            <AnimatedSpan className="wl-terminal-plan">→ Настроит подключение к выбранному клиенту</AnimatedSpan>
          </Terminal>
          <p className="wl-copy-status" role="status" aria-live="polite">{copied}</p>
          <p className="wl-package-state">{pypiPublished ? "Доступно в PyPI · 0.4.1" : "Пакет готовится к публикации в PyPI."}</p>
          <p className="wl-setup-next">Дальше общайтесь с агентом о работе. Подготовку инструментов и ведение поиска он возьмёт на себя.</p>
          <div className="wl-agent-faq" aria-label="Вопросы о работе с агентом">{questions.map(([question, answer]) => <details className="wl-setup-details" key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div>
        </div>
      </section>
      <section id="begin" className="wl-closing wl-container" aria-labelledby="closing-heading">
        <BlurFade inView className="wl-closing-intro"><p className="wl-eyebrow">Начните с разговора</p><h2 id="closing-heading">Расскажите<br /><span>о себе.</span></h2><p className="wl-closing-copy">Чем занимались, что умеете и какая работа вам подходит. Агент уточнит детали и займётся поиском.</p></BlurFade>
        <MagicCard className="wl-delegation-card" contentClassName="wl-delegation-content" style={{"--magic-card-bg":"#202a33"}}><div className="wl-delegation-label"><Waves aria-hidden="true" /><span>Поручение вашему агенту</span></div><blockquote>{firstGoal}</blockquote><button className="wl-copy" type="button" onClick={() => copy(firstGoal, "Поручение скопировано — передайте его своему агенту.", setGoalCopyStatus)}><Copy aria-hidden="true" /> Скопировать поручение</button><p className="wl-goal-copy-status" role="status" aria-live="polite">{goalCopyStatus}</p></MagicCard>
      </section>
    </main>
    <footer className="wl-footer wl-container"><a href="#top" aria-label="Worklife — к началу"><Brand /></a><span>Создан, чтобы быть на вашей стороне.</span><div><a href="#manifesto">Манифест</a><a href={github}>Открытый код <ArrowUpRight aria-hidden="true" /></a></div></footer>
  </div>;
}
