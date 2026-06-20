"""Set-of-marks overlay for the L3 vision layer.

Unlike the Browser skill (which marks DOM elements), a canvas/game target has no
per-element DOM, so we draw numbered marks from *explicit box geometry* supplied
by the target. The marked screenshot is the vision model's input; the model is
asked which mark holds the value and what the value is.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False

_PINK = (229, 30, 99)


def _font(size: int = 20):
    for path in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def marks_from_boxes(image_path: str, boxes: List[Dict[str, Any]], out_path: str) -> List[Dict[str, Any]]:
    """boxes: [{index, x, y, w, h}] in screenshot pixel coordinates."""
    if not _PIL_OK:
        return []
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = _font(20)
    marks: List[Dict[str, Any]] = []
    for b in boxes:
        i = int(b["index"])
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        draw.rectangle([x, y, x + w, y + h], outline=_PINK, width=3)
        lbl = str(i)
        draw.rectangle([x, y, x + 13 * len(lbl) + 8, y + 22], fill=_PINK)
        if font:
            draw.text((x + 4, y + 1), lbl, fill=(255, 255, 255), font=font)
        marks.append({"id": i, "box": [round(x), round(y), round(x + w), round(y + h)], "text": ""})
    img.save(out_path)
    return marks
