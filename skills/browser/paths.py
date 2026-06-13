"""The cheapest-correct-path cascade.

For *clicking* a control:   deterministic(CSS) -> a11y(role/name).
For *extracting* data:      extract(static) -> deterministic(DOM) -> a11y -> vision.

Each attempt is recorded so the Replay Viewer can show the ladder and the
single path that was ultimately chosen.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple


class ElementNotFound(Exception):
    pass


class PathSelector:
    def __init__(self, session, gateway, trace):
        self.session = session
        self.gateway = gateway
        self.trace = trace

    @property
    def page(self):
        return self.session.page

    # ------------------------------------------------------------------ click
    def click(
        self,
        intent: str,
        *,
        css: Optional[List[str]] = None,
        role: Optional[str] = None,
        name: Optional[Any] = None,
        primary: bool = False,
    ) -> str:
        attempts: List[Dict[str, Any]] = []

        # 1) deterministic CSS
        for sel in css or []:
            try:
                loc = self.page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    loc.first.scroll_into_view_if_needed(timeout=3000)
                    loc.first.click()
                    attempts.append({"path": "deterministic", "ok": True, "note": f"css {sel}"})
                    self._finish(intent, attempts, "deterministic", primary, "click", sel)
                    return "deterministic"
                attempts.append({"path": "deterministic", "ok": False, "note": f"css {sel}: no visible match"})
            except Exception as e:
                attempts.append({"path": "deterministic", "ok": False, "note": f"css {sel}: {type(e).__name__}"})

        # 2) a11y (role + accessible name -> Playwright reads the accessibility tree)
        if role and name is not None:
            try:
                loc = self.page.get_by_role(role, name=name)
                if loc.count() and loc.first.is_visible():
                    loc.first.scroll_into_view_if_needed(timeout=3000)
                    loc.first.click()
                    attempts.append({"path": "a11y", "ok": True, "note": f"role={role} name={name!r}"})
                    self._finish(intent, attempts, "a11y", primary, "click", f"role:{role}")
                    return "a11y"
                attempts.append({"path": "a11y", "ok": False, "note": f"role={role} name={name!r}: no match"})
            except Exception as e:
                attempts.append({"path": "a11y", "ok": False, "note": f"a11y: {type(e).__name__}"})

        self.trace.record_path_decision(intent, attempts, "failed", primary)
        raise ElementNotFound(intent)

    # ---------------------------------------------------------------- extract
    def extract(
        self,
        intent: str,
        *,
        static_fn: Optional[Callable[[], Any]] = None,
        css_fn: Optional[Callable[[], Any]] = None,
        a11y_fn: Optional[Callable[[], Any]] = None,
        vision_fn: Optional[Callable[[], Any]] = None,
        validate: Optional[Callable[[Any], bool]] = None,
        primary: bool = True,
    ) -> Tuple[str, Any]:
        validate = validate or (lambda v: bool(v))
        ladder = [
            ("extract", static_fn),
            ("deterministic", css_fn),
            ("a11y", a11y_fn),
            ("vision", vision_fn),
        ]
        attempts: List[Dict[str, Any]] = []
        for pathname, fn in ladder:
            if fn is None:
                attempts.append({"path": pathname, "ok": False, "note": "not implemented for this intent"})
                continue
            try:
                val = fn()
                ok = bool(val) and validate(val)
                attempts.append({"path": pathname, "ok": ok, "note": _describe(val) if ok else "empty/invalid"})
                if ok:
                    self.trace.record_path_decision(intent, attempts, pathname, primary)
                    return pathname, val
            except Exception as e:
                attempts.append({"path": pathname, "ok": False, "note": f"{type(e).__name__}: {e}"[:90]})
        self.trace.record_path_decision(intent, attempts, "blocked", primary)
        return "blocked", None

    # ---------------------------------------------------------------- helpers
    def _finish(self, intent, attempts, chosen, primary, kind, target):
        self.trace.record_path_decision(intent, attempts, chosen, primary)
        self.trace.record_action(kind, target=intent, value=str(target), path=chosen, url=self.page.url)


def _describe(v: Any) -> str:
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        keys = ",".join(list(v.keys())[:6])
        return f"dict{{{keys}}}"
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."
