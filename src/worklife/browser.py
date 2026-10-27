"""One persistent local browser, serialized on its owning thread."""

import html
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Browser:
    def __init__(self, home, headed=False):
        self.home = Path(home)
        self.headed = headed
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="worklife-browser")
        self.context = self.page = self.playwright = None

    def _run(self, fn, *args):
        return self.pool.submit(fn, *args).result(timeout=90)

    def _start(self):
        if self.context:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ValueError(
                "Install browser support: uv sync --extra browser; uv run playwright install chromium"
            ) from None
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.playwright = sync_playwright().start()
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                str(self.home), headless=not self.headed, accept_downloads=True
            )
            self.context.set_default_timeout(15000)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        except Exception:
            self.playwright.stop()
            self.playwright = None
            raise

    def _inspect(self):
        self._start()
        return {
            "url": self.page.url,
            "title": self.page.title(),
            "text": self.page.locator("body").inner_text()[:24000],
            "controls": self.page.locator("input,textarea,select,button,a[href]").evaluate_all(
                """els => els.slice(0,200).map(e => ({tag:e.tagName.toLowerCase(),id:e.id,
                    name:e.name||'',type:e.type||'',text:(e.innerText||'').slice(0,160),
                    label:e.getAttribute('aria-label')||'',placeholder:e.placeholder||'',
                    value:e.type==='password'?'[redacted]':(e.value||''),href:e.getAttribute('href')}))"""
            ),
        }

    def open(self, url):
        def operation():
            self._start()
            self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            return self._inspect()

        return self._run(operation)

    def inspect(self):
        return self._run(self._inspect)

    def prepare(self, operation, payload):
        def act():
            self._start()
            locator = self.page.locator(payload["selector"])
            if operation == "fill":
                locator.fill(payload["value"])
            elif operation == "select":
                locator.select_option(payload["value"])
            elif operation == "check":
                locator.set_checked(payload.get("checked", True))
            elif operation == "upload":
                locator.set_input_files([str(Path(p).expanduser().resolve()) for p in payload["paths"]])
            else:
                raise ValueError("Browser prepare supports fill, select, check, upload")
            return self._inspect()

        return self._run(act)

    def execute(self, operation, payload):
        def act():
            self._start()
            if not payload.get("expected_url") or self.page.url != payload["expected_url"]:
                raise ValueError("Browser page changed; inspect and prepare the action again")
            if operation == "click":
                self.page.locator(payload["selector"]).click()
            elif operation == "press":
                self.page.locator(payload["selector"]).press(payload["key"])
            else:
                raise ValueError("Queued browser actions support click or press")
            return self._inspect()

        return self._run(act)

    def screenshot(self, destination):
        def capture():
            self._start()
            path = Path(destination).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path), full_page=True)
            return str(path)

        return self._run(capture)

    def pdf(self, markdown, destination):
        def render():
            self._start()
            page = self.context.new_page()
            try:
                lines = []
                for line in markdown.splitlines():
                    escaped = html.escape(line)
                    if line.startswith("# "):
                        lines.append(f"<h1>{html.escape(line[2:])}</h1>")
                    elif line.startswith("## "):
                        lines.append(f"<h2>{html.escape(line[3:])}</h2>")
                    else:
                        lines.append(f"<p>{escaped}</p>")
                page.set_content(
                    '<meta charset="utf-8"><style>body{font:11pt Arial;line-height:1.5;color:#17202a}'
                    "h1{font-size:24pt}h2{font-size:15pt}p{margin:6pt 0}</style>" + "".join(lines)
                )
                path = Path(destination).expanduser().resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                page.pdf(
                    path=str(path),
                    format="A4",
                    margin={k: "18mm" for k in ("top", "bottom", "left", "right")},
                )
                return str(path)
            finally:
                page.close()

        return self._run(render)

    def close(self):
        def stop():
            if self.context:
                self.context.close()
                self.context = self.page = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None

        self._run(stop)
        self.pool.shutdown(wait=True)
