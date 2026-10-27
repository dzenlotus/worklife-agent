import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture
def webserver():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            received.append(("GET", self.path))
            if "/vacancies" in self.path:
                body = {
                    "items": [
                        {
                            "id": "7",
                            "name": "Python",
                            "employer": {"name": "Acme"},
                            "alternate_url": "https://example.org/7",
                            "salary": {"from": 100, "to": 150, "currency": "EUR"},
                            "work_format": [{"id": "REMOTE"}],
                            "snippet": {"requirement": "Python"},
                        }
                    ]
                }
            elif "/boards/" in self.path:
                body = {
                    "jobs": [
                        {
                            "id": 8,
                            "title": "Developer",
                            "absolute_url": "https://example.org/8",
                            "location": {"name": "Remote"},
                            "content": "Python APIs",
                        }
                    ]
                }
            elif "/postings/" in self.path:
                body = [
                    {
                        "id": "9",
                        "text": "Engineer",
                        "hostedUrl": "https://example.org/9",
                        "categories": {"location": "Remote"},
                        "workplaceType": "remote",
                    }
                ]
            else:
                body = {"messages": [{"id": "m1", "body": "Hello"}]}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append(("POST", self.path, body.decode()))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id":"sent-1"}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()
    server.server_close()
    thread.join()


def test_platform_adapters_and_universal_api(tmp_path, webserver):
    from worklife.connectors import Connectors
    from worklife.workspace import Workspace

    url, received = webserver
    configs = {
        "hh": {"type": "hh", "base_url": url, "user_agent": "test/1 (test@example.org)"},
        "gh": {"type": "greenhouse", "base_url": url, "board": "acme"},
        "lever": {"type": "lever", "base_url": url, "board": "acme"},
        "chat": {
            "type": "http",
            "base_url": url,
            "operations": {
                "inbox": {"method": "GET", "path": "/messages", "effect": "read"},
                "reply": {"method": "POST", "path": "/messages/{thread}", "effect": "write"},
            },
        },
    }
    w = Workspace(tmp_path)
    c = Connectors(configs, w)
    assert c.search("hh", "Python")[0]["remote"] is True
    assert c.search("gh", "Developer")[0]["employer"] == "acme"
    assert c.search("lever", "Engineer")[0]["remote"] is True
    assert len(w.store.list("job")) == 3
    assert c.read("chat", "inbox", {})["messages"][0]["id"] == "m1"
    with pytest.raises(ValueError, match="write"):
        c.read("chat", "reply", {"thread": "m1", "text": "Hello"})
    assert not any(r[0] == "POST" for r in received)
    draft = w.draft_action("chat", "reply", {"thread": "m1", "text": "Hello"}, "reply-1")
    w.approve_action(draft["id"])
    assert w.execute_action(draft["id"], c.execute)["result"]["id"] == "sent-1"
    assert json.loads(received[-1][2]) == {"text": "Hello"}


def test_config_resolves_environment_without_persisting_secrets(tmp_path, monkeypatch):
    from worklife.config import load_config

    monkeypatch.setenv("MAIL_PASSWORD", "test-secret")
    p = tmp_path / "config.toml"
    p.write_text('[worklife]\nhome="state"\n[connectors.mail]\ntype="email"\npassword_env="MAIL_PASSWORD"\n')
    config = load_config(p)
    assert config.home == tmp_path / "state"
    assert config.connectors["mail"]["password_env"] == "MAIL_PASSWORD"
    assert "test-secret" not in repr(config)


def test_connector_status_supports_custom_header_credentials(tmp_path, monkeypatch):
    from worklife.connectors import Connectors
    from worklife.workspace import Workspace

    monkeypatch.setenv("TEST_API_KEY", "secret-value")
    c = Connectors(
        {
            "search": {
                "type": "http",
                "base_url": "https://example.org",
                "headers_env": {"X-Api-Key": "TEST_API_KEY"},
            }
        },
        Workspace(tmp_path),
    )
    status = c.capabilities()[0]
    assert status["credentials"]["header:X-Api-Key"] == {"env": "TEST_API_KEY", "set": True}
    assert "secret-value" not in json.dumps(status)


def test_email_builds_threaded_attachment_message(tmp_path, monkeypatch):
    from worklife.connectors import Connectors
    from worklife.workspace import Workspace

    delivered = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            delivered.append(message)
            return {}

    monkeypatch.setattr("smtplib.SMTP", SMTP)
    monkeypatch.setenv("MAIL_FROM", "alex@example.org")
    attachment = tmp_path / "cv.md"
    attachment.write_text("CV body")
    c = Connectors(
        {"mail": {"type": "email", "smtp_host": "localhost", "from_env": "MAIL_FROM"}},
        Workspace(tmp_path / "w"),
    )
    result = c.execute(
        "mail",
        "send",
        {
            "to": "hr@example.org",
            "subject": "Re: Role",
            "body": "Hello",
            "in_reply_to": "<recruiter@example.org>",
            "attachments": [str(attachment)],
        },
    )
    assert result["message_id"] == delivered[0]["Message-ID"]
    assert delivered[0]["In-Reply-To"] == "<recruiter@example.org>"
    assert next(delivered[0].iter_attachments()).get_filename() == "cv.md"


def test_real_smtp_transport_delivers_to_local_test_server(tmp_path, monkeypatch):
    import socketserver

    from worklife.connectors import Connectors
    from worklife.workspace import Workspace

    delivered = []

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 local test SMTP\r\n")
            data_mode, content = False, []
            while line := self.rfile.readline():
                if data_mode:
                    if line == b".\r\n":
                        delivered.append(b"".join(content))
                        data_mode = False
                        self.wfile.write(b"250 queued\r\n")
                    else:
                        content.append(line)
                elif line.upper().startswith(b"DATA"):
                    data_mode = True
                    self.wfile.write(b"354 end with dot\r\n")
                elif line.upper().startswith(b"QUIT"):
                    self.wfile.write(b"221 bye\r\n")
                    break
                else:
                    self.wfile.write(b"250 OK\r\n")

    server = socketserver.TCPServer(("127.0.0.1", 0), SMTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TEST_MAIL_FROM", "alex@example.org")
    w = Workspace(tmp_path)
    c = Connectors(
        {
            "local": {
                "type": "email",
                "smtp_host": "127.0.0.1",
                "smtp_port": server.server_address[1],
                "tls": "none",
                "from_env": "TEST_MAIL_FROM",
            }
        },
        w,
    )
    try:
        a = w.draft_action(
            "local", "send", {"to": "hr@example.org", "subject": "Local test", "body": "Hello"}, "smtp-1"
        )
        w.approve_action(a["id"])
        receipt = w.execute_action(a["id"], c.execute)
        assert receipt["status"] == "sent"
        assert len(delivered) == 1 and b"Subject: Local test" in delivered[0] and b"Hello" in delivered[0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
