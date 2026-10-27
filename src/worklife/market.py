"""Private, reproducible descriptions of explicitly selected advertised jobs."""

import math
from collections import Counter, defaultdict
from copy import deepcopy
from statistics import median
from urllib.parse import unquote_plus, urlsplit, urlunsplit
from uuid import uuid4

from .storage import canonical, now

PERIODS = {
    "month": {"month", "monthly", "mo", "per month", "месяц", "месяц/мес", "мес", "мес.", "в месяц"},
    "year": {"year", "yearly", "annual", "annually", "annum", "per year", "год", "в год"},
    "week": {"week", "weekly", "per week", "неделя", "в неделю"},
    "day": {"day", "daily", "per day", "день", "в день"},
    "hour": {"hour", "hourly", "hr", "per hour", "час", "в час"},
}
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_source_platform",
    "utm_creative_format",
    "utm_marketing_tactic",
    "gclid",
    "fbclid",
    "msclkid",
}
SCOPE_FIELDS = ("role", "level", "region", "work_format")
FILTER_FIELDS = {
    *SCOPE_FIELDS,
    "location",
    "source",
    "platform",
    "employer",
    "currency",
    "period",
    "gross",
    "job_ids",
}
METHODOLOGY = (
    "Описательная выборка опубликованных вакансий, выбранных явно; дубли объединены только по строгим признакам. "
    "Зарплаты сгруппированы отдельно по валюте, периоду оплаты и сумме до/после налогов либо неизвестной базе; пересчёт валют и периодов не выполняется. "
    "Нижние и верхние границы считаются отдельно; середины рассчитываются только для закрытых вилок. "
    "Квартили используют линейную интерполяцию в точке (n - 1) * p. Счётчики относятся к уникальным вакансиям, кроме наблюдений "
    "и дублей; каждая вакансия учитывается во всех её источниках, поэтому сумма по источникам может превышать число вакансий. "
    "Условия группы дублей берутся из первого выбранного наблюдения; все исходные наблюдения сохраняются. "
    "Выборка не оценивает весь рынок, фактические выплаты, динамику рынка или вероятность найма."
)


def _text(value):
    if isinstance(value, dict):
        value = value.get("name") or value.get("label") or value.get("id")
    return " ".join(str(value or "").split())


def salary_terms(job):
    """Normalize explicit pay, retaining unknown basis and rejecting malformed bounds."""
    salary = job.get("salary") if isinstance(job.get("salary"), dict) else {}
    lower = job.get("salary_min", salary.get("from", salary.get("min")))
    upper = job.get("salary_max", salary.get("to", salary.get("max")))
    issues = []
    for label, value in (("lower", lower), ("upper", upper)):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))
            or value < 0
        ):
            issues.append("invalid_" + label)
    if "invalid_lower" in issues:
        lower = None
    if "invalid_upper" in issues:
        upper = None
    if lower is not None and upper is not None and lower > upper:
        issues.append("reversed_range")
    if lower is None and upper is None and not issues:
        issues.append("missing_salary")
    valid = not issues
    currency = _text(job.get("currency", salary.get("currency"))).upper() or "unknown"
    currency = "RUB" if currency in {"RUR", "РУБ", "РУБ.", "₽"} else currency
    period = _text(job.get("salary_period", salary.get("period", salary.get("interval")))).lower()
    period = next((key for key, aliases in PERIODS.items() if period in aliases), period or "unknown")
    gross = job.get("salary_gross", salary.get("gross"))
    if not isinstance(gross, bool):
        gross = None
    for field, value in (("currency", currency), ("period", period), ("gross", gross)):
        if value in ("unknown", None) or (field == "period" and value not in PERIODS):
            issues.append("unknown_" + field)
    return {
        "lower": lower,
        "upper": upper,
        "currency": currency,
        "period": period,
        "gross": gross,
        "valid": valid,
        "issues": issues,
    }


def _url(value):
    try:
        parsed = urlsplit(value or "")
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        # Preserve all meaningful parameters, their order, paths, and fragment routes.
        query = "&".join(
            part
            for part in parsed.query.split("&")
            if unquote_plus(part.split("=", 1)[0]).lower() not in TRACKING_PARAMS
        )
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, query, parsed.fragment))
    except ValueError:
        return None


def _identity_keys(job):
    keys = []
    if job.get("canonical_id"):
        keys.append(("canonical_id", str(job["canonical_id"])))
    url = _url(job.get("canonical_url") or job.get("url"))
    if url:
        keys.append(("url", url))
    fields = [_text(job.get(field)) for field in ("employer", "title", "location", "description")]
    # Missing descriptions or locations cannot prove that similar titles are the same opening.
    if all(fields):
        pay = {
            key: job.get(key)
            for key in ("salary", "salary_min", "salary_max", "currency", "salary_period", "salary_gross")
        }
        keys.append(("content", canonical([fields, pay])))
    return keys


def _deduplicate(observations):
    groups, seen = [], {}
    for job in observations:
        keys = _identity_keys(job)
        matches = sorted({seen[key] for key in keys if key in seen})
        target = matches[0] if matches else len(groups)
        if not matches:
            groups.append([])
        groups[target].append(job)
        # An explicit canonical ID may connect two earlier URL groups.
        for other in matches[1:]:
            groups[target].extend(groups[other])
            groups[other] = []
            for key in seen:
                if seen[key] == other:
                    seen[key] = target
        for key in keys:
            seen[key] = target
    return [group for group in groups if group]


def _work_formats(job):
    value = job.get("work_format")
    if value:
        return [_text(v).lower() for v in (value if isinstance(value, list) else [value])]
    if job.get("remote") is True:
        return ["remote"]
    # remote=False rules out fully remote; it does not establish office vs hybrid.
    return ["unknown"]


def _requirements(job):
    value = job.get("requirements") or job.get("key_skills") or []
    return [_text(item) for item in (value if isinstance(value, list) else [value]) if _text(item)]


def _matches(job, filters):
    salary = salary_terms(job)
    fields = {
        "role": _text(job.get("role") or job.get("title")),
        "level": _text(job.get("level") or job.get("seniority")) or "unknown",
        "region": _text(job.get("region") or job.get("location")) or "unknown",
        "location": _text(job.get("location")) or "unknown",
        "work_format": _work_formats(job),
        "source": _text(job.get("platform")) or "unknown",
        "platform": _text(job.get("platform")) or "unknown",
        "employer": _text(job.get("employer")) or "unknown",
        "currency": salary["currency"],
        "period": salary["period"],
        "gross": salary["gross"],
        "job_ids": job["id"],
    }
    for key, expected in filters.items():
        actual = fields[key] if isinstance(fields[key], list) else [fields[key]]
        choices = expected if isinstance(expected, list) else [expected]
        if not any(
            type(a) is type(b) and (a.casefold() == b.casefold() if isinstance(a, str) else a == b)
            for a in actual
            for b in choices
        ):
            return False
    return True


def _stats(values):
    values = sorted(values)

    def percentile(p):
        index = (len(values) - 1) * p
        left = int(index)
        return values[left] + (values[math.ceil(index)] - values[left]) * (index - left)

    return {
        "n": len(values),
        "median": median(values) if values else None,
        "p25": percentile(0.25) if values else None,
        "p75": percentile(0.75) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def _summary(snapshot):
    return {key: deepcopy(value) for key, value in snapshot.items() if key != "observations"}


class Market:
    def __init__(self, workspace):
        self.store = workspace.store

    def snapshot(self, name, job_ids, scope=None, sources=None, notes=""):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Укажите название снимка выборки")
        if not isinstance(job_ids, list) or any(not isinstance(item, str) or not item for item in job_ids):
            raise ValueError("Поле job_ids должно содержать явный список идентификаторов вакансий")
        if scope is not None and not isinstance(scope, dict):
            raise ValueError("Поле scope должно быть объектом с описанием охвата выборки")
        if sources is not None and not isinstance(sources, list):
            raise ValueError("Поле sources должно быть списком источников")
        ids = list(dict.fromkeys(job_ids))
        observations = [self.store.get("job", job_id) for job_id in ids]
        times = [job["fetched_at"] for job in observations if job.get("fetched_at")]
        value = {
            "id": uuid4().hex,
            "name": name.strip(),
            "created_at": now(),
            "scope": {**dict.fromkeys(SCOPE_FIELDS), **deepcopy(scope or {})},
            "sources": deepcopy(sources)
            if sources is not None
            else list(dict.fromkeys(_text(job.get("platform")) or "unknown" for job in observations)),
            "notes": notes,
            "job_ids": ids,
            "observation_count": len(observations),
            "observed_from": min(times) if times else None,
            "observed_to": max(times) if times else None,
            "observations": observations,
        }
        self.store.put("market_snapshot", value["id"], value)
        return _summary(value)

    def snapshots(self):
        return [
            _summary(item)
            for item in sorted(
                self.store.list("market_snapshot"), key=lambda item: item["created_at"], reverse=True
            )
        ]

    def report(self, snapshot_id=None, filters=None):
        filters = filters if filters is not None else {}
        if not isinstance(filters, dict) or set(filters) - FILTER_FIELDS:
            raise ValueError(
                "Недопустимый filters: доступны role, level, region, work_format, source, "
                "location, platform, employer, currency, period, gross и job_ids"
            )
        if snapshot_id is None:
            snapshots = self.snapshots()
            snapshot_id = snapshots[0]["id"] if snapshots else None
        try:
            snapshot = self.store.get("market_snapshot", snapshot_id) if snapshot_id else None
        except ValueError:
            snapshot = None
        observations = [job for job in snapshot["observations"] if _matches(job, filters)] if snapshot else []
        groups = _deduplicate(observations)
        jobs = [group[0] for group in groups]
        salary_groups = defaultdict(list)
        missing, invalid, exclusions = 0, 0, []
        limitations = [
            "Охват вакансий и источников неполный; выборка может быть смещена и не позволяет делать выводы обо всём рынке."
        ]
        if snapshot_id and snapshot is None:
            limitations.append(
                "Запрошенный снимок не найден; другие наблюдения вместо него не подставлялись."
            )
        for job in jobs:
            salary = salary_terms(job)
            if "missing_salary" in salary["issues"]:
                missing += 1
            elif not salary["valid"]:
                invalid += 1
                exclusions.append({"job_id": job["id"], "issues": salary["issues"]})
            else:
                salary_groups[(salary["currency"], salary["period"], salary["gross"])].append(salary)
        salaries = []
        for (currency, period, gross), values in salary_groups.items():
            lower = [v["lower"] for v in values if v["lower"] is not None]
            upper = [v["upper"] for v in values if v["upper"] is not None]
            midpoint = [
                v["lower"] + (v["upper"] - v["lower"]) / 2
                for v in values
                if v["lower"] is not None and v["upper"] is not None
            ]
            salaries.append(
                {
                    "currency": currency,
                    "period": period,
                    "gross": gross,
                    "n": len(values),
                    "lower": _stats(lower),
                    "upper": _stats(upper),
                    "midpoint": _stats(midpoint),
                    "one_sided_lower": sum(v["upper"] is None for v in values),
                    "one_sided_upper": sum(v["lower"] is None for v in values),
                    "small_sample": len(values) < 5,
                }
            )
        if any(group["small_sample"] for group in salaries):
            limitations.append(
                "Малые зарплатные группы (n < 5) дают неустойчивое описание и не служат надёжным рыночным ориентиром."
            )
        if any(
            group["gross"] is None or group["currency"] == "unknown" or group["period"] not in PERIODS
            for group in salaries
        ):
            limitations.append(
                "Неизвестная валюта, период оплаты или база до/после налогов учитываются отдельно и требуют уточнения."
            )
        share = missing / len(jobs) if jobs else None
        if jobs:
            limitations.append(
                f"В {missing} из {len(jobs)} уникальных вакансий ({share:.0%}) зарплата не указана; некорректные вилки: {invalid}."
            )
        else:
            limitations.append(
                "В выбранном снимке или группе нет наблюдений; сначала соберите явную выборку."
            )
        distributions = {
            key: Counter() for key in ("employers", "sources", "locations", "work_formats", "requirements")
        }
        duplicates = []
        for group in groups:
            job = group[0]
            sources = list(dict.fromkeys(_text(item.get("platform")) or "unknown" for item in group))
            distributions["employers"].update([_text(job.get("employer")) or "unknown"])
            distributions["sources"].update(sources)
            distributions["locations"].update([_text(job.get("location")) or "unknown"])
            distributions["work_formats"].update(set(_work_formats(job)))
            distributions["requirements"].update(set(_requirements(job)))
            if len(group) > 1:
                duplicates.append(
                    {"representative_id": job["id"], "job_ids": [j["id"] for j in group], "sources": sources}
                )
        return {
            "status": "empty"
            if not jobs
            else "ready"
            if any(g["n"] >= 5 for g in salaries)
            else "insufficient_data",
            "snapshot": _summary(snapshot) if snapshot else None,
            "filters": deepcopy(filters),
            "counts": {
                "observations": len(observations),
                "unique_jobs": len(jobs),
                "duplicates": len(observations) - len(jobs),
                "with_salary": len(jobs) - missing - invalid,
                "missing_salary": missing,
                "invalid_salary": invalid,
                "missing_salary_share": share,
            },
            "salary_groups": salaries,
            "salary_exclusions": exclusions,
            "distributions": {
                key: [
                    {"label": label, "count": count}
                    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                ]
                for key, counts in distributions.items()
            },
            "limitations": limitations,
            "job_ids": [job["id"] for job in jobs],
            "duplicates": duplicates,
            "methodology": METHODOLOGY,
        }
