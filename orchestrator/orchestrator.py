"""=====================================================================
  FROZEN ORCHESTRATOR  --  DO NOT MODIFY FOR NEW TASKS OR SITES.
=====================================================================

This engine is intentionally generic. It knows how to:

  1. ask the *planner* skill for a plan (a DAG of skill invocations),
  2. execute that DAG in topological order, dispatching each node to a
     skill looked up by name in the catalogue, and
  3. record every turn into the Trace.

It contains NO knowledge of browsers, Hugging Face, comparison tables,
CSS selectors, or any other task detail. All new behaviour is added by
registering / extending skills in the catalogue (see skills/). The
assignment constraint "the orchestrator must not be modified" is satisfied
by construction: this file never needs to change to support a new task.
"""
from __future__ import annotations

from typing import Any, Dict

from .catalogue import SkillCatalogue
from .context import Context
from .dag import DAG
from .errors import GatewayBlocked
from .trace import Trace

__frozen__ = True


def _summarise(out: Any) -> str:
    if isinstance(out, dict):
        if "summary" in out:
            return str(out["summary"])
        return ", ".join(f"{k}={_short(v)}" for k, v in list(out.items())[:4])
    return _short(out)


def _short(v: Any) -> str:
    s = str(v)
    return s if len(s) <= 80 else s[:77] + "..."


class Orchestrator:
    def __init__(self, catalogue: SkillCatalogue, planner_skill: str = "planner") -> None:
        self.catalogue = catalogue
        self.planner_skill = planner_skill

    def run(self, ctx: Context, trace: Trace) -> Dict[str, Any]:
        # ---- Turn 1: planning -------------------------------------------------
        planner = self.catalogue.get(self.planner_skill)
        pstep = trace.start_step("plan", planner.name, {"goal": ctx.goal})
        plan = planner.run(ctx, trace, goal=ctx.goal)
        dag = DAG.from_dict(plan)
        trace.set_plan(dag.to_dict(), dag.to_mermaid(), plan.get("source", "unknown"))
        trace.end_step(pstep, "ok", f"{len(dag.nodes)} nodes via {plan.get('source')}")

        # ---- Turns 2..N: execute the plan ------------------------------------
        for node in dag.topo_order():
            if not self.catalogue.has(node.skill):
                step = trace.start_step(node.id, node.skill, node.params)
                trace.end_step(step, "error", f"unknown skill {node.skill!r}")
                trace.log(f"Plan referenced unknown skill {node.skill!r}; skipping", "error")
                continue
            skill = self.catalogue.get(node.skill)
            step = trace.start_step(node.id, node.skill, node.params)
            try:
                out = skill.run(ctx, trace, **node.params) or {}
                trace.end_step(step, "ok", _summarise(out))
            except GatewayBlocked as e:
                trace.end_step(step, "blocked", str(e))
                trace.log(f"Node {node.id!r} blocked: {e}", "warn")
                # Keep going so the Distiller/QA/Report can still run on
                # whatever was gathered and surface the block to the user.
            except Exception as e:  # pragma: no cover - defensive
                trace.end_step(step, "error", repr(e))
                trace.log(f"Node {node.id!r} errored: {e!r}", "error")
                raise

        trace.finish()
        return ctx.get("report", {})
