import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    home: Path
    connectors: dict = field(default_factory=dict)
    peers: list = field(default_factory=list)
    network_token_env: str = "WORKLIFE_NETWORK_TOKEN"


def load_config(path=None):
    selected = path or os.getenv("WORKLIFE_CONFIG")
    if selected:
        selected = Path(selected).expanduser().resolve()
        data = tomllib.loads(selected.read_text())
        root = selected.parent
    else:
        data, root = {}, Path.cwd()
    home = Path(os.getenv("WORKLIFE_HOME", data.get("worklife", {}).get("home", "~/.worklife"))).expanduser()
    if not home.is_absolute():
        home = root / home
    connectors = data.get("connectors", {})
    for name, config in connectors.items():
        if not config.get("type"):
            raise ValueError(f"Connector {name} requires a type")
    return Config(
        home.resolve(),
        connectors,
        data.get("peers", []),
        data.get("network", {}).get("token_env", "WORKLIFE_NETWORK_TOKEN"),
    )


def secret(config, field, required=False):
    variable = config.get(field + "_env")
    value = os.getenv(variable, "") if variable else ""
    if required and not value:
        raise ValueError(f"Set the environment variable configured in {field}_env")
    return value
