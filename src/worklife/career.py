"""Private career resources. No network calls, account registration, or model calls."""

import ast
import copy
import hashlib
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .storage import now
from .workspace import uid

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".html": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
}
MANIFESTS = {"pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt", "Gemfile"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret)"
    r"\s*[=:]\s*[\"']?([^\s\"',;]+)"
)
ENV_REFERENCE = re.compile(r"(?:env:[A-Z_][A-Z0-9_]*|\$\{[A-Z_][A-Z0-9_]*\}|\$[A-Z_][A-Z0-9_]*)$")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} requires non-empty text")
    return value.strip()


def _metadata(text):
    """Catch accidental credential pastes; credential values belong in the environment."""
    if not isinstance(text, str):
        raise ValueError("Metadata must be text")
    if any(not ENV_REFERENCE.fullmatch(m.group(1)) for m in SECRET_ASSIGNMENT.finditer(text)):
        raise ValueError("Do not store secrets or credentials; use env:VARIABLE references")
    if re.search(r"(?i)\bBearer\s+\S+|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        raise ValueError("Do not store secrets or credentials; use env:VARIABLE references")
    return text


def _excerpt(text, limit=1600):
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1[redacted]@", text)
    text = SECRET_ASSIGNMENT.sub(lambda m: m.group(0).replace(m.group(1), "[redacted]"), text)
    return text[:limit]


class Career:
    def __init__(self, workspace):
        self.workspace = workspace
        self.store = workspace.store

    def _save(self, bucket, record, record_id=None):
        previous = self.store.get(bucket, record_id) if record_id else {}
        value = {
            **record,
            "id": record_id or uid(),
            "created_at": previous.get("created_at", now()),
            "updated_at": now(),
        }
        return self.store.put(bucket, value["id"], value)

    def repository_analyze(self, path, max_files=200):
        """Inspect a local checkout; code is read as data and never imported or run."""
        if type(max_files) is not int or not 1 <= max_files <= 2000:
            raise ValueError("max_files must be between 1 and 2000")
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_dir():
            raise ValueError("Git checkout directory required")
        # Ignore inherited Git overrides and forbid lazy object fetches in partial clones.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            GIT_NO_LAZY_FETCH="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_OPTIONAL_LOCKS="0",
        )

        def git(*args, optional=False):
            result = subprocess.run(
                ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", str(candidate), *args],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                env=env,
            )
            if result.returncode and not optional:
                raise ValueError("A readable local Git checkout is required")
            return result.stdout.rstrip("\n") if not result.returncode else ""

        root = Path(git("rev-parse", "--show-toplevel")).resolve()
        if not root.is_dir() or not candidate.is_relative_to(root):
            raise ValueError("Git checkout directory required")
        candidate = root
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD", optional=True) or "HEAD"
        commit = git("rev-parse", "--verify", "HEAD", optional=True) or None
        default_branch = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", optional=True)
        files = git("ls-files", "-z").split("\0")
        files = list(dict.fromkeys(p for p in files if p))

        def eligible(name):
            parts = Path(name).parts
            return (
                not any(
                    p.startswith(".") or p.lower() in {"node_modules", "vendor", "secrets"} for p in parts
                )
                and not re.search(
                    r"(?i)(?:secret|credential|password|token|private[_.-]?key)", Path(name).name
                )
                and (root / name).is_file()
                and not (root / name).is_symlink()
                and (root / name).resolve().is_relative_to(root)
            )

        selected = [p for p in files if eligible(p)][:max_files]
        languages = {}
        for name in selected:
            language = LANGUAGES.get(Path(name).suffix.lower())
            if language:
                languages[language] = languages.get(language, 0) + 1
        record_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        evidence, suggestions = [], {}

        def read(name):
            with (root / name).open("rb") as stream:
                return stream.read(16384).decode("utf-8", errors="replace")

        def add_evidence(name, kind, content, line=None):
            item = {
                "source": f"repository:{record_id}:{name}",
                "path": name,
                "kind": kind,
                "excerpt": _excerpt(content),
                "snapshot": "working_tree",
            }
            if line:
                item["line"] = line
            evidence.append(item)
            return item

        readmes = [
            p for p in selected if Path(p).name.lower() in {"readme", "readme.md", "readme.rst", "readme.txt"}
        ]
        readme = read(readmes[0]) if readmes else ""
        if readmes:
            add_evidence(readmes[0], "readme", readme)
        for name in [p for p in selected if Path(p).name in MANIFESTS][:4]:
            add_evidence(name, "manifest", read(name))
        for name in [p for p in selected if Path(p).suffix == ".py"][:8]:
            content = read(name)
            try:
                tree = ast.parse(content)
            except (SyntaxError, ValueError):
                continue
            nodes = list(ast.walk(tree))
            markers = (
                (
                    "Python implementation",
                    next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef))), None),
                ),
                (
                    "Asynchronous Python",
                    next((n for n in nodes if isinstance(n, ast.AsyncFunctionDef)), None),
                ),
                (
                    "Automated testing",
                    next((n for n in nodes if isinstance(n, ast.Assert)), None)
                    if Path(name).name.startswith("test_") or "tests" in Path(name).parts
                    else None,
                ),
            )
            for title, node in markers:
                if node is None:
                    continue
                excerpt = "\n".join(content.splitlines()[max(0, node.lineno - 1) : node.lineno + 4])
                item = add_evidence(name, "code", excerpt, node.lineno)
                suggestion = suggestions.setdefault(
                    title,
                    {
                        "title": title,
                        "description": "Observed implementation evidence; confirm authorship, role, and outcomes before claiming this strength.",
                        "status": "proposed",
                        "evidence": [],
                    },
                )
                suggestion["evidence"].append(item)
        recent = []
        if commit:
            for line in git(
                "log", "--no-show-signature", "-10", "--format=%H%x09%aI%x09%s", "HEAD"
            ).splitlines():
                fields = line.split("\t", 2)
                if len(fields) == 3:
                    recent.append({"commit": fields[0], "at": fields[1], "subject": _excerpt(fields[2], 300)})
        value = {
            "id": record_id,
            "path": str(root),
            "name": root.name,
            "branch": branch,
            "commit": commit,
            "default_branch": default_branch.removeprefix("origin/") or branch,
            "languages": languages,
            "file_count": len(files),
            "scanned_file_count": len(selected),
            "readme_excerpt": _excerpt(readme, 4000),
            "recent_commits": recent,
            "evidence": evidence,
            "strength_suggestions": list(suggestions.values()),
            "analyzed_at": now(),
        }
        return self.store.put("repository", record_id, value)

    def strengths_save(self, title, description, evidence, status="proposed", strength_id=None):
        if status not in {"proposed", "confirmed"}:
            raise ValueError("Unknown strength status")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Strength requires source evidence")
        if any(
            not isinstance(e, dict) or not isinstance(e.get("source"), str) or not e["source"].strip()
            for e in evidence
        ):
            raise ValueError("Each evidence item requires a source")
        return self._save(
            "strength",
            {
                "title": _text(title, "Title"),
                "description": _text(description, "Description"),
                "evidence": copy.deepcopy(evidence),
                "status": status,
            },
            strength_id,
        )

    def tactic_save(self, name, hypothesis, actions, success_metric, status="planned", tactic_id=None):
        if status not in {"planned", "active", "paused", "completed"}:
            raise ValueError("Unknown tactic status")
        if not isinstance(actions, list) or not actions:
            raise ValueError("Tactic requires actions")
        return self._save(
            "tactic",
            {
                "name": _text(name, "Name"),
                "hypothesis": _text(hypothesis, "Hypothesis"),
                "actions": [_text(a, "Action") for a in actions],
                "success_metric": _text(success_metric, "Success metric"),
                "status": status,
            },
            tactic_id,
        )

    def platform_save(self, name, url, capabilities, notes="", platform_id=None):
        url = _text(url, "URL")
        parts = urlsplit(url)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("Platform URL must be HTTP(S) without credentials")
        if not isinstance(capabilities, list):
            raise ValueError("Capabilities must be a list")
        return self._save(
            "platform",
            {
                "name": _text(name, "Name"),
                "url": _metadata(url),
                "capabilities": list(dict.fromkeys(_text(c, "Capability") for c in capabilities)),
                "notes": _metadata(notes),
            },
            platform_id,
        )

    def account_save(self, platform_id, identifier, status="planned", email="", notes="", account_id=None):
        self.store.get("platform", platform_id)
        if status not in {"planned", "registering", "verification_required", "active", "blocked", "closed"}:
            raise ValueError("Unknown account status")
        return self._save(
            "account",
            {
                "platform_id": platform_id,
                "identifier": _metadata(_text(identifier, "Identifier")),
                "status": status,
                "email": _metadata(email),
                "notes": _metadata(notes),
            },
            account_id,
        )

    def cv_localize(self, cv_id, language, translations, headline=None, summary=None, name=None):
        if not isinstance(language, str) or not re.fullmatch(
            r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language
        ):
            raise ValueError("A BCP47 language tag is required")
        original = self.store.get("cv", cv_id)
        facts = {f["id"]: f for f in original["facts"]}
        ids = list(dict.fromkeys(original["fact_ids"]))
        if not isinstance(translations, dict) or set(translations) != set(ids) or not ids:
            raise ValueError("Supply a translation keyed by every selected fact ID")
        selected = [
            {
                **copy.deepcopy(facts[i]),
                "original_text": facts[i].get("original_text", facts[i]["text"]),
                "text": _text(translations[i], "Fact translation"),
            }
            for i in ids
        ]
        headline = _text(headline, "Headline") if headline is not None else ""
        summary = _text(summary, "Summary") if summary is not None else ""
        first_line = original.get("markdown", "").splitlines()
        person = first_line[0].removeprefix("# ") if first_line else ""
        markdown = f"# {person}\n\n"
        if headline:
            markdown += f"## {headline}\n\n"
        if summary:
            markdown += summary + "\n\n"
        markdown += "\n".join(f"- {f['text']}" for f in selected) + "\n"
        value = {
            "id": uid(),
            "name": _text(name, "Name") if name is not None else f"{original['name']} ({language})",
            "source_cv_id": cv_id,
            "language": language,
            "headline": headline,
            "summary": summary,
            "original_headline": original.get("original_headline", original.get("headline", "")),
            "original_summary": original.get("original_summary", original.get("summary", "")),
            "original_facts": copy.deepcopy(original.get("original_facts", original["facts"])),
            "fact_ids": original["fact_ids"],
            "facts": selected,
            "markdown": markdown,
            "created_at": now(),
            "review_required": True,
        }
        return self.store.put("cv", value["id"], value)
