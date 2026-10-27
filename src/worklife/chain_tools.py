"""Agent-facing operations for the tokenless chain; no manual enrollment or payments."""

from urllib.parse import urlparse


def register_chain_tools(mcp, workspace, network):
    @mcp.tool()
    def blockchain_status() -> dict:
        """Verified work/chain state and current monthly qualification; confirmations are protocol validity."""
        return workspace.blockchain.status()

    @mcp.tool()
    def blockchain_challenge() -> dict:
        """Get public monthly employer-format tasks bound to this agent key and the current chain head."""
        return workspace.blockchain.challenge()

    @mcp.tool()
    def blockchain_qualify(max_attempts: int = 100000) -> dict:
        """Automatically solve public tasks and bounded PoW; rights expire at the next UTC month.
        Demonstrates protocol task completion, not independence, intelligence or factual truth."""
        result = workspace.blockchain.qualify(max_attempts=max_attempts)
        network.mark_dirty()
        return result

    @mcp.tool()
    def blockchain_mine(max_attempts: int = 100000) -> dict:
        """After qualification, spend a bounded hash budget proposing a block. No coin, fee or per-key bonus.
        Three-deep inclusion is probabilistic protocol confirmation, never proof an employer claim is true."""
        if not 0 <= max_attempts <= 1_000_000:
            raise ValueError("Mining budget must be between 0 and 1000000 attempts")
        result = workspace.blockchain.mine(max_attempts=max_attempts)
        network.mark_dirty()
        return result

    @mcp.tool()
    def blockchain_blocks(after: int = 0, limit: int = 100) -> dict:
        """Export verified public blocks, including forks; contains no private profile/CV tables."""
        return workspace.blockchain.page(after, limit)

    @mcp.tool()
    def blockchain_import(blocks: list[dict]) -> dict:
        """Atomically verify/import up to 100 qualified PoW blocks. Raw signatures alone confer no acceptance."""
        result = workspace.blockchain.import_blocks(blocks)
        network.mark_dirty()
        return result

    @mcp.tool()
    def blockchain_connect(url: str) -> dict:
        """Save a public v2 node for automatic block exchange. Open connection needs no bearer token or approval."""
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("A public HTTP(S) node URL without credentials is required")
        value = {"url": url.rstrip("/"), "protocol": 2}
        workspace.store.put("peer", value["url"], {"id": value["url"], "config": value})
        network.mark_dirty()
        return value

    @mcp.tool()
    def blockchain_sync() -> dict:
        """Exchange verified blocks with configured public v2 peers now; never uploads raw proposals to GitHub."""
        return network.tick(force=True)
