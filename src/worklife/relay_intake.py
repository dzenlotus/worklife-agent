"""Build the public relay snapshot from signed employer-event submissions."""

import argparse
import json
import os
import re
from pathlib import Path

import httpx

from .automatic_network import INTAKE_MARKER, merge_events
from .ledger import Ledger
from .storage import canonical, now

MARKER = INTAKE_MARKER


def build_snapshot(snapshot, issues):
    if snapshot.get("protocol") != 1 or not isinstance(snapshot.get("events"), list):
        raise ValueError("Unsupported previous snapshot")
    incoming, malformed = [], 0
    fragments = {}
    for issue in issues:
        body = issue.get("body") or ""
        if "pull_request" in issue or not isinstance(body, str) or not body.startswith(MARKER):
            continue
        try:
            batch = json.loads(body[len(MARKER) :])
            if batch.get("protocol") == 1 and "fragment" in batch:
                fragment = batch["fragment"]
                submitter = (issue.get("user") or {}).get("id")
                if (
                    set(batch) != {"protocol", "fragment"}
                    or not isinstance(fragment, dict)
                    or set(fragment) != {"event_id", "group", "index", "total", "data"}
                    or type(submitter) is not int
                    or submitter < 1
                    or not isinstance(fragment["group"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", fragment["group"])
                    or not isinstance(fragment["event_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", fragment["event_id"])
                    or type(fragment["index"]) is not int
                    or type(fragment["total"]) is not int
                    or not 0 <= fragment["index"] < fragment["total"]
                    or not isinstance(fragment["data"], str)
                    or len(fragment["data"]) > 40000
                ):
                    raise ValueError("Unsupported submission fragment")
                group = fragments.setdefault(
                    (submitter, fragment["group"]),
                    {
                        "event_id": fragment["event_id"],
                        "total": fragment["total"],
                        "chunks": {},
                        "conflict": False,
                    },
                )
                index, data = fragment["index"], fragment["data"]
                if (
                    group["event_id"] != fragment["event_id"]
                    or group["total"] != fragment["total"]
                    or (index in group["chunks"] and group["chunks"][index] != data)
                ):
                    group["conflict"] = True
                group["chunks"][index] = data
                continue
            if (
                batch.get("protocol") != 1
                or not isinstance(batch.get("events"), list)
                or len(batch["events"]) > 1000
            ):
                raise ValueError("Unsupported submission")
            incoming.extend(batch["events"])
        except (ValueError, TypeError, AttributeError, RecursionError):
            malformed += 1
    for group in fragments.values():
        try:
            if group["conflict"]:
                raise ValueError("Conflicting submission fragments")
            if len(group["chunks"]) != group["total"]:
                continue
            event = json.loads("".join(group["chunks"][index] for index in range(group["total"])))
            Ledger.check_event(event)
            if event["event_id"] != group["event_id"]:
                raise ValueError("Fragment event ID mismatch")
            incoming.append(event)
        except (ValueError, TypeError, KeyError, RecursionError):
            malformed += 1
    merged = merge_events(snapshot["events"], incoming)
    result = {
        "protocol": 1,
        "events": merged["events"],
        "validation": {
            "rejected": merged["rejected"] + malformed,
            "pending": merged["pending"],
            "conflicts": merged["conflicts"],
        },
    }
    unchanged = result["events"] == snapshot["events"] and result["validation"] == snapshot.get("validation")
    result["updated_at"] = snapshot.get("updated_at") if unchanged else now()
    return result


def fetch_submissions(repository, token):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid relay repository")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    issues = []
    with httpx.Client(headers=headers, timeout=30, follow_redirects=False) as client:
        page = 1
        while True:
            response = client.get(
                f"https://api.github.com/repos/{repository}/issues",
                params={"state": "all", "sort": "created", "direction": "asc", "per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError("Invalid issue response")
            issues.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Validate employer submissions into the shared relay snapshot"
    )
    parser.add_argument(
        "--repository", default=os.getenv("GITHUB_REPOSITORY", "dzenlotus/worklife-employers")
    )
    parser.add_argument("--snapshot", default="snapshot.json")
    args = parser.parse_args()
    path = Path(args.snapshot)
    old = json.loads(path.read_text()) if path.exists() else {"protocol": 1, "events": []}
    result = build_snapshot(old, fetch_submissions(args.repository, os.getenv("GITHUB_TOKEN", "")))
    path.with_suffix(".tmp").write_bytes(canonical(result) + b"\n")
    path.with_suffix(".tmp").replace(path)
    print(json.dumps({"events": len(result["events"]), "validation": result["validation"]}))


if __name__ == "__main__":
    main()
