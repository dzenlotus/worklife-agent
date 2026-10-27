"""One-command uvx setup with a durable Python runtime for installed MCP clients."""

import argparse
import os
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from .agent_install import targets


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="worklife-agent", description="Установить Worklife и подключить карьерного агента к MCP-клиенту"
    )
    parser.add_argument(
        "--target",
        default="generic",
        choices=[item["id"] for item in targets() if item["project"] or item["id"] == "generic"],
        help="Клиент для папки агента (по умолчанию generic)",
    )
    parser.add_argument(
        "--destination", type=Path, default=Path.home() / "worklife-career", help="Папка агента"
    )
    parser.add_argument(
        "--install-dir", type=Path, default=Path.home() / ".local/share/worklife", help="Постоянное окружение"
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=os.getenv("WORKLIFE_HOME") or Path.home() / ".worklife",
        help="Личные данные Worklife (или WORKLIFE_HOME)",
    )
    parser.add_argument("--no-browser", action="store_true", help="Не устанавливать Chromium")
    parser.add_argument("--package-source", help="Путь или URL wheel вместо текущей версии на PyPI")
    args = parser.parse_args(argv)
    step = "подготовка установки"
    try:
        uv = shutil.which("uv")
        if not uv:
            raise ValueError("uv не найден. Запустите установку через uvx или добавьте uv в PATH.")
        installation = args.install_dir.expanduser().resolve()
        destination = args.destination.expanduser().resolve()
        data_home = args.home.expanduser().resolve()
        package = "worklife-agent" + ("" if args.no_browser else "[browser]")
        if args.package_source:
            source = args.package_source
            if not source.startswith(("http://", "https://", "file://")):
                wheel = Path(source).expanduser().resolve()
                if not wheel.is_file():
                    raise ValueError(f"Wheel не найден: {wheel}")
                source = wheel.as_uri()
            package += f" @ {source}"
        else:
            package += f"=={version('worklife-agent')}"

        print("Worklife: подготавливаю постоянное окружение…", flush=True)
        installation.mkdir(parents=True, exist_ok=True, mode=0o700)
        venv = installation / "venv"
        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if not python.is_file():
            subprocess.run([uv, "venv", "--python", "3.12", str(venv)], check=True)

        step = "установка пакета"
        print("Worklife: устанавливаю пакет…", flush=True)
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--refresh-package",
                "worklife-agent",
                "--reinstall-package",
                "worklife-agent",
                package,
            ],
            check=True,
        )
        if not args.no_browser:
            step = "установка Chromium"
            print("Worklife: устанавливаю Chromium для работы с площадками…", flush=True)
            options = ["--with-deps"] if sys.platform == "linux" else []
            subprocess.run([str(python), "-m", "playwright", "install", *options, "chromium"], check=True)

        step = "подготовка личных данных"
        with (installation / "state.json").open("w", encoding="utf-8") as output:
            subprocess.run(
                [str(python), "-m", "worklife", "--home", str(data_home), "init"], check=True, stdout=output
            )
        step = "подключение агента"
        with (installation / "installation.json").open("w", encoding="utf-8") as output:
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "worklife.recruiter_cli",
                    "install",
                    "--target",
                    args.target,
                    "--destination",
                    str(destination),
                    "--home",
                    str(data_home),
                ],
                check=True,
                stdout=output,
            )
        print(f"\nWorklife установлен.\nПапка агента: {destination}\nЛичные данные: {data_home}")
        if args.target == "generic":
            print(f"Добавьте MCP из {destination}/.worklife/recruiter-mcp.json в свой клиент.")
        else:
            print(f"Откройте {destination} в {args.target} и включите Worklife Recruiter.")
        print("Первое поручение: «Используй Worklife. Начни с recruiter_start и уточни мои условия».")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"Worklife: {step}: команда завершилась с кодом {exc.returncode}.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Worklife: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nWorklife: установка прервана.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
