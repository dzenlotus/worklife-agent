"""Install the portable Recruiter workflow in documented MCP clients."""

import copy
import hashlib
import io
import json
import os
import re
import stat
import sys
from collections.abc import MutableMapping
from datetime import UTC, datetime
from pathlib import Path

import tomlkit
from json5.dumper import ModelDumper
from json5.dumper import dumps as json5_dumps
from json5.loader import DefaultLoader, ModelLoader
from json5.loader import loads as json5_loads
from json5.model import JSONObject
from ruamel.yaml import YAML

from .agent_profile import BUNDLE_DIR, load_agent_profile

SERVER_NAME = "worklife_recruiter"
AGENT_NAME = "worklife-recruiter"
DESCRIPTION = "Личный карьерный агент: рынок, вакансии, правдивые CV, отклики, интервью и офферы."
CATALOG_PATH = BUNDLE_DIR.parent / "harnesses.json"
GENERIC_MCP = {
    "format": "json",
    "root_key": ["mcpServers"],
    "entries_shape": "map",
    "entry_template": {"command": "$PROCESS_COMMAND", "args": "$PROCESS_ARGS"},
}


def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def targets():
    return [
        {
            "id": item["id"],
            "name": item["display_name"],
            "mode": item["mode"],
            "project": bool(
                item["mcp"].get("project")
                and item["mcp"].get("installable")
                and item["mcp"].get("auto_apply_documented", True)
            ),
            "user": list(item["mcp"].get("user", {})),
            "explicit_config": bool(item.get("mcp_schema")),
            "runtime_tested": item["runtime_tested"],
            "limits": item["limits"],
        }
        for item in load_catalog()["harnesses"]
    ]


def _platform():
    return "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate configuration key: {key}")
        result[key] = value
    return result


def _merge_mapping(document, path, identity, entry, shape="map", identity_field="name"):
    if not isinstance(document, MutableMapping):
        raise ValueError("Configuration must be a mapping")
    parent = document
    for key in path[:-1]:
        if key not in parent:
            parent[key] = {}
        parent = parent[key]
        if not isinstance(parent, MutableMapping):
            raise ValueError(f"Configuration field {key} must be a mapping")
    key = path[-1]
    if shape == "map":
        if key not in parent:
            parent[key] = {}
        if not isinstance(parent[key], MutableMapping):
            raise ValueError(f"Configuration field {key} must be a mapping")
        parent[key][identity] = copy.deepcopy(entry)
    else:
        if key not in parent:
            parent[key] = []
        entries = parent[key]
        if not isinstance(entries, list):
            raise ValueError(f"Configuration field {key} must be a list")
        positions = [
            i
            for i, value in enumerate(entries)
            if isinstance(value, dict) and value.get(identity_field) == identity
        ]
        if len(positions) > 1:
            raise ValueError(f"Duplicate configuration identity: {identity}")
        if positions:
            entries[positions[0]] = copy.deepcopy(entry)
        else:
            entries.append(copy.deepcopy(entry))
    return document


def _json_node_index(node, name):
    if not isinstance(node, JSONObject):
        raise ValueError("Configuration field must be an object")
    matches = [i for i, key in enumerate(node.keys) if DefaultLoader().load(key) == name]
    if len(matches) > 1:
        raise ValueError(f"Duplicate configuration key: {name}")
    return matches[0] if matches else None


def _json_set(node, name, value):
    index = _json_node_index(node, name)
    new = json5_loads(json.dumps({name: value}, ensure_ascii=False, indent=2), loader=ModelLoader()).value
    if index is None:
        node.keys.append(new.keys[0])
        node.values.append(new.values[0])
    else:
        new.values[0].wsc_before = node.values[index].wsc_before
        new.values[0].wsc_after = node.values[index].wsc_after
        node.values[index] = new.values[0]
    return node.values[index if index is not None else -1]


def merge_config(source, spec, entry, identity=SERVER_NAME):
    """Replace one owned entry, preserving unrelated settings and comments."""
    kind = spec["format"]
    path = spec["root_key"]
    shape = spec.get("entries_shape", "map")
    id_field = spec.get("identity_field", "name")
    source = source or ""
    if kind == "json":
        document = json.loads(source or "{}", object_pairs_hook=_unique_pairs)
        updated = copy.deepcopy(document)
        _merge_mapping(updated, path, identity, entry, shape, id_field)
        return (
            source
            if source and document == updated
            else json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        )
    if kind in {"jsonc", "json5"}:
        if not source.strip():
            document = _merge_mapping({}, path, identity, entry, shape, id_field)
            return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        tree = json5_loads(source or "{}", loader=ModelLoader())
        before = DefaultLoader().load(tree)
        expected = copy.deepcopy(before)
        _merge_mapping(expected, path, identity, entry, shape, id_field)
        if source and before == expected:
            return source
        node = tree.value
        for key in path:
            index = _json_node_index(node, key)
            node = _json_set(node, key, {}) if index is None else node.values[index]
        if shape != "map":
            raise ValueError("JSONC list adapter is not supported by this catalog")
        _json_set(node, identity, entry)
        output = json5_dumps(tree, dumper=ModelDumper())
        if json5_loads(output) != expected:
            raise ValueError("Configuration edit did not preserve unrelated data")
        return output if output.endswith("\n") else output + "\n"
    if kind == "toml":
        document = tomlkit.parse(source)
        parent = document
        for key in path[:-1]:
            if key not in parent:
                parent[key] = tomlkit.table()
            parent = parent[key]
            if not isinstance(parent, MutableMapping):
                raise ValueError(f"Configuration field {key} must be a table")
        key = path[-1]
        if shape == "map":
            if key not in parent:
                parent[key] = tomlkit.table()
            if not isinstance(parent[key], MutableMapping):
                raise ValueError(f"Configuration field {key} must be a table")
            if parent[key].get(identity) == entry:
                return source
            parent[key][identity] = entry
        else:
            if key not in parent:
                parent[key] = tomlkit.aot()
            entries = parent[key]
            if not isinstance(entries, list):
                raise ValueError(f"Configuration field {key} must be an array of tables")
            positions = [
                i
                for i, value in enumerate(entries)
                if isinstance(value, dict) and value.get(id_field) == identity
            ]
            if len(positions) > 1:
                raise ValueError(f"Duplicate configuration identity: {identity}")
            if positions and entries[positions[0]] == entry:
                return source
            table = tomlkit.table()
            table.update(entry)
            if positions:
                entries[positions[0]] = table
            else:
                entries.append(table)
        return tomlkit.dumps(document)
    if kind == "yaml":
        yaml = YAML(typ="rt")
        yaml.preserve_quotes = True
        document = yaml.load(source) if source.strip() else {}
        before = copy.deepcopy(document)
        _merge_mapping(document, path, identity, entry, shape, id_field)
        if source and before == document:
            return source
        output = io.StringIO()
        yaml.dump(document, output)
        return output.getvalue()
    raise ValueError(f"Unsupported configuration format: {kind}")


class _Plan:
    """Compute every edit before writing so invalid configuration leaves files intact."""

    def __init__(self):
        self.files = {}
        self.original = {}

    def read(self, path):
        path = Path(path).resolve()
        if path not in self.original:
            self.original[path] = path.read_bytes() if path.exists() else None
        data = self.files.get(path, self.original[path])
        return data.decode("utf-8") if data is not None else ""

    def add(self, path, content):
        path = Path(path).resolve()
        self.read(path)
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content

    def apply(self, dry_run):
        result = []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        for path, content in self.files.items():
            previous = self.original[path]
            changed = previous != content
            item = {
                "path": str(path),
                "action": "unchanged" if not changed else "update" if previous is not None else "create",
            }
            if changed and not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
                if previous is not None:
                    backup = path.with_name(path.name + f".worklife-backup-{stamp}")
                    backup.write_bytes(previous)
                    backup.chmod(0o600)
                    item["backup"] = str(backup)
                path.write_bytes(content)
                path.chmod(mode)
            result.append(item)
        return result


def _user_path(value, target_id, user_root, environment):
    overrides = {"codex": ("CODEX_HOME", ".codex"), "copilot": ("COPILOT_HOME", ".copilot")}
    if target_id in overrides:
        variable, prefix = overrides[target_id]
        if environment.get(variable) and value.startswith(f"~/{prefix}/"):
            return Path(environment[variable]).expanduser() / value.removeprefix(f"~/{prefix}/")
    if (
        target_id == "cline"
        and environment.get("CLINE_MCP_SETTINGS_PATH")
        and value.endswith("cline_mcp_settings.json")
    ):
        return Path(environment["CLINE_MCP_SETTINGS_PATH"]).expanduser()
    if target_id == "openclaw" and environment.get("OPENCLAW_CONFIG_PATH"):
        return Path(environment["OPENCLAW_CONFIG_PATH"]).expanduser()
    if environment.get("XDG_CONFIG_HOME") and value.startswith("~/.config/"):
        return Path(environment["XDG_CONFIG_HOME"]).expanduser() / value.removeprefix("~/.config/")
    if value.startswith("%APPDATA%/"):
        if not environment.get("APPDATA"):
            raise ValueError("APPDATA is required for this Windows client; use --config-path")
        return Path(environment["APPDATA"]) / value.removeprefix("%APPDATA%/")
    if value.startswith("~/"):
        return user_root / value[2:]
    raise ValueError(f"Unsupported user configuration path: {value}")


def _existing_variant(path, target_id):
    choices = [path]
    if path.suffix == ".json" and target_id in {"opencode", "kilo", "amp", "antigravity"}:
        choices.append(path.with_suffix(".jsonc"))
    if target_id == "kilo" and path.name in {"kilo.json", "kilo.jsonc"}:
        choices.extend([path.parent / ".kilo" / "kilo.json", path.parent / ".kilo" / "kilo.jsonc"])
    existing = [item for item in choices if item.exists()]
    if len(existing) > 1:
        raise ValueError(f"Multiple configurations found for {target_id}; choose one with --config-path")
    return existing[0] if existing else path


def _entry(spec, command, arguments):
    values = {
        "$PROCESS_COMMAND": command,
        "$PROCESS_ARGS": arguments,
        "$COMMAND_PLUS_ARGS_ARRAY": [command, *arguments],
        "$SERVER_NAME": SERVER_NAME,
    }
    return {
        key: values.get(value, value) if isinstance(value, str) else value
        for key, value in spec["entry_template"].items()
        if value != "$PROCESS_ENV_OPTIONAL"
    }


def _agent_files(plan, target, destination, scope, user_root, environment, instructions):
    agent = target.get("agent")
    selected = agent and agent.get(f"{scope}_path")
    if selected:
        path = (
            destination / selected
            if scope == "project"
            else _user_path(selected, target["id"], user_root, environment)
        )
        body = instructions
        for skill in load_agent_profile()["skills"]:
            relative = os.path.relpath(destination / ".worklife" / "recruiter" / skill["path"], path.parent)
            body = body.replace(f"({skill['path']})", f"({Path(relative).as_posix()})")
        fields = {"description": DESCRIPTION, **agent.get("extra_fields", {})}
        if "name" in agent["required_fields"]:
            fields["name"] = AGENT_NAME
        if agent.get("instructions_field"):
            fields[agent["instructions_field"]] = body
        if agent["format"] == "toml":
            existing = tomlkit.parse(plan.read(path))
            existing.update(fields)
            plan.add(path, tomlkit.dumps(existing))
        elif agent["format"] == "json":
            existing = json.loads(plan.read(path) or "{}", object_pairs_hook=_unique_pairs)
            if not isinstance(existing, dict):
                raise ValueError("Agent definition must be an object")
            existing.update(fields)
            plan.add(path, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
        elif agent["format"] == "markdown_frontmatter":
            old = plan.read(path)
            yaml = YAML(typ="rt")
            yaml.preserve_quotes = True
            existing = {}
            if old:
                sections = re.split(r"(?m)^---[ \t]*\r?$", old, maxsplit=2)
                if len(sections) != 3 or sections[0].strip():
                    raise ValueError(f"Agent file has no YAML frontmatter: {path}")
                existing = yaml.load(sections[1])
                if not isinstance(existing, MutableMapping):
                    raise ValueError("Agent frontmatter must be a mapping")
            existing.update(fields)
            frontmatter = io.StringIO()
            yaml.dump(existing, frontmatter)
            plan.add(path, f"---\n{frontmatter.getvalue()}---\n\n{body}")
        elif agent["format"] == "yaml_or_json":
            old = plan.read(path)
            mode = {
                key: body if value == "$INSTRUCTIONS" else value
                for key, value in agent["entry_template"].items()
            }
            spec = {
                "format": "json" if old.lstrip().startswith("{") else "yaml",
                "root_key": ["customModes"],
                "entries_shape": "list",
                "identity_field": "slug",
            }
            plan.add(path, merge_config(old, spec, mode, identity=AGENT_NAME))
        else:
            raise ValueError(f"Unsupported native-agent format: {agent['format']}")
        prompt_path = agent.get(f"companion_prompt_{scope}")
        if prompt_path:
            prompt_path = (
                destination / prompt_path
                if scope == "project"
                else _user_path(prompt_path, target["id"], user_root, environment)
            )
            plan.add(prompt_path, body)
    for skill_location in target.get("skills", []):
        location = skill_location.get(f"{scope}_path")
        if not location:
            continue
        root = (
            destination / location
            if scope == "project"
            else _user_path(location, target["id"], user_root, environment)
        )
        for source in (BUNDLE_DIR / "skills").rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
                plan.add(root / source.relative_to(BUNDLE_DIR / "skills"), source.read_bytes())


def install_agent(
    destination,
    target_ids,
    *,
    scope="project",
    config=None,
    home=None,
    env_file=None,
    command=None,
    dry_run=False,
    config_path=None,
    user_root=None,
    environment=None,
    platform=None,
):
    """Prepare/apply documented adapters; project scope exports user-only clients."""
    if scope not in {"project", "user"}:
        raise ValueError("Scope must be project or user")
    destination = Path(destination).expanduser().resolve()
    user_root = Path(user_root).resolve() if user_root else Path.home()
    environment = dict(os.environ if environment is None else environment)
    platform = platform or _platform()
    catalog = load_catalog()
    registry = {target["id"]: target for target in catalog["harnesses"]}
    target_ids = list(dict.fromkeys(target_ids))
    if not target_ids or any(name not in registry for name in target_ids):
        raise ValueError("Choose supported target IDs from `worklife-recruiter targets`")
    if config_path and len(target_ids) != 1:
        raise ValueError("--config-path requires exactly one target")
    # Resolving a venv's Python symlink loses its installed Worklife package.
    command = str(Path(command or sys.executable).expanduser().absolute())
    args = ["-m", "worklife.recruiter_cli", "mcp"]
    if config:
        config = Path(config).expanduser().resolve()
        if not config.is_file():
            raise ValueError("Worklife config file does not exist")
        args.extend(["--config", str(config)])
    if home:
        args.extend(["--home", str(Path(home).expanduser().resolve())])
    if env_file:
        env_file = Path(env_file).expanduser().resolve()
        if not env_file.is_file():
            raise ValueError("Environment file does not exist")
        args.extend(["--env-file", str(env_file)])
    plan = _Plan()
    for source in BUNDLE_DIR.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            plan.add(
                destination / ".worklife" / "recruiter" / source.relative_to(BUNDLE_DIR), source.read_bytes()
            )
    plan.add(
        destination / ".worklife" / "harnesses.json", json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    results = []
    profile = load_agent_profile()
    for target_id in target_ids:
        target = registry[target_id]
        spec = (
            target["mcp"].get("project")
            if scope == "project"
            else target["mcp"].get("user", {}).get(platform)
        )
        installable = bool(
            target["mcp"].get("installable")
            and target["mcp"].get("auto_apply_documented", True)
            and spec
            and target["evidence_status"] == "official_documentation"
        )
        if config_path:
            spec = (
                spec
                or target.get("mcp_schema")
                or next(iter(target["mcp"].get("user", {}).values()), None)
                or target["mcp"].get("project")
            )
            installable = bool(
                spec
                and target["evidence_status"] in {"official_documentation", "official_schema_manual_path"}
            )
            if not installable:
                raise ValueError(f"No verified configuration schema for {target_id}")
            path = Path(config_path).expanduser().resolve()
        elif installable:
            path = (
                destination / spec["path"]
                if scope == "project"
                else _user_path(spec["path"], target_id, user_root, environment)
            )
            path = _existing_variant(path, target_id)
        if installable:
            plan.add(path, merge_config(plan.read(path), spec, _entry(spec, command, args)))
            _agent_files(plan, target, destination, scope, user_root, environment, profile["instructions"])
            status = "configured"
        else:
            spec = (
                spec
                or target.get("mcp_schema")
                or next(iter(target["mcp"].get("user", {}).values()), None)
                or GENERIC_MCP
            )
            path = destination / ".worklife" / "exports" / target_id / f"mcp.{spec['format']}"
            plan.add(path, merge_config(plan.read(path), spec, _entry(spec, command, args)))
            status = "exported"
        results.append(
            {
                "target": target_id,
                "status": status,
                "mode": target["mode"] if installable else "export_only",
                "config": str(path),
                "runtime_tested": False,
                "limits": target["limits"],
                "sources": target["citations"],
                "launch": target.get("cli", {}).get("launch"),
            }
        )
    launch = {"command": command, "args": args}
    plan.add(
        destination / ".worklife" / "recruiter-mcp.json",
        json.dumps({"mcpServers": {SERVER_NAME: launch}}, ensure_ascii=False, indent=2) + "\n",
    )
    plan.add(
        destination / "WORKLIFE-START.md",
        "# Worklife Recruiter\n\nОткройте эту папку в выбранном клиенте. Выберите агента `worklife-recruiter`, если он поддерживается; иначе попросите агента вызвать `recruiter_start` у MCP `worklife_recruiter`.\n\nИнструкции и скиллы: [.worklife/recruiter/AGENTS.md](.worklife/recruiter/AGENTS.md). Клиенту без файлов доступны те же инструкции через `recruiter_start` и `recruiter_skill`.\n\nУстановка не начинает поиск, отправку писем или создание аккаунтов. Для расписаний оставьте запущенным локальное приложение Worklife или worker.\n\nФайлы в `.worklife/exports` — подготовленные конфигурации для импорта: эти клиенты ещё не подключены. Не заменяйте ими целиком существующие настройки клиента. Для автоматического добавления одного клиента используйте `--scope user` либо `--config-path` с его точным файлом.\n\nПосле установки перезапустите клиент и проверьте `recruiter_start`. Доверие к папке и разрешения инструментов остаются настройками самого клиента.\n",
    )
    report = {
        "scope": scope,
        "destination": str(destination),
        "server": SERVER_NAME,
        "launch": launch,
        "targets": results,
        "catalog_checked_at": catalog["checked_at"],
        "runtime_verified": False,
    }
    plan.add(
        destination / ".worklife" / "installation.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    return {**report, "dry_run": dry_run, "files": plan.apply(dry_run)}


def doctor(destination):
    """Inspect generated files only; do not start clients or network operations."""
    destination = Path(destination).expanduser().resolve()
    path = destination / ".worklife" / "installation.json"
    if not path.exists():
        raise ValueError("No installation manifest found in this destination")
    report = json.loads(path.read_text(encoding="utf-8"))
    checks = []
    for target in report["targets"]:
        file = Path(target["config"])
        checks.append(
            {
                "target": target["target"],
                "config_exists": file.is_file(),
                "configured": target["status"] == "configured",
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None,
            }
        )
    return {
        "destination": str(destination),
        "python_exists": Path(report["launch"]["command"]).is_file(),
        "checks": checks,
        "runtime_verified": False,
        "next_step": "Перезапустите клиент и вызовите recruiter_start. Doctor проверяет файлы, а не подключение клиента.",
    }
