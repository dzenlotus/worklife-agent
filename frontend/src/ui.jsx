import { Card, Chip, Accordion, Button, Modal, Table, Alert, Typography, Separator } from "@heroui/react";
import { formatDate, label } from "./model.js";

export function Status({ value, children }) {
  const color = ["running", "queued", "reply", "offer", "active"].includes(value) ? "accent"
    : ["completed", "sent", "done", "confirmed", "verified", "success"].includes(value) ? "success"
      : ["failed", "uncertain", "blocked", "rejected"].includes(value) ? "danger" : "default";
  return <Chip color={color} size="sm" variant="soft">{children || label(value)}</Chip>;
}
export function Panel({ title, action, children, className = "" }) {
  return <Card className={className}>
    {title || action ? <Card.Header className="flex flex-row flex-wrap items-center justify-between gap-3"><Card.Title>{title}</Card.Title>{action}</Card.Header> : null}
    <Card.Content className="flex flex-col gap-4">{children}</Card.Content>
  </Card>;
}
export function PageHeading({ title, description, children }) {
  return <div className="flex flex-wrap items-start justify-between gap-4">
    <div className="flex flex-col gap-2"><Typography.Heading level={1}>{title}</Typography.Heading>{description ? <p>{description}</p> : null}</div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>;
}
export function Empty({ title, children, action }) {
  return <div className="flex flex-col gap-3 py-4"><Typography.Heading level={3}>{title}</Typography.Heading><p>{children}</p>{action}</div>;
}
export function PrivateNote() {
  return <Alert><Alert.Content><Alert.Description>Личная база хранится на этом устройстве. Подключённый MCP-агент получает данные для поручения. В общую базу передаются только наблюдения о работодателях.</Alert.Description></Alert.Content></Alert>;
}
export function DataTable({ headers, rows }) {
  return <>
    <div className="flex flex-col gap-4 sm:hidden">
      {rows.map((row, index) => <div className="flex flex-col gap-3" key={index}>
        <div>{row[0] ?? "—"}</div>
        <dl className="flex flex-col gap-2">{row.slice(1).map((cell, cellIndex) => <div className="flex flex-wrap items-center justify-between gap-2" key={cellIndex}>
          {headers[cellIndex + 1] ? <dt><Typography.Paragraph size="sm" color="muted">{headers[cellIndex + 1]}</Typography.Paragraph></dt> : null}
          <dd>{cell ?? "—"}</dd>
        </div>)}</dl>
        {index < rows.length - 1 ? <Separator /> : null}
      </div>)}
    </div>
    <div className="hidden sm:block"><Table><Table.ScrollContainer><Table.Content aria-label={headers.filter(Boolean).join(", ")}>
    <Table.Header>{headers.map((header, index) => <Table.Column key={index} id={`column-${index}`} isRowHeader={index === 0}>{header || "Действия"}</Table.Column>)}</Table.Header>
    <Table.Body>{rows.map((row, index) => <Table.Row key={index} id={`row-${index}`}>{row.map((cell, cellIndex) => <Table.Cell key={cellIndex}>{cell ?? "—"}</Table.Cell>)}</Table.Row>)}</Table.Body>
  </Table.Content></Table.ScrollContainer></Table></div></>;
}
export function AgentButton({ onPress, children = "Подготовить поручение" }) {
  return <Button variant="outline" size="sm" onPress={onPress}>{children}</Button>;
}
export function DetailAccordion({ title, children, id = "details" }) {
  return <Accordion><Accordion.Item id={id}>
    <Accordion.Heading><Accordion.Trigger>{title}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
    <Accordion.Panel><Accordion.Body><div className="flex flex-col gap-3">{children}</div></Accordion.Body></Accordion.Panel>
  </Accordion.Item></Accordion>;
}
export function RecordList({ items, render, empty }) {
  return items.length ? <div className="flex flex-col gap-4">{items.map((item, index) => <div className="flex flex-wrap items-start gap-4" key={item.id || index}>{render(item)}</div>)}</div> : <p>{empty}</p>;
}
export function Timestamp({ value }) { return <time dateTime={value || undefined}>{formatDate(value)}</time>; }
export function Dialog({ open, onClose, title, children, footer, size = "lg" }) {
  return <Modal><Modal.Backdrop isOpen={open} onOpenChange={(value) => { if (!value) onClose(); }}>
    <Modal.Container size={size}><Modal.Dialog>
      <Modal.CloseTrigger aria-label="Закрыть" />
      <Modal.Header><Modal.Heading>{title}</Modal.Heading></Modal.Header>
      <Modal.Body>{children}</Modal.Body>
      {footer ? <Modal.Footer>{footer}</Modal.Footer> : null}
    </Modal.Dialog></Modal.Container>
  </Modal.Backdrop></Modal>;
}
