"""Personal recommendations must be explainable from private, sourced evidence."""

import importlib.util

import pytest

from worklife.career import Career
from worklife.workspace import Workspace


def advisor(tmp_path, profile=True):
    assert importlib.util.find_spec("worklife.advisor"), "Advisor service is not implemented"
    from worklife.advisor import Advisor

    w = Workspace(tmp_path)
    if profile:
        w.save_profile(
            {
                "name": "Alex",
                "target_roles": ["Engineer"],
                "facts": [
                    {"id": "py", "text": "Built Python APIs", "source": "portfolio:api"},
                    {"id": "sql", "text": "Used SQL for reporting", "source": "project:reports"},
                ],
                "constraints": {},
            }
        )
    return w, Advisor(w)


def job(w, key="one", **fields):
    return w.save_job(
        {
            "id": key,
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "employer_domain": "acme.example",
            "url": f"https://acme.example/jobs/{key}",
            "requirements": ["Python"],
            **fields,
        }
    )


def test_empty_profile_requests_real_facts_and_target_roles(tmp_path):
    w, a = advisor(tmp_path, profile=False)
    job(w)
    result = a.report()
    assert result["status"] == "needs_profile"
    assert set(result["missing_profile_fields"]) == {"facts", "target_roles"}
    assert result["recommendations"] == []
    w.save_profile({"name": "Python Engineer", "facts": []})
    assert a.report()["status"] == "needs_profile"


def test_explicit_constraints_reject_violations_and_keep_unknowns_separate(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile({**w.get_profile(), "constraints": {"remote": True, "max_hours": 32}})
    office = job(w, "office", remote=False, hours=40)
    unknown = job(w, "unknown")
    good = job(w, "good", remote=True, hours=30)
    rows = a.report()["recommendations"]
    assert [r["job_id"] for r in rows] == [good["id"], unknown["id"], office["id"]]
    assert [r["decision"] for r in rows] == ["consider", "clarify", "reject"]
    assert rows[1]["questions"]
    assert len(rows[2]["reasons"]) >= 2
    assert [r["rank"] for r in rows] == [1, 2, 3]


@pytest.mark.parametrize(
    "changes, decision",
    [
        ({"salary_max": 90, "salary_min": 70}, "reject"),
        ({"salary_min": 120, "salary_max": None}, "consider"),
        ({"salary_min": None, "salary_max": 150}, "clarify"),
        ({"currency": "USD"}, "clarify"),
        ({"salary_period": "month"}, "clarify"),
        ({"salary_gross": True}, "clarify"),
        ({"salary_gross": None}, "clarify"),
        ({"salary_min": 200, "salary_max": 100}, "clarify"),
    ],
)
def test_salary_comparisons_require_same_currency_period_and_tax_basis(tmp_path, changes, decision):
    w, a = advisor(tmp_path)
    w.save_profile(
        {
            **w.get_profile(),
            "constraints": {
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "year",
                "salary_gross": False,
            },
        }
    )
    j = job(
        w,
        **dict(salary_min=120, salary_max=150, currency="EUR", salary_period="year", salary_gross=False)
        | changes,
    )
    assert a.report([j["id"]])["recommendations"][0]["decision"] == decision


def test_blocked_employer_is_rejected_even_when_all_terms_match(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w)
    w.store.put("employer_block", "acme.example", {"blocked": True})
    row = a.report([j["id"]])["recommendations"][0]
    assert row["decision"] == "reject"
    assert any("заблокирован" in reason.lower() for reason in row["reasons"])
    assert not any(
        action["kind"] in {"consider", "prepare_interview"} for action in a.report()["next_actions"]
    )


def test_requirement_matches_quote_existing_facts_and_never_cv_headlines(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, requirements=[{"name": "Python"}, {"text": "Kubernetes"}], key_skills=[{"name": "SQL"}])
    w.create_cv("Misleading headline", ["sql"], "Python Kubernetes expert")
    row = a.report()["recommendations"][0]
    assert {r["requirement"] for r in row["matched_requirements"]} == {"Python", "SQL"}
    assert row["missing_requirements"] == ["Kubernetes"]
    for match in row["matched_requirements"]:
        assert match["match_method"] == "literal_phrase"
        assert match["fact_ids"]
        for evidence in match["evidence"]:
            assert evidence["fact_id"] in {"py", "sql"}
            assert evidence["source"] in {"portfolio:api", "project:reports"}
    variant = a.cv_match(j["id"])["variants"][0]
    assert [m["requirement"] for m in variant["matched_requirements"]] == ["SQL"]
    assert set(variant["missing_requirements"]) == {"Python", "Kubernetes"}


def test_cv_choice_uses_selected_facts_and_language_and_does_not_break_ties(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, cv_language="en")
    wrong = w.create_cv("SQL", ["sql"], "Python developer")
    py = w.create_cv("Python", ["py"], "Engineer")
    en = Career(w).cv_localize(py["id"], "en", {"py": "Built Python APIs"})
    result = a.cv_match(j["id"])
    assert result["recommended_cv_id"] == en["id"]
    assert next(v for v in result["variants"] if v["cv_id"] == wrong["id"])["matched_requirements"] == []
    Career(w).cv_localize(py["id"], "en", {"py": "Built Python APIs"})
    assert a.cv_match(j["id"])["recommended_cv_id"] is None
    assert a.cv_match(j["id"])["notes"]


def test_no_requirement_information_or_no_cv_does_not_make_up_a_choice(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, requirements=[])
    assert a.cv_match(j["id"])["recommended_cv_id"] is None
    w.create_cv("Python", ["py"], "Engineer")
    assert a.cv_match(j["id"])["recommended_cv_id"] is None
    assert a.report()["recommendations"][0]["decision"] == "clarify"


def test_negated_claim_and_substrings_are_not_positive_skill_evidence(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile(
        {
            **w.get_profile(),
            "facts": [{"id": "no", "text": "No Python experience. Used JavaScript.", "source": "user"}],
        }
    )
    job(w, requirements=["Python", "Java"])
    row = a.report()["recommendations"][0]
    assert row["matched_requirements"] == []
    assert set(row["missing_requirements"]) == {"Python", "Java"}


def test_import_preserves_profile_and_sources_private_self_reported_paragraphs(tmp_path):
    w, a = advisor(tmp_path)
    before = w.get_profile()
    text = "Built Rust services.\nImproved release notes.\n\nWorked with SQL."
    result = a.import_resume("My CV", text, "en", "uploaded:resume.txt")
    cv = result["cv"]
    assert cv["source_text"] == text
    assert cv["language"] == "en"
    assert cv["review_required"] is True
    assert len(result["imported_fact_ids"]) == 2
    profile = w.get_profile()
    for key, value in before.items():
        assert profile[key] == value if key != "facts" else profile[key][:2] == value
    for f in cv["facts"]:
        assert f["text"] in text
        assert f["evidence_status"] == "self_reported"
        assert f["source"].startswith("resume:")
        assert f["origin"] == "uploaded:resume.txt"
    again = a.import_resume("My CV again", text, "en", "uploaded:resume.txt")
    assert again["imported_fact_ids"] == result["imported_fact_ids"]
    assert len(w.get_profile()["facts"]) == 4
    assert w.ledger.export() == []
    translated = Career(w).cv_localize(cv["id"], "ru", {f["id"]: "Перевод " + f["text"] for f in cv["facts"]})
    assert translated["fact_ids"] == cv["fact_ids"]


def test_import_without_profile_does_not_infer_target_profession(tmp_path):
    w, a = advisor(tmp_path, profile=False)
    a.import_resume("Engineer CV", "Built Python APIs.")
    assert w.get_profile().get("target_roles") in (None, [])
    assert a.report()["missing_profile_fields"] == ["target_roles"]
    with pytest.raises(ValueError):
        a.import_resume("Empty", "   ")


def test_interview_preparation_uses_real_job_facts_gaps_and_unknown_terms(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile({**w.get_profile(), "constraints": {"remote": True}, "income_deadline": "2026-11-10"})
    j = job(w, requirements=["Python", "Kubernetes"])
    brief = a.interview_brief(j["id"])
    assert brief["job"]["id"] == j["id"]
    assert brief["job"]["url"] == j["url"]
    assert brief["evidence"][0]["fact_id"] == "py"
    assert brief["gaps"] == ["Kubernetes"]
    assert brief["questions_for_employer"]
    assert brief["preparation"]
    assert not w.store.list("action")
    with pytest.raises(ValueError, match="Unknown job"):
        a.interview_brief("missing")


def test_report_handles_limits_selected_jobs_and_no_jobs(tmp_path):
    w, a = advisor(tmp_path)
    assert a.report()["status"] == "empty"
    one, two = job(w, "one"), job(w, "two")
    assert [r["job_id"] for r in a.report([two["id"], two["id"]])["recommendations"]] == [two["id"]]
    assert len(a.report(limit=1)["recommendations"]) == 1
    with pytest.raises(ValueError):
        a.report(limit=0)
    with pytest.raises(ValueError, match="Unknown job"):
        a.report([one["id"], "missing"])


@pytest.mark.parametrize(
    "text", ["I don't know Python.", "I haven’t used Python.", "Python experience: none."]
)
def test_negated_contractions_are_not_positive_evidence(tmp_path, text):
    w, a = advisor(tmp_path)
    w.save_profile({**w.get_profile(), "facts": [{"id": "denial", "text": text, "source": "user"}]})
    job(w)
    assert a.report()["recommendations"][0]["matched_requirements"] == []


def test_dots_inside_skill_names_are_preserved_in_literal_matches(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile(
        {
            **w.get_profile(),
            "facts": [{"id": "dot", "text": "Built .NET services and Node.js APIs.", "source": "project"}],
        }
    )
    job(w, requirements=[".NET", "Node.js"])
    row = a.report()["recommendations"][0]
    assert {r["requirement"] for r in row["matched_requirements"]} == {".NET", "Node.js"}


def test_unrecognized_salary_period_is_not_comparable_even_when_strings_match(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile(
        {
            **w.get_profile(),
            "constraints": {
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "bananas",
                "salary_gross": False,
            },
        }
    )
    job(w, salary_min=120, currency="EUR", salary_period="bananas", salary_gross=False)
    assert a.report()["recommendations"][0]["decision"] == "clarify"


def test_advisor_explanations_are_russian_without_translating_user_evidence_or_codes(tmp_path):
    w, a = advisor(tmp_path, profile=False)
    assert a.report()["next_actions"][0]["title"] == "Заполните профиль"
    imported = a.import_resume("Original CV", "Built Python APIs", "en")
    w.save_profile({**w.get_profile(), "target_roles": ["Engineer"], "constraints": {"remote": True}})
    j = job(w, requirements=["Python", "SQL"])
    row = a.report()["recommendations"][0]
    assert row["decision"] == "clarify"
    assert row["questions"][0].startswith("Можно ли")
    assert row["cv_match"]["notes"][0].startswith("Буквальные совпадения")
    assert row["matched_requirements"][0]["requirement"] == "Python"
    assert row["matched_requirements"][0]["evidence"][0]["text"] == "Built Python APIs"
    assert imported["notes"][0].startswith("Абзацы резюме")
    assert a.interview_brief(j["id"])["preparation"][0]["prompt"].startswith("Подготовьте")


def test_agent_recommendation_resolves_evidence_from_private_source_data(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, salary_min=150)
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    saved = a.save_recommendation(
        j["id"],
        "consider",
        ["Есть подходящий опыт"],
        [
            {"fact_id": "py", "text": "Invented achievement", "source": "forged"},
            {"job_field": "salary_min", "value": 999, "source": "forged"},
        ],
    )
    fact, condition = saved["evidence"]
    assert fact["text"] == "Built Python APIs" and fact["source"] == "portfolio:api"
    assert condition["value"] == 150 and condition["source"] == j["url"]
    assert w.store.list("recommendation") == [saved]
    assert w.ledger.export() == []


@pytest.mark.parametrize(
    "evidence",
    [
        [{"fact_id": "absent"}],
        [{"job_field": "absent"}],
        [{"job_field": "salary_min"}],
        [{"fact_id": "py", "job_field": "title"}],
    ],
)
def test_agent_recommendation_rejects_missing_or_ambiguous_evidence(tmp_path, evidence):
    w, a = advisor(tmp_path)
    j = job(w, salary_min=None)
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    with pytest.raises(ValueError):
        a.save_recommendation(j["id"], "consider", ["Основание"], evidence)
    assert w.store.list("recommendation") == []


def test_agent_priority_orders_viable_jobs_without_overriding_hard_rejections(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile({**w.get_profile(), "constraints": {"remote": True}})
    low = job(w, "a", remote=True)
    high = job(w, "b", remote=True)
    rejected = job(w, "c", remote=False)
    unknown = job(w, "d", remote=None)
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    for j in (high, rejected, unknown):
        a.save_recommendation(j["id"], "consider", ["Приоритет агента"], [{"fact_id": "py"}], priority=1)
    rows = a.report()["recommendations"]
    assert rows[0]["job_id"] == high["id"]
    assert rows[-1]["job_id"] == rejected["id"] and rows[-1]["decision"] == "reject"
    assert next(row for row in rows if row["job_id"] == unknown["id"])["decision"] == "clarify"
    assert next(row for row in rows if row["job_id"] == low["id"])["assessment_status"] == "none"
    assert rows[0]["agent_assessment"]["priority"] == 1
    assert "Приоритет агента" in rows[0]["reasons"]
    w.store.put("employer_block", "acme.example", {"blocked": True})
    assert all(row["decision"] == "reject" for row in a.report()["recommendations"])


@pytest.mark.parametrize("changed", ["salary", "profile"])
def test_changed_job_or_profile_makes_agent_assessment_stale_and_clears_agent_cv_choice(tmp_path, changed):
    w, a = advisor(tmp_path)
    j = job(w, salary_min=100)
    w.create_cv("First", ["py"], "Engineer")
    second = w.create_cv("Second", ["py"], "Engineer")
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    a.save_recommendation(j["id"], "consider", ["Сохранённый вывод"], [{"fact_id": "py"}], cv_id=second["id"])
    fresh = a.report()["recommendations"][0]
    assert fresh["assessment_status"] == "fresh" and fresh["recommended_cv_id"] == second["id"]
    if changed == "salary":
        w.save_job({**j, "salary_min": 200})
    else:
        w.save_profile({**w.get_profile(), "target_roles": ["Data Engineer"]})
    stale = a.report()["recommendations"][0]
    assert stale["assessment_status"] == "stale"
    assert stale["recommended_cv_id"] is None
    assert "Сохранённый вывод" not in stale["reasons"]
    assert stale["agent_assessment"]["reasons"] == ["Сохранённый вывод"]


def test_refetch_timestamps_do_not_invalidate_agent_assessment(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w)
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    saved = a.save_recommendation(
        j["id"], "clarify", ["Нужно обсудить роль"], [{"job_field": "title"}], ["Как устроена команда?"]
    )
    w.save_job(j)
    row = a.report()["recommendations"][0]
    assert row["assessment_status"] == "fresh"
    assert row["agent_assessment"]["context_hash"] == saved["context_hash"]
    assert row["decision"] == "clarify"
    assert "Как устроена команда?" in row["questions"]


def test_agent_semantics_can_resolve_only_lexical_gaps_without_fabricating_matched_skills(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, requirements=["Backend engineering"])
    cv = w.create_cv("Backend", ["py"], "Engineer")
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    a.save_recommendation(
        j["id"],
        "consider",
        ["Разработка API относится к серверной разработке"],
        [{"fact_id": "py"}],
        cv_id=cv["id"],
    )
    row = a.report()["recommendations"][0]
    assert row["decision"] == "consider"
    assert row["matched_requirements"] == []
    assert row["agent_assessment"]["method"] == "external_agent"
    assert row["recommended_cv_id"] == cv["id"]
    assert a.report()["next_actions"][0]["kind"] == "consider"
    assert a.cv_match(j["id"])["variants"][0]["matched_requirements"] == []


def test_agent_cv_evidence_must_be_selected_in_that_cv_and_language_must_be_compatible(tmp_path):
    w, a = advisor(tmp_path)
    j = job(w, cv_language="en")
    sql = w.create_cv("SQL", ["sql"], "Engineer")
    py = w.create_cv("Python", ["py"], "Engineer")
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    with pytest.raises(ValueError):
        a.save_recommendation(j["id"], "consider", ["Опыт Python"], [{"fact_id": "py"}], cv_id=sql["id"])
    ru = Career(w).cv_localize(py["id"], "ru", {"py": "Создавал Python API"})
    a.save_recommendation(j["id"], "consider", ["Опыт Python"], [{"fact_id": "py"}], cv_id=ru["id"])
    row = a.report()["recommendations"][0]
    assert row["recommended_cv_id"] is None
    assert row["questions"]
    assert w.ledger.export() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"verdict": "perfect"},
        {"reasons": []},
        {"questions": [""]},
        {"priority": True},
        {"priority": 6},
        {"cv_id": "missing"},
    ],
)
def test_agent_recommendation_validates_explicit_verdict_text_priority_and_cv(tmp_path, kwargs):
    w, a = advisor(tmp_path)
    j = job(w)
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    values = {
        "job_id": j["id"],
        "verdict": "consider",
        "reasons": ["Основание"],
        "evidence": [{"fact_id": "py"}],
        **kwargs,
    }
    with pytest.raises(ValueError):
        a.save_recommendation(**values)
    assert w.store.list("recommendation") == []


def test_semantic_consider_does_not_bypass_unknown_salary_basis(tmp_path):
    w, a = advisor(tmp_path)
    w.save_profile(
        {
            **w.get_profile(),
            "constraints": {
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "month",
                "salary_gross": False,
            },
        }
    )
    j = job(w, requirements=["Backend engineering"], salary_min=150, currency="EUR", salary_period="month")
    assert hasattr(a, "save_recommendation"), "External agent assessments cannot be saved"
    a.save_recommendation(
        j["id"], "consider", ["Разработка API относится к серверной разработке"], [{"fact_id": "py"}]
    )
    row = a.report()["recommendations"][0]
    assert row["decision"] == "clarify"
    assert row["assessment_status"] == "fresh"
    assert any("налог" in question for question in row["questions"])


@pytest.mark.parametrize("localized", [False, True])
def test_corrected_profile_fact_disqualifies_old_cv_but_keeps_its_snapshot(tmp_path, localized):
    w, a = advisor(tmp_path)
    j = job(w, **({"cv_language": "ru"} if localized else {}))
    cv = w.create_cv("Original", ["py", "sql"], "Engineer")
    if localized:
        cv = Career(w).cv_localize(
            cv["id"], "ru", {"py": "Разрабатывал API на Python", "sql": "Отчёты на SQL"}
        )
    assert a.cv_match(j["id"])["recommended_cv_id"] == cv["id"]
    profile = w.get_profile()
    profile["facts"][1]["text"] = "I have never used SQL"
    w.save_profile(profile)
    result = a.cv_match(j["id"])
    assert result["recommended_cv_id"] is None
    old_variant = next(item for item in result["variants"] if item["cv_id"] == cv["id"])
    assert old_variant["facts_current"] is False
    assert old_variant["matched_requirements"]  # The still-current Python fact alone cannot endorse this CV.
    assert w.store.get("cv", cv["id"]) == cv
    for evidence in ([{"fact_id": "sql"}], [{"fact_id": "py"}], [{"job_field": "requirements"}]):
        with pytest.raises(ValueError, match="актуальн"):
            a.save_recommendation(j["id"], "consider", ["Experience"], evidence, cv_id=cv["id"])
    assert w.store.list("recommendation") == []
