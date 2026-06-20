"""Task A -- Calculator via deterministic hotkeys, verified with ZERO vision.

Headline layer: **L2a** (keystrokes). The result is read back the cheapest way
that works (L2a clipboard copy), cross-checked against the **L2b** accessibility
tree, and the vision layer (L3) is present in the ladder but never reached --
the "zero vision calls" constraint is *measured* (a counter), not merely claimed.
"""
from __future__ import annotations

from ..layers import BLOCKED, L1, L2A, L2B_AX, L2B_LLM, L3
from ..macos import KEY_ESCAPE, MacOSBackend

EXPR = "123+654"          # Calculator is immediate-execution: 123 + 654 = 777
EXPECTED = "777"
APP = "Calculator"


def _numeric(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def run(ctx, trace, recorder, cascade) -> dict:
    title = f"Compute {EXPR} = {EXPECTED} in Calculator via hotkeys; verify without vision"
    mac = MacOSBackend(trace)
    recorder.screenshot_fn = lambda p: mac.screenshot(p, APP)
    recorder.start_recording(title)

    result = {
        "task": "calculator", "title": title, "status": "fail",
        "headline_layer": None, "vision_calls": 0, "checks": [],
        "observations": {"expression": EXPR, "expected": EXPECTED},
        "trajectory_dir": f"trajectory/{recorder.task_id}",
    }

    # ---- preflight: synthetic keystrokes need macOS Accessibility ----
    if not mac.accessibility_ok():
        cascade.note(
            "preflight: Accessibility permission for synthetic input", BLOCKED, False,
            "System Events refused assistive access (error -1719). Grant Terminal/host "
            "app Accessibility in System Settings → Privacy & Security → Accessibility.",
            primary=True,
        )
        result["status"] = "blocked"
        result["checks"].append({"name": "Accessibility permission", "ok": False,
                                  "detail": "not granted — task cannot send keystrokes"})
        recorder.frame("blocked: no accessibility permission")
        recorder.stop_recording(status="blocked", verdict={"passed": False, "reason": "accessibility"})
        return result

    # ---- L1: launch + focus ----
    cascade.run("launch & focus Calculator", [(L1, lambda: bool(mac.launch(APP) or True))],
                kind="do", target=APP)
    recorder.frame("Calculator launched")

    # ---- L2a: clear, then type the expression via keystrokes ----
    def _enter() -> bool:
        mac.key_code(KEY_ESCAPE)            # clear (AC)
        mac.type_sequence(EXPR)             # 1 2 3 + 6 5 4  (char-by-char)
        mac.keystroke("=")                  # evaluate
        return True

    entry_layer, _ = cascade.run(
        "enter '123+654=' (no menu can do free-form arithmetic → keystrokes)",
        [(L1, None), (L2A, _enter)],        # L1 shown as not-applicable, L2a does it
        kind="hotkey", target=EXPR,
    )
    recorder.frame("after entering expression")
    if entry_layer == BLOCKED:              # keystrokes refused at runtime -> block before any vision rung
        result["status"] = "blocked"
        result["checks"].append({"name": "Accessibility permission for keystrokes", "ok": False,
                                  "detail": "System Events refused to send keystrokes (error 1002)"})
        mac.quit(APP)
        recorder.frame("blocked: keystrokes not permitted")
        recorder.stop_recording(status="blocked", verdict={"passed": False, "reason": "accessibility_keystrokes"})
        return result

    # ---- PRIMARY verify (read), cheapest-correct: clipboard(L2a) → AX(L2b) → vision(L3) ----
    def _read_clipboard():
        mac.clipboard_copy()
        return mac.pbpaste()

    def _read_ax():
        for v in mac.ax_static_texts(APP):
            if _numeric(v):
                return v
        return None

    def _read_vision():                     # present but should never be reached
        result["vision_calls"] += 1
        return None

    layer, value = cascade.run(
        "read the displayed result",
        [(L2A, _read_clipboard), (L2B_AX, _read_ax), (L3, _read_vision)],
        validate=lambda v: _numeric(v) == EXPECTED,
        kind="read", primary=True,
    )
    result["headline_layer"] = layer
    result["observations"]["read_value"] = value
    recorder.frame("result read + verified")
    primary_ok = _numeric(value) == EXPECTED

    # ---- L2b capability cross-check: read the SAME value off the accessibility tree ----
    ax_texts = []
    try:
        ax_texts = mac.ax_static_texts(APP)
    except Exception as e:  # noqa: BLE001
        trace.log(f"AX read failed: {e!r}", "warn")
    ax_val = next((v for v in ax_texts if _numeric(v) == EXPECTED), None)
    cascade.note(
        "L2b cross-check: read result from the accessibility tree", L2B_AX,
        ax_val is not None,
        f"AX static-texts={ax_texts} → matched {ax_val!r}" if ax_val else
        f"AX static-texts={ax_texts or '[]'} (no exact match; clipboard already verified)",
    )
    result["observations"]["ax_texts"] = ax_texts

    # ---- L2b cheap text-LLM judge (deterministic verdict offline; live with a key) ----
    judge_q = (f"Calculator shows {value!r} after computing {EXPR}. "
               f"Is that the correct result? Answer yes or no.")
    judge_txt = (ctx.gateway.complete(judge_q, purpose="cu:judge") or "").strip()
    cascade.note(
        "L2b cheap text-LLM judge: does the read value equal the arithmetic result?",
        L2B_LLM, primary_ok,
        f"deterministic check {value!r}=={EXPECTED!r} → {'match' if primary_ok else 'mismatch'}"
        + (f"; model said: {judge_txt[:60]!r}" if judge_txt else " (offline: no model text)"),
    )

    # ---- checks / verdict ----
    result["checks"] = [
        {"name": "result entered via L2a keystrokes", "ok": True,
         "detail": f"typed {EXPR!r} + '='"},
        {"name": "clipboard read == expected", "ok": primary_ok,
         "detail": f"clipboard={value!r} expected={EXPECTED!r}"},
        {"name": "accessibility-tree read == expected", "ok": ax_val is not None,
         "detail": f"AX={ax_val!r}" if ax_val else "AX display value not exposed as plain static text"},
        {"name": "ZERO vision calls", "ok": result["vision_calls"] == 0,
         "detail": f"vision_calls={result['vision_calls']}"},
    ]
    result["status"] = "ok" if primary_ok else "fail"

    mac.quit(APP)
    recorder.frame("Calculator closed")
    recorder.stop_recording(
        status=result["status"],
        verdict={"passed": primary_ok, "headline_layer": layer, "vision_calls": result["vision_calls"]},
    )
    return result
