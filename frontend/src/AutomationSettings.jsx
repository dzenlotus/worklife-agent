import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Typography } from "@heroui/react";
import { t } from "./i18n.js";
import { Panel, Status } from "./ui.jsx";

const defaults = {
  enabled: false,
  interval_minutes: 60,
  refresh_search: true,
  check_inbox: true,
  review: true,
  agent_goal: "",
};

function warningText(warning) {
  const parts = /^(Входящие|Поиск) (.+): (.+)\.$/.exec(warning);
  if (!parts) return t(warning);
  const reason = t(parts[3]);
  return parts[1] === "Входящие" ? t`Входящие ${parts[2]}: ${reason}.` : t`Поиск ${parts[2]}: ${reason}.`;
}

export default function AutomationSettings({ state, onCommand, onModel, pending }) {
  const automation = state.automation || {};
  const savedConfig = JSON.stringify({ ...defaults, ...automation.config });
  const [config, setConfig] = useState(() => JSON.parse(savedConfig));
  useEffect(() => { setConfig(JSON.parse(savedConfig)); }, [savedConfig]);
  const [lastCheck, setLastCheck] = useState(null);
  const change = (key, value) => setConfig((previous) => ({ ...previous, [key]: value }));
  const busy = Boolean(pending);
  const selected = config.refresh_search || config.check_inbox || config.review || config.agent_goal.trim();
  const needsModel = Boolean(config.agent_goal.trim()) && !state.agent?.configured;
  async function save(runNow = false) {
    const saved = await onCommand("automation_configure", config, "automation:save");
    if (saved && runNow) {
      const result = await onCommand("automation_run", {}, "automation:run");
      if (result) setLastCheck(result);
    }
  }
  const checks = [
    ["refresh_search", "Новые вакансии", "Повторять сохранённые поисковые запросы с их источниками и языками."],
    ["check_inbox", "Входящие сообщения", "Проверять подключённую почту и уже настроенные каналы переписки."],
    ["review", "Следующие шаги и подбор", "Проверять сроки, этапы откликов и соответствие сохранённых вакансий вашим условиям."],
  ];
  return <Panel title={t("Автоматические проверки")}>
    <form className="flex flex-col gap-5" onSubmit={(event) => { event.preventDefault(); save(); }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Checkbox isSelected={config.enabled} onChange={(value) => change("enabled", value)} isDisabled={busy}>
          <Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>{t("Запускать автоматически")}</Checkbox.Content>
        </Checkbox>
        <Status value={automation.config?.enabled ? "active" : "paused"}>
          {automation.config?.enabled ? t("Автопроверки включены") : t("Автопроверки выключены")}
        </Status>
      </div>
      <label className="form-field max-w-sm">{t("Проверять каждые")}
        <select value={config.interval_minutes} onChange={(event) => change("interval_minutes", Number(event.target.value))} disabled={busy}>
          {![15, 30, 60, 180, 360, 720, 1440].includes(config.interval_minutes) ? <option value={config.interval_minutes}>{t`${config.interval_minutes} мин.`}</option> : null}
          {[15, 30, 60, 180, 360, 720, 1440].map((minutes) => <option value={minutes} key={minutes}>{minutes < 60 ? t`${minutes} мин.` : t`${minutes / 60} ч.`}</option>)}
        </select>
      </label>
      <div className="grid gap-4">
        {checks.map(([key, title, description]) => <div className="flex flex-col gap-1" key={key}>
          <Checkbox isSelected={config[key]} onChange={(value) => change(key, value)} isDisabled={busy}>
            <Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>{t(title)}</Checkbox.Content>
          </Checkbox>
          <Typography.Paragraph size="sm" color="muted">{t(description)}</Typography.Paragraph>
        </div>)}
      </div>
      <label className="form-field">{t("Поручение встроенному исполнителю (необязательно)")}
        <textarea value={config.agent_goal} onChange={(event) => change("agent_goal", event.target.value)} maxLength={16000} rows={3} disabled={busy} placeholder={t("Например: продолжай поиск по моим условиям и разбирай новые ответы.")} />
      </label>
      <Typography.Paragraph size="sm" color="muted">{t("Для обычных проверок модель не нужна. Поручение исполнителю запускается по тому же расписанию в пределах ваших полномочий и использует подключённую модель.")}</Typography.Paragraph>
      {needsModel ? <div className="flex flex-wrap items-center gap-3"><Typography.Paragraph size="sm">{t("Для этого поручения подключите модель исполнителя.")}</Typography.Paragraph><Button size="sm" variant="outline" onPress={onModel}>{t("Подключить модель")}</Button></div> : null}
      {(automation.warnings || []).length ? <Alert status="warning"><Alert.Content><Alert.Title>{t("Доступные проверки")}</Alert.Title><Alert.Description><ul className="list-disc pl-5">{automation.warnings.map((warning) => <li key={warning}>{warningText(warning)}</li>)}</ul></Alert.Description></Alert.Content></Alert> : null}
      <Typography.Paragraph size="sm" color="muted">{t("Расписание выполняется, пока запущено локальное приложение или worker. Окно браузера можно закрыть. После остановки процесса проверки продолжатся при следующем запуске.")}</Typography.Paragraph>
      {state.scheduler?.running === false ? <Typography.Paragraph size="sm">{t("Планировщик приложения сейчас выключен. Для фоновых проверок запустите worker.")}</Typography.Paragraph> : null}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="primary" isDisabled={busy || (config.enabled && (!selected || needsModel))} isPending={pending === "automation:save"}>{t("Сохранить автопроверки")}</Button>
        <Button variant="outline" onPress={() => save(true)} isDisabled={busy || !selected || needsModel} isPending={pending === "automation:run"}>{t("Проверить сейчас")}</Button>
      </div>
      {lastCheck ? <div className="flex flex-wrap items-center gap-3" role="status"><Status value={lastCheck.status} /><Typography.Paragraph size="sm">{t`Запусков: ${lastCheck.runs?.length || 0}.`}</Typography.Paragraph></div> : null}
    </form>
  </Panel>;
}
