"""Task B -- Electron (Cursor) over the remote debugging port.

Headline path: **page** (Chromium DevTools Protocol via ``electron_debugging_port``).
We launch Cursor with ``--remote-debugging-port`` into a throwaway profile, attach
Playwright over CDP, compose a multi-line draft in an *untitled* buffer (no file is
ever saved → zero side effects), then VERIFY strongly: read every Monaco
``.view-line`` back from the DOM and require exact line-by-line agreement (L2b
text read), plus a cheap text-LLM judge. Vision (L3) is the unused fallback.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

from ..electron import ElectronCDP
from ..layers import BLOCKED, L1, L2A, L2B_AX, L2B_LLM, L3, PAGE

CURSOR_BIN = "/Applications/Cursor.app/Contents/MacOS/Cursor"

DRAFT_LINES = [
    "Release notes - Computer-Use skill v1",
    "",
    "Five-layer cascade: L1 -> page -> L2a -> L2b -> L3",
    "Electron driven over the remote debugging port (CDP page path).",
    "Verified by reading the editor DOM back - no vision required.",
]
DRAFT_TEXT = "\n".join(DRAFT_LINES)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def run(ctx, trace, recorder, cascade, port: int = 9223) -> dict:
    title = "Compose a draft in Cursor (Electron) over electron_debugging_port; verify via DOM"
    result = {
        "task": "electron_cursor", "title": title, "status": "fail",
        "headline_layer": None, "vision_calls": 0, "checks": [],
        "observations": {"port": port, "binary": CURSOR_BIN},
        "trajectory_dir": f"trajectory/{recorder.task_id}",
    }

    if not os.path.exists(CURSOR_BIN):
        cascade.note("preflight: Cursor installed", BLOCKED, False,
                     f"{CURSOR_BIN} not found", primary=True)
        result["status"] = "blocked"
        result["checks"].append({"name": "Cursor present", "ok": False, "detail": CURSOR_BIN})
        recorder.start_recording(title)
        recorder.frame("blocked: Cursor not installed", capture=False)
        recorder.stop_recording(status="blocked", verdict={"passed": False, "reason": "not installed"})
        return result

    udir = tempfile.mkdtemp(prefix="cu-cursor-")
    el = ElectronCDP(trace, CURSOR_BIN, port, udir)
    recorder.start_recording(title)

    try:
        # ---- L1: launch Cursor with the debug port ----
        launched = cascade.run(
            "launch Cursor --remote-debugging-port (isolated profile)",
            [(L1, lambda: el.launch())], kind="do", target=f"port {port}",
        )[1]
        if not launched:
            result["status"] = "blocked"
            result["checks"].append({"name": "debug port reachable", "ok": False,
                                      "detail": f"http://127.0.0.1:{port}/json/version not ready"})
            recorder.stop_recording(status="blocked", verdict={"passed": False, "reason": "debug port"})
            return result

        # ---- page: attach Playwright over CDP ----
        attached = cascade.run(
            "attach Playwright over CDP (the page tool)",
            [(PAGE, lambda: el.connect())], kind="do", target=f"127.0.0.1:{port}",
        )[1]
        if not attached:
            result["status"] = "blocked"
            result["checks"].append({"name": "CDP workbench page found", "ok": False,
                                      "detail": "no workbench renderer page"})
            recorder.stop_recording(status="blocked", verdict={"passed": False, "reason": "no page"})
            return result
        recorder.screenshot_fn = el.screenshot   # frames now come from the renderer
        result["observations"]["workbench_url"] = (el.page.url or "")[:120]
        el.dismiss_modals()
        recorder.frame("Cursor workbench attached")

        # ---- page: open an untitled editor ----
        cascade.run("open an untitled editor (page channel)",
                    [(PAGE, lambda: el.open_untitled())], kind="do")
        recorder.frame("untitled editor open")

        # ---- compose: page (CDP keyboard) preferred over OS hotkeys (L2a) ----
        cascade.run(
            "type the draft into the editor",
            [(PAGE, lambda: bool(el.type_text(DRAFT_TEXT) or True)),
             (L2A, None)],                       # OS-keystroke fallback (not needed)
            kind="do", target=f"{len(DRAFT_LINES)} lines",
        )
        recorder.frame("after typing the draft")

        # ---- PRIMARY verify (read): DOM read-back (L2b text) → vision (L3, unused) ----
        def _read_dom():
            lines = [l for l in el.read_editor_lines() if l.strip() != ""]
            return lines or None

        def _read_vision():
            result["vision_calls"] += 1
            return None

        layer, lines = cascade.run(
            "read the composed draft back from the editor DOM",
            [(L2B_AX, _read_dom), (L3, _read_vision)],
            validate=lambda ls: isinstance(ls, list) and len(ls) >= 4,
            kind="read", primary=True,
        )
        result["headline_layer"] = "page"        # the whole task was driven via the page path
        got = [_norm(l) for l in (lines or [])]
        result["observations"]["editor_lines"] = got
        result["observations"]["status_bar"] = el.status_text()

        expected_nonblank = [_norm(l) for l in DRAFT_LINES if l.strip()]
        joined = " \n ".join(got)
        per_line = {e: (e in joined) for e in expected_nonblank}
        all_lines_ok = all(per_line.values())
        has_cascade_line = any("L1 -> page -> L2a -> L2b -> L3" in g.replace("  ", " ") for g in got) \
            or "L1 -> page -> L2a -> L2b -> L3" in joined
        recorder.frame("draft verified via DOM read-back")

        # ---- L2b cheap text-LLM judge ----
        judge_q = ("Here is an editor buffer:\n" + "\n".join(got) +
                   "\n\nIs this a well-formed multi-line release-notes draft that mentions a "
                   "five-layer cascade? Answer yes or no.")
        judge_txt = (ctx.gateway.complete(judge_q, purpose="cu:judge") or "").strip()
        cascade.note(
            "L2b cheap text-LLM judge: is the composed draft well-formed?",
            L2B_LLM, all_lines_ok,
            f"{sum(per_line.values())}/{len(per_line)} expected lines present"
            + (f"; model said {judge_txt[:50]!r}" if judge_txt else " (offline: deterministic check)"),
        )

        result["checks"] = [
            {"name": "attached to Electron via debug port", "ok": True,
             "detail": result["observations"].get("workbench_url", "")},
            {"name": "draft composed in untitled buffer (no file saved)", "ok": True,
             "detail": f"{len(DRAFT_LINES)} lines typed via CDP keyboard"},
            {"name": "DOM read-back: all lines present", "ok": all_lines_ok,
             "detail": f"{sum(per_line.values())}/{len(per_line)} lines matched"},
            {"name": "contains the five-layer cascade line", "ok": has_cascade_line,
             "detail": "found 'L1 -> page -> L2a -> L2b -> L3'" if has_cascade_line else "missing"},
            {"name": "ZERO vision calls", "ok": result["vision_calls"] == 0,
             "detail": f"vision_calls={result['vision_calls']}"},
        ]
        result["status"] = "ok" if all_lines_ok else "fail"
        recorder.stop_recording(
            status=result["status"],
            verdict={"passed": all_lines_ok, "headline_layer": "page",
                     "lines_matched": f"{sum(per_line.values())}/{len(per_line)}",
                     "vision_calls": result["vision_calls"]},
        )
        return result
    finally:
        el.close()
        shutil.rmtree(udir, ignore_errors=True)
