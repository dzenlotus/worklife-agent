import stat
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from dotenv import dotenv_values


def helper():
    path = (
        Path(__file__).parents[1]
        / "src/worklife/agent_bundle/recruiter/skills/worklife-onboarding/scripts/telegram_login.py"
    )
    assert path.is_file(), "Onboarding needs an executable Telegram login helper"
    module = ModuleType("onboarding_telegram_login")
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture
def telegram(monkeypatch):
    state = SimpleNamespace(authorized=True, bot=False, failure=False, starts=0, clients=[])

    class StringSession:
        def __init__(self, value=""):
            self.value = value

        def save(self):
            return "new-session-secret"

    class Client:
        def __init__(self, session, api_id, api_hash, **kwargs):
            self.session = session
            self.arguments = (api_id, api_hash)
            self.disconnected = False
            state.clients.append(self)

        async def connect(self):
            pass

        async def is_user_authorized(self):
            return state.authorized

        async def start(self, **kwargs):
            state.starts += 1
            state.prompts = kwargs
            kwargs["phone"]()
            kwargs["code_callback"]()
            state.password = kwargs["password"]()
            print("Signed in as private-account-name")

        async def get_me(self):
            if state.failure:
                raise RuntimeError("new-session-secret hash-secret private-account-name")
            return SimpleNamespace(bot=state.bot)

        async def disconnect(self):
            self.disconnected = True

    telethon = ModuleType("telethon")
    telethon.TelegramClient = Client
    sessions = ModuleType("telethon.sessions")
    sessions.StringSession = StringSession
    monkeypatch.setitem(sys.modules, "telethon", telethon)
    monkeypatch.setitem(sys.modules, "telethon.sessions", sessions)
    for name in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"):
        monkeypatch.delenv(name, raising=False)
    return state


def test_login_reuses_session_preserves_env_and_never_prints_secrets(tmp_path, monkeypatch, capsys, telegram):
    login = helper()
    path = tmp_path / "private.env"
    path.write_text(
        "# keep this\nOTHER='unrelated-value'\nTELEGRAM_API_ID=123\n"
        "TELEGRAM_API_HASH='hash-secret'\nTELEGRAM_SESSION_STRING='old-session-secret'\n"
    )
    monkeypatch.setattr(login, "getpass", lambda prompt: pytest.fail("Existing session must not prompt"))
    assert login.main(["--env-file", str(path)]) == 0
    values = dotenv_values(path)
    assert values["OTHER"] == "unrelated-value"
    assert "# keep this" in path.read_text()
    assert values["TELEGRAM_SESSION_STRING"] == "new-session-secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert telegram.starts == 0
    assert telegram.clients[0].session.value == "old-session-secret"
    assert telegram.clients[0].disconnected
    output = capsys.readouterr()
    for secret in ("new-session-secret", "old-session-secret", "hash-secret", "private-account-name"):
        assert secret not in output.out + output.err


def test_interactive_login_hides_callbacks_and_default_client_output(tmp_path, monkeypatch, capsys, telegram):
    login = helper()
    telegram.authorized = False
    monkeypatch.setattr(login.sys.stdin, "isatty", lambda: True)
    replies = iter(["456", "hash-secret", "+70000000000", "12345", " password-secret "])
    monkeypatch.setattr(login, "getpass", lambda prompt: next(replies))
    path = tmp_path / "private" / "telegram.env"
    assert login.main(["--env-file", str(path)]) == 0
    assert telegram.starts == 1
    assert telegram.clients[0].arguments == (456, "hash-secret")
    assert telegram.password == " password-secret "
    assert dotenv_values(path)["TELEGRAM_SESSION_STRING"] == "new-session-secret"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert "private-account-name" not in capsys.readouterr().out


@pytest.mark.parametrize("failure,bot", [(True, False), (False, True)])
def test_failed_identity_check_does_not_change_env(tmp_path, capsys, telegram, failure, bot):
    login = helper()
    path = tmp_path / "private.env"
    original = "OTHER=keep\nTELEGRAM_API_ID=123\nTELEGRAM_API_HASH=hash-secret\n"
    path.write_text(original)
    telegram.failure, telegram.bot = failure, bot
    assert login.main(["--env-file", str(path)]) == 1
    assert path.read_text() == original
    assert telegram.clients[0].disconnected
    output = capsys.readouterr()
    assert "hash-secret" not in output.out + output.err
    assert "new-session-secret" not in output.out + output.err


def test_missing_tty_stops_before_prompting_or_writing(tmp_path, monkeypatch, capsys, telegram):
    login = helper()
    path = tmp_path / "private.env"
    monkeypatch.setattr(login.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(login, "getpass", lambda prompt: pytest.fail("No TTY must not prompt"))
    assert login.main(["--env-file", str(path)]) == 1
    assert not path.exists()
    assert "терминал" in capsys.readouterr().err.lower()
