"""Canvas/game target backend -- forces the L3 vision layer.

Opens a local ``<canvas>`` page in Playwright's own Chromium. The target value
is rendered as *pixels* (canvas ``fillText``), so there is no DOM/AX text to read
-- the cheaper L2b layer provably returns nothing and the cascade must escalate
to vision. Screenshots come from Playwright's rasteriser, so no macOS
Screen-Recording permission is involved.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class CanvasTarget:
    def __init__(self, trace, config, url: str):
        self.trace = trace
        self.config = config
        self.url = url
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None

    def open(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.config.headless, slow_mo=self.config.slow_mo_ms)
        self.context = self.browser.new_context(viewport={"width": 520, "height": 640}, locale="en-US")
        self.page = self.context.new_page()
        self.page.goto(self.url, wait_until="load")
        self.page.wait_for_timeout(500)

    # ---- L2b probe: is the value available as accessible / DOM text? (it isn't) ----
    def dom_text(self) -> str:
        try:
            return (self.page.locator("body").inner_text() or "").strip()
        except Exception:
            return ""

    def dom_number_probe(self) -> str:
        """Return any digit sequence reachable as DOM/AX text. Canvas pixels are
        invisible to this, so it returns '' -> the cascade escalates to vision."""
        digits = re.findall(r"\d+", self.dom_text())
        return "".join(digits)

    # ---- geometry (screenshot-pixel coords) for marks + clicking ----
    def tiles_page(self) -> List[Dict[str, Any]]:
        box = self.page.locator("#c").bounding_box() or {"x": 0, "y": 0}
        tiles = self.page.evaluate("() => (window.__cu_game ? window.__cu_game.tiles : [])") or []
        out = []
        for t in tiles:
            out.append({"index": t["index"], "x": box["x"] + t["x"], "y": box["y"] + t["y"],
                        "w": t["w"], "h": t["h"]})
        return out

    def screenshot(self, out_path: str) -> bool:
        try:
            self.page.screenshot(path=out_path)
            return Path(out_path).exists()
        except Exception as e:  # noqa: BLE001
            if self.trace:
                self.trace.log(f"canvas screenshot failed: {e!r}", "warn")
            return False

    # ---- action + verification ----
    def click_tile(self, index: int) -> None:
        for t in self.tiles_page():
            if t["index"] == index:
                self.page.mouse.click(t["x"] + t["w"] / 2, t["y"] + t["h"] / 2)
                self.page.wait_for_timeout(400)
                return
        raise ValueError(f"tile {index} not found")

    def solved(self) -> bool:
        try:
            return bool(self.page.evaluate("() => !!(window.__cu_game && window.__cu_game.solved)"))
        except Exception:
            return False

    def close(self) -> None:
        for fn in (getattr(self.context, "close", None),
                   getattr(self.browser, "close", None),
                   getattr(self._pw, "stop", None)):
            try:
                if fn:
                    fn()
            except Exception:
                pass
