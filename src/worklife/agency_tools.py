"""Deterministic market and hiring operations for the external agent and local board."""

from mcp.types import ToolAnnotations

from .advisor import Advisor
from .agency import Agency
from .inbox import InboxBridge
from .market import Market
from .storage import now


def _search_metadata(value):
    if isinstance(value, dict):
        clean, redacted = {}, False
        for key, item in value.items():
            normalized = "".join(char for char in key.lower() if char.isalnum())
            if any(
                secret in normalized
                for secret in ("token", "password", "secret", "authorization", "apikey", "credentials")
            ):
                clean[key], redacted = "[СКРЫТО]", True
            else:
                clean[key], changed = _search_metadata(item)
                redacted = redacted or changed
        return clean, redacted
    if isinstance(value, list):
        items = [_search_metadata(item) for item in value]
        return [item for item, _ in items], any(changed for _, changed in items)
    return value, False


def register_agency_tools(mcp, workspace, connectors):
    market, advisor, agency = Market(workspace), Advisor(workspace), Agency(workspace)
    inbox = InboxBridge(workspace, connectors, agency)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
    external_read = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)

    @mcp.tool(annotations=write)
    def market_snapshot(
        name: str, job_ids: list[str], scope: dict | None = None, sources: list | None = None, notes: str = ""
    ) -> dict:
        """Freeze an explicit collected vacancy sample, scope and source coverage. Private, not the whole market.
        Record role/level/region/work format and collection limits. Do not sample only personal favourites."""
        return market.snapshot(name, job_ids, scope, sources, notes)

    @mcp.tool(annotations=read)
    def market_report(snapshot_id: str | None = None, filters: dict | None = None) -> dict:
        """Describe an immutable sample: deduplicated demand, salary bounds/quantiles, coverage and exclusions.
        Currency, pay period and gross/net remain separate; no invented FX, wages or hiring probabilities."""
        return market.report(snapshot_id, filters)

    def collect(name, searches, scope=None):
        if not isinstance(searches, list) or not searches or len(searches) > 20:
            raise ValueError("Укажите от 1 до 20 явных поисковых запросов к источникам")
        ids, sources, errors = [], [], []
        for search in searches:
            if not isinstance(search, dict) or not isinstance(search.get("connector"), str):
                raise ValueError("Для каждого запроса укажите источник в поле connector")
            parameters = search.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise ValueError("Параметры поиска должны быть объектом")
            metadata, redacted = _search_metadata(parameters)
            source = {
                "connector": search["connector"],
                "query": search.get("query", ""),
                "observed_at": now(),
                "local_blocklist_applied": True,
                "parameters": metadata,
                "parameters_redacted": redacted,
            }
            try:
                rows = connectors.search(search["connector"], search.get("query", ""), **parameters)
                ids.extend(row["id"] for row in rows)
                source.update(status="collected", received=len(rows))
            except (ValueError, ConnectionError, OSError) as exc:
                message = f"Поиск в источнике не выполнен: {exc}"
                source.update(status="unavailable", received=0, error=type(exc).__name__, message=message)
                errors.append(
                    {"connector": search["connector"], "error": type(exc).__name__, "message": message}
                )
            sources.append(source)
        sample = market.snapshot(
            name,
            list(dict.fromkeys(ids)),
            scope,
            sources,
            "Выборка собрана из явно выбранных доступных источников с учётом локальных исключений.",
        )
        return {
            "status": "partial" if errors else "completed",
            "snapshot": sample,
            "report": market.report(sample["id"]),
            "errors": errors,
        }

    @mcp.tool(annotations=external_read)
    def market_collect(name: str, searches: list[dict], scope: dict | None = None) -> dict:
        """Collect explicit source searches then freeze a market sample. Each search: connector,query,parameters.
        Source failures remain visible. For browser/custom APIs, use job_save then market_snapshot instead."""
        return collect(name, searches, scope)

    @mcp.tool(annotations=read)
    def recommendations_report(job_ids: list[str] | None = None, limit: int = 20) -> dict:
        """Explain vacancy fit to explicit profile conditions and sourced facts; unknowns stay questions.
        Ranking is deterministic evidence/constraint coverage, not a probability of being hired."""
        return advisor.report(job_ids, limit)

    @mcp.tool(annotations=write)
    def recommendation_save(
        job_id: str,
        verdict: str,
        reasons: list[str],
        evidence: list[dict],
        questions: list[str] | None = None,
        cv_id: str | None = None,
        priority: int = 3,
    ) -> dict:
        """Save the external agent's semantic job/CV assessment separately from literal rule checks.
        Evidence cites existing fact_id or nonempty job_field; quotations come from stored data.
        Priority 1–5 is order, not hiring probability. Hard constraints prevail; changed context makes it stale."""
        return advisor.save_recommendation(job_id, verdict, reasons, evidence, questions, cv_id, priority)

    @mcp.tool(annotations=read)
    def cv_match(job_id: str) -> dict:
        """Compare private CV variants against explicit job requirements and requested CV language.
        Every evidence match references existing facts; return no winner when evidence cannot distinguish variants."""
        return advisor.cv_match(job_id)

    @mcp.tool(annotations=write)
    def resume_import(name: str, text: str, language: str = "ru", source: str = "user") -> dict:
        """Import extracted resume text as a private CV and quoted self-reported evidence.
        Preserve existing profile/facts. The external agent can interpret it without inventing experience."""
        return advisor.import_resume(name, text, language, source)

    @mcp.tool(annotations=read)
    def interview_brief(job_id: str) -> dict:
        """Prepare a vacancy-specific interview brief: sourced experience, gaps and questions about unknown terms."""
        return advisor.interview_brief(job_id)

    @mcp.tool(annotations=write)
    def pipeline_update(
        job_id: str,
        stage: str = "saved",
        cv_id: str | None = None,
        note: str = "",
        next_action: str = "",
        due_at: str | None = None,
    ) -> dict:
        """Persist an observed hiring stage and next action. CV is optional before it is selected.
        Stages: saved,applied,reply,interview,offer,accepted,rejected,withdrawn. This never sends or accepts anything."""
        return agency.pipeline_update(job_id, stage, cv_id, note, next_action, due_at)

    @mcp.tool(annotations=write)
    def conversation_record(
        job_id: str | None = None,
        direction: str = "unknown",
        channel: str = "",
        text: str = "",
        external_id: str = "",
        in_reply_to: str = "",
        occurred_at: str | None = None,
        status: str = "observed",
    ) -> dict:
        """Record an observed private message; never sends it. Stable provider IDs deduplicate messages.
        Only known inbound messages may advance saved/applied to reply. Ambiguous links remain unassigned."""
        return agency.conversation_record(
            job_id, direction, channel, text, external_id, in_reply_to, occurred_at, status
        )

    @mcp.tool(annotations=read)
    def conversation_list(job_id: str | None = None, limit: int = 50) -> list[dict]:
        """Read recent private messages, optionally linked to one vacancy. Reading does not mark them read."""
        return agency.conversation_list(job_id, limit)

    @mcp.tool(annotations=write)
    def conversation_update(
        message_id: str, job_id: str | None = None, read: bool | None = None, unlink: bool = False
    ) -> dict:
        """Set an explicit vacancy link and local read state on an existing message. No provider writes.
        Omitted job_id keeps the link; unlink=True removes it. Source, body and provider IDs stay unchanged."""
        return agency.conversation_update(message_id, job_id, read, unlink)

    @mcp.tool(annotations=external_read)
    def inbox_sync(
        connector: str,
        operation: str = "inbox",
        parameters: dict | None = None,
        job_id: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Read a configured inbox and persist observed messages. Exact reply IDs link known applications.
        Unknown direction/link stays unknown. Returns next cursor parameters; does not send external messages."""
        return inbox.sync(connector, operation, parameters, job_id, limit)

    @mcp.tool(annotations=write)
    def interview_save(
        job_id: str,
        scheduled_at: str,
        kind: str = "interview",
        notes: str = "",
        meeting_url: str = "",
        status: str = "scheduled",
        interview_id: str | None = None,
    ) -> dict:
        """Record an interview and its timezone-aware time privately. Does not book or send an invitation."""
        return agency.interview_save(job_id, scheduled_at, kind, notes, meeting_url, status, interview_id)

    @mcp.tool(annotations=write)
    def offer_save(
        job_id: str, terms: dict, notes: str = "", status: str = "received", offer_id: str | None = None
    ) -> dict:
        """Record actually received offer terms: pay/currency/period/gross, hours, format, dates and benefits.
        Preserve unknown conditions. Does not accept an offer or communicate with the employer."""
        return agency.offer_save(job_id, terms, notes, status, offer_id)

    @mcp.tool(annotations=read)
    def offer_compare(offer_ids: list[str] | None = None) -> dict:
        """Compare private offers against user constraints and income deadline, preserving incompatible pay groups."""
        return agency.offer_compare(offer_ids)

    @mcp.tool(annotations=read)
    def search_review(days: int = 30) -> dict:
        """Measured hiring funnel, reply delays, pending conversations and due actions in a stated time window.
        No response is not a rejection; these observations do not establish future hiring probability."""
        return agency.search_review(days)

    @mcp.tool(annotations=read)
    def agency_brief() -> dict:
        """Resume the user's search: market coverage, evidence-based recommendations and next hiring actions."""
        return {**agency.brief(), "market": market.report(), "advisor": advisor.report()}

    mcp.worklife_market = market
    mcp.worklife_advisor = advisor
    mcp.worklife_agency = agency
    mcp.worklife_inbox = inbox
    mcp.worklife_market_collect = collect
