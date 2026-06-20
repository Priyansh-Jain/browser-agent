"""Electron control backend -- the ``page`` path over ``electron_debugging_port``.

An Electron app (Cursor, VS Code, Slack, ...) is a Chromium renderer, so once it
is launched with ``--remote-debugging-port`` we can attach Playwright over CDP
and drive its **DOM** deterministically -- the cheapest, most reliable path for
this whole class of target (no pixels, no OS accessibility needed).

Notes that make this actually work:
  * Chromium >= 111 enforces an origin allow-list on the DevTools WebSocket, so
    we must launch with ``--remote-allow-origins=*`` or ``connect_over_cdp``
    is rejected with HTTP 403.
  * We launch into an **isolated, throwaway** ``--user-data-dir`` and never save
    a file (untitled buffer only), so the run has zero side effects on the user's
    real Cursor profile.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import List, Optional


class ElectronCDP:
    def __init__(self, trace, binary: str, port: int, user_data_dir: str):
        self.trace = trace
        self.binary = binary
        self.port = port
        self.user_data_dir = user_data_dir
        self.proc: Optional[subprocess.Popen] = None
        self._pw = None
        self.browser = None
        self.page = None

    # ---------------------------------------------------------------- lifecycle
    def launch(self, ready_timeout: float = 30.0) -> bool:
        args = [
            self.binary,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.user_data_dir}",
            "--disable-workspace-trust",
            "--skip-release-notes",
            "--disable-updates",
        ]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        endpoint = f"http://127.0.0.1:{self.port}/json/version"
        deadline = time.time() + ready_timeout
        last = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(endpoint, timeout=2) as r:
                    if r.status == 200:
                        json.loads(r.read().decode())
                        time.sleep(2.0)  # let the workbench renderer finish booting
                        return True
            except Exception as e:  # noqa: BLE001
                last = repr(e)
            time.sleep(0.6)
        if self.trace:
            self.trace.log(f"electron debug port not ready in {ready_timeout}s ({last})", "warn")
        return False

    def connect(self) -> bool:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self.page = self._find_workbench_page()
        return self.page is not None

    def _all_pages(self) -> list:
        pages = []
        for ctx in (self.browser.contexts if self.browser else []):
            pages.extend(ctx.pages)
        return pages

    def _find_workbench_page(self, tries: int = 20):
        for _ in range(tries):
            for pg in self._all_pages():
                try:
                    url = pg.url or ""
                except Exception:
                    continue
                if "workbench" in url or url.endswith(".html"):
                    return pg
            # nothing obvious yet -- fall back to the first titled, non-devtools page
            for pg in self._all_pages():
                try:
                    if pg.url and "devtools" not in pg.url:
                        return pg
                except Exception:
                    continue
            time.sleep(0.7)
        return None

    # ---------------------------------------------------------------- DOM verbs
    def dismiss_modals(self) -> None:
        try:
            for _ in range(2):
                self.page.keyboard.press("Escape")
                time.sleep(0.2)
        except Exception:
            pass

    def open_untitled(self) -> bool:
        """Open a fresh untitled editor. Try Cmd-N, then the command palette."""
        try:
            self.page.keyboard.press("Meta+KeyN")
            time.sleep(1.0)
            if self.has_editor():
                return True
        except Exception:
            pass
        # palette fallback
        for cmd in ("New Untitled Text File", "Create: New Text File", "New Text File"):
            if self.run_command(cmd) and self.has_editor():
                return True
        return self.has_editor()

    def run_command(self, label: str) -> bool:
        try:
            self.page.keyboard.press("Meta+Shift+KeyP")
            time.sleep(0.6)
            self.page.keyboard.type(label, delay=20)
            time.sleep(0.6)
            self.page.keyboard.press("Enter")
            time.sleep(0.9)
            return True
        except Exception as e:  # noqa: BLE001
            if self.trace:
                self.trace.log(f"run_command({label!r}) failed: {e!r}", "warn")
            return False

    def has_editor(self) -> bool:
        try:
            return self.page.locator(".monaco-editor .view-lines").count() > 0
        except Exception:
            return False

    def focus_editor(self) -> None:
        try:
            self.page.locator(".monaco-editor").first.click()
            time.sleep(0.2)
        except Exception:
            pass

    def type_text(self, text: str) -> None:
        self.focus_editor()
        self.page.keyboard.type(text, delay=12)
        time.sleep(0.4)

    def read_editor_lines(self) -> List[str]:
        """Read the rendered Monaco lines back from the DOM (the verification read)."""
        try:
            raw = self.page.locator(".monaco-editor .view-line").all_inner_texts()
        except Exception:
            return []
        out = []
        for ln in raw:
            out.append(ln.replace(" ", " ").replace("​", "").rstrip())
        return out

    def status_text(self) -> str:
        try:
            return " | ".join(t.strip() for t in self.page.locator(".statusbar").all_inner_texts() if t.strip())[:300]
        except Exception:
            return ""

    def screenshot(self, out_path: str) -> bool:
        try:
            self.page.screenshot(path=out_path)
            return Path(out_path).exists()
        except Exception as e:  # noqa: BLE001
            if self.trace:
                self.trace.log(f"electron screenshot failed: {e!r}", "warn")
            return False

    # ---------------------------------------------------------------- teardown
    def close(self) -> None:
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        try:
            if self.proc:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=6)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass
