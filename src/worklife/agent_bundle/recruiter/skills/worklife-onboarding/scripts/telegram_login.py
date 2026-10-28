"""Authorize a personal Telegram account without exposing its credentials.

Run with Worklife's Python: telegram_login.py --env-file /absolute/private.env.
Call main(argv) for the same command-line behavior. Inputs are collected only
in the user's terminal; no group is created and no chat message is sent.
"""

import argparse
import asyncio
import io
import os
import re
import sys
from contextlib import redirect_stdout
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key


class InputError(ValueError):
    """A local input problem whose message is safe to display."""


def prompt(label, trim=True):
    if not sys.stdin.isatty():
        raise InputError("Откройте свой терминал и повторите команду для скрытого ввода данных.")
    value = getpass(label)
    if trim:
        value = value.strip()
    if not value:
        raise InputError("Ввод отменён: пустое значение.")
    return value


async def authorize(api_id, api_hash, session):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(session), api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            # Telethon start() normally prints the account's identity on success.
            with redirect_stdout(io.StringIO()):
                await client.start(
                    phone=lambda: prompt("Номер телефона Telegram: "),
                    code_callback=lambda: prompt("Код входа из Telegram: "),
                    password=lambda: prompt("Пароль двухэтапной проверки Telegram: ", trim=False),
                    max_attempts=1,
                )
        user = await client.get_me()
        if user is None or user.bot:
            raise InputError("Требуется личный аккаунт Telegram, а не бот.")
        return client.session.save()
    finally:
        await client.disconnect()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Вход в личный Telegram для Worklife; секреты не выводятся.")
    parser.add_argument("--env-file", required=True, type=Path, help="Абсолютный путь к личному .env")
    parser.add_argument("--api-id-env", default="TELEGRAM_API_ID")
    parser.add_argument("--api-hash-env", default="TELEGRAM_API_HASH")
    parser.add_argument("--session-env", default="TELEGRAM_SESSION_STRING")
    args = parser.parse_args(argv)
    try:
        path = args.env_file.expanduser()
        if not path.is_absolute():
            raise InputError("Укажите абсолютный путь к личному .env.")
        names = (args.api_id_env, args.api_hash_env, args.session_env)
        if len(set(names)) != 3 or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) for n in names):
            raise InputError("Укажите три разных допустимых имени переменных окружения.")
        values = dotenv_values(path) if path.exists() else {}

        def existing(name):
            return os.getenv(name) or values.get(name) or ""

        raw_api_id = existing(args.api_id_env) or prompt("Telegram API ID: ")
        try:
            api_id = int(raw_api_id)
        except ValueError as exc:
            raise InputError("Telegram API ID должен быть целым числом.") from exc
        if api_id <= 0:
            raise InputError("Telegram API ID должен быть положительным числом.")
        api_hash = existing(args.api_hash_env) or prompt("Telegram API hash: ")
        session = asyncio.run(authorize(api_id, api_hash, existing(args.session_env)))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        path.chmod(0o600)
        for name, value in zip(names, (str(api_id), api_hash, session), strict=True):
            set_key(path, name, value)
        path.chmod(0o600)
        print(f"Telegram: вход проверен, настройки сохранены в {path}. Перезапустите MCP с этим .env.")
        return 0
    except ModuleNotFoundError:
        print("Установите worklife-agent[telegram] в окружение Worklife и повторите команду.", file=sys.stderr)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
    except OSError:
        print("Не удалось завершить вход или сохранить личный .env. Проверьте доступ и повторите.", file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("Вход отменён; настройки не сохранены.", file=sys.stderr)
    except Exception:
        print("Не удалось войти в Telegram. Проверьте подключение и данные в своём терминале.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
