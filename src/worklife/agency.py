"""Private job-search records and measured follow-up guidance, without external actions."""

import hashlib
import math
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from statistics import median

from .market import salary_terms
from .storage import now
from .workspace import timestamp, uid

ACTIVE_STAGES = {"saved", "applied", "reply", "interview", "offer"}
OBSERVED_MESSAGE_STATUSES = {"observed", "received", "read"}
SALARY_ISSUE_LABELS = {
    "invalid_lower": "некорректная нижняя граница",
    "invalid_upper": "некорректная верхняя граница",
    "reversed_range": "нижняя граница выше верхней",
    "missing_salary": "зарплата не указана",
    "unknown_currency": "неизвестная валюта",
    "unknown_period": "неизвестный период оплаты",
    "unknown_gross": "не указано, до или после налогов",
}


def _observed_inbound(message):
    return message.get("direction") == "inbound" and message.get("status") in OBSERVED_MESSAGE_STATUSES


def _instant(value, field):
    try:
        return timestamp(value).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Для поля {field} укажите дату и время в формате ISO с часовым поясом") from None


def _day(value, field):
    try:
        if isinstance(value, str) and len(value) == 10:
            return date.fromisoformat(value)
        return timestamp(value).date()
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            f"Для поля {field} укажите дату ГГГГ-ММ-ДД либо дату и время ISO с часовым поясом"
        ) from None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class Agency:
    def __init__(self, workspace):
        self.workspace = workspace
        self.store = workspace.store

    def pipeline_update(self, job_id, stage="saved", cv_id=None, note="", next_action="", due_at=None):
        due_at = _instant(due_at, "due_at") if due_at is not None else None
        if not isinstance(next_action, str):
            raise ValueError("Следующий шаг (next_action) должен быть текстом")
        value = self.workspace.application(job_id, cv_id, stage, note)
        value.update(next_action=next_action, due_at=due_at, updated_at=now())
        return self.store.put("application", value["id"], value)

    def conversation_record(
        self,
        job_id=None,
        direction="unknown",
        channel="",
        text="",
        external_id="",
        in_reply_to="",
        occurred_at=None,
        status="observed",
    ):
        if direction not in {"inbound", "outbound", "unknown"}:
            raise ValueError(
                "Направление сообщения: inbound (входящее), outbound (исходящее) или unknown (неизвестно)"
            )
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError("Укажите канал сообщения")
        if not isinstance(text, str) or not text.strip() or len(text) > 100000:
            raise ValueError("Текст сообщения должен содержать от 1 до 100000 символов")
        if any(not isinstance(value, str) for value in (external_id, in_reply_to, status)):
            raise ValueError("Поля external_id, in_reply_to и status должны быть текстовыми")
        channel = channel.strip().lower()
        key = hashlib.sha256((channel + "\0" + external_id).encode()).hexdigest() if external_id else uid()
        previous = {}
        if external_id:
            try:
                previous = self.store.get("message", key)
            except ValueError:
                pass
            if previous:
                if _observed_inbound(previous) or not _observed_inbound(
                    {"direction": direction, "status": status}
                ):
                    return previous
                job_id = job_id or previous.get("job_id")
                in_reply_to = in_reply_to or previous.get("in_reply_to", "")
        if not job_id and in_reply_to:
            linked_jobs = {
                message["job_id"]
                for message in self.store.list("message")
                if message["channel"] == channel
                and message.get("external_id") == in_reply_to
                and message.get("job_id")
            }
            job_id = next(iter(linked_jobs)) if len(linked_jobs) == 1 else None
        if job_id:
            self.store.get("job", job_id)
        occurred_at = _instant(occurred_at or now(), "occurred_at")
        value = {
            "id": key,
            "job_id": job_id,
            "direction": direction,
            "channel": channel,
            "text": text,
            "external_id": external_id,
            "in_reply_to": in_reply_to,
            "occurred_at": occurred_at,
            "status": status,
            "unread": _observed_inbound({"direction": direction, "status": status}) and status != "read",
            "created_at": previous.get("created_at", now()),
        }
        self.store.put("message", key, value)
        self._advance_reply(value)
        return value

    def _advance_reply(self, message):
        job_id = message.get("job_id")
        if _observed_inbound(message) and job_id:
            application = next(
                (item for item in self.store.list("application") if item["job_id"] == job_id), None
            )
            if application and application["stage"] in {"saved", "applied"}:
                self.workspace.application(job_id, None, "reply", "Входящее сообщение сохранено локально")

    def conversation_update(self, message_id, job_id=None, read=None, unlink=False):
        """Change an explicit job association/local read flag, preserving the provider observation."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("Укажите ID сохранённого сообщения")
        if type(unlink) is not bool or read is not None and type(read) is not bool:
            raise ValueError("Поля read и unlink должны быть логическими значениями")
        if job_id is not None:
            if not isinstance(job_id, str) or not job_id.strip():
                raise ValueError("Укажите ID существующей вакансии")
            if unlink:
                raise ValueError("Нельзя одновременно назначить вакансию и снять связь")
            self.store.get("job", job_id)
        previous = self.store.get("message", message_id)
        value = deepcopy(previous)
        if unlink and value.get("job_id") is not None:
            value.update(job_id=None, metadata_link_basis="unassigned")
        elif job_id is not None and value.get("job_id") != job_id:
            value.update(job_id=job_id, metadata_link_basis="explicit")
        if read is True:
            value["unread"] = False
            if not value.get("read_at"):
                value["read_at"] = now()
        elif read is False:
            value["unread"] = _observed_inbound(value)
            if value.get("read_at"):
                value["read_at"] = None
        if value == previous:
            return previous
        value["updated_at"] = now()
        self.store.put("message", message_id, value)
        if value.get("job_id") != previous.get("job_id"):
            self._advance_reply(value)
        return value

    def conversation_list(self, job_id=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Параметр limit должен быть целым числом от 1 до 500")
        values = [
            value for value in self.store.list("message") if job_id is None or value["job_id"] == job_id
        ]
        return sorted(values, key=lambda value: (value["occurred_at"], value["created_at"]), reverse=True)[
            :limit
        ]

    def interview_save(
        self,
        job_id,
        scheduled_at,
        kind="interview",
        notes="",
        meeting_url="",
        status="scheduled",
        interview_id=None,
    ):
        self.store.get("job", job_id)
        scheduled_at = _instant(scheduled_at, "scheduled_at")
        if status not in {"scheduled", "rescheduled", "completed", "cancelled", "no_show"}:
            raise ValueError("Неизвестный статус интервью")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("Укажите тип интервью")
        previous = self.store.get("interview", interview_id) if interview_id else {}
        if previous and previous["job_id"] != job_id:
            raise ValueError("Нельзя перенести интервью в другую вакансию")
        value = {
            "id": interview_id or uid(),
            "job_id": job_id,
            "scheduled_at": scheduled_at,
            "kind": kind,
            "notes": notes,
            "meeting_url": meeting_url,
            "status": status,
            "created_at": previous.get("created_at", now()),
            "updated_at": now(),
        }
        return self.store.put("interview", value["id"], value)

    def offer_save(self, job_id, terms, notes="", status="received", offer_id=None):
        self.store.get("job", job_id)
        if not isinstance(terms, dict):
            raise ValueError("Условия оффера должны быть объектом с фактически полученными условиями")
        if status not in {"received", "negotiating", "accepted", "declined", "expired", "withdrawn"}:
            raise ValueError("Неизвестный статус оффера")
        for field in ("start_date", "income_date"):
            if terms.get(field) is not None:
                _day(terms[field], field)
        previous = self.store.get("offer", offer_id) if offer_id else {}
        if previous and previous["job_id"] != job_id:
            raise ValueError("Нельзя перенести оффер в другую вакансию")
        value = {
            "id": offer_id or uid(),
            "job_id": job_id,
            "terms": deepcopy(terms),
            "notes": notes,
            "status": status,
            "created_at": previous.get("created_at", now()),
            "updated_at": now(),
        }
        return self.store.put("offer", value["id"], value)

    def offer_compare(self, offer_ids=None):
        if offer_ids is not None and (
            not isinstance(offer_ids, list) or any(not isinstance(i, str) for i in offer_ids)
        ):
            raise ValueError("Поле offer_ids должно содержать список идентификаторов сохранённых офферов")
        offers = (
            self.store.list("offer")
            if offer_ids is None
            else [self.store.get("offer", i) for i in dict.fromkeys(offer_ids)]
        )
        try:
            profile = self.workspace.get_profile()
        except ValueError:
            profile = {}
        rules = profile.get("constraints") or {}
        criteria = {
            key: profile[key]
            for key in ("constraints", "income_deadline", "target_locations")
            if profile.get(key)
        }
        rows, groups = [], defaultdict(list)
        for offer in offers:
            terms = offer["terms"]
            actual = salary_terms(terms)
            questions, reasons, rejected = [], [], []
            comparable = False
            if not criteria:
                questions.append(
                    "Укажите свои обязательные условия оффера, минимальный доход и срок первой выплаты."
                )
            if rules.get("min_salary") is not None:
                expected = salary_terms({**rules, "salary_min": rules["min_salary"]})
                comparable = (
                    expected["valid"]
                    and actual["valid"]
                    and not expected["issues"]
                    and not actual["issues"]
                    and all(expected[key] == actual[key] for key in ("currency", "period", "gross"))
                )
                if not comparable:
                    questions.append(
                        "Уточните сопоставимые границы зарплаты, валюту, период оплаты и сумму до/после налогов; пересчёт не выполнялся."
                    )
                elif actual["upper"] is not None and actual["upper"] < expected["lower"]:
                    rejected.append(
                        "Верхняя граница зарплаты в оффере ниже вашего минимума при одинаковой базе оплаты."
                    )
                elif actual["lower"] is None or actual["lower"] < expected["lower"]:
                    questions.append(
                        "Может ли работодатель гарантировать ваш минимальный доход в пределах этой вилки?"
                    )
                else:
                    reasons.append(
                        "Указанная нижняя граница зарплаты соответствует вашему минимуму при одинаковой валюте, периоде и налоговой базе."
                    )
            else:
                questions.append(
                    "Укажите минимальную зарплату, валюту, период оплаты и сумму до/после налогов."
                )
                if not actual["valid"] or actual["issues"]:
                    questions.append(
                        "Уточните отсутствующие или некорректные условия оплаты: "
                        + ", ".join(SALARY_ISSUE_LABELS.get(issue, issue) for issue in actual["issues"])
                        + "."
                    )
            if rules.get("remote") is True:
                if terms.get("remote") is False:
                    rejected.append(
                        "Необходимость посещать офис противоречит вашему условию полностью удалённой работы."
                    )
                elif terms.get("remote") is not True:
                    questions.append("Подтвердите, что оффер допускает полностью удалённую работу.")
                else:
                    reasons.append("В оффере прямо указана полностью удалённая работа.")
            if rules.get("max_hours") is not None:
                if not _number(rules["max_hours"]) or not _number(terms.get("hours")):
                    questions.append(
                        "Уточните число рабочих часов в неделю и сопоставьте с вашим максимумом."
                    )
                elif terms["hours"] > rules["max_hours"]:
                    rejected.append("Число рабочих часов в неделю превышает ваш максимум.")
                else:
                    reasons.append("Число рабочих часов в неделю не превышает ваш максимум.")
            locations = profile.get("target_locations") or []
            if isinstance(locations, str):
                locations = [locations]
            if locations:
                if not terms.get("location") or not any(
                    str(terms["location"]).casefold() == str(location).casefold() for location in locations
                ):
                    questions.append(
                        "Уточните, совместимо ли место работы в оффере с выбранными вами регионами."
                    )
            deadline = profile.get("income_deadline")
            if deadline:
                try:
                    deadline_day = _day(deadline, "income_deadline")
                except ValueError:
                    questions.append("Уточните конкретную дату, к которой должен поступить первый доход.")
                else:
                    if not terms.get("income_date"):
                        questions.append(
                            "Уточните дату первого дохода: дата начала работы не определяет дату выплаты."
                        )
                    elif _day(terms["income_date"], "income_date") > deadline_day:
                        rejected.append("Первый доход поступит позже указанного вами срока.")
                    else:
                        reasons.append("Первая выплата назначена не позже указанного вами срока.")
            supported = {"min_salary", "currency", "salary_period", "salary_gross", "remote", "max_hours"}
            for key, value in rules.items():
                if key not in supported and value is not None:
                    questions.append(
                        f"Проверьте дополнительное условие «{key}»: {value}; оно не оценивалось автоматически."
                    )
            if actual["valid"]:
                groups[(actual["currency"], actual["period"], actual["gross"])].append(offer["id"])
            rows.append(
                {
                    "offer_id": offer["id"],
                    "job_id": offer["job_id"],
                    "status": offer["status"],
                    "terms": deepcopy(terms),
                    "salary": actual,
                    "comparable": comparable,
                    "decision": "reject" if rejected else "clarify" if questions else "consider",
                    "reasons": rejected + reasons,
                    "questions": questions,
                }
            )
        return {
            "status": "empty" if not offers else "ready" if criteria else "needs_profile",
            "criteria": criteria,
            "offers": rows,
            "salary_groups": [
                {"currency": key[0], "period": key[1], "gross": key[2], "offer_ids": ids}
                for key, ids in groups.items()
            ],
            "limitations": [
                "Сравниваются только записанные условия и ваши явные ограничения. Отсутствующие льготы и условия не предполагаются.",
                "Валюты, периоды оплаты и суммы до/после налогов учитываются отдельно. Сравнение не ранжирует, не принимает и не отправляет офферы.",
            ],
        }

    def _due_actions(self, as_of):
        values = [
            {
                "kind": "pipeline",
                "id": item["id"],
                "job_id": item["job_id"],
                "title": item["next_action"],
                "due_at": item.get("due_at"),
            }
            for item in self.store.list("application")
            if item["stage"] in ACTIVE_STAGES
            and item.get("next_action")
            and item.get("due_at")
            and timestamp(item["due_at"]) <= as_of
        ]
        values.extend(
            {
                "kind": "task",
                "id": item["id"],
                "job_id": item.get("job_id"),
                "title": item["title"],
                "due_at": item.get("due_at"),
            }
            for item in self.workspace.due_tasks(as_of.isoformat())
        )
        return sorted(values, key=lambda value: value.get("due_at") or "")

    def search_review(self, days=30):
        if type(days) is not int or not 1 <= days <= 3650:
            raise ValueError("Параметр days должен быть целым числом от 1 до 3650")
        end = timestamp(now())
        start = end - timedelta(days=days)
        applications = [
            item
            for item in self.store.list("application")
            if any(start <= timestamp(event["at"]) <= end for event in item.get("history", []))
        ]
        inbound = defaultdict(list)
        messages = [
            message
            for message in self.store.list("message")
            if start <= timestamp(message["occurred_at"]) <= end
        ]
        for message in messages:
            if _observed_inbound(message) and message.get("job_id"):
                inbound[message["job_id"]].append(timestamp(message["occurred_at"]))
        delays, pending = [], []
        applied, replied = 0, 0
        for item in applications:
            submissions = [
                timestamp(event["at"])
                for event in item["history"]
                if event["stage"] == "applied" and timestamp(event["at"]) <= end
            ]
            replies = inbound[item["job_id"]] + [
                timestamp(event["at"])
                for event in item["history"]
                if event["stage"] == "reply" and start <= timestamp(event["at"]) <= end
            ]
            if replies:
                replied += 1
            if not submissions:
                continue
            submitted = min(submissions)
            if not start <= submitted <= end:
                continue
            applied += 1
            response_times = [reply for reply in replies if reply >= submitted]
            if response_times:
                delays.append((min(response_times) - submitted).total_seconds() / 3600)
            elif item["stage"] == "applied":
                pending.append(
                    {
                        "job_id": item["job_id"],
                        "applied_at": submitted.isoformat().replace("+00:00", "Z"),
                        "waiting_hours": (end - submitted).total_seconds() / 3600,
                        "status": "awaiting_reply",
                    }
                )
        return {
            "status": "ready" if applications or messages else "empty",
            "window": {
                "from": start.isoformat().replace("+00:00", "Z"),
                "to": end.isoformat().replace("+00:00", "Z"),
                "days": days,
            },
            "counts": {
                "applications": len(applications),
                "applied": applied,
                "replied": replied,
                "pending": len(pending),
                "messages": len(messages),
                "interviews": sum(
                    start <= timestamp(item["created_at"]) <= end for item in self.store.list("interview")
                ),
                "offers": sum(
                    start <= timestamp(item["created_at"]) <= end for item in self.store.list("offer")
                ),
            },
            "stages": dict(Counter(item["stage"] for item in applications)),
            "reply_delays": {
                "n": len(delays),
                "median_hours": median(delays) if delays else None,
                "min_hours": min(delays) if delays else None,
                "max_hours": max(delays) if delays else None,
            },
            "pending": pending,
            "due_actions": self._due_actions(end),
            "limitations": [
                "Обзор описывает только локальные записи и не оценивает будущую вероятность найма.",
                "Ожидание без записанного ответа не означает отказ. Сообщения с неизвестным направлением не считаются ответами.",
                "В выборку входят вакансии с изменениями этапа за выбранный период; задержка ответа считается для первых откликов в этом периоде. Просроченные действия включают все текущие активные задачи.",
                "Задержки измеряются только для откликов с записанным ответом; ожидание ответа учитывается отдельно.",
            ],
        }

    def brief(self):
        at = now()
        moment = timestamp(at)
        messages = sorted(self.store.list("message"), key=lambda value: value["occurred_at"], reverse=True)
        unread = [message for message in messages if message.get("unread")]
        unassigned = [message for message in messages if not message.get("job_id")]
        interviews = sorted(
            (item for item in self.store.list("interview") if item["status"] in {"scheduled", "rescheduled"}),
            key=lambda item: item["scheduled_at"],
        )
        offers = [item for item in self.store.list("offer") if item["status"] in {"received", "negotiating"}]
        due = self._due_actions(moment)
        steps = [
            {
                "kind": "follow_up",
                "job_id": item.get("job_id"),
                "title": item["title"],
                "reason": "Наступил срок записанного следующего шага.",
            }
            for item in due
        ]
        if unassigned:
            steps.append(
                {
                    "kind": "assign_messages",
                    "title": "Свяжите непривязанные сообщения с вакансиями",
                    "reason": f"Сообщений без подтверждённой связи с вакансией: {len(unassigned)}.",
                }
            )
        if unread:
            steps.append(
                {
                    "kind": "read_messages",
                    "title": "Просмотрите входящие сообщения",
                    "reason": f"Непрочитанных входящих сообщений: {len(unread)}.",
                }
            )
        for item in interviews:
            steps.append(
                {
                    "kind": "prepare_interview",
                    "job_id": item["job_id"],
                    "title": "Подготовьтесь к назначенному интервью",
                    "reason": item["scheduled_at"],
                }
            )
        if offers:
            steps.append(
                {
                    "kind": "compare_offers",
                    "title": "Проверьте полученные условия офферов",
                    "reason": "Сопоставьте известные условия с вашими явными требованиями.",
                }
            )
        return {
            "generated_at": at,
            "due_actions": due,
            "unread_messages": unread,
            "unassigned_messages": unassigned,
            "interviews": interviews,
            "offers": offers,
            "next_steps": steps,
        }
