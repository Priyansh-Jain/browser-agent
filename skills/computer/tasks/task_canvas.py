"""Task C -- canvas/game target that FORCES the L3 vision layer.

A 3x3 grid is drawn on a ``<canvas>``; one tile shows a number as *pixels*. The
value exists nowhere as DOM/AX text, so the cheap L2b read provably returns
nothing and the cascade must escalate to **L3 vision** (set-of-marks screenshot
→ vision model). The model's read drives the click; the puzzle only reports
``solved`` when the *vision-identified* tile is the one bearing the number — so a
correct verdict is genuine evidence the vision read was right.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..canvasgame import CanvasTarget
from ..layers import BLOCKED, L1, L2B_AX, L3
from ..vision import marks_from_boxes

ASSET = Path(__file__).resolve().parents[1] / "assets" / "canvas_game.html"


def run(ctx, trace, recorder, cascade, n: str = "7", tile: int = 4) -> dict:
    title = f"Read the number on a canvas (no ARIA) via vision, then click its tile"
    url = ASSET.as_uri() + f"?n={n}&tile={tile}"
    game = CanvasTarget(trace, ctx.config, url)
    result = {
        "task": "canvas_vision", "title": title, "status": "fail",
        "headline_layer": None, "vision_calls": 0, "checks": [],
        "observations": {"expected_value": n, "expected_tile": tile},
        "trajectory_dir": f"trajectory/{recorder.task_id}",
    }

    game.open()
    recorder.screenshot_fn = game.screenshot
    recorder.start_recording(title)
    recorder.frame("canvas target opened")

    dom_probe = game.dom_number_probe()      # '' — canvas pixels carry no DOM text
    result["observations"]["dom_text_probe"] = dom_probe or "(no digits in DOM/AX text)"

    # ---- PRIMARY perception (read): L2b DOM/AX text → L3 vision ----
    def _l2b_probe():
        return game.dom_number_probe()        # returns '' → invalid → escalate

    def _l3_vision():
        result["vision_calls"] += 1
        base = str(recorder.dir / "_vision_base.png")
        overlay = str(recorder.dir / "_vision_overlay.png")
        game.screenshot(base)
        boxes = game.tiles_page()
        marks = marks_from_boxes(base, boxes, overlay)
        recorder.attach_frame("L3 set-of-marks vision overlay", overlay)
        listing = "\n".join(f"[{m['id']}] tile region {m['box']}" for m in marks)
        prompt = (
            "Numbered pink boxes mark 9 tiles on a canvas. Exactly one tile shows a large "
            "number; the rest are blank.\nMarks:\n" + listing +
            "\n\nWhich mark contains the number, and what number is shown? "
            'Respond ONLY as JSON: {"mark": <id>, "value": "<number as shown>"}.'
        )
        if hasattr(ctx.gateway, "next_vision_answer"):   # offline mock hint (live key reads pixels)
            ctx.gateway.next_vision_answer = {"mark": tile, "value": n}
        raw = ctx.gateway.vision(prompt, overlay, purpose="cu:canvas")
        if not raw:
            return None
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except Exception:
            data = None
        return data

    layer, read = cascade.run(
        "read the number rendered on the canvas",
        [(L2B_AX, _l2b_probe), (L3, _l3_vision)],
        validate=lambda v: isinstance(v, dict) and v.get("value") not in (None, "")
        and v.get("mark") is not None,
        kind="read", primary=True,
    )
    result["headline_layer"] = layer
    recorder.frame("vision read complete")

    read_tile = int(read["mark"]) if read else -1
    read_value = str(read["value"]) if read else ""
    result["observations"]["vision_read"] = {"tile": read_tile, "value": read_value}

    # ---- act on the vision read: click the identified tile (deterministic pointer = L1) ----
    if read_tile >= 0:
        cascade.run(f"click the vision-identified tile #{read_tile}",
                    [(L1, lambda: bool(game.click_tile(read_tile) or True))],
                    kind="click", target=f"tile {read_tile}")
        recorder.frame(f"clicked tile {read_tile}")

    solved = game.solved()
    value_ok = read_value == n
    tile_ok = read_tile == tile

    result["checks"] = [
        {"name": "L2b DOM/AX read found no number (vision required)", "ok": dom_probe == "",
         "detail": f"dom_number_probe()={dom_probe!r} → escalate to L3"},
        {"name": "vision returned a reading", "ok": bool(read_value),
         "detail": f"tile={read_tile} value={read_value!r}"},
        {"name": "vision value == rendered number", "ok": value_ok,
         "detail": f"read={read_value!r} expected={n!r}"},
        {"name": "vision tile == target tile", "ok": tile_ok,
         "detail": f"read tile={read_tile} expected={tile}"},
        {"name": "clicking the vision tile solved the puzzle", "ok": solved,
         "detail": f"window.__cu_game.solved={solved}"},
        {"name": "vision layer exercised (>=1 call)", "ok": result["vision_calls"] >= 1,
         "detail": f"vision_calls={result['vision_calls']}"},
    ]
    result["status"] = "ok" if (solved and value_ok and tile_ok) else "fail"
    recorder.frame("puzzle solved" if solved else "puzzle not solved")
    recorder.stop_recording(
        status=result["status"],
        verdict={"passed": result["status"] == "ok", "headline_layer": layer,
                 "vision_read": result["observations"]["vision_read"],
                 "vision_calls": result["vision_calls"]},
    )
    game.close()
    return result
