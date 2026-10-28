import { useState } from "react";
import { Button, Link } from "@heroui/react";
import { Copy, Share2, Star } from "lucide-react";
import { t } from "./i18n.js";
import { repositoryUrl, siteUrl } from "./page-metadata.js";
import { copyProjectLink, shareProject } from "./project-actions.js";
import "./project-actions.css";

export default function ProjectActions({ placement = "site" }) {
  const [feedback, setFeedback] = useState("");
  const [pending, setPending] = useState(false);
  async function share() {
    setPending(true);
    setFeedback("");
    setFeedback(await shareProject(navigator, t("Поиск работы с личным ИИ-агентом.")));
    setPending(false);
  }

  return <div className={`project-actions project-actions--${placement}`}>
    <div className="project-actions-buttons" role="group" aria-label={t("О проекте Worklife")}>
      <Button className="project-action" variant="ghost" onPress={share} isDisabled={pending} aria-label={t("Поделиться проектом Worklife")} title={t("Поделиться проектом Worklife")}>
        <Share2 aria-hidden="true" /><span className="project-action-label">{t("Поделиться")}</span>
      </Button>
      <Link className="project-action project-action-star" href={repositoryUrl} target="_blank" rel="noopener noreferrer" aria-label={t("Поставить звезду на GitHub — открыть репозиторий Worklife")} title={t("Поставить звезду на GitHub")}>
        <Star aria-hidden="true" /><span className="project-action-label">{t("Звезда")}</span>
      </Link>
    </div>
    <div className="project-actions-notice">
      <p className="project-actions-feedback" role="status" aria-live="polite">{feedback === "copied" ? t("Ссылка на проект скопирована.") : feedback === "manual" ? t("Не удалось скопировать ссылку. Выделите адрес ниже и скопируйте его вручную.") : ""}</p>
      {feedback === "manual" ? <div className="project-actions-fallback">
        <Link href={siteUrl} target="_blank" rel="noopener noreferrer">{t("Открыть сайт проекта")}</Link>
        <input aria-label={t("Публичная ссылка на Worklife")} value={siteUrl} readOnly onFocus={event => event.target.select()} />
        <Button variant="ghost" onPress={async () => setFeedback(await copyProjectLink(navigator))}><Copy aria-hidden="true" />{t("Скопировать ссылку")}</Button>
      </div> : null}
    </div>
  </div>;
}
