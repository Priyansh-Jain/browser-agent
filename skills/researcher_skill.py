"""Researcher skill -- resolve the goal to concrete candidate URLs on
authoritative, dynamic sites (so the Browser skill has somewhere to act). This
is deliberately NOT snippet scraping: it just points the browser at the right
JS-rendered catalogue page."""
from __future__ import annotations

from typing import Any, Dict

from orchestrator.skill import Skill

# Tiny keyword registry. Extend with more sites without touching anything else.
_REGISTRY = [
    (("hugging face", "huggingface", "hf ", "text-generation", "text generation", "model"),
     "https://huggingface.co/models"),
]


class ResearcherSkill(Skill):
    name = "researcher"
    description = "Resolve the goal into concrete candidate URLs on dynamic catalogue sites."
    writes = ("candidate_urls", "intent")

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        goal = ctx.goal.lower()
        url = ctx.config.target_url
        for kws, u in _REGISTRY:
            if any(k in goal for k in kws):
                url = u
                break
        candidates = [url]
        intent = {
            "task": ctx.config.task_filter,
            "sort": ctx.config.sort_by,
            "top_n": ctx.config.top_n,
        }
        if ctx.gateway.available:
            note = ctx.gateway.complete(
                f"In ONE sentence, why is {url} the right place to accomplish: '{ctx.goal}', "
                "and confirm we must filter by task and sort by likes via the UI.",
                purpose="research",
            )
            if note:
                trace.log("researcher rationale: " + note.strip()[:240])
        ctx.put("candidate_urls", candidates)
        ctx.put("intent", intent)
        return {"summary": f"candidate_urls={candidates}", "candidate_urls": candidates, "intent": intent}
