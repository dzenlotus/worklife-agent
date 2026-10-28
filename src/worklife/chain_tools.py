"""Agent-facing operations for the tokenless chain; no manual enrollment or payments."""

import asyncio
from urllib.parse import urlparse


def register_chain_tools(mcp, workspace, network):
    @mcp.tool()
    def blockchain_status() -> dict:
        """Verified work/chain state and current monthly qualification; confirmations are protocol validity."""
        return {**workspace.blockchain.status(), "synchronization": network.status()}

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
    async def blockchain_sync() -> dict:
        """Sync verified public blocks via configured Telegram service group and v2 peers; no private data."""
        return await asyncio.to_thread(network.tick, force=True)

    @mcp.tool()
    def blockchain_telegram_connect(chat: str) -> dict:
        """Select a joined Telegram service group for automatic public block exchange.
        Requires user authorization to publish the public employer database to that group.
        Telegram account credentials are environment references, never tool arguments."""
        return network.connect_telegram(chat)

    @mcp.tool()
    async def blockchain_telegram_create_group(title: str = "Worklife — общая база") -> dict:
        """Create a private service supergroup and select it for public block synchronization.
        Requires explicit user authorization to create a group. Invites nobody and sends no private data.
        An authorized Telegram user session must already be configured in the environment."""
        return await network.create_telegram_group(title)
