"""Fixed, incompatible network profiles, selected once when the process imports."""

import os

PROFILE = os.environ.get("WORKLIFE_CHAIN_PROFILE", "development")
try:
    NETWORK, BLOCK_BITS, QUALIFICATION_BITS, CONFIRMATIONS = {
        "development": ("worklife-chain-v1", 12, 10, 3),
        "public-testnet-v1": ("worklife-public-testnet-v1", 25, 18, 6),
    }[PROFILE]
except KeyError:
    raise ValueError(f"Unknown WORKLIFE_CHAIN_PROFILE: {PROFILE!r}") from None
