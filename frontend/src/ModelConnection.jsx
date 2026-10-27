import { useEffect, useState } from "react";
import { Button, Input, Label, Checkbox, Alert, Select, ListBox, Accordion, Link, Typography } from "@heroui/react";
import { Dialog } from "./ui.jsx";
import { connectionPayload, modelRequest } from "./model-api.js";

export default function ModelConnection({ initial, runAfter, onClose, onSaved }) {
  const [connection, setConnection] = useState(initial || {}),
    [base, setBase] = useState(initial?.base_url || ""),
    [model, setModel] = useState(initial?.model || ""),
    [key, setKey] = useState(""),
    [persist, setPersist] = useState(true),
    [models, setModels] = useState([]),
    [pending, setPending] = useState("loading"),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    modelRequest().then((value) => {
      if (!active) return;
      setConnection(value);
      setBase(value.base_url || "");
      setModel(value.model || "");
    }).catch((error) => { if (active) setError(error.message); })
      .finally(() => { if (active) setPending(""); });
    return () => { active = false; };
  }, []);
  function close() { setKey(""); onClose(); }
  async function loadModels() {
    setPending("models"); setError("");
    try {
      if (!base.trim()) throw new Error("Сначала укажите адрес сервиса модели.");
      const result = await modelRequest("/models", { base_url: base.trim(), ...(key.trim() ? { api_key: key.trim() } : {}) });
      setModels(Array.isArray(result) ? result : []);
      if (!result.length) setError("Сервис не вернул список. Можно ввести название модели вручную.");
    } catch (error) { setError(error.message); }
    finally { setPending(""); }
  }
  async function save(event) {
    event.preventDefault(); setPending("save"); setError("");
    try {
      const result = await modelRequest("", connectionPayload({ base_url: base, model, api_key: key, persist }));
      if (!result.configured) throw new Error("Параметры сохранены не полностью. Проверьте адрес, модель и ключ.");
      setKey("");
      await onSaved(result, runAfter);
    } catch (error) { setError(error.message); setPending(""); }
  }
  const busy = Boolean(pending);
  return (
    <Dialog open title="Подключить модель" onClose={close} footer={<>
      <Button variant="ghost" onPress={close} isDisabled={pending === "save"}>Отмена</Button>
      <Button type="submit" form="model-connection-form" isPending={pending === "save"} isDisabled={busy}>
        {runAfter ? "Сохранить и запустить поручение" : "Сохранить подключение"}
      </Button>
    </>}>
      <form id="model-connection-form" className="flex flex-col gap-3" onSubmit={save}>
        <Typography.Paragraph>Модель читает поручение и выбирает действия агента. Подключите локальный сервер или внешний сервис с совместимым API и поддержкой инструментов.</Typography.Paragraph>
        <Accordion>
          <Accordion.Item id="model-guide"><Accordion.Heading><Accordion.Trigger>Где взять адрес, ключ и название модели?<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body><div className="flex flex-col gap-4">
            <Typography.Paragraph>Сначала выберите, где будет работать модель. Ни один сервис не выбран автоматически.</Typography.Paragraph>
            <div className="flex flex-col gap-3"><Typography.Heading level={3}>На своём компьютере</Typography.Heading><Typography.Paragraph>Например, в LM Studio загрузите подходящую для компьютера модель и включите сервер во вкладке Developer. Нужна модель с поддержкой вызова инструментов.</Typography.Paragraph><div className="flex flex-wrap gap-3"><Link href="https://lmstudio.ai/docs/developer/core/server" target="_blank" rel="noreferrer">Инструкция LM Studio ↗</Link><Link href="https://docs.ollama.com/api/openai-compatibility" target="_blank" rel="noreferrer">Альтернатива: Ollama ↗</Link></div><Typography.Paragraph size="sm" color="muted">Обычный адрес LM Studio: http://127.0.0.1:1234/v1. У Ollama: http://localhost:11434/v1. Проверьте адрес в настройках своего сервера; ключ зависит от его настроек.</Typography.Paragraph><Button variant="outline" size="sm" onPress={() => { setBase("http://127.0.0.1:1234/v1"); setModels([]); }} isDisabled={busy}>Вставить адрес LM Studio</Button></div>
            <div className="flex flex-col gap-3"><Typography.Heading level={3}>У внешнего поставщика</Typography.Heading><Typography.Paragraph>В кабинете выбранного сервиса создайте API-ключ. Адрес API и идентификатор модели возьмите из его документации. Например, у OpenRouter адрес https://openrouter.ai/api/v1; название и стоимость модели указаны в каталоге.</Typography.Paragraph><div className="flex flex-wrap gap-3"><Link href="https://openrouter.ai/docs/quickstart" target="_blank" rel="noreferrer">Пример настройки API ↗</Link><Link href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">Ключи OpenRouter ↗</Link><Link href="https://openrouter.ai/models" target="_blank" rel="noreferrer">Модели и тарифы ↗</Link></div><Typography.Paragraph size="sm" color="muted">Это пример поставщика, а не готовое подключение. Запросы могут быть платными. При внешнем API поручение и нужный контекст передаются выбранному сервису.</Typography.Paragraph></div>
            <Typography.Paragraph>Введите адрес и ключ ниже, нажмите «Получить список моделей» и выберите модель. Если список недоступен, введите её точное имя из настроек сервера или документации.</Typography.Paragraph>
          </div></Accordion.Body></Accordion.Panel></Accordion.Item>
        </Accordion>
        <Label htmlFor="model-base">Адрес сервиса модели</Label>
        <Input id="model-base" type="url" value={base} onChange={(event) => { setBase(event.target.value); setModels([]); }} placeholder="Адрес из настроек сервера или документации" required disabled={busy} autoComplete="off" />
        <Label htmlFor="model-key">API-ключ · для локальной модели обычно не нужен</Label>
        <Input id="model-key" type="password" value={key} onChange={(event) => setKey(event.target.value)} placeholder={connection.has_key ? "Ключ уже настроен" : "Ключ от вашего поставщика"} disabled={busy} autoComplete="new-password" />
        {connection.has_key ? <p >Ключ настроен. Оставьте поле пустым, чтобы использовать его для прежнего адреса сервиса.</p> : null}
        <Label htmlFor="model-name">Название модели</Label>
        <Input id="model-name" value={model} onChange={(event) => setModel(event.target.value)} placeholder="Введите название модели" required disabled={busy} autoComplete="off" />
        <Button variant="outline" size="sm" onPress={loadModels} isPending={pending === "models"} isDisabled={busy || !base.trim()}>Получить список моделей</Button>
        {models.length ? <Select value={models.includes(model) ? model : null} onChange={(value) => { if (typeof value === "string") setModel(value); }} isDisabled={busy} placeholder="Выберите модель">
          <Label>Доступные модели</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
          <Select.Popover><ListBox>{models.map((id) => <ListBox.Item key={id} id={id} textValue={id}>{id}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
        </Select> : null}
        <Typography.Paragraph size="sm" color="muted">Расходы и лимиты определяет поставщик модели. Проверьте тариф до запуска; локальная модель использует ресурсы вашего компьютера.</Typography.Paragraph>
        <Checkbox isSelected={persist} onChange={setPersist} isDisabled={busy}><Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>Сохранить на этом устройстве для следующих запусков</Checkbox.Content></Checkbox>
        <p >{persist ? "Параметры и ключ сохраняет локальное приложение Worklife. В хранилище браузера и общую базу ключ не попадает." : "Подключение будет действовать до остановки Worklife. После перезапуска введите его снова."}</p>
        <p >{runAfter ? "После сохранения запустится ваша основная цель с выбранным уточнением. Текст поручения сохранён." : "Сохранение параметров не запускает агента. Доступность сервиса будет видна при запросе списка моделей или запуске поручения."}</p>
        {error ? <Alert status="danger"><Alert.Content><Alert.Description>{error}</Alert.Description></Alert.Content></Alert> : null}
      </form>
    </Dialog>
  );
}
