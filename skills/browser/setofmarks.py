"""Set-of-Marks vision helper.

``annotate`` overlays numbered boxes on the candidate elements of the current
viewport and returns the marks. The Browser skill then (when an API key is
present) asks the vision model which mark holds the value. The overlay image is
produced even without a key, so the report can always show the vision-path input.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    _PIL_OK = True
except Exception:  # pragma: no cover
    _PIL_OK = False


def _font(size: int = 16):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def annotate(session, candidate_selector: str, out_path: Path, max_marks: int = 18) -> List[Dict[str, Any]]:
    """Screenshot the viewport and draw numbered boxes over candidate elements.
    Returns the list of marks (id, box, text)."""
    if not _PIL_OK:
        return []
    page = session.page
    raw = out_path.with_name(out_path.stem + "_raw.png")
    page.screenshot(path=str(raw))
    img = Image.open(raw).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = _font(16)
    handles = page.query_selector_all(candidate_selector)
    marks: List[Dict[str, Any]] = []
    vw, vh = img.size
    for el in handles:
        if len(marks) >= max_marks:
            break
        try:
            if not el.is_visible():
                continue
            box = el.bounding_box()
            txt = (el.inner_text() or "").strip().replace("\n", " ")
        except Exception:
            continue
        if not box or box["width"] < 8 or box["height"] < 8:
            continue
        if box["y"] > vh or box["x"] > vw:
            continue
        mid = len(marks)
        x0, y0 = box["x"], box["y"]
        x1, y1 = x0 + box["width"], y0 + box["height"]
        draw.rectangle([x0, y0, x1, y1], outline=(229, 30, 99), width=2)
        label = str(mid)
        draw.rectangle([x0, max(0, y0 - 18), x0 + 9 * len(label) + 6, y0], fill=(229, 30, 99))
        if font:
            draw.text((x0 + 3, max(0, y0 - 18)), label, fill=(255, 255, 255), font=font)
        marks.append({"id": mid, "box": [round(x0), round(y0), round(x1), round(y1)], "text": txt[:50]})
    img.save(out_path)
    try:
        raw.unlink()
    except Exception:
        pass
    return marks
