"""The five-layer control cascade -- the computer-use cost ladder.

The Browser skill ranks data paths ``extract < deterministic < a11y < vision``.
Computer use ranks *control* paths the same way: always reach for the cheapest,
most-deterministic layer that actually works, and only escalate when it doesn't.
Making this ladder explicit (and recording every rung that was tried) is the
"cascade discipline" the assignment asks for.

    cheapest ───────────────────────────────────────────────► costliest
    L1            page          L2a          L2b            L3          L4
    lifecycle     Electron      hotkeys      a11y tree +    set-of-     blocked /
    / menus /     CDP DOM       / keystrokes cheap TEXT     marks       escalate
    AppleScript   (debug port)  (no model)   LLM judge      vision

Why this order:
  * L1 / page are *deterministic and free* -- a menu item or a DOM selector can
    never be misread, so they're tried first.
  * L2a hotkeys are deterministic but "blind" (you must already know the target),
    so they rank just above scripted control.
  * L2b reads the accessibility tree / DOM text and may consult a *cheap text*
    model to disambiguate -- text tokens only, no pixels.
  * L3 vision (screenshot -> set-of-marks -> vision model) is the expensive
    fallback used only when there is no AX/DOM to read (canvas, games).
  * L4 is "couldn't do it" -- permission denied, element absent -> record + escalate.
"""
from __future__ import annotations

# Layer identifiers (kept short; used as the ``path`` label in path_decisions).
L1 = "L1"            # deterministic: app lifecycle, menu items, AppleScript verbs
PAGE = "page"        # Electron CDP DOM via electron_debugging_port (deterministic)
L2A = "L2a"          # deterministic hotkeys / keystrokes (no model)
L2B_AX = "L2b-ax"    # accessibility tree / DOM text read (no pixels, no model)
L2B_LLM = "L2b-llm"  # cheap *text* LLM judgment over the AX/DOM dump
L3 = "L3"            # vision: set-of-marks screenshot -> vision model
BLOCKED = "L4"       # escalate / blocked (permission denied, element absent)

LAYER_COST = {L1: 1, PAGE: 1, L2A: 2, L2B_AX: 3, L2B_LLM: 3, L3: 4, BLOCKED: 5}

LAYER_LABEL = {
    L1: "L1 · deterministic (lifecycle / menu)",
    PAGE: "page · Electron CDP DOM",
    L2A: "L2a · deterministic hotkeys",
    L2B_AX: "L2b · accessibility tree",
    L2B_LLM: "L2b · cheap text-LLM judge",
    L3: "L3 · vision (set-of-marks)",
    BLOCKED: "L4 · blocked / escalate",
}

# Layers that consume a vision model call -- used to assert the "zero vision" task.
VISION_LAYERS = {L3}


def cost(layer: str) -> int:
    return LAYER_COST.get(layer, 0)
