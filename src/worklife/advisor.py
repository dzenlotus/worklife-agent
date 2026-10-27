"""Private, deterministic evidence for the person's agent; no model or external actions."""

import hashlib
import math
import re
from copy import deepcopy

from .market import salary_terms
from .storage import canonical, now
from .workspace import uid

METHOD_NOTE = (
    "Буквальные совпадения в фактах с источниками помогают проверить резюме; они не доказывают владение навыком и не оценивают вероятность найма. "
    "Отсутствие подтверждения не означает отсутствия навыка. Условия из объявления нужно подтвердить."
)


def _labels(value):
    if isinstance(value, str):
        return [s.strip(" \t-•") for s in re.split(r"[\n;,]+", value) if s.strip(" \t-•")]
    if isinstance(value, list):
        return list(dict.fromkeys(label for item in value for label in _labels(item)))
    if isinstance(value, dict):
        for key in ("name", "text", "label", "code"):
            if isinstance(value.get(key), str):
                return _labels(value[key])
        return [label for key in ("required", "preferred", "items") for label in _labels(value.get(key))]
    return []


def _requirements(job):
    return list(
        dict.fromkeys(
            label for key in ("requirements", "key_skills", "skills") for label in _labels(job.get(key))
        )
    )


def _facts(value):
    return (
        [
            f
            for f in value
            if isinstance(f, dict)
            and all(isinstance(f.get(key), str) and f[key].strip() for key in ("id", "text", "source"))
        ]
        if isinstance(value, list)
        else []
    )


def _literal(phrase, text):
    return re.search(r"(?<!\w)" + re.escape(phrase.strip()) + r"(?!\w)", text, re.IGNORECASE)


def _positive_literal(phrase, text):
    # ponytail: conservative sentence-level negation filter; semantic review belongs to the external agent.
    for sentence in re.split(r"[.!?;](?:\s|$)|\n", text):
        match = _literal(phrase, sentence)
        if match and not re.search(
            r"\b(no|not|none|never|without|нет|не|без|\w+n['’]t)\b", sentence, re.IGNORECASE
        ):
            return True
    return False


def _evidence(fact):
    result = {
        "fact_id": fact["id"],
        "text": fact["text"],
        "source": fact["source"],
        "evidence_status": fact.get("evidence_status", "supplied"),
    }
    if fact.get("original_text"):
        result["original_text"] = fact["original_text"]
    return result


def _current_cv_facts(cv, profile_facts):
    return {
        fact["id"]: fact
        for fact in _facts(cv.get("facts"))
        if fact["id"] in cv.get("fact_ids", [])
        and fact["id"] in profile_facts
        and fact["source"] == profile_facts[fact["id"]]["source"]
        and (fact.get("original_text") or fact["text"]) == profile_facts[fact["id"]]["text"]
    }


def _matches(requirements, facts):
    matched, missing = [], []
    for requirement in requirements:
        evidence = [_evidence(f) for f in facts if _positive_literal(requirement, f["text"])]
        if evidence:
            matched.append(
                {
                    "requirement": requirement,
                    "match_method": "literal_phrase",
                    "fact_ids": [e["fact_id"] for e in evidence],
                    "evidence": evidence,
                }
            )
        else:
            missing.append(requirement)
    return matched, missing


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _context_hash(job, profile):
    volatile = {"fetched_at", "first_seen_at", "last_seen_at"}
    context = {"job": {key: value for key, value in job.items() if key not in volatile}, "profile": profile}
    return hashlib.sha256(canonical(context)).hexdigest()


def _text_list(value, label, required=False):
    if (
        not isinstance(value, list)
        or (required and not value)
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{label}: нужен список непустых текстов")
    return [item.strip() for item in value]


class Advisor:
    def __init__(self, workspace):
        self.workspace = workspace
        self.store = workspace.store

    def _profile(self):
        try:
            return self.workspace.get_profile()
        except ValueError:
            return {}

    def save_recommendation(self, job_id, verdict, reasons, evidence, questions=None, cv_id=None, priority=3):
        job, profile = self.store.get("job", job_id), self._profile()
        if verdict not in {"consider", "clarify", "reject"}:
            raise ValueError("Решение должно быть consider, clarify или reject")
        if type(priority) is not int or not 1 <= priority <= 5:
            raise ValueError("Приоритет должен быть целым числом от 1 до 5; это порядок, не вероятность")
        reasons = _text_list(reasons, "Основания", required=True)
        questions = _text_list([] if questions is None else questions, "Вопросы")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Нужны ссылки на факты профиля или поля вакансии")
        facts = {fact["id"]: fact for fact in _facts(profile.get("facts"))}
        cv = self.store.get("cv", cv_id) if cv_id is not None else None
        cv_facts = _current_cv_facts(cv, facts) if cv else {}
        if cv and (not cv_facts or set(cv.get("fact_ids", [])) - cv_facts.keys()):
            raise ValueError("Факты выбранного резюме не актуальны: подготовьте вариант из текущего профиля")
        resolved = []
        for item in evidence:
            if not isinstance(item, dict) or ("fact_id" in item) == ("job_field" in item):
                raise ValueError("Каждое доказательство должно указывать fact_id либо job_field")
            if "fact_id" in item:
                fact_id = item["fact_id"]
                if not isinstance(fact_id, str) or fact_id not in facts:
                    raise ValueError("Факт отсутствует в текущем профиле")
                fact = facts[fact_id]
                citation = _evidence(fact)
                if cv:
                    if (
                        fact_id not in cv.get("fact_ids", [])
                        or fact_id not in cv_facts
                        or cv_facts[fact_id]["source"] != fact["source"]
                    ):
                        raise ValueError(
                            "Доказательство выбранного резюме должно присутствовать в его фактах"
                        )
                    citation.update(cv_id=cv_id, cv_text=cv_facts[fact_id]["text"])
                resolved.append(citation)
            else:
                field = item["job_field"]
                if not isinstance(field, str) or field not in job or job[field] is None:
                    raise ValueError("Поле вакансии отсутствует или не содержит известного значения")
                resolved.append({"job_field": field, "value": deepcopy(job[field]), "source": job["url"]})
        try:
            previous = self.store.get("recommendation", job_id)
        except ValueError:
            previous = {}
        record = {
            "id": job_id,
            "job_id": job_id,
            "verdict": verdict,
            "reasons": reasons,
            "evidence": resolved,
            "questions": questions,
            "cv_id": cv_id,
            "priority": priority,
            "method": "external_agent",
            "context_hash": _context_hash(job, profile),
            "created_at": previous.get("created_at", now()),
            "updated_at": now(),
        }
        return self.store.put("recommendation", job_id, record)

    def _merge_assessment(self, row, job, profile, cvs):
        row.update(agent_assessment=None, assessment_status="none")
        row["recommended_cv_basis"] = "literal_phrase" if row["recommended_cv_id"] else None
        try:
            assessment = self.store.get("recommendation", job["id"])
        except ValueError:
            return row
        row["agent_assessment"] = assessment
        row["assessment_status"] = (
            "fresh" if assessment["context_hash"] == _context_hash(job, profile) else "stale"
        )
        if row["assessment_status"] == "stale":
            return row
        row["reasons"] = list(dict.fromkeys(row["reasons"] + assessment["reasons"]))
        row["questions"] = list(dict.fromkeys(row["questions"] + assessment["questions"]))
        if row["decision"] != "reject":
            verdict = assessment["verdict"]
            if verdict == "reject":
                row["decision"] = "reject"
            elif row["condition_questions"] or assessment["questions"] or verdict == "clarify":
                row["decision"] = "clarify"
            elif row["decision"] == "consider" or any("fact_id" in item for item in assessment["evidence"]):
                row["decision"] = "consider"
        if assessment["cv_id"] and row["decision"] != "reject":
            cv = next((cv for cv in cvs if cv["id"] == assessment["cv_id"]), None)
            language = job.get("cv_language") or job.get("application_language")
            if cv and (not language or (cv.get("language") or "").casefold() == language.casefold()):
                row["recommended_cv_id"] = cv["id"]
                row["recommended_cv_basis"] = "external_agent"
            else:
                row["questions"].append(
                    "Уточните доступность и язык резюме, выбранного агентом: соответствие запрошенному языку не подтверждено."
                )
                row["decision"] = "clarify"
        return row

    def _cv_match(self, job, profile, cvs):
        requirements = _requirements(job)
        required_language = job.get("cv_language") or job.get("application_language")
        known_facts = {f["id"]: f for f in _facts(profile.get("facts"))}
        variants = []
        for cv in cvs:
            selected = set(cv.get("fact_ids", []))
            facts = list(_current_cv_facts(cv, known_facts).values())
            facts_current = bool(selected) and len(facts) == len(selected)
            matched, missing = _matches(requirements, facts)
            language = cv.get("language")
            language_match = "not_specified"
            if required_language:
                language_match = (
                    "unknown"
                    if not language
                    else "match"
                    if language.casefold() == required_language.casefold()
                    else "mismatch"
                )
            notes = [METHOD_NOTE]
            if not facts_current:
                notes.append(
                    "Факты резюме изменились или отсутствуют в текущем профиле. Этот документ сохранён, но для рекомендации нужен актуальный вариант."
                )
            if language_match == "unknown":
                notes.append(f"Уточните язык этого резюме: для отклика запрошен {required_language}.")
            if language_match == "mismatch":
                notes.append(f"Нужен проверенный перевод резюме на язык {required_language}.")
            variants.append(
                {
                    "cv_id": cv["id"],
                    "name": cv.get("name", ""),
                    "language": language,
                    "language_match": language_match,
                    "facts_current": facts_current,
                    "matched_requirements": matched,
                    "missing_requirements": missing,
                    "notes": notes,
                }
            )
        eligible = [
            v
            for v in variants
            if v["facts_current"]
            and v["language_match"] in {"match", "not_specified"}
            and v["matched_requirements"]
        ]
        best_count = max((len(v["matched_requirements"]) for v in eligible), default=0)
        best = [v for v in eligible if len(v["matched_requirements"]) == best_count]
        recommended = best[0]["cv_id"] if len(best) == 1 else None
        notes = [METHOD_NOTE]
        if not cvs:
            notes.append("Создайте вариант резюме из фактов профиля с источниками или импортируйте резюме.")
        elif not requirements:
            notes.append(
                "В вакансии не указаны отдельные требования, поэтому пока недостаточно оснований для выбора резюме."
            )
        elif len(best) > 1:
            notes.append(
                "Несколько резюме содержат одинаковое число буквальных совпадений с требованиями. Выберите вариант вместе с агентом после проверки фактов."
            )
        elif not recommended:
            notes.append(
                "Пока нет резюме, в котором одновременно найдены факты по требованиям и подтверждён запрошенный язык."
            )
        else:
            notes.append(
                "Среди резюме на подходящем языке выбран вариант с наибольшим числом требований, буквально упомянутых в его фактах."
            )
        return {
            "status": "ready" if recommended else "needs_review",
            "job_id": job["id"],
            "variants": variants,
            "recommended_cv_id": recommended,
            "notes": notes,
        }

    def cv_match(self, job_id):
        return self._cv_match(self.store.get("job", job_id), self._profile(), self.store.list("cv"))

    def _assess(self, job, profile, cvs):
        rules = profile.get("constraints") or {}
        reasons, questions, rejected = [], [], []
        domain = self.workspace.job_domain(job)
        if domain and self.workspace.employer_blocked(domain):
            rejected.append("Работодатель заблокирован в вашем личном списке исключений.")
        if rules.get("remote") is True:
            if job.get("remote") is False:
                rejected.append("Посещение офиса противоречит вашему условию полностью удалённой работы.")
            elif job.get("remote") is not True:
                questions.append("Можно ли работать полностью удалённо из вашего местоположения?")
            else:
                reasons.append("В объявлении прямо указана полностью удалённая работа.")
        if rules.get("min_salary") is not None:
            expected = salary_terms({**rules, "salary_min": rules["min_salary"]})
            actual = salary_terms(job)
            comparable = (
                expected["valid"]
                and actual["valid"]
                and not any(
                    issue.startswith("unknown_") for terms in (expected, actual) for issue in terms["issues"]
                )
                and all(expected[k] != "unknown" and actual[k] == expected[k] for k in ("currency", "period"))
                and expected["gross"] is not None
                and actual["gross"] is expected["gross"]
            )
            if not comparable:
                questions.append(
                    "Уточните сумму, валюту, период выплаты и указание зарплаты до или после налогов, чтобы сравнить её с вашим минимумом. Пересчёт валют и налогов не выполнялся."
                )
            elif actual["upper"] is not None and actual["upper"] < expected["lower"]:
                rejected.append(
                    f"Верхняя граница зарплаты {actual['upper']} ниже вашего минимума {expected['lower']} {expected['currency']}/{expected['period']} при одинаковом учёте налогов."
                )
            elif actual["lower"] is None or actual["lower"] < expected["lower"]:
                questions.append(
                    f"Может ли работодатель гарантировать не менее {expected['lower']} {expected['currency']}/{expected['period']} с указанным вами учётом налогов?"
                )
            else:
                reasons.append(
                    "Нижняя граница зарплаты соответствует вашему минимуму: валюта, период выплаты и учёт налогов совпадают."
                )
        for field, constraint, label in (
            ("hours", "max_hours", "рабочие часы в неделю"),
            ("hiring_stages", "max_hiring_stages", "число этапов отбора"),
            ("test_hours", "max_test_hours", "часы на тестовое задание"),
        ):
            limit = rules.get(constraint)
            if limit is None:
                continue
            value = job.get(field)
            if not _number(limit) or not _number(value):
                questions.append(f"Уточните условие «{label}» с учётом вашего предела ({limit}).")
            elif value > limit:
                rejected.append(f"Условие «{label}» в объявлении ({value}) превышает ваш предел ({limit}).")
            else:
                reasons.append(
                    f"Условие «{label}» в объявлении ({value}) соответствует вашему пределу ({limit})."
                )
        roles = _labels(profile.get("target_roles"))
        if roles and not any(_literal(role, job.get("title", "")) for role in roles):
            questions.append(
                "Уточните, соответствуют ли реальные обязанности вашим целевым ролям: "
                + ", ".join(roles)
                + "."
            )
        locations = _labels(profile.get("target_locations"))
        if locations:
            advertised = _labels(job.get("location") or job.get("area"))
            if not any(_literal(target, place) for target in locations for place in advertised):
                questions.append(
                    "Можно ли выполнять эту работу из выбранных вами мест: " + ", ".join(locations) + "?"
                )
        for language in _labels(job.get("required_languages") or job.get("languages")):
            if language.casefold() not in {s.casefold() for s in _labels(profile.get("languages"))}:
                questions.append(
                    f"Уточните требуемый уровень языка {language} и добавьте сведения о вашем фактическом владении им."
                )
        if profile.get("income_deadline"):
            questions.append(
                f"Позволят ли сроки отбора, выхода на работу и первой выплаты получить доход к нужной вам дате {profile['income_deadline']}?"
            )
        supported = {
            "remote",
            "min_salary",
            "currency",
            "salary_period",
            "salary_gross",
            "max_hours",
            "max_hiring_stages",
            "max_test_hours",
        }
        for constraint, value in rules.items():
            if constraint not in supported and value is not None:
                questions.append(
                    f"Проверьте дополнительное условие «{constraint}»: {value}. Оно не оценивалось автоматически."
                )
        condition_questions = list(questions)
        matched, missing = _matches(_requirements(job), _facts(profile.get("facts")))
        if not _requirements(job):
            questions.append(
                "Какие навыки и опыт обязательны для этой вакансии? Отдельные требования пока не указаны."
            )
            condition_questions.append(questions[-1])
        elif missing:
            questions.append(
                "Проверьте, какие факты опыта можно подтвердить для требований: "
                + ", ".join(missing)
                + ". Уточните обязательные требования и добавьте только реальный опыт."
            )
        if matched:
            reasons.append(
                f"Требований с буквальным упоминанием в фактах профиля: {len(matched)}. Проверьте приведённые цитаты и источники."
            )
        cv_result = self._cv_match(job, profile, cvs)
        return {
            "job_id": job["id"],
            "decision": "reject" if rejected else "clarify" if questions else "consider",
            "reasons": rejected + reasons,
            "questions": questions,
            "condition_questions": condition_questions,
            "matched_requirements": matched,
            "missing_requirements": missing,
            "recommended_cv_id": cv_result["recommended_cv_id"],
            "cv_match": cv_result,
            "basis": METHOD_NOTE,
        }

    def report(self, job_ids=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Лимит должен быть целым числом от 1 до 200")
        if job_ids is not None and (
            not isinstance(job_ids, list) or any(not isinstance(i, str) for i in job_ids)
        ):
            raise ValueError("Нужен список идентификаторов сохранённых вакансий")
        profile = self._profile()
        missing = (["facts"] if not _facts(profile.get("facts")) else []) + (
            ["target_roles"] if not _labels(profile.get("target_roles")) else []
        )
        criteria = {
            key: profile[key]
            for key in ("constraints", "target_roles", "target_locations", "languages", "income_deadline")
            if key in profile
        }
        result = {
            "status": "needs_profile" if missing else "empty",
            "missing_profile_fields": missing,
            "recommendations": [],
            "next_actions": [],
            "criteria": criteria,
            "methodology": METHOD_NOTE,
            "ranking_basis": "Отклонённые вакансии всегда в конце. Для остальных учитываются свежий приоритет агента от 1 до 5, решение по условиям и буквальные совпадения в фактах. При равенстве используется идентификатор вакансии. Вероятность найма не рассчитывается.",
        }
        if missing:
            result["next_actions"] = [
                {
                    "kind": "complete_profile",
                    "title": "Заполните профиль",
                    "reason": "Добавьте "
                    + ", ".join(
                        {"facts": "факты опыта с источниками", "target_roles": "целевые роли"}[field]
                        for field in missing
                    )
                    + ".",
                }
            ]
            return result
        jobs = (
            self.store.list("job")
            if job_ids is None
            else [self.store.get("job", i) for i in dict.fromkeys(job_ids)]
        )
        cvs = self.store.list("cv")
        rows = [self._merge_assessment(self._assess(job, profile, cvs), job, profile, cvs) for job in jobs]
        order = {"consider": 0, "clarify": 1, "reject": 2}
        rows.sort(
            key=lambda r: (
                r["decision"] == "reject",
                r["agent_assessment"]["priority"] if r["assessment_status"] == "fresh" else 3,
                order[r["decision"]],
                -len(r["matched_requirements"]),
                len(r["missing_requirements"]),
                r["job_id"],
            )
        )
        result["recommendations"] = [dict(row, rank=i) for i, row in enumerate(rows[:limit], 1)]
        result["status"] = "ready" if rows else "empty"
        applications = {v["job_id"]: v for v in self.store.list("application")}
        for row in result["recommendations"]:
            if row["decision"] == "reject":
                continue
            if row["decision"] == "clarify" and row["questions"]:
                kind, title, reason = (
                    "clarify",
                    "Уточните условия вакансии и факты опыта",
                    row["questions"][0],
                )
            elif applications.get(row["job_id"], {}).get("stage") == "interview":
                kind, title, reason = (
                    "prepare_interview",
                    "Подготовьтесь к интервью",
                    "Проверьте факты опыта с источниками и требования вакансии.",
                )
            elif not row["recommended_cv_id"]:
                kind, title, reason = (
                    "review_cv" if cvs else "add_cv",
                    "Выберите или подготовьте резюме с подтверждёнными фактами",
                    row["cv_match"]["notes"][-1],
                )
            else:
                kind, title, reason = (
                    "consider",
                    "Рассмотрите вакансию",
                    "Заявленные условия соответствуют вашим ограничениям. Проверьте факты перед откликом.",
                )
            result["next_actions"].append(
                {"kind": kind, "title": title, "job_id": row["job_id"], "reason": reason}
            )
        return result

    def interview_brief(self, job_id):
        job = self.store.get("job", job_id)
        profile = self._profile()
        row = self._assess(job, profile, self.store.list("cv"))
        evidence = {e["fact_id"]: e for match in row["matched_requirements"] for e in match["evidence"]}
        preparation = [
            {
                "requirement": match["requirement"],
                "fact_ids": match["fact_ids"],
                "prompt": "Подготовьте правдивый пример по приведённым фактам: ваша роль, действия, результат и его подтверждение. Не придумывайте показатели.",
            }
            for match in row["matched_requirements"]
        ] + [
            {
                "requirement": gap,
                "fact_ids": [],
                "prompt": "Пример с источником пока не найден. Уточните требуемую глубину знаний и опишите реальный опыт или честный план обучения.",
            }
            for gap in row["missing_requirements"]
        ]
        return {
            "status": "ready" if _facts(profile.get("facts")) else "needs_profile",
            "job_id": job_id,
            "job": {key: job[key] for key in ("id", "title", "employer", "url", "platform") if key in job},
            "decision": row["decision"],
            "reasons": row["reasons"],
            "recommended_cv_id": row["recommended_cv_id"],
            "cv_match": row["cv_match"],
            "evidence": list(evidence.values()),
            "gaps": row["missing_requirements"],
            "questions_for_employer": row["questions"],
            "preparation": preparation,
            "notes": [
                METHOD_NOTE,
                "Здесь собраны вопросы для подготовки. Ответы кандидата и сведения о компании не выдумываются.",
            ],
        }

    def import_resume(self, name, text, language="ru", source="user"):
        if any(not isinstance(value, str) or not value.strip() for value in (name, text, source)):
            raise ValueError("Укажите название резюме, извлечённый текст и источник")
        if not isinstance(language, str) or not re.fullmatch(
            r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language
        ):
            raise ValueError("Укажите код языка BCP47, например ru или en")
        profile = self._profile()
        document_id = hashlib.sha256((source + "\0" + text).encode()).hexdigest()[:24]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        facts = [
            {
                "id": f"resume_{document_id}_{i}",
                "text": paragraph,
                "source": f"resume:{document_id}#paragraph:{i}",
                "origin": source,
                "evidence_status": "self_reported",
            }
            for i, paragraph in enumerate(paragraphs, 1)
        ]
        previous = {f["id"]: f for f in profile.get("facts", [])}
        selected = [previous.get(f["id"], f) for f in facts]
        self.workspace.save_profile(
            {**profile, "facts": list(previous.values()) + [f for f in facts if f["id"] not in previous]}
        )
        cv = {
            "id": uid(),
            "name": name.strip(),
            "headline": "",
            "summary": "",
            "language": language,
            "source": source,
            "source_document_id": document_id,
            "source_text": text,
            "fact_ids": [f["id"] for f in selected],
            "facts": selected,
            "markdown": f"# {profile.get('name', '')}\n\n{text}\n",
            "created_at": now(),
            "review_required": True,
            "evidence_status": "self_reported",
        }
        self.store.put("cv", cv["id"], cv)
        return {
            "status": "imported",
            "cv": cv,
            "imported_fact_ids": cv["fact_ids"],
            "notes": [
                "Абзацы резюме сохранены приватно как ваши собственные утверждения; независимая проверка достижений не проводилась. Прежние поля профиля и факты сохранены. Целевые роли нужно указать отдельно."
            ],
        }
