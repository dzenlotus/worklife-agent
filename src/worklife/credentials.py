"""OS-backed credentials; private database records contain metadata only."""

import hashlib
import secrets

from .storage import now


class Credentials:
    def __init__(self, workspace, backend=None):
        self.store, self.backend = workspace.store, backend
        self.service = "worklife:" + hashlib.sha256(str(workspace.home).encode()).hexdigest()[:24]

    def _call(self, operation, *args):
        try:
            backend = self.backend
            if backend is None:
                import keyring

                native = ("macOS", "Windows", "SecretService", "libsecret", "kwallet")
                if not keyring.get_keyring().__class__.__module__.startswith(
                    tuple("keyring.backends." + name for name in native)
                ):
                    raise ValueError("An OS credential backend is required")
                backend = keyring
            return getattr(backend, operation)(*args)
        except Exception:
            raise ValueError("OS credential store unavailable; configure a system keyring backend") from None

    def create(self, name, username="", secret=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Credential name is required")
        if not isinstance(username, str):
            raise ValueError("Credential username must be text")
        name = name.strip()
        try:
            previous = self.store.get("credential", name)
        except ValueError:
            previous = None
        if previous and secret is None:
            return previous
        if secret is not None and (not isinstance(secret, str) or not secret):
            raise ValueError("An explicit credential secret must be non-empty text")
        self._call(
            "set_password", self.service, name, secrets.token_urlsafe(24) if secret is None else secret
        )
        metadata = {
            "id": name,
            "name": name,
            "username": username,
            "service": self.service,
            "created_at": previous["created_at"] if previous else now(),
        }
        return self.store.put("credential", name, metadata)

    def fill(self, browser, selector, name, field="password"):
        if field not in {"password", "username"}:
            raise ValueError("Credential field must be password or username")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("Credential field selector is required")
        metadata = self.store.get("credential", name)
        value = metadata["username"]
        if field == "password":
            value = self._call("get_password", metadata["service"], metadata["name"])
            if not isinstance(value, str) or not value:
                raise ValueError("OS credential store unavailable; saved credential is missing")
        try:
            browser.prepare("fill", {"selector": selector, "value": value})
        except Exception:
            # Browser errors can include the filled value in their call log.
            raise ValueError("Credential field fill failed; inspect the page and selector") from None
        return {"filled": True, "name": metadata["name"], "field": field}
