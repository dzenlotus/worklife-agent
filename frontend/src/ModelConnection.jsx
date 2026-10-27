import { useEffect, useState } from "react";
import { Button, Input, Label, Checkbox, Alert, Select, ListBox } from "@heroui/react";
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
        <p >Нужны адрес сервиса, название модели и, для внешнего сервиса, ваш API-ключ. Подойдёт совместимый с OpenAI сервис или локальная модель. Стоимость запросов определяет ваш поставщик.</p>
        <Label htmlFor="model-base">Адрес сервиса модели</Label>
        <Input id="model-base" type="url" value={base} onChange={(event) => { setBase(event.target.value); setModels([]); }} placeholder="https://api.example.com/v1" required disabled={busy} autoComplete="off" />
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
        <Checkbox isSelected={persist} onChange={setPersist} isDisabled={busy}><Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control>Сохранить на этом устройстве для следующих запусков</Checkbox.Content></Checkbox>
        <p >{persist ? "Параметры и ключ сохраняет локальное приложение Worklife. В хранилище браузера и общую базу ключ не попадает." : "Подключение будет действовать до остановки Worklife. После перезапуска введите его снова."}</p>
        <p >{runAfter ? "После сохранения запустится ваша основная цель с выбранным уточнением. Текст поручения сохранён." : "Сохранение параметров не запускает агента. Доступность сервиса будет видна при запросе списка моделей или запуске поручения."}</p>
        {error ? <Alert status="danger"><Alert.Content><Alert.Description>{error}</Alert.Description></Alert.Content></Alert> : null}
      </form>
    </Dialog>
  );
}
