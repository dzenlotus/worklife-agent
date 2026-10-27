import importlib.util
from datetime import UTC, datetime, timedelta

import pytest

from worklife.workspace import Workspace


def agency(tmp_path):
    assert importlib.util.find_spec("worklife.agency") is not None, "Agency workflow is not implemented"
    from worklife.agency import Agency

    workspace = Workspace(tmp_path)
    job = workspace.save_job(
        {
            "id": "one",
            "platform": "manual",
            "title": "Engineer",
            "employer": "Acme",
            "url": "https://example.org/jobs/one",
        }
    )
    return workspace, Agency(workspace), job["id"]


def iso(days=0):
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def test_saved_job_needs_no_cv_and_pipeline_details_persist(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    record = engine.pipeline_update(job_id, next_action="Ask working hours", due_at=iso(1))
    assert record["cv_id"] is None and record["stage"] == "saved"
    assert record["next_action"] == "Ask working hours"
    assert workspace.store.get("application", record["id"]) == record
    updated = engine.pipeline_update(job_id, stage="applied", note="Sent manually")
    assert updated["id"] == record["id"] and len(updated["history"]) == 2
    assert updated["history"][-1]["note"] == "Sent manually"
    with pytest.raises(ValueError):
        engine.pipeline_update(job_id, due_at="2026-11-01T09:00:00")
    with pytest.raises(ValueError):
        engine.pipeline_update("missing")
    assert workspace.ledger.export() == []


def test_message_idempotency_links_only_known_reply_and_never_regresses_pipeline(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    engine.pipeline_update(job_id, stage="applied")
    outgoing = engine.conversation_record(job_id, "outbound", "email", "Application", "mail-1", status="sent")
    reply = engine.conversation_record(None, "inbound", "email", "Let's discuss", "mail-2", "mail-1")
    duplicate = engine.conversation_record(None, "inbound", "email", "Let's discuss", "mail-2", "mail-1")
    assert duplicate == reply and reply["job_id"] == job_id and reply["unread"] is True
    assert outgoing["unread"] is False
    assert workspace.store.list("application")[0]["stage"] == "reply"
    engine.pipeline_update(job_id, "offer")
    engine.conversation_record(job_id, "inbound", "email", "More details", "mail-3")
    assert workspace.store.list("application")[0]["stage"] == "offer"
    assert len(engine.conversation_list(job_id)) == 3
    assert workspace.ledger.export() == []


def test_unknown_direction_or_unresolved_thread_does_not_invent_a_reply(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    engine.pipeline_update(job_id, "applied")
    unknown = engine.conversation_record(job_id, "unknown", "email", "Direction absent", "u-1")
    orphan = engine.conversation_record(None, "inbound", "email", "Engineer at Acme", "u-2", "not-known")
    assert orphan["job_id"] is None and unknown["direction"] == "unknown"
    assert workspace.store.list("application")[0]["stage"] == "applied"
    other_channel = engine.conversation_record(None, "inbound", "telegram", "Cross-channel", "u-3", "u-1")
    assert other_channel["job_id"] is None
    with pytest.raises(ValueError):
        engine.conversation_record(job_id, "sideways", "email", "Bad")
    with pytest.raises(ValueError):
        engine.conversation_record(job_id, "inbound", "email", "x" * 100001)


def test_interview_dates_updates_and_private_records(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    for bad in ("tomorrow", "2026-11-01T12:00:00", None):
        with pytest.raises(ValueError):
            engine.interview_save(job_id, bad)
    interview = engine.interview_save(
        job_id, "2026-11-01T12:00:00+03:00", notes="Architecture", meeting_url="https://meet.example.org/one"
    )
    updated = engine.interview_save(
        job_id, "2026-11-02T12:00:00+03:00", notes="Rescheduled", interview_id=interview["id"]
    )
    assert updated["id"] == interview["id"] and updated["created_at"] == interview["created_at"]
    assert updated["scheduled_at"] == "2026-11-02T09:00:00Z"
    assert workspace.store.list("interview") == [updated]
    assert workspace.actions() == [] and workspace.ledger.export() == []


def profile(workspace):
    workspace.save_profile(
        {
            "facts": [],
            "target_roles": ["Writer"],
            "constraints": {
                "min_salary": 100,
                "currency": "EUR",
                "salary_period": "month",
                "salary_gross": False,
                "remote": True,
                "max_hours": 32,
            },
            "income_deadline": "2026-12-01",
        }
    )


def pay(**changes):
    return {
        "salary_min": 120,
        "salary_max": 180,
        "currency": "EUR",
        "salary_period": "monthly",
        "salary_gross": False,
        "hours": 30,
        "remote": True,
        "start_date": "2026-11-01",
        "income_date": "2026-11-20",
        "source": "Employer email",
        **changes,
    }


def test_offer_comparison_preserves_terms_and_separates_currency_and_tax(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    profile(workspace)
    good = engine.offer_save(job_id, pay())
    usd = engine.offer_save(job_id, pay(currency="USD"))
    gross = engine.offer_save(job_id, pay(salary_gross=True))
    report = engine.offer_compare()
    rows = {row["offer_id"]: row for row in report["offers"]}
    assert report["status"] == "ready"
    assert rows[good["id"]]["decision"] == "consider" and rows[good["id"]]["comparable"] is True
    assert rows[usd["id"]]["decision"] == "clarify" and rows[usd["id"]]["comparable"] is False
    assert rows[gross["id"]]["decision"] == "clarify" and rows[gross["id"]]["comparable"] is False
    assert len(report["salary_groups"]) == 3
    assert good["terms"]["source"] == "Employer email"
    assert all("rank" not in row and "score" not in row for row in report["offers"])
    assert all(offer["status"] == "received" for offer in workspace.store.list("offer"))
    assert workspace.actions() == [] and workspace.ledger.export() == []


def test_offer_dates_use_first_income_not_start_and_unknowns_require_questions(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    profile(workspace)
    late = engine.offer_save(job_id, pay(income_date="2026-12-15"))
    unknown = engine.offer_save(job_id, pay(income_date=None, salary_gross=None))
    rows = {row["offer_id"]: row for row in engine.offer_compare()["offers"]}
    assert rows[late["id"]]["decision"] == "reject"
    assert any("доход" in reason.lower() for reason in rows[late["id"]]["reasons"])
    assert rows[unknown["id"]]["decision"] == "clarify"
    assert any("доход" in question.lower() for question in rows[unknown["id"]]["questions"])
    with pytest.raises(ValueError):
        engine.offer_save(job_id, pay(income_date="soon"))
    assert len(workspace.store.list("offer")) == 2


def test_offer_without_profile_reports_missing_criteria_and_never_infers_them(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    assert engine.offer_compare()["status"] == "empty"
    engine.offer_save(job_id, {"salary_min": 100})
    report = engine.offer_compare()
    assert report["status"] == "needs_profile" and report["criteria"] == {}
    assert report["offers"][0]["questions"]
    assert workspace.store.list("profile") == []


def test_search_review_measures_reply_delay_and_pending_without_declaring_failure(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    pending_id = workspace.save_job(
        {
            "id": "two",
            "platform": "manual",
            "title": "Engineer",
            "employer": "Other",
            "url": "https://example.org/jobs/two",
        }
    )["id"]
    first = engine.pipeline_update(job_id, "applied")
    second = engine.pipeline_update(pending_id, "applied", next_action="Follow up", due_at=iso(-1))
    for app in (first, second):
        app["history"][0]["at"] = iso(-3)
        workspace.store.put("application", app["id"], app)
    engine.conversation_record(job_id, "inbound", "email", "Reply", occurred_at=iso(-2))
    engine.conversation_record(pending_id, "unknown", "email", "Unknown", occurred_at=iso(-2))
    review = engine.search_review(7)
    assert review["counts"]["applied"] == 2 and review["counts"]["replied"] == 1
    assert review["reply_delays"]["n"] == 1
    assert review["reply_delays"]["median_hours"] == pytest.approx(24, abs=0.01)
    assert [item["job_id"] for item in review["pending"]] == [pending_id]
    assert review["pending"][0]["status"] == "awaiting_reply"
    assert [item["job_id"] for item in review["due_actions"]] == [pending_id]
    assert review["stages"]["applied"] == 1 and review["stages"]["reply"] == 1
    assert any("не означает отказ" in text.lower() for text in review["limitations"])
    assert "probability" not in review and "prediction" not in review
    assert review["window"]["from"] < review["window"]["to"]


def test_brief_surfaces_due_actions_unassigned_messages_and_confirmed_records(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    engine.pipeline_update(job_id, next_action="Ask hours", due_at=iso(-1))
    orphan = engine.conversation_record(None, "inbound", "email", "Unassigned", "unknown-thread")
    interview = engine.interview_save(job_id, iso(1))
    offer = engine.offer_save(job_id, pay())
    result = engine.brief()
    assert result["due_actions"][0]["title"] == "Ask hours"
    assert [message["id"] for message in result["unassigned_messages"]] == [orphan["id"]]
    assert [message["id"] for message in result["unread_messages"]] == [orphan["id"]]
    assert result["interviews"][0]["id"] == interview["id"]
    assert result["offers"][0]["id"] == offer["id"]
    assert result["next_steps"]
    assert workspace.actions() == [] and workspace.ledger.export() == []


def test_ambiguous_imported_message_reference_is_not_assigned_by_order(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    other = workspace.save_job(
        {
            "id": "other",
            "platform": "manual",
            "title": "Engineer",
            "employer": "Other",
            "url": "https://example.org/other",
        }
    )["id"]
    parent = engine.conversation_record(job_id, "outbound", "email", "Original", "shared-id")
    workspace.store.put(
        "message", "imported-second-copy", {**parent, "id": "imported-second-copy", "job_id": other}
    )
    reply = engine.conversation_record(None, "inbound", "email", "Ambiguous reply", "reply-id", "shared-id")
    assert reply["job_id"] is None
    assert workspace.store.list("application") == []


@pytest.mark.parametrize("stage", ["interview", "offer", "accepted", "rejected", "withdrawn"])
def test_inbound_messages_do_not_reopen_or_regress_later_stages(tmp_path, stage):
    workspace, engine, job_id = agency(tmp_path)
    before = engine.pipeline_update(job_id, stage)
    engine.conversation_record(job_id, "inbound", "email", "Additional correspondence", "reply-id")
    assert workspace.store.get("application", before["id"]) == before


def test_offer_open_bounds_are_compared_as_bounds_and_invalid_pay_needs_clarification(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    profile(workspace)
    cases = [
        (pay(salary_min=None, salary_max=80), "reject"),
        (pay(salary_min=None, salary_max=180), "clarify"),
        (pay(salary_min=120, salary_max=None), "consider"),
        (pay(salary_min=180, salary_max=120), "clarify"),
        (pay(salary_min=True), "clarify"),
    ]
    for terms, decision in cases:
        offer = engine.offer_save(job_id, terms)
        row = engine.offer_compare([offer["id"]])["offers"][0]
        assert row["decision"] == decision
        if terms["salary_min"] is None:
            assert row["salary"]["lower"] is None


@pytest.mark.parametrize("status", ["draft", "pending", "failed", "provider_custom_state"])
def test_unobserved_inbound_states_are_metadata_not_replies(tmp_path, status):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "applied")
    message = engine.conversation_record(job_id, "inbound", "email", "Not received", status=status)
    assert message["status"] == status and message["direction"] == "inbound"
    assert message["unread"] is False
    assert workspace.store.get("application", application["id"]) == application


@pytest.mark.parametrize("status,unread", [("observed", True), ("received", True), ("read", False)])
def test_observed_inbound_states_advance_pipeline_and_respect_read_status(tmp_path, status, unread):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "applied")
    message = engine.conversation_record(job_id, "inbound", "email", "Actual reply", status=status)
    assert message["unread"] is unread
    assert workspace.store.get("application", application["id"])["stage"] == "reply"


def test_draft_becoming_observed_updates_one_record_and_agrees_with_search_review(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "applied")
    draft = engine.conversation_record(job_id, "inbound", "email", "Provisional", "same-id", status="draft")
    waiting = engine.search_review()
    assert waiting["counts"]["replied"] == 0 and waiting["counts"]["pending"] == 1
    assert waiting["reply_delays"]["n"] == 0 and engine.brief()["unread_messages"] == []
    observed = engine.conversation_record(
        job_id, "inbound", "email", "Actual reply", "same-id", status="observed"
    )
    assert observed["id"] == draft["id"] and observed["status"] == "observed"
    assert observed["created_at"] == draft["created_at"] and observed["unread"] is True
    assert len(engine.conversation_list()) == 1
    assert workspace.store.get("application", application["id"])["stage"] == "reply"
    answered = engine.search_review()
    assert answered["counts"]["replied"] == 1 and answered["counts"]["pending"] == 0
    assert answered["reply_delays"]["n"] == 1
    assert (
        engine.conversation_record(job_id, "inbound", "email", "Actual reply", "same-id", status="observed")
        == observed
    )


def test_explicit_message_assignment_and_read_state_preserve_provider_evidence(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "applied")
    message = engine.conversation_record(None, "inbound", "email", "Actual reply", "imported-id")
    message["source"] = {"link_basis": "unassigned", "sender": "Synthetic", "provider_id": "imported-id"}
    workspace.store.put("message", message["id"], message)

    updated = engine.conversation_update(message["id"], job_id=job_id, read=True)
    assert updated["job_id"] == job_id and updated["unread"] is False and updated["read_at"]
    assert updated["metadata_link_basis"] == "explicit"
    for field in ("source", "text", "direction", "external_id", "status", "created_at", "occurred_at"):
        assert updated[field] == message[field]
    assert workspace.store.get("application", application["id"])["stage"] == "reply"
    assert engine.brief()["unread_messages"] == engine.brief()["unassigned_messages"] == []
    assert engine.conversation_update(message["id"], job_id=job_id, read=True) == updated

    unread = engine.conversation_update(message["id"], read=False)
    assert unread["unread"] is True and unread["read_at"] is None and unread["job_id"] == job_id
    unlinked = engine.conversation_update(message["id"], unlink=True)
    assert unlinked["job_id"] is None and unlinked["metadata_link_basis"] == "unassigned"
    assert unlinked["source"] == message["source"]
    assert engine.conversation_update(message["id"], unlink=True) == unlinked
    assert workspace.store.get("application", application["id"])["stage"] == "reply"
    assert len(workspace.store.list("message")) == 1 and workspace.ledger.export() == []


@pytest.mark.parametrize(
    "direction,status", [("unknown", "observed"), ("outbound", "sent"), ("inbound", "draft")]
)
def test_assigning_or_reading_unconfirmed_messages_does_not_invent_replies(tmp_path, direction, status):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "applied")
    message = engine.conversation_record(None, direction, "email", "Unconfirmed", "new-id", status=status)
    result = engine.conversation_update(message["id"], job_id=job_id, read=True)
    assert result["status"] == status and result["unread"] is False
    assert engine.conversation_update(message["id"], read=False)["unread"] is False
    assert workspace.store.get("application", application["id"]) == application


def test_message_assignment_does_not_regress_later_stage_and_invalid_metadata_is_rejected(tmp_path):
    workspace, engine, job_id = agency(tmp_path)
    application = engine.pipeline_update(job_id, "offer")
    message = engine.conversation_record(None, "inbound", "email", "Later reply", "late-id")
    before = workspace.store.get("message", message["id"])
    for arguments in (
        {"job_id": "missing"},
        {"job_id": ""},
        {"job_id": job_id, "unlink": True},
        {"read": "true"},
        {"unlink": 1},
    ):
        with pytest.raises(ValueError):
            engine.conversation_update(message["id"], **arguments)
        assert workspace.store.get("message", message["id"]) == before
    with pytest.raises(ValueError):
        engine.conversation_update("missing", read=True)
    engine.conversation_update(message["id"], job_id=job_id)
    assert workspace.store.get("application", application["id"]) == application
