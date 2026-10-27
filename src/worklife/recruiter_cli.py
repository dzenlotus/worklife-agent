"""Portable Worklife Recruiter installation and its filtered MCP entrypoint."""

import argparse
import json
import sys
from pathlib import Path

from ruamel.yaml import YAMLError


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="worklife-recruiter", description="Карьерный агент Worklife и установка в MCP-клиенты"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("targets", help="Поддерживаемые клиенты и ограничения")
    install = commands.add_parser("install", help="Установить агента, скиллы и конфигурацию MCP")
    selection = install.add_mutually_exclusive_group(required=True)
    selection.add_argument("--target", action="append", dest="targets", help="ID клиента; можно повторять")
    selection.add_argument("--all", action="store_true", help="Все адаптеры; неподтверждённые экспортируются")
    install.add_argument(
        "--destination", type=Path, required=True, help="Папка рабочего пространства карьерного агента"
    )
    install.add_argument("--scope", choices=["project", "user"], default="project")
    install.add_argument("--config", type=Path, help="Существующий config.toml Worklife")
    install.add_argument("--home", type=Path, help="Папка данных Worklife (обычно ~/.worklife)")
    install.add_argument(
        "--env-file", type=Path, help="Файл переменных окружения; секреты в настройки клиента не копируются"
    )
    install.add_argument("--config-path", type=Path, help="Точный файл настроек одного клиента")
    install.add_argument("--dry-run", action="store_true", help="Показать план без записи файлов")
    inspect = commands.add_parser("doctor", help="Проверить созданные файлы без запуска клиента")
    inspect.add_argument("--destination", type=Path, required=True)
    mcp = commands.add_parser("mcp", help="Запустить MCP только с инструментами карьерного агента")
    mcp.add_argument("--config", type=Path)
    mcp.add_argument("--home", type=Path)
    mcp.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "mcp":
            from dotenv import load_dotenv

            from .config import load_config
            from .server import create_server

            if args.env_file:
                if not args.env_file.is_file():
                    raise ValueError("Environment file does not exist")
                load_dotenv(args.env_file, override=False)
            config = load_config(args.config)
            if args.home:
                config.home = args.home.expanduser().resolve()
            create_server(config, profile="recruiter").run(transport="stdio")
            return 0
        from .agent_install import doctor, install_agent, targets

        if args.command == "targets":
            _emit(targets())
        elif args.command == "doctor":
            _emit(doctor(args.destination))
        else:
            ids = [item["id"] for item in targets()] if args.all else args.targets
            _emit(
                install_agent(
                    args.destination,
                    ids,
                    scope=args.scope,
                    config=args.config,
                    home=args.home,
                    env_file=args.env_file,
                    dry_run=args.dry_run,
                    config_path=args.config_path,
                )
            )
        return 0
    except YAMLError:
        print("Worklife Recruiter: Invalid YAML configuration; no files were changed", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Worklife Recruiter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
