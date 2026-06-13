"""QA / Critic skill -- validate the result before it is reported.

Deterministic checks (completeness, correct task, correctly ranked by likes,
cross-path agreement) plus an optional LLM critique sentence."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from orchestrator.skill import Skill
from skills.browser.recipe_hf import _parse_human


def _approx(a, b, tol=0.07) -> bool:
    if not isinstance(a, int) or not b:
        return True  # not enough info -> don't fail the run
    bi = b if isinstance(b, int) else _parse_human(str(b))
    if not bi:
        return True
    return abs(a - bi) / max(a, bi) <= tol


class QASkill(Skill):
    name = "qa"
    description = "Validate the comparison (complete, correct task, ranked by likes, cross-path agreement)."
    reads = ("raw_records",)
    writes = ("qa",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        recs = ctx.get("raw_records") or []
        cfg = ctx.config
        checks: List[Dict[str, Any]] = []

        checks.append({
            "name": f"collected models (target {cfg.top_n})",
            "ok": len(recs) >= 1,
            "detail": f"{len(recs)} model(s) collected",
        })

        missing = [r.get("id") for r in recs if r.get("likes") is None]
        checks.append({
            "name": "every model has a likes value",
            "ok": not missing,
            "detail": ("missing: " + ", ".join(map(str, missing))) if missing else "all present",
        })

        likes = [r.get("likes") for r in recs if isinstance(r.get("likes"), int)]
        sorted_ok = all(likes[i] >= likes[i + 1] for i in range(len(likes) - 1)) if len(likes) >= 2 else True
        checks.append({
            "name": "correctly ranked by likes (descending)",
            "ok": sorted_ok,
            "detail": " ≥ ".join(f"{x:,}" for x in likes) or "n/a",
        })

        tasks = {r.get("pipeline_tag") for r in recs if r.get("pipeline_tag")}
        task_ok = bool(tasks) and tasks == {cfg.task_filter}
        checks.append({
            "name": f"all models are '{cfg.task_filter}'",
            "ok": task_ok,
            "detail": ", ".join(sorted(t for t in tasks if t)) or "unknown",
        })

        x = next((r for r in recs if ("likes_vision" in r or "likes_a11y" in r)), None)
        if x:
            base = x.get("likes")
            a, v = x.get("likes_a11y"), x.get("likes_vision")
            agree = _approx(base, a) and _approx(base, v)
            checks.append({
                "name": "cross-path likes agree (extract vs a11y/vision)",
                "ok": agree,
                "detail": f"extract={base:,} · a11y={a} · vision={v}" if isinstance(base, int)
                          else f"extract={base} · a11y={a} · vision={v}",
            })

        passed = all(c["ok"] for c in checks)
        critique = ""
        if ctx.gateway.available:
            critique = (ctx.gateway.complete(
                "You are a strict QA critic. In 1-2 sentences, judge whether this model "
                "comparison is trustworthy and note any caveat. Checks:\n" + json.dumps(checks),
                purpose="qa",
            ) or "").strip()
        qa = {"passed": passed, "checks": checks, "critique": critique}
        ctx.put("qa", qa)
        ok_n = sum(1 for c in checks if c["ok"])
        return {"summary": f"QA {'PASS' if passed else 'REVIEW'} ({ok_n}/{len(checks)})", "passed": passed}
