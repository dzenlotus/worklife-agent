'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const arr = value => Array.isArray(value) ? value : [];
const pretty = value => JSON.stringify(value, null, 2);
const lines = value => String(value || '').split('\n').map(s => s.trim()).filter(Boolean);
const date = value => { if (!value) return '—'; const d = new Date(value); return Number.isNaN(+d) ? esc(value) : d.toLocaleString('ru', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}); };
const time = value => { const d = new Date(value); return Number.isNaN(+d) ? '—' : d.toLocaleTimeString('ru', {hour:'2-digit',minute:'2-digit'}); };
const url = value => { try { const u = new URL(value); return ['http:','https:'].includes(u.protocol) ? esc(u.href) : ''; } catch { return ''; } };
const iconPaths = {
  overview:'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9', search:'M21 21l-6-6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0', schedules:'M5 5h14a1 1 0 0 1 1 1v15H4V6a1 1 0 0 1 1-1ZM4 10h16M8 3v5M16 3v5', experiments:'M9 3h6M10 3v7L4 20a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1l-6-10V3M8 15h8', strengths:'M12 21S2 15 2 8a5 5 0 0 1 10-1A5 5 0 0 1 22 8c0 7-10 13-10 13Z', cv:'M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8M8 17h6', employers:'M4 21V7h10v14M14 12h6v9M2 21h20M8 3h10v9M8 11h2M8 15h2M8 18h2M17 16h1', resources:'M5 6h14v15H5ZM8 6V3h8v3M8 11h8M8 15h6', accounts:'M20 21v-2a7 7 0 0 0-14 0v2M17 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0', repositories:'M9 4H4v16h5M15 4h5v16h-5M10 8l-4 4 4 4M14 8l4 4-4 4', tactics:'m4 20 16-16M4 4h6M4 4v6M20 20h-6M20 20v-6', settings:'m9 3-1 3-3 1-2 4 2 3 3 1 1 3h5l1-3 3-1 2-3-2-4-3-1-1-3ZM15 11a3 3 0 1 1-6 0 3 3 0 0 1 6 0', clock:'M12 7v5l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', activity:'m5 12 4 4L19 6', lock:'M6 10h12v11H6ZM8 10V7a4 4 0 1 1 8 0v3M12 14v3', agent:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPaths[name] || iconPaths.activity}"/></svg>`;
const pages = [['overview','Обзор'],['search','Поиск'],['schedules','Расписание'],['experiments','Эксперименты'],['strengths','Сильные стороны'],['cv','CV'],['employers','Работодатели'],['resources','Ресурсы'],['accounts','Аккаунты'],['repositories','Репозитории'],['tactics','Тактики'],['settings','Настройки']];
const stageLabels = {saved:'Сохранена',applied:'Отклик отправлен',reply:'Ответ получен',interview:'Интервью',offer:'Предложение',accepted:'Принято',rejected:'Отказ',withdrawn:'Снята',draft:'Черновик',approved:'Разрешено',sent:'Отправлено',cancelled:'Отменено',uncertain:'Нужна проверка',sending:'Отправляется',failed:'Ошибка',active:'Активен',planned:'Запланировано',proposed:'Предложено',verified:'Подтверждено',registered:'Зарегистрирован',done:'Выполнено',open:'Открыто',completed:'Завершён',running:'Работает',disabled:'Отключено',enabled:'Включено',insufficient_data:'Недостаточно данных',descriptive_only:'Результат наблюдения'};
const label = value => stageLabels[value] || value || '—';
const badge = (value, text) => `<span class="badge ${['reply','offer','approved','running','enabled'].includes(value)?'amber':['accepted','sent','done','verified','completed'].includes(value)?'green':['rejected','failed','uncertain'].includes(value)?'red':['cancelled','withdrawn','disabled'].includes(value)?'muted':''}">${esc(text || label(value))}</span>`;
const button = (text, action, id = '', primary = false) => `<button type="button" class="button ${primary?'primary':''}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(text)}</button>`;
const small = (text, action, id = '') => `<button type="button" class="button small" data-action="${esc(action)}" data-id="${esc(id)}">${esc(text)}</button>`;
const heading = (title, description, actions = '') => `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(description)}</p></div><div class="heading-actions">${actions}</div></div>`;
const empty = (name, title, description, action = '') => `<div class="empty-state">${icon(name)}<h2>${esc(title)}</h2><p>${esc(description)}</p>${action}</div>`;
const table = (headers, rows) => `<div class="table-scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const row = cells => `<tr>${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`;
const panel = (title, content, action = '') => `<section class="panel"><div class="panel-header"><h2>${esc(title)}</h2>${action}</div>${content}</section>`;
const privateNote = () => `<div class="context-strip">${icon('lock')}<span>Этот раздел — <strong>только в вашей локальной базе</strong>. Его данные не передаются в общую базу работодателей.</span></div>`;
let state = null;
let current = pages.some(p=>p[0]===location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
let jobFilter = 'all';
let searchFilter = '';
let runtime = null;
let detailRunId = null;
let loading = false;
let editorConfig = null;
let toastTimer;

function notify(message, error = false) {
  const el = $('#toast'); el.textContent = message; el.className = `toast${error?' error':''}`; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(()=>{el.hidden = true;}, error?9000:5000);
}
async function tool(name, args = {}) {
  const response = await fetch(`/api/tools/${encodeURIComponent(name)}`, {method:'POST',headers:{'Content-Type':'application/json','X-Worklife-Client':'local'},body:JSON.stringify(args)});
  let data; try { data = await response.json(); } catch { throw new Error('Сервер вернул ответ, который не удалось прочитать.'); }
  if (!response.ok || data.ok === false) throw new Error(typeof data.error==='string' ? data.error : pretty(data.error || `Ошибка ${response.status}`));
  return data.result;
}
async function load(force = false) {
  if (loading) return; loading = true;
  try {
    const response = await fetch('/api/state',{cache:'no-store'});
    if (!response.ok) throw new Error('Локальное приложение недоступно.');
    const data = await response.json();
    if (data.ok === false) throw new Error(data.error || 'Не удалось загрузить базу.');
    state = data.result || data;
    runtime = arr(state.agent?.runs).find(r=>r.id===(runtime?.id||runtime?.run_id)) || arr(state.agent?.runs)[0] || runtime;
    if(detailRunId && $('#detail').open) { const run=arr(state.agent?.runs).find(r=>r.id===detailRunId); if(run)showRun(run); }
    const connection = $('#connection'); connection.className = 'connection online'; connection.innerHTML = '<i></i>Локально · '+new Date().toLocaleTimeString('ru',{hour:'2-digit',minute:'2-digit'});
    renderNav();
    if (force || !$('#workspace').contains(document.activeElement) || !document.activeElement.matches('input,textarea,select')) render();
  } catch (error) {
    const connection = $('#connection'); connection.className = 'connection failed'; connection.innerHTML = '<i></i>Нет соединения';
    if (!state) $('#workspace').innerHTML = `<div class="initial-state">${icon('resources')}<h1>Не удалось подключиться</h1><p>${esc(error.message)} Проверьте, что Worklife запущен на вашем компьютере.</p>${button('Попробовать ещё раз','refresh')}</div>`;
    else if (force) notify(error.message,true);
  } finally { loading = false; }
}
function renderNav() {
  const counts = state ? {search:arr(state.jobs).length,schedules:arr(state.schedules).length,experiments:arr(state.experiments).length,cv:arr(state.cvs).length,employers:arr(state.employers).length} : {};
  $('#navigation').innerHTML = pages.map(([key,title])=>`<a href="#${key}" class="nav-link${current===key?' active':''}" ${current===key?'aria-current="page"':''}>${icon(key)}<span>${title}</span>${counts[key]?`<span class="nav-count">${counts[key]}</span>`:''}</a>`).join('');
  $('#breadcrumb-current').textContent = pages.find(p=>p[0]===current)?.[1] || 'Обзор';
}
function navigate() {
  current = pages.some(p=>p[0]===location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
  $('#sidebar').classList.remove('open'); $('#menu-toggle').setAttribute('aria-expanded','false'); renderNav(); if (state) render();
}
function render() {
  if (!state) return;
  const views = {overview:renderOverview,search:renderSearch,schedules:renderSchedules,experiments:renderExperiments,strengths:renderStrengths,cv:renderCV,employers:renderEmployers,resources:renderResources,accounts:renderAccounts,repositories:renderRepositories,tactics:renderTactics,settings:renderSettings};
  $('#workspace').innerHTML = views[current]();
}
function jobRows(limit) {
  const applications = new Map(arr(state.applications).map(a=>[a.job_id,a]));
  let jobs = arr(state.jobs).filter(j=>!searchFilter || `${j.title} ${j.employer}`.toLowerCase().includes(searchFilter.toLowerCase()));
  if (jobFilter==='new') jobs = jobs.filter(j=>!applications.has(j.id));
  if (jobFilter==='active') jobs = jobs.filter(j=>['saved','applied','interview'].includes(applications.get(j.id)?.stage));
  if (jobFilter==='reply') jobs = jobs.filter(j=>['reply','offer','accepted'].includes(applications.get(j.id)?.stage));
  jobs = jobs.slice().sort((a,b)=>(b.fetched_at||'').localeCompare(a.fetched_at||''));
  if (limit) jobs = jobs.slice(0,limit);
  return jobs.map(j=>{ const a=applications.get(j.id); const href=url(j.url); const salary=j.salary_min||j.salary_max ? [j.salary_min,j.salary_max].filter(Boolean).join(' — ')+' '+(j.currency||'') : (j.remote===true?'Удалённо':j.remote===false?'В офисе':'Условия уточняются'); return row([`<span class="cell-main">${href?`<a href="${href}" target="_blank" rel="noopener noreferrer">${esc(j.title)} ↗</a>`:esc(j.title)}</span><span class="cell-note">${esc(j.platform||'')} · ${esc(salary)}</span>`,esc(typeof j.employer==='object'?j.employer.name:j.employer),a?badge(a.stage):badge('new','Новая'),date(j.fetched_at),`<div class="table-actions">${small('Подробнее','job-detail',j.id)}${small('Стадия','application',j.id)}</div>`]); });
}
function pipeline(limit) {
  const count = arr(state.jobs).length;
  const filters = [['all','Все'],['new','Новые'],['active','В работе'],['reply','Ответ получен']].map(([key,title])=>`<button class="filter ${jobFilter===key?'active':''}" type="button" data-action="filter" data-id="${key}">${title}${key==='all'?` <span>${count}</span>`:''}</button>`).join('');
  const rows=jobRows(limit);
  return `<section class="panel"><div class="table-toolbar"><h2>Конвейер вакансий</h2><div class="filters">${filters}</div>${current==='overview'?'<a class="text-link" href="#search">Открыть поиск ↗</a>':''}</div>${rows.length?table(['Вакансия','Компания','Статус','Обновлено',''],rows):empty('search',count?'Нет вакансий по этому фильтру':'Здесь появятся вакансии',count?'Выберите другой фильтр.':'Поручите поиск агенту или сохраните интересующую вакансию.',button('Добавить вакансию','job'))}</section>`;
}
function activityList(limit = 5) {
  return arr(state.activity).slice().sort((a,b)=>(b.at||b.created_at||'').localeCompare(a.at||a.created_at||'')).slice(0,limit);
}
function chart() {
  const dates = arr(state.applications).flatMap(a=>arr(a.history).filter(h=>h.stage==='applied').slice(0,1).map(h=>h.at)).filter(Boolean).sort();
  if (!dates.length) return '<div class="chart-empty">График появится после первых откликов</div>';
  const end=Date.now(), start=end-13*86400000, values=Array.from({length:14},(_,i)=>dates.filter(d=>+new Date(d)<=start+i*86400000).length), max=Math.max(...values,1);
  const points=values.map((v,i)=>`${12+i*28},${112-v/max*95}`).join(' ');
  return `<div class="actual-chart"><svg viewBox="0 0 390 125" preserveAspectRatio="none" role="img" aria-label="Накопленные отклики за последние 14 дней"><g stroke="#ffffff08"><path d="M12 17H376M12 65H376M12 112H376"/></g><polyline points="${points}" fill="none" stroke="#ffb548" stroke-width="2"/></svg><div class="chart-caption"><span>14 дней назад</span><span>Сегодня · всего ${dates.length}</span></div></div>`;
}
function renderOverview() {
  const stats=state.statistics||{}, apps=arr(state.applications);
  const replies=apps.filter(a=>['reply','interview','offer','accepted'].includes(a.stage)||arr(a.history).some(h=>['reply','interview','offer','accepted'].includes(h.stage))).length;
  const applied=apps.filter(a=>arr(a.history).some(h=>h.stage==='applied') || ['applied','reply','interview','offer','accepted'].includes(a.stage)).length;
  const activity=activityList();
  const next=arr(state.schedules).filter(s=>s.enabled).sort((a,b)=>(a.next_run_at||'').localeCompare(b.next_run_at||''))[0];
  const active=runtime && ['running','queued','cancelling'].includes(runtime.status);
  return heading('Обзор','Ваш поиск работы: действия агента, результаты и следующие шаги.',button('Ваши условия','profile'))+
    `<form class="agent-bar" id="agent-goal-form">${icon('agent')}<input name="goal" aria-label="Задача агенту" placeholder="Что поручить агенту? Например: найти удалённую работу…" required><button class="button primary" type="submit">Запустить агента <span aria-hidden="true">↗</span></button></form><p class="agent-note">${state.agent?.configured===false?'Модель агента ещё не подключена. Настройте её в локальной конфигурации или работайте через свою среду агента.':'Агент работает с вашими условиями и доступными источниками. История действий сохраняется здесь.'}</p>`+
    (runtime?`<div class="runtime-strip">${badge(runtime.status||'active',label(runtime.status||'active'))}<span class="subtle">${esc(runtime.goal||runtime.message||'Запуск агента')}</span>${small('Подробности','runtime-detail')}${active?small('Остановить','agent-cancel',runtime.run_id||runtime.id||''):''}</div>`:'')+
    `<div class="overview-top"><section class="panel activity-panel"><div class="panel-header"><h2>Активность агента</h2><a href="#resources" class="text-link">История ↗</a></div>${activity.length?`<ol class="timeline">${activity.map(a=>`<li><time>${time(a.at||a.created_at)}</time><span class="timeline-icon">${icon(a.kind==='search'?'search':a.kind==='schedule'?'schedules':'activity')}</span><div><strong>${esc(a.title||a.summary||a.kind||'Действие')}</strong><p>${esc(a.details||a.message||a.description||a.reference_id||'')}</p></div></li>`).join('')}</ol>`:empty('activity','Пока нет событий','Запустите агента. Его действия и результаты появятся в этой ленте.')}</section><div class="overview-side"><section class="panel statistics-panel"><div class="panel-header"><h2>Статистика поиска</h2><span class="subtle">Ваша локальная база</span></div><div class="metrics"><div class="metric"><span>Найдено вакансий</span><strong>${esc(stats.jobs??arr(state.jobs).length)}</strong></div><div class="metric"><span>Отправлено откликов</span><strong>${applied}</strong></div><div class="metric"><span>Получено ответов</span><strong>${replies}</strong></div></div>${chart()}</section><section class="panel schedule-summary">${icon('clock')}<div><h2>Следующий запуск</h2><p>${next?date(next.next_run_at):'Расписание не задано'}</p><span class="subtle">${next?esc(next.name):'Выберите удобное время для поиска'}</span></div><a href="#schedules" class="button small">${next?'Изменить':'Настроить'}</a></section></div></div>`+pipeline(6)+
    `<div class="section-gap">${renderActions()}</div>`+runtimeHistory();
}
function runtimeHistory() {
  const runs=arr(state.agent?.runs);
  return runs.length?`<div class="section-gap">${panel('Запуски агента',table(['Поручение','Состояние','Шаги','Начало',''],runs.map(r=>row([`<span class="cell-main">${esc(r.goal)}</span>`,badge(r.status),`${arr(r.steps).length} / ${esc(r.max_steps)}`,date(r.started_at||r.created_at),small('Журнал','agent-run-detail',r.id)]))))}</div>`:'';
}
function renderSearch() {
  const connectors=arr(state.connectors).filter(c=>c.type!=='http' && arr(c.read).includes('search'));
  return heading('Поиск','Агент выбирает источники под задачу. Здесь — найденные вакансии и ваш конвейер.',button('Поручить агенту','agent')+button('Добавить вакансию','job', '', true))+
    `<section class="panel"><form id="job-search-form" class="search-bar"><input name="query" aria-label="Поисковый запрос" placeholder="Должность, навыки или компания" required><select name="connector" aria-label="Источник поиска"><option value="agent">Выбрать источники агенту</option>${connectors.map(c=>`<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('')}</select><button class="button primary" type="submit">Найти вакансии</button></form></section><div class="section-gap">${pipeline()}</div>`;
}
function renderActions() {
  const actions=arr(state.actions).slice().reverse();
  return panel('Переписка и действия',actions.length?table(['Действие','Канал','Состояние','Создано',''],actions.map(a=>row([`<span class="cell-main">${esc(a.operation)}</span><span class="cell-note">${esc(a.payload?.subject||a.payload?.to||a.payload?.url||a.id)}</span>`,esc(a.connector),badge(a.status),date(a.created_at),`<div class="table-actions">${small('Открыть','action-detail',a.id)}${a.status==='draft'?small('Разрешить','approve',a.id):''}${a.status==='approved'?small('Выполнить','execute',a.id):''}${['draft','approved'].includes(a.status)?small('Отменить','cancel',a.id):''}</div>`]))):'<p class="empty-inline">Черновики и отправленные сообщения появятся здесь. Каждое действие сохраняет своё состояние.</p>',small('Новый черновик','draft'));
}
function renderSchedules() {
  const rows=arr(state.schedules);
  const tasks=arr(state.tasks);
  return heading('Расписание','Регулярный поиск, задачи агента и напоминания.',button('Напоминание','task')+button('Конкретный инструмент','schedule-custom')+button('Добавить расписание','schedule','',true))+
    panel('Регулярные запуски',rows.length?table(['Название','Периодичность','Следующий запуск','Состояние',''],rows.map(s=>row([`<span class="cell-main">${esc(s.name)}</span><span class="cell-note">${esc(s.tool)}</span>`,`Каждые ${esc(s.interval_minutes)} мин.`,date(s.next_run_at),badge(s.enabled?'enabled':'disabled'),`<div class="table-actions">${small('Запустить','schedule-run',s.id)}${small(s.enabled?'Пауза':'Включить','schedule-toggle',s.id)}${small('Подробнее','schedule-detail',s.id)}</div>`]))):empty('schedules','Пусть поиск работает по расписанию','Добавьте регулярное поручение агенту или запуск конкретного инструмента.',button('Добавить расписание','schedule')))+
    `<div class="section-gap">${panel('Напоминания',tasks.length?table(['Задача','Срок','Состояние',''],tasks.map(t=>row([esc(t.title),date(t.due_at),badge(t.status),t.status==='open'?small('Готово','task-complete',t.id):'']))):'<p class="empty-inline">Нет напоминаний. Можно запланировать следующий контакт или возвращение к вакансии.</p>')}</div>`+
    (arr(state.schedule_runs).length?`<div class="section-gap">${panel('Последние запуски',table(['Расписание','Время','Результат',''],arr(state.schedule_runs).slice(-10).reverse().map(r=>row([esc(r.name||r.schedule_id),date(r.started_at||r.at||r.created_at),badge(r.status),small('Подробности','run-detail',r.id)]))))}</div>`:'');
}
function renderExperiments() {
  const values=arr(state.experiments);
  return heading('Эксперименты','Гипотеза, варианты и срок наблюдения задаются до начала сравнения.',button('Создать эксперимент','experiment','',true))+privateNote()+
    panel('Гипотезы и результаты',values.length?`<ul class="resource-list">${values.map(e=>{const report=arr(state.experiment_reports).find(r=>r.experiment?.id===e.id||r.experiment_id===e.id);return `<li><div class="row-icon">${icon('experiments')}</div><div class="row-body"><h3>${esc(e.hypothesis)}</h3><div class="row-meta"><span>${esc(e.variant_ids?.length||0)} варианта CV</span><span>Окно: ${esc(e.horizon_hours)} ч.</span><span>Метрика: ${esc(label(e.metric))}</span></div>${report?`<p>${esc(label(report.conclusion))}</p>`:''}</div><div class="list-actions">${badge(e.status)}${small('Результаты','experiment-detail',e.id)}${small('Назначить','experiment-assign',e.id)}${small('Записать исход','experiment-outcome',e.id)}</div></li>`;}).join('')}</ul>`:empty('experiments','Есть идея, что улучшить?','Создайте минимум два варианта CV, затем задайте гипотезу и измеряемый результат.',button('Создать эксперимент','experiment')));
}
function renderStrengths() {
  const values=arr(state.strengths);
  return heading('Сильные стороны','Сохраняйте подтверждения навыков и опыта, которые можно использовать в CV.',button('Добавить сильную сторону','strength','',true))+privateNote()+
    panel('Ваши подтверждения',values.length?`<ul class="resource-list">${values.map(s=>`<li><div class="row-icon">${icon('strengths')}</div><div class="row-body"><h3>${esc(s.title)}</h3><p>${esc(s.description)}</p><div class="row-meta">${arr(s.evidence).map(e=>`<span>${esc(e.source||e)}</span>`).join('')}</div></div><div class="list-actions">${badge(s.status)}${small('Подробности','strength-detail',s.id)}</div></li>`).join('')}</ul>`:empty('strengths','Опыт начинается с фактов','Добавьте сильную сторону с источником: проектом, результатом работы или отзывом.',button('Добавить сильную сторону','strength')));
}
function renderCV() {
  const values=arr(state.cvs);
  return heading('CV','Правдивые варианты резюме из фактов вашего профиля.',button('Факты профиля','profile')+button('Создать CV','cv','',true))+privateNote()+
    panel('Варианты резюме',values.length?`<ul class="resource-list">${values.map(c=>`<li><div class="row-icon">${icon('cv')}</div><div class="row-body"><h3>${esc(c.name||c.headline)}</h3><p>${esc(c.headline)}</p><div class="row-meta"><span>${esc(c.language||'Язык не указан')}</span><span>${arr(c.facts).length} фактов</span><span>${date(c.created_at)}</span></div></div><div class="list-actions">${small('Открыть','cv-detail',c.id)}${small('Другой язык','cv-language',c.id)}${small('Экспорт','cv-export',c.id)}</div></li>`).join('')}</ul>`:empty('cv','Первый вариант CV','Заполните факты профиля с источниками, затем соберите из них резюме.',button('Создать CV','cv')));
}
function renderEmployers() {
  const values=arr(state.employers), blocks=arr(state.employer_blocks), network=state.network||{};
  return heading('Работодатели','Общие наблюдения о компаниях по их доменам. Решения о работодателях принимаете вы.',button('Блокировать компанию','block')+button('Добавить наблюдение','employer','',true))+
    `<div class="context-strip">${icon('employers')}<span><strong>Общая база — только о работодателях.</strong> CV, личная статистика и результаты кандидатов остаются локальными. Перед публикацией проверьте текст: без имён, контактов и персональных сведений.</span></div>`+
    panel('Наблюдения о компаниях',values.length?`<ul class="resource-list">${values.map(e=>{const p=e.payload||e;return `<li><div class="row-icon">${icon('employers')}</div><div class="row-body"><h3>${esc(p.name||e.subject||e.domain)}</h3><p>${esc(p.claim||e.claim)}</p>${url(p.source_url)?`<a href="${url(p.source_url)}" target="_blank" rel="noopener noreferrer">Источник ↗</a>`:''}<div class="row-meta"><span>${esc(e.subject||e.domain)}</span><span>${date(p.observed_at||e.created_at)}</span><span>${esc(p.evidence_kind||'')}</span></div></div><div class="list-actions">${small('Подробнее','employer-detail',e.event_id||e.id||e.subject)}${small('Блокировать','block',e.subject||e.domain||'')}</div></li>`;}).join('')}</ul>`:empty('employers','Общая база пока пуста','Сохраните наблюдение об условиях компании или подключите другую реплику.'))+
    `<div class="section-gap split-panels">${panel('Локальные блокировки',blocks.length?`<ul class="resource-list">${blocks.map(b=>`<li><div class="row-body"><h3>${esc(b.domain||b.id)}</h3><p>${esc(b.reason)}</p></div>${b.blocked!==false?small('Снять','unblock',b.id||b.domain):badge('disabled','Блокировка снята')}</li>`).join('')}</ul>`:'<p class="empty-inline">Нет заблокированных компаний.</p>')}${panel('Обмен наблюдениями',`<div class="settings-body"><p>${network.valid===false?'Ошибка целостности: '+esc(network.error||'проверьте журнал'):'Подписи проверены.'} В журнале: ${esc(network.events??values.length)} записей. Подпись связывает запись с ключом автора; она не подтверждает правдивость утверждения.</p>${arr(network.peers).length?arr(network.peers).map(p=>{const sync=arr(network.last_sync).find(s=>s.id===p.url||s.author===p.author);return `<div class="row-meta"><span>${esc(p.name||p.id)}</span><span>Последний обмен: ${sync?date(sync.last_success):'ещё не выполнен'}</span>${small('Синхронизировать','peer-sync',p.name||p.id)}</div>`;}).join(''):'<p class="section-gap">Другие реплики не подключены.</p>'}${button('Подключить реплику','peer')}</div>`)}</div>`;
}
function renderResources() {
  const values=arr(state.resources), activity=activityList(30);
  return heading('Ресурсы','Сервисы и материалы, доступные агенту для поиска работы.',button('Добавить ресурс','resource','',true))+
    panel('Доступные ресурсы',values.length?`<ul class="resource-list">${values.map(r=>`<li><div class="row-icon">${icon('resources')}</div><div class="row-body"><h3>${esc(r.name)}</h3><p>${esc(r.notes||'')}</p>${url(r.url)?`<a href="${url(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.url)} ↗</a>`:''}<div class="row-meta"><span>${esc(r.kind)}</span>${r.budget?`<span>Бюджет: ${esc(typeof r.budget==='object'?pretty(r.budget):r.budget)}</span>`:''}</div></div>${small('Подробнее','resource-detail',r.id)}</li>`).join('')}</ul>`:empty('resources','Добавьте полезные ресурсы','Сохраните сервис, источник вакансий или материал, который агент сможет использовать.',button('Добавить ресурс','resource')))+
    `<div class="section-gap">${panel('История активности',activity.length?table(['Событие','Описание','Время'],activity.map(a=>row([esc(a.title||a.summary||a.kind),`<span class="cell-wrap">${esc(a.details||a.message||a.description||'')}</span>`,date(a.at||a.created_at)]))):'<p class="empty-inline">Пока нет событий.</p>')}</div>`;
}
function renderAccounts() {
  const platforms=arr(state.platforms), accounts=arr(state.accounts);
  return heading('Аккаунты','Площадки и состояния аккаунтов, с которыми работает ваш агент.',button('Добавить площадку','platform')+button('Добавить аккаунт','account','',true))+privateNote()+
    panel('Ваши аккаунты',accounts.length?table(['Аккаунт','Площадка','Состояние','Почта',''],accounts.map(a=>row([esc(a.identifier),esc(platforms.find(p=>p.id===a.platform_id)?.name||a.platform_id),badge(a.status),esc(a.email||'—'),small('Подробнее','account-detail',a.id)]))):empty('accounts','Аккаунты ещё не добавлены','Сохраните площадку и идентификатор аккаунта. Секреты задаются отдельно в локальной конфигурации.',button('Добавить аккаунт','account')))+
    `<div class="section-gap">${panel('Площадки',platforms.length?`<ul class="resource-list">${platforms.map(p=>`<li><div class="row-icon">${icon('accounts')}</div><div class="row-body"><h3>${esc(p.name)}</h3>${url(p.url)?`<a href="${url(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.url)} ↗</a>`:''}<p>${esc(p.notes||'')}</p><div class="row-meta">${arr(p.capabilities).map(c=>`<span>${esc(c)}</span>`).join('')}</div></div></li>`).join('')}</ul>`:'<p class="empty-inline">Агент может выбирать подходящие сайты. Добавьте известную площадку или поручите ему исследование.</p>')}</div>`;
}
function renderRepositories() {
  const values=arr(state.repositories);
  return heading('Репозитории','Локальные проекты как источник подтверждённых фактов для CV.',button('Анализировать репозиторий','repository','',true))+privateNote()+
    panel('Проанализированные проекты',values.length?`<ul class="resource-list">${values.map(r=>`<li><div class="row-icon">${icon('repositories')}</div><div class="row-body"><h3>${esc(r.name||r.path)}</h3><p>${esc(r.summary||r.description||'')}</p><div class="row-meta"><span>${esc(r.path||'')}</span><span>${date(r.analyzed_at||r.created_at)}</span></div></div>${small('Результат анализа','repository-detail',r.id)}</li>`).join('')}</ul>`:empty('repositories','Покажите, что вы умеете','Укажите путь к локальному репозиторию. Результат анализа останется в вашем пространстве.',button('Анализировать репозиторий','repository')));
}
function renderTactics() {
  const values=arr(state.tactics);
  return heading('Тактики','Личные гипотезы и конкретные действия для вашего поиска.',button('Добавить тактику','tactic','',true))+privateNote()+
    panel('Подходы к поиску',values.length?`<ul class="resource-list">${values.map(t=>`<li><div class="row-icon">${icon('tactics')}</div><div class="row-body"><h3>${esc(t.name)}</h3><p>${esc(t.hypothesis)}</p><div class="row-meta"><span>Метрика: ${esc(t.success_metric)}</span><span>${arr(t.actions).length} действий</span></div></div><div class="list-actions">${badge(t.status)}${small('Открыть','tactic-detail',t.id)}</div></li>`).join('')}</ul>`:empty('tactics','Следующий подход к поиску','Сформулируйте гипотезу, действия и признак успеха. Общие уроки о CV и откликах остаются локальными.',button('Добавить тактику','tactic')));
}
function renderSettings() {
  const profile=state.profile||{}, connectors=arr(state.connectors);
  return heading('Настройки','Ваши условия, подключения и работа агента.')+
    `<div class="settings-grid">${panel('Ваши условия',`<div class="settings-body"><p>Условия жизни и факты опыта помогают агенту оценивать предложения и собирать правдивые CV.</p><dl><dt>Имя</dt><dd>${esc(profile.name||'Не указано')}</dd><dt>Факты опыта</dt><dd>${arr(profile.facts).length}</dd><dt>Предпочтения</dt><dd>${esc(arr(profile.life_preferences).join(' · ')||'Не заданы')}</dd></dl>${button('Редактировать профиль','profile')}</div>`)}${panel('Среда агента',`<div class="settings-body"><p>Worklife использует выбранную вами модель и локальные подключения. Запуск агента и все его действия видны в обзоре.</p><div class="section-gap">${button('Дать поручение','agent','',true)} ${button('Состояние агента','agent-status')}</div><p class="section-gap">Настройки модели и секреты читаются из локальной конфигурации. Значения секретов здесь не отображаются.</p></div>`)}</div><div class="section-gap">${panel('Подключения',connectors.length?`<ul class="resource-list">${connectors.map(c=>`<li><div class="row-icon">${icon('resources')}</div><div class="row-body"><h3>${esc(c.name)}</h3><div class="row-meta"><span>Чтение: ${esc(arr(c.read).join(', ')||'—')}</span><span>Действия: ${esc(arr(c.write).join(', ')||'—')}</span></div><div class="credentials">${Object.entries(c.credentials||{}).map(([key,v])=>badge(v.set?'verified':'planned',`${key}: ${v.set?'настроено':'не настроено'}`)).join('')}</div></div></li>`).join('')}</ul>`:'<p class="empty-inline">Подключения ещё не настроены. Добавьте нужный сервис в локальной конфигурации или через расширенную форму.</p>',small('Добавить подключение','connector'))}</div>`;
}

const f = (name,label,type='text',extra={}) => ({name,label,type,...extra});
const opts = object => Object.entries(object);
function formConfig(action,id='') {
  const cvs=arr(state.cvs), jobs=arr(state.jobs), profile=state.profile||{};
  const cv=cvs.find(c=>c.id===id);
  const configs = {
    agent:{title:'Поручение агенту',description:'Опишите, какую работу вы ищете и какие действия поручаете. Агент сохранит ход работы в журнале.',tool:'agent_run',submit:'Запустить агента',fields:[f('goal','Задача','textarea',{placeholder:'Найди подходящие удалённые вакансии, изучи условия и подготовь следующие действия.'}),f('max_steps','Максимум шагов','number',{value:8,min:1,max:30})]},
    resource:{title:'Добавить ресурс',description:'Источник, сервис, материал или бюджет для вашего поиска работы.',tool:'resource_save',fields:[f('name','Название'),f('kind','Тип','select',{options:opts({source:'Источник вакансий',service:'Сервис',material:'Материал',time:'Время',other:'Другое'})}),f('url','Ссылка','url',{required:false}),f('notes','Заметки','textarea',{required:false}),f('budget','Бюджет','number',{required:false,nullable:true,min:0,step:'any',hint:'Необязательное числовое ограничение. Единицы укажите в заметках.'})]},
    schedule:{title:'Поиск по расписанию',description:'Поручение будет запускаться, пока локальное приложение или рабочий процесс Worklife работает.',tool:'schedule_save',fields:[f('name','Название расписания'),f('goal','Поручение агенту','textarea',{placeholder:'Найди новые подходящие вакансии, проверь изменения и сохрани результаты.'}),f('interval_minutes','Повторять каждые, минут','number',{value:60,min:1,step:'any'}),f('enabled','Включить расписание','checkbox',{value:true})],map:v=>({name:v.name,tool:'agent_cycle',arguments:{goal:v.goal,max_steps:8},interval_minutes:v.interval_minutes,enabled:v.enabled})},
    'schedule-custom':{title:'Расширенное расписание',description:'Запуск конкретного инструмента. Аргументы задаются в формате JSON.',tool:'schedule_save',fields:[f('name','Название'),f('tool','Инструмент','select',{options:opts({agent_cycle:'Поручение агенту',jobs_search:'Поиск через подключение',connector_read:'Чтение подключения',peer_sync:'Обмен с репликой',repository_analyze:'Анализ репозитория',reminder:'Напоминание'})}),f('arguments','Аргументы','json',{value:{},hint:'Например для напоминания: {"title":"Вернуться к вакансии"}'}),f('interval_minutes','Интервал, минут','number',{value:60,min:1}),f('enabled','Включено','checkbox',{value:true})]},
    block:{title:'Блокировать работодателя',description:'Локальное исключение компании по её домену. Агент учитывает блокировку, когда связь вакансии или контакта с компанией установлена.',tool:'employer_block',submit:'Блокировать',fields:[f('domain','Домен компании','text',{value:id,placeholder:'company.example'}),f('reason','Причина','textarea'),f('evidence_url','Источник','url',{required:false})],map:v=>({...v,blocked:true})},
    repository:{title:'Анализировать репозиторий',description:'Worklife прочитает локальный проект и сохранит подтверждения опыта. Код репозитория не запускается.',tool:'repository_analyze',submit:'Анализировать',fields:[f('path','Путь к репозиторию','text',{placeholder:'/Users/you/projects/project'}),f('max_files','Максимум файлов','number',{value:200,min:1,max:2000})]},
    strength:{title:'Добавить сильную сторону',description:'Укажите конкретное подтверждение: проект, результат работы или документ.',tool:'strength_save',fields:[f('title','Название'),f('description','Описание','textarea'),f('evidence','Источники','textarea',{hint:'Один источник на строку: ссылка, путь к проекту или описание документа.'}),f('status','Состояние','select',{options:opts({proposed:'Предложено',confirmed:'Подтверждено'})})],map:v=>({...v,evidence:lines(v.evidence).map(source=>({source}))})},
    tactic:{title:'Добавить тактику',description:'Личная стратегия поиска. Она не публикуется в общей базе.',tool:'tactic_save',fields:[f('name','Название'),f('hypothesis','Гипотеза','textarea'),f('actions','Действия','textarea',{hint:'По одному действию на строку.'}),f('success_metric','Как измерить результат'),f('status','Состояние','select',{options:opts({planned:'Запланировано',active:'В работе',paused:'На паузе',completed:'Завершено'})})],map:v=>({...v,actions:lines(v.actions)})},
    platform:{title:'Добавить площадку',description:'Агрегатор, карьерный сайт работодателя или сервис для поиска работы.',tool:'platform_save',fields:[f('name','Название'),f('url','Адрес','url'),f('capabilities','Возможности','textarea',{required:false,hint:'Например: поиск вакансий, отклики, переписка. По одной возможности на строку.'}),f('notes','Заметки','textarea',{required:false})],map:v=>({...v,capabilities:lines(v.capabilities)})},
    account:{title:'Добавить аккаунт',description:'Сохраняются только сведения об аккаунте. Пароли и токены сюда не вводятся.',tool:'account_save',fields:[f('platform_id','Площадка','select',{options:arr(state.platforms).map(p=>[p.id,p.name]),hint:arr(state.platforms).length?'':'Сначала добавьте площадку в разделе «Аккаунты».'}),f('identifier','Логин или идентификатор'),f('email','Почта','email',{required:false}),f('status','Состояние','select',{options:opts({planned:'Запланирована регистрация',registering:'Регистрация начата',verification_required:'Нужно подтвердить почту',active:'Активен',blocked:'Заблокирован',closed:'Закрыт'})}),f('notes','Заметки','textarea',{required:false})]},
    cv:{title:'Создать вариант CV',description:'В резюме попадут выбранные факты вашего профиля с сохранением источников.',tool:'cv_create',fields:[f('name','Название варианта'),f('headline','Заголовок резюме'),f('summary','Кратко о себе','textarea',{required:false}),f('fact_ids','Факты опыта','checkboxes',{options:arr(profile.facts).map(fact=>[fact.id,fact.text]),hint:arr(profile.facts).length?'Выберите факты для этого варианта.':'Сначала добавьте факты в профиль в настройках.'})]},
    'cv-language':{title:'Создать версию на языке',description:'Агент переведёт выбранное резюме, сохранив исходные факты и источники. После создания проверьте результат.',tool:'agent_run',submit:'Поручить перевод',fields:[f('language','Язык новой версии','text',{value:'en',placeholder:'Например: en, de, fr, it, ru',hint:'Код языка, например en для английского или de для немецкого.'})],map:v=>({goal:`Создай новую версию моего CV «${cv?.name||id}» (cv_id=${id}) на языке ${v.language}. Прочитай оригинальные факты, переведи каждый выбранный факт без добавления нового опыта. Используй cv_localize с translations для каждого исходного fact_id, переведёнными headline и summary, отдельным именем версии. Сохрани источники. Затем сообщи результат и что нужно проверить.`,max_steps:8})},
    'cv-language-manual':{title:'Перевод CV вручную',description:'Расширенная форма: перевод каждого исходного факта по его идентификатору.',tool:'cv_localize',fields:[f('language','Код языка','text',{value:'en'}),f('headline','Заголовок на выбранном языке'),f('summary','Кратко о себе','textarea',{required:false}),f('name','Название версии'),f('translations','Переводы фактов','json',{value:Object.fromEntries(arr(cv?.facts).map(fact=>[fact.id,''])),hint:arr(cv?.facts).map(fact=>`${fact.id}: ${fact.text}`).join('\n')})],map:v=>({...v,cv_id:id,summary:v.summary||null})},
    'cv-export':{title:'Скачать CV',description:'Выберите формат файла. Резюме будет сформировано из сохранённых фактов.',submit:'Скачать файл',fields:[f('format','Формат','select',{options:[['pdf','PDF'],['md','Markdown'],['html','HTML']]})],run:async v=>{const response=await fetch(`/api/cv/${encodeURIComponent(id)}/download?format=${v.format}`);if(!response.ok){const error=await response.json();throw new Error(error.error||'Не удалось сформировать файл.');}const objectURL=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=objectURL;link.download=`worklife-cv.${v.format}`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(objectURL),1000);return {download:true};}},
    job:{title:'Сохранить вакансию',description:'Добавьте предложение, найденное в браузере или на сайте работодателя.',tool:'job_save',fields:[f('title','Название вакансии'),f('employer','Компания'),f('url','Ссылка','url'),f('platform','Источник','text',{value:'manual'}),f('remote','Формат работы','select',{options:[['unknown','Неизвестен'],['yes','Удалённо'],['no','В офисе']]}),f('notes','Заметки','textarea',{required:false})],map:v=>({job:{...v,id:crypto.randomUUID(),remote:v.remote==='unknown'?null:v.remote==='yes'}})},
    application:{title:'Обновить стадию',description:'Запишите фактическое состояние отклика. Это действие не отправляет заявление.',tool:'application_update',fields:[f('cv_id','Вариант CV','select',{options:cvs.map(c=>[c.id,c.name]),hint:cvs.length?'':'Для отклика сначала создайте вариант CV.'}),f('stage','Новая стадия','select',{value:arr(state.applications).find(a=>a.job_id===id)?.stage||'saved',options:opts({saved:'Сохранена',applied:'Отклик отправлен',reply:'Ответ получен',interview:'Интервью',offer:'Предложение',accepted:'Принято',rejected:'Отказ',withdrawn:'Снята'})}),f('note','Подтверждение или заметка','textarea',{required:false})],map:v=>({...v,job_id:id})},
    experiment:{title:'Создать эксперимент',description:'Выберите минимум два CV и заранее задайте метрику и окно наблюдения.',tool:'experiment_create',fields:[f('hypothesis','Гипотеза','textarea'),f('variant_ids','Варианты CV','checkboxes',{options:cvs.map(c=>[c.id,c.name]),hint:cvs.length<2?'Создайте минимум два варианта CV.':''}),f('metric','Измеряемый результат','select',{options:opts({reply:'Ответ',interview:'Интервью',offer:'Предложение'})}),f('horizon_hours','Окно наблюдения, часов','number',{value:168,min:1}),f('min_samples','Минимум наблюдений на вариант','number',{value:20,min:2})]},
    'experiment-assign':{title:'Назначить вариант вакансии',description:'Назначение сохраняется; агент не отправляет два варианта одной компании.',tool:'experiment_assign',fields:[f('job_id','Вакансия','select',{options:jobs.map(j=>[j.id,j.title+' · '+j.employer])})],map:v=>({...v,experiment_id:id})},
    'experiment-outcome':{title:'Записать результат',description:'Сохраните только реально наблюдавшееся событие.',tool:'experiment_outcome',fields:[f('job_id','Вакансия','select',{options:jobs.map(j=>[j.id,j.title+' · '+j.employer])}),f('outcome','Событие','select',{options:opts({applied:'Отклик отправлен',reply:'Ответ',interview:'Интервью',offer:'Предложение',rejected:'Отказ',no_reply:'Ответа нет'})})],map:v=>({...v,experiment_id:id})},
    task:{title:'Добавить напоминание',tool:'task_add',fields:[f('title','Задача'),f('due_at','Когда','datetime-local',{required:false}),f('job_id','Связать с вакансией','select',{required:false,options:[['','Без вакансии'],...jobs.map(j=>[j.id,j.title]) ]})],map:v=>({...v,job_id:v.job_id||null,due_at:v.due_at?new Date(v.due_at).toISOString():null})},
    profile:{title:'Ваши условия и факты',description:'Личный профиль остаётся локальным. У каждого факта укажите источник.',tool:'profile_save',fields:[f('name','Ваше имя','text',{value:profile.name||'',required:false}),f('preferences','Что важно в работе','textarea',{value:arr(profile.life_preferences).join('\n'),required:false,hint:'По одному предпочтению на строку.'}),f('facts','Факты опыта','json',{value:arr(profile.facts),hint:'Список {"id":"fact-1","text":"Что вы сделали","source":"Подтверждение"}.'}),f('constraints','Условия поиска','json',{value:profile.constraints||{},hint:'Например: {"remote":true,"max_hours":40,"max_test_hours":2}. Дополнительные условия можно сформулировать агенту обычным языком.'})],map:v=>({profile:{...profile,name:v.name,life_preferences:lines(v.preferences),facts:v.facts,constraints:v.constraints}})},
    draft:{title:'Подготовить действие',description:'Расширенная форма. Черновик сохраняется без отправки; содержимое можно проверить перед разрешением.',tool:'action_draft',fields:[f('connector','Подключение','select',{options:[['browser','Браузер'],...arr(state.connectors).map(c=>[c.name,c.name])]}),f('operation','Операция'),f('payload','Содержимое','json',{value:{}})],map:v=>({...v,idempotency_key:crypto.randomUUID()})},
    peer:{title:'Подключить реплику',description:'Обмен между репликами передаёт только подписанные наблюдения о работодателях.',tool:'peer_register',fields:[f('name','Название'),f('url','Адрес реплики','url'),f('author','Отпечаток ключа автора','text',{hint:'Технический идентификатор из 64 символов.'}),f('token_env','Имя переменной токена','text',{hint:'Имя локальной переменной окружения, а не сам токен.'})]},
    connector:{title:'Добавить подключение',description:'Расширенная форма. Значения секретов задавайте через переменные окружения.',tool:'connector_configure',fields:[f('name','Имя подключения'),f('config','Конфигурация','json',{value:{type:'http',base_url:'https://',operations:{}}})]},
    employer:{title:'Наблюдение о работодателе',description:'Публикуется в общей базе. Только компания и её условия: без имён, контактов, CV и личных результатов кандидатов.',tool:'knowledge_publish',submit:'Опубликовать наблюдение',fields:[f('domain','Домен компании','text',{placeholder:'company.example'}),f('claim','Наблюдение','textarea'),f('source_url','Источник','url'),f('evidence_kind','Основание','select',{options:opts({advertised:'Заявлено компанией',confirmed:'Подтверждено',observed:'Наблюдалось',hypothesis:'Гипотеза'})}),f('reviewed','Я проверил текст: он касается работодателя и не содержит персональных сведений','checkbox',{value:false,mustCheck:true})],map:v=>({kind:'employer',subject:v.domain,payload:{claim:v.claim,source_url:v.source_url,observed_at:new Date().toISOString(),evidence_kind:v.evidence_kind}})}
  };
  return configs[action];
}
function fieldHTML(field) {
  const {name,label,type,value,options=[],required=true,hint,placeholder,min,max,step,mustCheck}=field;
  const attrs=`name="${esc(name)}" id="field-${esc(name)}" ${required && type!=='checkbox'?'required':''} ${placeholder?`placeholder="${esc(placeholder)}"`:''} ${hint?`aria-describedby="hint-${esc(name)}"`:''}`;
  let input;
  if (type==='textarea'||type==='json') input=`<textarea ${attrs} ${type==='json'?'spellcheck="false"':''} rows="${type==='json'?6:3}">${esc(type==='json'?pretty(value??{}):(value||''))}</textarea>`;
  else if(type==='select') input=`<select ${attrs}>${options.length?options.map(([v,text])=>`<option value="${esc(v)}" ${String(value)===String(v)?'selected':''}>${esc(text)}</option>`).join(''):'<option value="">Нет доступных записей</option>'}</select>`;
  else if(type==='checkbox') return `<div class="field checkbox"><input type="checkbox" name="${esc(name)}" id="field-${esc(name)}" ${value?'checked':''} ${mustCheck?'required':''}><label for="field-${esc(name)}">${esc(label)}</label></div>`;
  else if(type==='checkboxes') input=`<div class="fieldset-options" role="group" aria-labelledby="label-${esc(name)}">${options.length?options.map(([v,text])=>`<label class="option-label"><input type="checkbox" name="${esc(name)}" value="${esc(v)}"><span>${esc(text)}</span></label>`).join(''):'<span class="subtle">Пока нет вариантов.</span>'}</div>`;
  else input=`<input ${attrs} type="${esc(type)}" value="${esc(value??'')}" ${min!==undefined?`min="${min}"`:''} ${max!==undefined?`max="${max}"`:''} ${step!==undefined?`step="${step}"`:''}>`;
  return `<div class="field"><label id="label-${esc(name)}" for="field-${esc(name)}">${esc(label)}</label>${input}${hint?`<small id="hint-${esc(name)}">${esc(hint)}</small>`:''}</div>`;
}
function openEditor(action,id) {
  editorConfig=formConfig(action,id); if (!editorConfig) return;
  $('#editor-title').textContent=editorConfig.title;
  $('#editor-description').textContent=editorConfig.description||'';
  $('#editor-fields').innerHTML=editorConfig.fields.map(fieldHTML).join('');
  $('#editor-error').textContent='';
  $('#editor-submit').textContent=editorConfig.submit||'Сохранить';
  $('#editor-submit').disabled=false;
  $('#editor').showModal();
}
function readFields(config) {
  const data=new FormData($('#editor-form')), values={};
  for(const field of config.fields) {
    let value=data.get(field.name);
    if(field.type==='checkbox') value=data.has(field.name);
    else if(field.type==='checkboxes') value=data.getAll(field.name);
    else if(field.type==='number') value=value===''&&field.nullable?null:Number(value);
    else if(field.type==='json') {try {value=JSON.parse(value);}catch{throw new Error(`«${field.label}»: проверьте формат JSON.`);}}
    else value=String(value||'').trim();
    values[field.name]=value;
  }
  return config.map?config.map(values):values;
}
function showDetail(title,value) {
  detailRunId=null;
  $('#detail-title').textContent=title;
  $('#detail-content').innerHTML=`<pre class="pre-content">${esc(typeof value==='string'?value:pretty(value))}</pre>`;
  $('#detail').showModal();
}
function showRun(run) {
  detailRunId=run.id;
  $('#detail-title').textContent='Журнал работы агента';
  $('#detail-content').innerHTML=`<p class="detail-summary">${esc(run.goal||'')}</p><dl class="detail-grid"><dt>Состояние</dt><dd>${badge(run.status)}</dd><dt>Модель</dt><dd>${esc(run.model||'—')}</dd><dt>Начало</dt><dd>${date(run.started_at||run.created_at)}</dd><dt>Завершение</dt><dd>${date(run.finished_at)}</dd></dl>${run.error?`<p class="form-error">${esc(run.error)}</p>`:''}${run.final_answer?`<p class="detail-summary section-gap">${esc(run.final_answer)}</p>`:''}${arr(run.steps).map(s=>`<section class="section-gap"><h3 class="section-title">Шаг ${esc(s.index)} <span class="subtle">· ${time(s.started_at)}</span></h3>${s.assistant?.content?`<p class="detail-summary">${esc(s.assistant.content)}</p>`:''}${arr(s.assistant?.tool_calls).map(c=>`<details class="section-gap"><summary>${esc(c.function?.name||'Вызов инструмента')}</summary><pre class="pre-content">${esc(c.function?.arguments||'')}</pre></details>`).join('')}${arr(s.tool_results).length?`<details class="section-gap"><summary>Результаты инструментов</summary><pre class="pre-content">${esc(pretty(s.tool_results))}</pre></details>`:''}</section>`).join('')}${!arr(run.steps).length?'<p class="empty-inline">Шаги появятся после начала работы агента.</p>':''}`;
  if(!$('#detail').open)$('#detail').showModal();
}

async function perform(action,id,target) {
  if (!state && action!=='refresh') return;
  if(action==='refresh') {await load(true);return;}
  if(action==='filter') {jobFilter=id;render();return;}
  if(formConfig(action,id)) {openEditor(action,id);return;}
  if(action==='runtime-detail') {if(runtime)showRun(runtime);return;}
  if(action==='agent-run-detail') {const run=arr(state.agent?.runs).find(r=>r.id===id);if(run)showRun(run);return;}
  if(action==='job-detail') {
    detailRunId=null;
    const job=arr(state.jobs).find(j=>j.id===id); if(!job)return;
    $('#detail-title').textContent=job.title;
    $('#detail-content').innerHTML=`<p class="detail-summary">${esc(job.employer)}${job.description?'\n\n'+esc(job.description):''}</p><dl class="detail-grid">${Object.entries(job).filter(([key])=>!['title','employer','description'].includes(key)).map(([key,value])=>`<dt>${esc(({url:'Источник',platform:'Источник',remote:'Удалённо',salary_min:'Зарплата от',salary_max:'Зарплата до',currency:'Валюта',notes:'Заметки',fetched_at:'Найдено',employer_domain:'Домен компании',blocked:'Локальная блокировка'})[key]||key)}</dt><dd>${esc(typeof value==='object'?pretty(value):value)}</dd>`).join('')}</dl><div class="section-gap">${button('Оценить условия','job-assess',id)} ${url(job.url)?`<a href="${url(job.url)}" class="button" target="_blank" rel="noopener noreferrer">Открыть вакансию ↗</a>`:''}</div>`;
    $('#detail').showModal();return;
  }
  if(action==='cv-detail') {
    detailRunId=null;
    const cv=arr(state.cvs).find(c=>c.id===id);if(!cv)return;
    $('#detail-title').textContent=cv.name||'CV';
    $('#detail-content').innerHTML=`<pre class="pre-content">${esc(cv.markdown||'')}</pre><div class="section-gap">${button('Создать версию на языке','cv-language',id,true)} ${button('Скачать','cv-export',id)}</div><details class="section-gap"><summary class="subtle">Перевести факты вручную</summary><div class="section-gap">${button('Открыть расширенную форму','cv-language-manual',id)}</div></details>`;
    $('#detail').showModal();return;
  }
  if(action==='experiment-detail') {
    detailRunId=null;
    target.disabled=true;
    try{const report=await tool('experiment_report',{experiment_id:id});const experiment=report.experiment||{};
      $('#detail-title').textContent='Результаты эксперимента';
      $('#detail-content').innerHTML=`<p class="detail-summary">${esc(experiment.hypothesis||'')}</p><p class="section-gap">${badge(report.conclusion)}</p><div class="section-gap">${table(['Вариант CV','Назначено','Отправлено','Созрело','Успехи','Доля'],arr(report.variants).map(v=>row([esc(arr(state.cvs).find(c=>c.id===v.variant_id)?.name||v.variant_id),esc(v.assigned),esc(v.exposed),esc(v.mature),esc(v.successes),v.rate===null?'—':`${Math.round(v.rate*100)}%`])))}</div><p class="inline-notice">В расчёт входят отправленные отклики с завершённым окном наблюдения. Малое количество данных не позволяет сделать вывод об эффективности.</p>`;
      $('#detail').showModal();
    }catch(error){notify(error.message,true);}finally{target.disabled=false;}return;
  }
  const detailBuckets={'action-detail':'actions','schedule-detail':'schedules','run-detail':'schedule_runs','strength-detail':'strengths','resource-detail':'resources','account-detail':'accounts','repository-detail':'repositories','tactic-detail':'tactics','employer-detail':'employers'};
  if(detailBuckets[action]) {
    const value=arr(state[detailBuckets[action]]).find(v=>v.id===id||v.event_id===id||v.subject===id);
    if(value)showDetail(value.name||value.title||value.operation||value.subject||'Подробности',value);
    return;
  }
  const s=arr(state.schedules).find(v=>v.id===id), b=arr(state.employer_blocks).find(v=>v.id===id||v.domain===id);
  const calls={
    approve:['action_approve',{action_id:id}], execute:['action_execute',{action_id:id}], cancel:['action_cancel',{action_id:id}],
    'schedule-run':['schedule_run',{schedule_id:id}], 'schedule-toggle':['schedule_toggle',{schedule_id:id,enabled:!s?.enabled}],
    'task-complete':['task_complete',{task_id:id}], 'peer-sync':['peer_sync',{name:id}],
    unblock:['employer_block',{domain:b?.domain||id,reason:b?.reason||'Блокировка снята владельцем',evidence_url:b?.evidence_url||'',blocked:false}],
    'job-assess':['job_assess',{job_id:id}], 'agent-status':['agent_status',{}], 'agent-cancel':['agent_cancel',{run_id:id}]
  };
  if(!calls[action])return;
  target.disabled=true;
  try {
    const result=await tool(...calls[action]);
    if(action==='agent-status') {runtime=arr(result?.runs)[0]||runtime;if(runtime)showRun(runtime);else notify(result?.configured?'Агент настроен. Запусков пока нет.':'Модель агента ещё не настроена. Укажите подключение в локальной конфигурации.');}
    else if(action==='job-assess')showDetail('Оценка условий вакансии',result);
    else if(action==='schedule-run')showDetail('Результат запуска расписания',result);
    else notify(action==='execute' && result?.status==='uncertain'?'Доставка не подтверждена. Проверьте результат у получателя.':action==='execute' && result?.status==='sent'?'Действие выполнено.':action==='agent-cancel'?'Остановка запрошена.':'Сохранено.');
    await load(true);
  }catch(error){notify(error.message,true);}finally{target.disabled=false;}
}
document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');
  if(!target)return;
  if($('#detail').open && formConfig(target.dataset.action,target.dataset.id)) $('#detail').close();
  perform(target.dataset.action,target.dataset.id||'',target).catch(error=>notify(error.message,true));
});
document.addEventListener('submit',async event=>{
  if(event.target.id==='editor-form') {
    event.preventDefault();const config=editorConfig,submit=$('#editor-submit');submit.disabled=true;$('#editor-error').textContent='';
    try{
      const args=readFields(config);
      const result=config.run?await config.run(args):await tool(config.tool,args);
      if(config.tool==='agent_run')runtime=result;
      $('#editor').close();
      notify(config.tool==='agent_run'?'Задача передана агенту. Ход работы появится в обзоре.':config.tool==='knowledge_publish'?'Наблюдение о работодателе опубликовано.':config.submit==='Скачать файл'?'Файл подготовлен.':'Сохранено.');
      await load(true);
    }catch(error){$('#editor-error').textContent=error.message;}finally{submit.disabled=false;}
  }
  if(event.target.id==='agent-goal-form'||event.target.id==='job-search-form') {
    event.preventDefault();const form=event.target,submit=$('button[type="submit"]',form),data=new FormData(form);submit.disabled=true;
    try {
      let result;
      if(form.id==='agent-goal-form') result=await tool('agent_run',{goal:String(data.get('goal')).trim(),max_steps:8});
      else if(data.get('connector')==='agent') result=await tool('agent_run',{goal:`Найди подходящие вакансии по запросу «${data.get('query')}» с учётом моего профиля. Самостоятельно выбери подходящие агрегаторы, карьерные сайты работодателей и сервисы. Изучи условия и сохрани вакансии и источники. Ничего не отправляй без поручения.`,max_steps:8});
      else {result=await tool('jobs_search',{connector:data.get('connector'),query:data.get('query'),parameters:{}});notify(`Поиск завершён. Получено записей: ${arr(result).length}.`);}
      if(result?.id){runtime=result;notify('Задача передана агенту.');}
      await load(true);
    }catch(error){notify(error.message,true);}finally{submit.disabled=false;}
  }
});
$('#close-editor').addEventListener('click',()=>$('#editor').close());
$('#cancel-editor').addEventListener('click',()=>$('#editor').close());
$('#close-detail').addEventListener('click',()=>$('#detail').close());
$('#refresh').addEventListener('click',()=>load(true));
$('#menu-toggle').addEventListener('click',()=>{const open=$('#sidebar').classList.toggle('open');$('#menu-toggle').setAttribute('aria-expanded',String(open));});
document.addEventListener('click',event=>{if(window.innerWidth<=700 && $('#sidebar').classList.contains('open')&&!$('#sidebar').contains(event.target)&&!$('#menu-toggle').contains(event.target)){$('#sidebar').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');}});
window.addEventListener('hashchange',navigate);
renderNav();load();setInterval(()=>{if(!document.hidden)load();},10000);
