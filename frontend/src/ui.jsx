import { t } from "./i18n.js";
import {
  Card,
  Chip,
  Accordion,
  Button,
  Modal,
  Table,
  Alert,
  Typography,
  Separator,
} from "@heroui/react";
import { typographyVariants } from "@heroui/styles";

import { formatDate, label } from "./model.js";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BriefcaseBusiness,
  Building2,
  Calendar,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  FlaskConical,
  FolderOpen,
  House,
  List,
  Menu,
  Mail,
  Laptop,
  MapPin,
  RefreshCw,
  Search,
  Settings,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  UsersRound,
  Wrench,
} from "lucide-react";

const icons = {
  overview: House,
  market: BarChart3,
  search: BriefcaseBusiness,
  messages: Mail,
  remote: Laptop,
  location: MapPin,
  employers: Building2,
  schedules: Calendar,
  materials: FileText,
  tools: Wrench,
  settings: Settings,
  cv: FileText,
  strengths: Sparkles,
  repositories: FolderOpen,
  resources: FileText,
  accounts: UsersRound,
  experiments: FlaskConical,
  tactics: SquareTerminal,
  activity: Activity,
  discover: Search,
  refresh: RefreshCw,
  next: ChevronRight,
  external: ArrowUpRight,
  check: Check,
  clock: Clock3,
  list: List,
  menu: Menu,
  verified: ShieldCheck,
};
export function Icon({ name, className = "size-5 shrink-0" }) {
  const Glyph = icons[name] || Activity;
  return <Glyph aria-hidden="true" className={className} strokeWidth={1.75} />;
}
export function IconCircle({ name }) {
  return (
    <span className="icon-circle">
      <Icon name={name} />
    </span>
  );
}
export function Status({ value, children }) {
  const kind = [
    "completed",
    "sent",
    "done",
    "confirmed",
    "verified",
    "success",
  ].includes(value)
    ? "success"
    : ["failed", "blocked", "rejected"].includes(value)
      ? "danger"
      : value === "partial"
        ? "warning"
        : ["running", "queued", "reply", "offer", "active"].includes(value)
          ? "active"
          : "neutral";
  return (
    <span className={`status status-${kind}`} data-status={value}>
      {kind === "success" ? <Icon name="check" /> : null}
      {children || label(value)}
    </span>
  );
}
export function Panel({ title, action, children, className = "", id, tabIndex }) {
  return (
    <section id={id} tabIndex={tabIndex} className={`panel ${className}`}>
      {title || action ? (
        <header className="panel-heading">
          {title ? <h2>{title}</h2> : null}
          {action}
        </header>
      ) : null}
      <div className="panel-content">{children}</div>
    </section>
  );
}
export function PageHeading({ title, description, children }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      <div className="page-actions">{children}</div>
    </div>
  );
}
export function Empty({ title, children, action, icon }) {
  return (
    <div className="empty-state">
      {icon ? <span className="empty-mark"><Icon name={icon} /></span> : null}
      <div>
        <h3 className="empty-title">{title}</h3>
        <div className="empty-description">{children}</div>
      </div>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}
export function PrivateNote() {
  return (
    <Alert>
      <Alert.Content>
        <Alert.Description>{t("Личная база хранится на этом устройстве. Подключённый MCP-агент получает данные для поручения. В общую базу передаются только наблюдения о работодателях.")}</Alert.Description>
      </Alert.Content>
    </Alert>
  );
}
export function DataTable({ headers, rows }) {
  return (
    <>
      <div className="flex flex-col gap-4 sm:hidden">
        {rows.map((row, index) => (
          <div className="flex flex-col gap-3" key={index}>
            <div>{row[0] ?? "—"}</div>
            <dl className="flex flex-col gap-2">
              {row.slice(1).map((cell, cellIndex) => (
                <div
                  className="flex flex-wrap items-center justify-between gap-2"
                  key={cellIndex}
                >
                  {headers[cellIndex + 1] ? (
                    <dt>
                      <Typography.Paragraph size="sm" color="muted">
                        {headers[cellIndex + 1]}
                      </Typography.Paragraph>
                    </dt>
                  ) : null}
                  <dd>{cell ?? "—"}</dd>
                </div>
              ))}
            </dl>
            {index < rows.length - 1 ? <Separator /> : null}
          </div>
        ))}
      </div>
      <div className="hidden sm:block">
        <Table>
          <Table.ScrollContainer>
            <Table.Content aria-label={headers.filter(Boolean).join(", ")}>
              <Table.Header>
                {headers.map((header, index) => (
                  <Table.Column
                    key={index}
                    id={`column-${index}`}
                    isRowHeader={index === 0}
                  >
                    {header || t("Действия")}
                  </Table.Column>
                ))}
              </Table.Header>
              <Table.Body>
                {rows.map((row, index) => (
                  <Table.Row key={index} id={`row-${index}`}>
                    {row.map((cell, cellIndex) => (
                      <Table.Cell key={cellIndex}>{cell ?? "—"}</Table.Cell>
                    ))}
                  </Table.Row>
                ))}
              </Table.Body>
            </Table.Content>
          </Table.ScrollContainer>
        </Table>
      </div>
    </>
  );
}
export function AgentButton({ onPress, children = t("Подготовить поручение") }) {
  return (
    <Button variant="outline" size="sm" onPress={onPress}>
      {children}
    </Button>
  );
}
export function DetailAccordion({
  title,
  children,
  id = "details",
  level = 3,
}) {
  return (
    <Accordion>
      <Accordion.Item id={id}>
        <Accordion.Heading level={level}>
          <Accordion.Trigger>
            {title}
            <Accordion.Indicator />
          </Accordion.Trigger>
        </Accordion.Heading>
        <Accordion.Panel>
          <Accordion.Body>
            <div className="flex min-w-0 flex-col gap-3 overflow-x-auto">
              {children}
            </div>
          </Accordion.Body>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
export function RecordList({ items, render, empty }) {
  return items.length ? (
    <div className="flex flex-col gap-6">
      {items.map((item, index) => (
        <div className="flex flex-col gap-6" key={item.id || index}>
          {index ? <Separator /> : null}
          <div className="flex flex-wrap items-start gap-4">{render(item)}</div>
        </div>
      ))}
    </div>
  ) : (
    <Typography.Paragraph className="py-4" color="muted">
      {empty}
    </Typography.Paragraph>
  );
}
export function Timestamp({ value }) {
  return <time dateTime={value || undefined}>{formatDate(value)}</time>;
}
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  size = "lg",
}) {
  return (
    <Modal.Backdrop
      isOpen={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
    >
      <Modal.Container size={size}>
        <Modal.Dialog>
          <Modal.CloseTrigger aria-label={t("Закрыть")} />
          <Modal.Header>
            <Modal.Heading>{title}</Modal.Heading>
          </Modal.Header>
          <Modal.Body>
            <div className="flex min-w-0 flex-col gap-5">{children}</div>
          </Modal.Body>
          {footer ? <Modal.Footer>{footer}</Modal.Footer> : null}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
