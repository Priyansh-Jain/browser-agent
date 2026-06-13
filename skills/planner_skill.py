"""Planner skill -- turns the user goal into a DAG of catalogue skill calls.

Uses the LLM (given the catalogue manifest) when a key is available, and always
validates the result against the catalogue. Falls back to a known-good
deterministic plan if the LLM is unavailable or returns something invalid, so a
run never depends on the model behaving.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from orchestrator.dag import DAG
from orchestrator.skill import Skill


def _fallback_plan(cfg) -> Dict[str, Any]:
    return {
        "source": "fallback",
        "nodes": [
            {"id": "research", "skill": "researcher", "title": "Find candidate URLs", "params": {}},
            {"id": "browse", "skill": "browser", "title": "Interact + extract (cheapest path)",
             "params": {"top_n": cfg.top_n}, "deps": ["research"]},
            {"id": "distill", "skill": "distiller", "title": "Distill comparison rows",
             "params": {}, "deps": ["browse"]},
            {"id": "qa", "skill": "qa", "title": "QA / Critic", "params": {}, "deps": ["distill"]},
            {"id": "report", "skill": "report", "title": "Replay Viewer / report",
             "params": {}, "deps": ["qa"]},
        ],
        "edges": [],
    }


class PlannerSkill(Skill):
    name = "planner"
    description = "Decompose the user goal into a DAG of skill invocations drawn from the catalogue."
    writes = ("plan",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        manifest: List[Dict[str, Any]] = ctx.get("catalogue_manifest", [])
        known = {m["name"] for m in manifest}
        plan = self._llm_plan(ctx, trace, manifest, known)
        if plan is None:
            plan = _fallback_plan(ctx.config)
            trace.log("planner: using deterministic fallback plan", "info")
        else:
            trace.log("planner: using LLM-generated plan", "info")
        # guarantee the browser node carries top_n
        for n in plan["nodes"]:
            if n["skill"] == "browser":
                n.setdefault("params", {}).setdefault("top_n", ctx.config.top_n)
        return plan

    def _llm_plan(self, ctx, trace, manifest, known):
        if not ctx.gateway.available:
            return None
        cat = "\n".join(f"- {m['name']}: {m['description']}" for m in manifest)
        prompt = (
            f"User goal: {ctx.goal}\n\n"
            f"Available skills (use ONLY these names):\n{cat}\n\n"
            "Produce a plan as a DAG. Output JSON: "
            '{"nodes":[{"id":"...","skill":"<one of the skill names>","title":"...",'
            '"params":{},"deps":["<id>"...]}], "edges":[]}.\n'
            "Rules: start by researching URLs, then use the browser skill to interact and "
            "extract, then distiller, then qa, then report (terminal). The 'browser' and "
            "'report' skills are mandatory."
        )
        data = ctx.gateway.json(prompt, purpose="plan")
        if not isinstance(data, dict):
            return None
        try:
            nodes = data.get("nodes")
            assert isinstance(nodes, list) and nodes
            used = {n["skill"] for n in nodes}
            assert {"browser", "report"} <= used, "missing mandatory skills"
            assert used <= known, f"unknown skills {used - known}"
            DAG.from_dict(data)  # validates deps + acyclic
        except Exception as e:
            trace.log(f"planner: LLM plan rejected ({e}); falling back", "warn")
            return None
        data["source"] = "llm"
        return data
