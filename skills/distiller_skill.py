"""Distiller skill -- normalise the raw per-model records into clean comparison
rows with stable columns. Adds an optional LLM one-liner comparing the models."""
from __future__ import annotations

import json
from typing import Any, Dict

from orchestrator.skill import Skill
from skills.browser.recipe_hf import humanize_int

_COLUMNS = [
    {"key": "rank", "label": "#"},
    {"key": "id", "label": "Model"},
    {"key": "likes", "label": "Likes"},
    {"key": "downloads", "label": "Downloads/mo"},
    {"key": "params", "label": "Params"},
    {"key": "license", "label": "License"},
    {"key": "task", "label": "Task"},
    {"key": "updated", "label": "Updated"},
]


class DistillerSkill(Skill):
    name = "distiller"
    description = "Normalise raw browser records into a structured comparison table."
    reads = ("raw_records",)
    writes = ("comparison",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        recs = ctx.get("raw_records") or []
        rows = []
        for r in recs:
            likes = r.get("likes")
            rows.append({
                "rank": r.get("rank"),
                "id": r.get("id"),
                "url": r.get("url"),
                "likes": f"{likes:,}" if isinstance(likes, int) else (likes or "—"),
                "downloads": humanize_int(r.get("downloads_last_month")) or "—",
                "params": r.get("params") or "—",
                "license": r.get("license") or "—",
                "task": r.get("pipeline_tag") or "—",
                "updated": r.get("last_modified") or "—",
            })
        winner = f"{rows[0]['id']} ({rows[0]['likes']} likes)" if rows else ""
        notes = ""
        if ctx.gateway.available and rows:
            slim = [{k: r.get(k) for k in ("id", "likes", "downloads", "params", "license")} for r in rows]
            notes = (ctx.gateway.complete(
                "In 2 sentences, compare these models by popularity (likes), reach (downloads) "
                "and size (params). Be specific and neutral:\n" + json.dumps(slim),
                purpose="distill",
            ) or "").strip()
        comparison = {"columns": _COLUMNS, "rows": rows, "winner": winner, "notes": notes}
        ctx.put("comparison", comparison)
        trace.set_final(raw_records=recs)
        return {"summary": f"{len(rows)} comparison rows", "rows": len(rows)}
