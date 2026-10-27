import importlib.util

import pytest

from worklife.workspace import Workspace


def market(tmp_path):
    assert importlib.util.find_spec("worklife.market") is not None, "Market engine is not implemented"
    from worklife.market import Market

    workspace = Workspace(tmp_path)
    return workspace, Market(workspace)


def terms(job):
    assert importlib.util.find_spec("worklife.market") is not None, "Salary normalization is not implemented"
    from worklife.market import salary_terms

    return salary_terms(job)


def save(workspace, key, **values):
    return workspace.save_job(
        {
            "id": key,
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "url": f"https://jobs.example.org/{key}",
            "location": "Berlin",
            "description": f"Build service {key}",
            "salary_min": 100,
            "salary_max": 200,
            "currency": "EUR",
            "salary_period": "month",
            "salary_gross": True,
            **values,
        }
    )


def test_salary_normalizes_aliases_and_preserves_open_bounds():
    value = terms({"salary": {"from": 0, "currency": "rur", "period": "monthly", "gross": False}})
    assert value == {
        "lower": 0,
        "upper": None,
        "currency": "RUB",
        "period": "month",
        "gross": False,
        "valid": True,
        "issues": [],
    }
    value = terms({"salary_max": 90000, "salary_period": "annually"})
    assert value["lower"] is None and value["upper"] == 90000
    assert value["currency"] == "unknown" and value["period"] == "year"
    assert value["gross"] is None and value["valid"] is True
    assert "unknown_currency" in value["issues"] and "unknown_gross" in value["issues"]


@pytest.mark.parametrize(
    "lower,upper,issue",
    [
        (True, 100, "invalid_lower"),
        (100, False, "invalid_upper"),
        (-1, 100, "invalid_lower"),
        (float("inf"), 100, "invalid_lower"),
        (0, float("nan"), "invalid_upper"),
        ("100", 200, "invalid_lower"),
        (200, 100, "reversed_range"),
        (None, None, "missing_salary"),
    ],
)
def test_invalid_salary_is_excluded_with_reason(lower, upper, issue):
    value = terms({"salary_min": lower, "salary_max": upper})
    assert value["valid"] is False
    assert issue in value["issues"]


def test_empty_state_is_pollable_and_snapshot_requires_explicit_ids(tmp_path):
    workspace, engine = market(tmp_path)
    save(workspace, "unselected")
    report = engine.report()
    assert report["status"] == "empty" and report["snapshot"] is None
    assert report["counts"]["unique_jobs"] == 0 and report["salary_groups"] == []
    snapshot = engine.snapshot("Empty", [])
    assert engine.report(snapshot["id"])["status"] == "empty"
    assert engine.report(snapshot["id"])["job_ids"] == []
    with pytest.raises(ValueError, match="job_ids"):
        engine.snapshot("Not explicit", None)
    assert workspace.ledger.export() == []


def test_snapshot_is_immutable_and_preserves_query_scope_sources_and_time(tmp_path):
    workspace, engine = market(tmp_path)
    job = save(workspace, "a")
    scope = {
        "role": "Engineer",
        "level": "Senior",
        "region": "Berlin",
        "work_format": "remote",
        "queries": [{"query": "Senior engineer", "pages": [1, 2]}],
    }
    sources = [{"name": "manual", "query": "Senior engineer", "coverage": "selected results"}]
    snapshot = engine.snapshot("October", [job["id"]], scope, sources, "Selected manually")
    before = engine.report(snapshot["id"])
    scope["queries"][0]["query"] = "mutated"
    sources[0]["name"] = "mutated"
    save(workspace, "a", salary_min=999, salary_max=999, title="Changed")
    assert engine.report(snapshot["id"]) == before
    assert snapshot["scope"]["queries"][0]["query"] == "Senior engineer"
    assert snapshot["sources"][0]["name"] == "manual"
    assert snapshot["created_at"] and snapshot["notes"] == "Selected manually"
    assert engine.snapshots() == [snapshot]
    assert workspace.store.get("market_snapshot", snapshot["id"])["observations"][0]["title"] == "Engineer"
    assert workspace.ledger.export() == []


def test_salary_groups_do_not_mix_currency_period_or_tax_basis(tmp_path):
    workspace, engine = market(tmp_path)
    records = [
        save(workspace, "gross"),
        save(workspace, "net", salary_gross=False),
        save(workspace, "unknown-tax", salary_gross=None),
        save(workspace, "hour", salary_period="hourly"),
        save(workspace, "rub", currency="RUR"),
        save(workspace, "unknown-period", salary_period=None),
    ]
    report = engine.report(engine.snapshot("Separate", [job["id"] for job in records])["id"])
    groups = {(g["currency"], g["period"], g["gross"]): g for g in report["salary_groups"]}
    assert set(groups) == {
        ("EUR", "month", True),
        ("EUR", "month", False),
        ("EUR", "month", None),
        ("EUR", "hour", True),
        ("RUB", "month", True),
        ("EUR", "unknown", True),
    }
    assert all(g["midpoint"]["n"] == 1 for g in groups.values())
    assert report["status"] == "insufficient_data"
    assert any("неизвестн" in item.lower() for item in report["limitations"])
    assert any("малые" in item.lower() for item in report["limitations"])


def test_statistics_keep_separate_bounds_and_closed_midpoints(tmp_path):
    workspace, engine = market(tmp_path)
    jobs = [
        save(workspace, "a", salary_min=100, salary_max=200),
        save(workspace, "b", salary_min=200, salary_max=400),
        save(workspace, "c", salary_min=300, salary_max=600),
        save(workspace, "d", salary_min=400, salary_max=None),
        save(workspace, "e", salary_min=None, salary_max=800),
        save(workspace, "missing", salary_min=None, salary_max=None),
        save(workspace, "invalid", salary_min=900, salary_max=200),
    ]
    report = engine.report(engine.snapshot("Bounds", [j["id"] for j in jobs])["id"])
    assert report["status"] == "ready"
    group = report["salary_groups"][0]
    assert group["lower"] == {"n": 4, "median": 250, "p25": 175, "p75": 325, "min": 100, "max": 400}
    assert group["upper"] == {"n": 4, "median": 500, "p25": 350, "p75": 650, "min": 200, "max": 800}
    assert group["midpoint"]["n"] == 3 and group["midpoint"]["median"] == 300
    assert group["one_sided_lower"] == 1 and group["one_sided_upper"] == 1
    assert report["counts"]["with_salary"] == 5
    assert report["counts"]["missing_salary"] == 1 and report["counts"]["invalid_salary"] == 1
    assert report["counts"]["missing_salary_share"] == pytest.approx(1 / 7)
    assert report["salary_exclusions"] == [{"job_id": "manual:invalid", "issues": ["reversed_range"]}]
    assert "описательная выборка опубликованных вакансий" in report["methodology"].lower()


def test_dedup_keeps_all_ids_and_sources_but_does_not_merge_similar_roles(tmp_path):
    workspace, engine = market(tmp_path)
    jobs = [
        save(workspace, "a", url="https://JOBS.example.org/a?position=1&utm_source=mail"),
        save(workspace, "copy", platform="board", url="https://jobs.example.org/a?position=1"),
        save(workspace, "different-query", url="https://jobs.example.org/a?position=2"),
        save(workspace, "same-title"),
        save(workspace, "canonical", canonical_id="employer:role-1"),
        save(workspace, "canonical-copy", canonical_id="employer:role-1"),
        save(workspace, "strict", description="Unique exact text", requirements=["Python", "SQL"]),
        save(workspace, "strict-copy", description="Unique exact text", requirements=["Python", "SQL"]),
    ]
    report = engine.report(engine.snapshot("Dedup", [j["id"] for j in jobs])["id"])
    assert report["counts"]["observations"] == 8
    assert report["counts"]["unique_jobs"] == 5 and report["counts"]["duplicates"] == 3
    duplicate = next(d for d in report["duplicates"] if "manual:a" in d["job_ids"])
    assert duplicate["job_ids"] == ["manual:a", "board:copy"]
    assert duplicate["sources"] == ["manual", "board"]
    assert "manual:different-query" in report["job_ids"] and "manual:same-title" in report["job_ids"]
    assert report["distributions"]["requirements"] == [
        {"label": "Python", "count": 1},
        {"label": "SQL", "count": 1},
    ]
    assert {r["label"]: r["count"] for r in report["distributions"]["sources"]} == {"manual": 5, "board": 1}


def test_filters_use_frozen_cohort_without_mutating_snapshot(tmp_path):
    workspace, engine = market(tmp_path)
    jobs = [
        save(workspace, "remote", role="Backend", level="Senior", remote=True, requirements=["Python"]),
        save(workspace, "office", role="Backend", level="Junior", remote=False, location="Paris"),
        save(workspace, "hybrid", role="Frontend", level="Senior", work_format="hybrid", remote=False),
    ]
    snapshot = engine.snapshot("Cohorts", [j["id"] for j in jobs])
    original = engine.report(snapshot["id"])
    report = engine.report(
        snapshot["id"], {"role": "Backend", "level": "Senior", "region": "Berlin", "work_format": "remote"}
    )
    assert report["job_ids"] == ["manual:remote"]
    assert report["counts"]["observations"] == 1
    assert report["distributions"]["locations"] == [{"label": "Berlin", "count": 1}]
    assert report["distributions"]["work_formats"] == [{"label": "remote", "count": 1}]
    assert engine.report(snapshot["id"]) == original
    assert engine.report(snapshot["id"], {"region": "Rome"})["status"] == "empty"
    with pytest.raises(ValueError, match="filter"):
        engine.report(snapshot["id"], {"unsupported": "x"})


def test_missing_snapshot_reference_remains_a_pollable_empty_state(tmp_path):
    _, engine = market(tmp_path)
    report = engine.report("no-longer-present")
    assert report["status"] == "empty" and report["snapshot"] is None
    assert any("не найден" in note.lower() for note in report["limitations"])


def test_one_sided_only_sample_has_no_fabricated_upper_or_midpoint(tmp_path):
    workspace, engine = market(tmp_path)
    jobs = [save(workspace, str(index), salary_min=100 + index, salary_max=None) for index in range(5)]
    report = engine.report(engine.snapshot("From", [job["id"] for job in jobs])["id"])
    group = report["salary_groups"][0]
    assert group["lower"]["median"] == 102
    assert group["upper"] == {"n": 0, "median": None, "p25": None, "p75": None, "min": None, "max": None}
    assert group["midpoint"] == group["upper"]
    assert group["one_sided_lower"] == 5 and group["one_sided_upper"] == 0


def test_url_identity_keeps_semantic_query_parameters_and_fragment_routes(tmp_path):
    workspace, engine = market(tmp_path)
    jobs = [
        save(workspace, "one", url="https://jobs.example.org/list?ref=1#opening-a"),
        save(workspace, "two", url="https://jobs.example.org/list?ref=2#opening-a"),
        save(workspace, "three", url="https://jobs.example.org/list?ref=1#opening-b"),
        save(workspace, "copy", url="https://jobs.example.org/list?ref=1&utm_medium=email#opening-a"),
    ]
    snapshot = engine.snapshot("Exact identity", [job["id"] for job in jobs])
    report = engine.report(snapshot["id"])
    assert report["counts"]["unique_jobs"] == 3
    assert report["duplicates"][0]["job_ids"] == ["manual:one", "manual:copy"]
    assert engine.report(snapshot["id"], {"job_ids": ["manual:two"]})["job_ids"] == ["manual:two"]


def test_unrecognized_periods_remain_distinct_and_are_flagged_for_clarification(tmp_path):
    workspace, engine = market(tmp_path)
    period = terms({"salary_min": 100, "currency": "EUR", "salary_period": "fortnight", "salary_gross": True})
    assert period["period"] == "fortnight"
    assert period["valid"] is True and "unknown_period" in period["issues"]
    jobs = [save(workspace, "a", salary_period="fortnight"), save(workspace, "b", salary_period="quarter")]
    report = engine.report(engine.snapshot("Other periods", [job["id"] for job in jobs])["id"])
    assert {group["period"] for group in report["salary_groups"]} == {"fortnight", "quarter"}
    assert any("неизвестн" in note.lower() for note in report["limitations"])
