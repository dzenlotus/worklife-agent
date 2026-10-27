"""Portable instructions and explicit tool selection for the user's career agent."""

import json
from pathlib import Path

BUNDLE_DIR = Path(__file__).parent / "agent_bundle" / "recruiter"


def load_agent_profile(name: str = "recruiter") -> dict:
    if name != "recruiter":
        raise ValueError(f"Unknown agent profile: {name}")
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    toolset = json.loads((BUNDLE_DIR / "toolset.json").read_text(encoding="utf-8"))
    return {
        "id": manifest["id"],
        "name": manifest["name"],
        "instructions": (BUNDLE_DIR / "AGENTS.md").read_text(encoding="utf-8"),
        "allowed_tools": toolset["allowed_tools"],
        "skills": manifest["skills"],
    }


def read_agent_skill(name: str) -> str:
    for skill in load_agent_profile()["skills"]:
        if skill["name"] == name:
            return (BUNDLE_DIR / skill["path"]).read_text(encoding="utf-8")
    raise ValueError(f"Unknown recruiter skill: {name}")
