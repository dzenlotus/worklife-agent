"""Daily, private update metadata for the running Worklife installation."""

import os
import re
import shlex
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

import httpx

PYPI_URL = "https://pypi.org/pypi/worklife-agent/json"
PROJECT_URL = "https://pypi.org/project/worklife-agent/"
CHECK_INTERVAL = 24 * 60 * 60


def stable_version(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        return tuple(int(part) for part in value.split("."))
    return None


class ReleaseUpdates:
    def __init__(self, store):
        self.store = store

    def status(self):
        try:
            installed = version("worklife-agent")
        except PackageNotFoundError:
            installed = "unknown"
        try:
            cached = self.store.get("release", "pypi")
        except ValueError:
            cached = {}
        timestamp = time.time()
        checked_time = cached.get("checked_time")
        fresh = isinstance(checked_time, (int, float)) and 0 <= timestamp - checked_time < CHECK_INTERVAL
        offline = os.getenv("WORKLIFE_NETWORK_OFFLINE") == "1"
        if not offline and not fresh:
            cached = {
                "checked_time": timestamp,
                "checked_at": datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z"),
                "latest_version": cached.get("latest_version"),
                "status": "unavailable",
            }
            try:
                with httpx.Client(timeout=2, follow_redirects=False) as client:
                    response = client.get(PYPI_URL)
                    response.raise_for_status()
                    info = response.json()["info"]
                    latest = info["version"]
                    if stable_version(latest) is None or info.get("yanked"):
                        raise ValueError("No stable release available")
                cached.update(latest_version=latest, status="checked")
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                pass
            self.store.put("release", "pypi", cached)
        status = "offline" if offline else cached.get("status", "unavailable")
        latest = cached.get("latest_version")
        installed_parts, latest_parts = stable_version(installed), stable_version(latest)
        if latest_parts is None:
            latest = None
        return {
            "installed_version": installed,
            "latest_version": latest,
            "update_available": bool(
                status == "checked" and installed_parts and latest_parts and latest_parts > installed_parts
            ),
            "status": status,
            "checked_at": cached.get("checked_at"),
            "release_url": f"{PROJECT_URL}{latest}/" if latest else PROJECT_URL,
            "update_command": shlex.join(
                ["uv", "pip", "install", "--python", sys.executable, "--upgrade", "worklife-agent"]
            ),
        }
