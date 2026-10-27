"""Job-search operations shared by the MCP host and the local application."""

from .career import Career
from .credentials import Credentials
from .federation import sync_peer
from .operations import Operations


def register_tools(mcp, workspace, connectors, peers):
    from .agent_runtime import AgentRuntime

    w = workspace
    career = Career(w)
    credentials = Credentials(w)
    runtime = AgentRuntime(w, mcp)

    def scheduled(tool, arguments):
        args = dict(arguments)
        if tool == "jobs_search":
            return connectors.search(
                args.pop("connector"), args.pop("query", ""), **args.pop("parameters", {})
            )
        if tool == "connector_read":
            return connectors.read(args["connector"], args["operation"], args.get("parameters", {}))
        if tool == "peer_sync":
            name = args["name"]
            if name not in peers():
                raise ValueError("Unknown replica")
            return sync_peer(w, peers()[name])
        if tool == "repository_analyze":
            return career.repository_analyze(**args)
        if tool == "reminder":
            return w.add_task(**args)
        if tool == "agent_cycle":
            return runtime.start(**args)
        raise ValueError("Unsupported scheduled job-search operation")

    operations = Operations(w, scheduled)

    @mcp.tool()
    def credential_create(name: str, username: str = "") -> dict:
        """Generate/reuse a registration password in the OS credential store. Returns only a reference.
        No password is returned to the model or written to the shared database."""
        return credentials.create(name, username)

    @mcp.tool()
    def browser_fill_credential(selector: str, name: str, field: str = "password") -> dict:
        """Fill a stored username/password directly into the browser without returning its value.
        Use credential_create when registering an account; account_save retains only its reference."""
        return credentials.fill(mcp.worklife_browser, selector, name, field)

    @mcp.tool()
    def resource_save(
        name: str,
        kind: str,
        url: str = "",
        notes: str = "",
        budget: float | None = None,
        resource_id: str | None = None,
    ) -> dict:
        """Save a private job-search resource: source, service, learning material, time/money budget."""
        return operations.resource_save(name, kind, url, notes, budget, resource_id)

    @mcp.tool()
    def activity_record(
        kind: str, summary: str, related_id: str | None = None, metrics: dict | None = None
    ) -> dict:
        """Record actual private activity and measured costs/duration/tokens. Never publish personal statistics."""
        return operations.activity_record(kind, summary, related_id, metrics)

    @mcp.tool()
    def statistics_report() -> dict:
        """Real private search statistics, stages, action states and measured resource usage."""
        return operations.statistics()

    @mcp.tool()
    def schedule_save(
        name: str,
        tool: str,
        arguments: dict,
        interval_minutes: float = 60,
        enabled: bool = True,
        schedule_id: str | None = None,
    ) -> dict:
        """Persistent job-search schedule. tools: agent_cycle,jobs_search,connector_read,peer_sync,
        repository_analyze,reminder. The app or worker executes due jobs while running."""
        return operations.schedule_save(name, tool, arguments, interval_minutes, enabled, schedule_id)

    @mcp.tool()
    def schedule_toggle(schedule_id: str, enabled: bool) -> dict:
        """Pause or resume a persistent schedule."""
        return operations.schedule_toggle(schedule_id, enabled)

    @mcp.tool()
    def schedule_run(schedule_id: str) -> dict:
        """Run a configured scheduled operation now and retain its actual result/error."""
        return operations.schedule_run(schedule_id)

    @mcp.tool()
    def employer_block(domain: str, reason: str, evidence_url: str = "", blocked: bool = True) -> dict:
        """Block/unblock a company locally. Excludes known company matches from search and prevents contacts.
        Company observations may be shared separately, never worker profiles or personal blacklists."""
        return operations.block_employer(domain, reason, evidence_url, blocked)

    @mcp.tool()
    def employer_block_status(domain: str) -> dict:
        """Read your local company's block state and reason."""
        return operations.employer_block_status(domain)

    @mcp.tool()
    def repository_analyze(path: str, max_files: int = 200) -> dict:
        """Analyze your local Git checkout read-only: code evidence, languages, commits and proposed strengths.
        Does not execute repository code or publish private repository findings."""
        return career.repository_analyze(path, max_files)

    @mcp.tool()
    def strength_save(
        title: str,
        description: str,
        evidence: list[dict],
        status: str = "proposed",
        strength_id: str | None = None,
    ) -> dict:
        """Save a private strength with evidence [{source,...}]. Confirm only after reviewing supporting work."""
        return career.strengths_save(title, description, evidence, status, strength_id)

    @mcp.tool()
    def tactic_save(
        name: str,
        hypothesis: str,
        actions: list[str],
        success_metric: str,
        status: str = "planned",
        tactic_id: str | None = None,
    ) -> dict:
        """Save a private search tactic, hypothesis, actions and measurable success criterion."""
        return career.tactic_save(name, hypothesis, actions, success_metric, status, tactic_id)

    @mcp.tool()
    def platform_save(
        name: str, url: str, capabilities: list[str], notes: str = "", platform_id: str | None = None
    ) -> dict:
        """Register a discovered aggregator, employer career site or relevant job-search service.
        Sources are chosen by the agent, not limited to bundled provider adapters."""
        return career.platform_save(name, url, capabilities, notes, platform_id)

    @mcp.tool()
    def account_save(
        platform_id: str,
        identifier: str,
        status: str = "planned",
        email: str = "",
        notes: str = "",
        account_id: str | None = None,
    ) -> dict:
        """Track a job-search account/registration and email verification locally. Metadata only, no secrets.
        Actual registration uses browser/API and mail tools; record active only after successful verification."""
        return career.account_save(platform_id, identifier, status, email, notes, account_id)

    @mcp.tool()
    def cv_localize(
        cv_id: str,
        language: str,
        translations: dict,
        headline: str | None = None,
        summary: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Create a CV in any language from agent-supplied translations keyed by every original fact ID.
        Preserve sources and original text; no invented experience or automatic English fallback."""
        return career.cv_localize(cv_id, language, translations, headline, summary, name)

    @mcp.tool()
    def agent_run(goal: str, max_steps: int = 8) -> dict:
        """Start an observable autonomous job-search cycle with your configured model and existing tools.
        WORKLIFE_AGENT_BASE_URL/MODEL and optional API_KEY configure an OpenAI-compatible endpoint."""
        return runtime.start(goal, max_steps)

    @mcp.tool()
    def agent_status() -> dict:
        """Model configuration availability and actual local agent-run states, without secret values."""
        return runtime.status()

    @mcp.tool()
    def agent_cancel(run_id: str) -> dict:
        """Request cancellation; the agent stops between operations and retains completed work."""
        return runtime.cancel(run_id)

    mcp.worklife_workspace = w
    mcp.worklife_operations = operations
    mcp.worklife_career = career
    mcp.worklife_runtime = runtime
    mcp.worklife_connectors = connectors
    mcp.worklife_peers = peers
