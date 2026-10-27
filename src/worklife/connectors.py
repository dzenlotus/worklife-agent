"""Official adapters plus configured HTTP operations; credentials stay in the environment."""

import html
import imaplib
import mimetypes
import os
import re
import smtplib
import ssl
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import make_msgid
from pathlib import Path
from urllib.parse import quote

import httpx

from .config import secret


def plain(value):
    return re.sub(r"<[^>]+>", " ", html.unescape(value or "")).strip()


class Connectors:
    def __init__(self, configs, workspace):
        self.configs, self.workspace = configs, workspace

    def config(self, name):
        overrides = {c["id"]: c["config"] for c in self.workspace.store.list("connector")}
        config = overrides.get(name, self.configs.get(name))
        if config is None:
            raise ValueError(f"Unknown connector {name}; configure it first")
        return config

    def register(self, name, config):
        if config.get("type") not in {"http", "hh", "greenhouse", "lever", "email", "telegram"}:
            raise ValueError("Unknown connector type")
        if any(k in config for k in {"token", "password", "api_key", "authorization"}):
            raise ValueError("Use environment variable references, never literal credentials")
        self.workspace.store.put("connector", name, {"id": name, "config": config})
        return {"name": name, "type": config["type"]}

    def capabilities(self):
        configs = {**self.configs, **{c["id"]: c["config"] for c in self.workspace.store.list("connector")}}
        result = []
        for name, c in configs.items():
            kind = c["type"]
            read, write = [], []
            if kind in {"hh", "greenhouse", "lever"}:
                read = ["search"]
            if kind == "hh":
                read += ["me", "resumes", "negotiations", "messages"]
                write = ["apply", "reply"]
            elif kind == "email":
                read, write = ["inbox", "message"], ["send"]
            elif kind == "telegram":
                read, write = ["updates"], ["send"]
            elif kind == "http":
                for operation, spec in c.get("operations", {}).items():
                    (read if spec.get("effect") == "read" else write).append(operation)
            credentials = {k: v for k, v in c.items() if k.endswith("_env") and k != "headers_env"}
            credentials.update({"header:" + k: v for k, v in c.get("headers_env", {}).items()})
            result.append(
                {
                    "name": name,
                    "type": kind,
                    "read": read,
                    "write": write,
                    "credentials": {k: {"env": v, "set": bool(os.getenv(v))} for k, v in credentials.items()},
                }
            )
        return result

    def _request(self, c, method, path, params=None, body=None, form=None):
        base = c.get("base_url", "https://api.hh.ru").rstrip("/")
        if not base.startswith(("https://", "http://")):
            raise ValueError("Connector requires an HTTP(S) base_url")
        headers = {"User-Agent": c.get("user_agent", "Worklife/0.1")}
        token = secret(c, "token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for header, variable in c.get("headers_env", {}).items():
            value = os.getenv(variable)
            if not value:
                raise ValueError(f"Missing header environment variable: {variable}")
            headers[header] = value
        # Keep credentials on the configured origin. Redirects are not followed.
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.request(
                    method,
                    base + "/" + path.lstrip("/"),
                    headers=headers,
                    params=params,
                    json=body,
                    data=form,
                )
                response.raise_for_status()
                return response.json() if response.content else {"status": response.status_code}
        except httpx.HTTPStatusError as exc:
            retry = exc.response.headers.get("Retry-After")
            raise ValueError(f"Provider HTTP {exc.response.status_code}; retry_after={retry}") from None
        except httpx.TransportError as exc:
            raise ConnectionError(f"Provider transport failure: {type(exc).__name__}") from None

    def search(self, name, query="", **parameters):
        c = self.config(name)
        kind = c["type"]
        jobs = []
        if kind == "hh":
            data = self._request(c, "GET", "/vacancies", params={"text": query, "per_page": 50, **parameters})
            for j in data["items"]:
                salary = j.get("salary") or {}
                formats = {v["id"] for v in j.get("work_format", [])}
                remote = (
                    True
                    if "REMOTE" in formats or (j.get("schedule") or {}).get("id") == "remote"
                    else (False if formats else None)
                )
                jobs.append(
                    {
                        "id": str(j["id"]),
                        "title": j["name"],
                        "employer": (j.get("employer") or {}).get("name", "Undisclosed"),
                        "employer_id": (j.get("employer") or {}).get("id"),
                        "url": j["alternate_url"],
                        "remote": remote,
                        "location": (j.get("area") or {}).get("name"),
                        "salary_min": salary.get("from"),
                        "salary_max": salary.get("to"),
                        "currency": salary.get("currency"),
                        "salary_period": "month",
                        "salary_gross": salary.get("gross"),
                        "description": plain(" ".join(v or "" for v in (j.get("snippet") or {}).values())),
                    }
                )
        elif kind == "greenhouse":
            board = parameters.pop("board", c.get("board", ""))
            if not board:
                raise ValueError("Greenhouse requires board")
            c = {"base_url": "https://boards-api.greenhouse.io", **c}
            data = self._request(
                c, "GET", f"/v1/boards/{quote(board, safe='')}/jobs", params={"content": "true"}
            )
            jobs = [
                {
                    "id": str(j["id"]),
                    "title": j["title"],
                    "employer": c.get("employer", board),
                    "url": j["absolute_url"],
                    "location": (j.get("location") or {}).get("name"),
                    "remote": None,
                    "description": plain(j.get("content")),
                }
                for j in data["jobs"]
            ]
        elif kind == "lever":
            board = parameters.pop("board", c.get("board", ""))
            if not board:
                raise ValueError("Lever requires board")
            c = {"base_url": "https://api.lever.co", **c}
            data = self._request(
                c, "GET", f"/v0/postings/{quote(board, safe='')}", params={"mode": "json", **parameters}
            )
            for j in data:
                salary = j.get("salaryRange") or {}
                jobs.append(
                    {
                        "id": j["id"],
                        "title": j["text"],
                        "employer": c.get("employer", board),
                        "url": j["hostedUrl"],
                        "apply_url": j.get("applyUrl"),
                        "location": (j.get("categories") or {}).get("location"),
                        "remote": {"remote": True, "on-site": False, "hybrid": False}.get(
                            j.get("workplaceType")
                        ),
                        "salary_min": salary.get("min"),
                        "salary_max": salary.get("max"),
                        "currency": salary.get("currency"),
                        "salary_period": salary.get("interval"),
                        "description": plain(j.get("descriptionPlain") or j.get("description")),
                    }
                )
        else:
            raise ValueError("Use connector_read for configured HTTP search operations")
        if kind != "hh" and query:
            terms = query.lower().split()
            jobs = [
                j
                for j in jobs
                if all(t in (j["title"] + " " + j.get("description", "")).lower() for t in terms)
            ]
        # Qualify board IDs too: two different companies can share provider-local IDs.
        platform = name + (":" + board if kind in {"greenhouse", "lever"} else "")
        return [self.workspace.save_job({**j, "platform": platform}) for j in jobs]

    def read(self, name, operation, parameters):
        c = self.config(name)
        kind = c["type"]
        if operation == "search" and kind in {"hh", "greenhouse", "lever"}:
            p = dict(parameters)
            return self.search(name, p.pop("query", ""), **p)
        if kind == "hh":
            paths = {"me": "/me", "resumes": "/resumes/mine", "negotiations": "/negotiations"}
            p = dict(parameters)
            if operation == "messages":
                path = f"/negotiations/{quote(str(p.pop('negotiation_id')), safe='')}/messages"
            elif operation in paths:
                path = paths[operation]
            else:
                raise ValueError("Unknown read operation; use draft_action for writes")
            return self._request(c, "GET", path, params=p)
        if kind == "http":
            return self._generic(c, operation, parameters, "read")
        if kind == "email" and operation in {"inbox", "message"}:
            return self._mail_read(c, operation, parameters)
        if kind == "telegram" and operation == "updates":
            return self._telegram(c, "getUpdates", parameters)
        raise ValueError("Unsupported read operation; writes require draft_action")

    def execute(self, name, operation, payload):
        c = self.config(name)
        kind = c["type"]
        if kind == "http":
            return self._generic(c, operation, payload, "write")
        if kind == "email" and operation == "send":
            return self._mail_send(c, payload)
        if kind == "telegram" and operation == "send":
            p = {"chat_id": payload["chat_id"], "text": payload["text"]}
            if payload.get("reply_to_message_id"):
                p["reply_parameters"] = {"message_id": payload["reply_to_message_id"]}
            return self._telegram(c, "sendMessage", p)
        if kind == "hh":
            if operation == "apply":
                return self._request(
                    c,
                    "POST",
                    "/negotiations",
                    form={k: payload[k] for k in ("vacancy_id", "resume_id", "message") if k in payload},
                )
            if operation == "reply":
                return self._request(
                    c,
                    "POST",
                    f"/negotiations/{quote(str(payload['negotiation_id']), safe='')}/messages",
                    form={"message": payload["message"]},
                )
        raise ValueError("Unsupported write operation")

    def _generic(self, c, operation, parameters, effect):
        spec = c.get("operations", {}).get(operation)
        if not spec or spec.get("effect") != effect:
            raise ValueError(f"Operation is not a configured {effect}; writes require draft_action")
        method = spec.get("method", "GET").upper()
        if effect == "read" and method not in {"GET", "HEAD", "OPTIONS"}:
            raise ValueError("Read operations require a read-only HTTP method")
        p = dict(parameters)
        path = re.sub(
            r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", lambda m: quote(str(p.pop(m[1])), safe=""), spec["path"]
        )
        return self._request(
            c,
            method,
            path,
            params=p if method in {"GET", "HEAD"} else None,
            body=p if method not in {"GET", "HEAD"} else None,
        )

    def _telegram(self, c, method, payload):
        token = secret(c, "token", required=True)
        result = self._request(
            {"base_url": c.get("base_url", "https://api.telegram.org")},
            "POST",
            f"/bot{token}/{method}",
            body=payload,
        )
        if not result.get("ok"):
            raise ValueError("Telegram rejected the operation")
        return result["result"]

    def _mail_send(self, c, p):
        message = EmailMessage()
        message["From"] = secret(c, "from", required=True)
        for field, key in (("To", "to"), ("Cc", "cc"), ("Bcc", "bcc")):
            if p.get(key):
                message[field] = ", ".join(p[key]) if isinstance(p[key], list) else p[key]
        if not p.get("to"):
            raise ValueError("Email requires recipients")
        message["Subject"] = p.get("subject", "")
        message["Message-ID"] = make_msgid(domain=message["From"].split("@")[-1])
        if p.get("in_reply_to"):
            message["In-Reply-To"] = p["in_reply_to"]
            message["References"] = p.get("references", p["in_reply_to"])
        message.set_content(p["body"])
        for filename in p.get("attachments", []):
            path = Path(filename).expanduser()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            main, subtype = mime.split("/", 1)
            message.add_attachment(path.read_bytes(), maintype=main, subtype=subtype, filename=path.name)
        mode = c.get("tls", "starttls")
        if mode not in {"ssl", "starttls", "none"}:
            raise ValueError("Email TLS must be ssl, starttls or none (local testing only)")
        smtp = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
        with smtp(c["smtp_host"], c.get("smtp_port", 465 if mode == "ssl" else 587), timeout=30) as client:
            if mode == "starttls":
                client.starttls(context=ssl.create_default_context())
            if c.get("username_env"):
                client.login(secret(c, "username", True), secret(c, "password", True))
            rejected = client.send_message(message)
        return {
            "message_id": str(message["Message-ID"]),
            "rejected_recipients": list(rejected),
            "delivery": "accepted_by_smtp_not_proof_of_receipt",
        }

    def _mail_read(self, c, operation, p):
        with imaplib.IMAP4_SSL(c["imap_host"], c.get("imap_port", 993)) as client:
            client.login(secret(c, "username", True), secret(c, "password", True))
            status, _ = client.select(p.get("folder", "INBOX"), readonly=True)
            if status != "OK":
                raise ValueError("Cannot select mailbox")
            if operation == "message":
                ids = [str(p["uid"]).encode()]
            else:
                status, data = client.uid("search", None, p.get("criteria", "UNSEEN"))
                if status != "OK":
                    raise ValueError("IMAP search failed")
                ids = data[0].split()[-min(int(p.get("limit", 20)), 100) :]
            messages = []
            for identifier in ids:
                status, data = client.uid("fetch", identifier, "(BODY.PEEK[])")
                if status != "OK":
                    continue
                raw = next((part[1] for part in data if isinstance(part, tuple)), None)
                if raw is None:
                    continue
                message = BytesParser(policy=policy.default).parsebytes(raw)
                body = message.get_body(preferencelist=("plain", "html"))
                text = body.get_content() if body else ""
                if body and body.get_content_type() == "text/html":
                    text = plain(text)
                messages.append(
                    {
                        "uid": identifier.decode(),
                        "message_id": message.get("Message-ID"),
                        "from": str(message.get("From", "")),
                        "to": str(message.get("To", "")),
                        "subject": str(message.get("Subject", "")),
                        "date": message.get("Date"),
                        "body": text,
                        "attachments": [a.get_filename() for a in message.iter_attachments()],
                    }
                )
            return {"folder": p.get("folder", "INBOX"), "messages": messages}
