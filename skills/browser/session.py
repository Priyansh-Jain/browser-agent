"""Thin Playwright wrapper used by the Browser skill.

Owns the browser lifecycle, records every navigation/click/scroll as an action
in the Trace, saves screenshots (referenced by the Replay Viewer), writes a
Playwright trace.zip (a literal time-travel replay), and detects bot-walls so
the orchestrator can mark a step ``blocked``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from orchestrator.errors import GatewayBlocked

_BLOCK_MARKERS = (
    "just a moment",
    "verify you are human",
    "verifying you are human",
    "captcha",
    "access denied",
    "unusual traffic",
    "cf-browser-verification",
    "are you a robot",
)


def _slug(s: str, n: int = 32) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s or "shot")[:n]


class BrowserSession:
    def __init__(self, config, trace, run_dir: Path):
        self.config = config
        self.trace = trace
        self.run_dir = Path(run_dir)
        self.shots_dir = self.run_dir / "screenshots"
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self._n_shot = 0
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=config.headless, slow_mo=config.slow_mo_ms
        )
        self.context = self.browser.new_context(
            user_agent=config.user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        self.context.set_default_timeout(config.action_timeout_ms)
        self.context.set_default_navigation_timeout(config.nav_timeout_ms)
        # Playwright tracing => artifacts/<run>/trace.zip (open with `playwright show-trace`)
        self._tracing = False
        try:
            self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self._tracing = True
        except Exception as e:  # pragma: no cover
            self.trace.log(f"tracing unavailable: {e!r}", "warn")
        self.page = self.context.new_page()

    # ---- navigation ----
    def goto(self, url: str, note: str = "") -> None:
        resp = self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1500)
        self.trace.record_action("navigate", target=url, url=self.page.url, note=note)
        self._check_blocked(resp)

    def wait(self, ms: int = 1200) -> None:
        self.page.wait_for_timeout(ms)

    def scroll(self, pixels: int = 1600, note: str = "lazy-load") -> None:
        self.page.mouse.wheel(0, pixels)
        self.page.wait_for_timeout(900)
        self.trace.record_action("scroll", value=str(pixels), url=self.page.url, note=note)

    # ---- introspection ----
    def html(self) -> str:
        return self.page.content()

    def url(self) -> str:
        return self.page.url

    def page_state(self, note: str = "") -> None:
        try:
            title = self.page.title()
        except Exception:
            title = ""
        self.trace.record_page_state(self.page.url, title, note)

    # ---- screenshots ----
    def shot(self, caption: str, full_page: bool = False) -> str:
        self._n_shot += 1
        fname = f"{self._n_shot:02d}_{_slug(caption)}.png"
        abspath = self.shots_dir / fname
        try:
            self.page.screenshot(path=str(abspath), full_page=full_page)
        except Exception as e:  # pragma: no cover
            self.trace.log(f"screenshot failed: {e!r}", "warn")
            return ""
        rel = f"screenshots/{fname}"
        self.trace.record_screenshot(rel, caption, self.page.url)
        return rel

    # ---- blocking ----
    def _check_blocked(self, resp) -> None:
        status = getattr(resp, "status", 200) if resp else 200
        if status in (401, 403, 407, 429, 503):
            raise GatewayBlocked(f"HTTP {status} at {self.page.url}")
        try:
            head = self.page.title().lower() + " " + self.page.inner_text("body")[:600].lower()
        except Exception:
            head = ""
        for mk in _BLOCK_MARKERS:
            if mk in head:
                raise GatewayBlocked(f"bot-wall marker {mk!r} at {self.page.url}")

    # ---- teardown ----
    def close(self) -> None:
        if self._tracing:
            try:
                self.context.tracing.stop(path=str(self.run_dir / "trace.zip"))
            except Exception as e:  # pragma: no cover
                self.trace.log(f"tracing stop failed: {e!r}", "warn")
        for fn in (self.context.close, self.browser.close, self._pw.stop):
            try:
                fn()
            except Exception:
                pass
