"""Run trace + cost/turn accounting.

Everything the agent does is appended to a Trace: the plan, every step, every
browser action, every screenshot/page-state, every path decision, and every LLM
call (with token usage so we can compute an estimated cost). The Trace is the
single source of truth for the Replay Viewer and is serialised to trace.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# USD per 1,000,000 tokens (input, output). Estimates -- override via Config.
DEFAULT_PRICING: Dict[str, tuple] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-opus-4-8[1m]": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "_default": (3.0, 15.0),
}

# Relative cost ordering of browser paths (cheap -> expensive). Used to pick the
# single "headline" path for the run and to justify the cascade.
PATH_COST = {"extract": 1, "deterministic": 2, "a11y": 3, "vision": 4, "blocked": 5}


class Trace:
    def __init__(
        self,
        goal: str,
        run_id: str,
        pricing: Optional[Dict[str, tuple]] = None,
    ) -> None:
        self.goal = goal
        self.run_id = run_id
        self.pricing = pricing or DEFAULT_PRICING
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.plan: Optional[Dict[str, Any]] = None
        self.plan_mermaid: str = ""
        self.plan_source: str = ""          # "llm" | "fallback"
        self.steps: List[Dict[str, Any]] = []
        self.llm_calls: List[Dict[str, Any]] = []
        self.actions: List[Dict[str, Any]] = []
        self.screenshots: List[Dict[str, Any]] = []
        self.page_states: List[Dict[str, Any]] = []
        self.path_decisions: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.final: Dict[str, Any] = {}

    # ----- generic log -----
    def log(self, msg: str, level: str = "info") -> None:
        self.events.append({"t": self._rel(), "level": level, "msg": msg})

    # ----- plan -----
    def set_plan(self, plan: Dict[str, Any], mermaid: str, source: str) -> None:
        self.plan = plan
        self.plan_mermaid = mermaid
        self.plan_source = source

    # ----- steps (a "turn" == one executed DAG node) -----
    def start_step(self, node_id: str, skill: str, params: Dict[str, Any]) -> Dict[str, Any]:
        rec = {
            "node": node_id,
            "skill": skill,
            "params": params,
            "started": self._rel(),
            "ended": None,
            "status": "running",
            "summary": None,
        }
        self.steps.append(rec)
        return rec

    def end_step(self, rec: Dict[str, Any], status: str = "ok", summary: Any = None) -> None:
        rec["ended"] = self._rel()
        rec["status"] = status
        rec["summary"] = summary

    # ----- LLM usage / cost -----
    def record_llm(self, model: str, in_tok: int, out_tok: int, purpose: str = "") -> float:
        pin, pout = self.pricing.get(model, self.pricing["_default"])
        cost = in_tok / 1_000_000 * pin + out_tok / 1_000_000 * pout
        self.llm_calls.append(
            {
                "model": model,
                "purpose": purpose,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(cost, 6),
                "t": self._rel(),
            }
        )
        return cost

    # ----- browser actions -----
    def record_action(
        self,
        kind: str,
        target: str = "",
        value: str = "",
        path: str = "",
        url: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        a = {
            "i": len(self.actions) + 1,
            "kind": kind,
            "target": target,
            "value": value,
            "path": path,
            "url": url,
            "note": note,
            "t": self._rel(),
        }
        self.actions.append(a)
        return a

    def record_screenshot(self, path: str, caption: str = "", url: str = "") -> None:
        self.screenshots.append(
            {"path": str(path), "caption": caption, "url": url, "t": self._rel()}
        )

    def record_page_state(self, url: str, title: str, note: str = "") -> None:
        self.page_states.append(
            {"url": url, "title": title, "note": note, "t": self._rel()}
        )

    def record_path_decision(
        self, intent: str, attempts: List[Dict[str, Any]], chosen: str, primary: bool = False
    ) -> None:
        self.path_decisions.append(
            {"intent": intent, "attempts": attempts, "chosen": chosen, "primary": primary}
        )

    def set_final(self, **kw: Any) -> None:
        self.final.update(kw)

    def finish(self) -> None:
        self.ended_at = time.time()

    # ----- derived -----
    def headline_path(self) -> str:
        """The single browser path to report -- the most expensive path used on
        a *primary* (critical-path) extraction."""
        primary = [d for d in self.path_decisions if d.get("primary")]
        pool = primary or self.path_decisions
        if not pool:
            return "n/a"
        return max((d["chosen"] for d in pool), key=lambda p: PATH_COST.get(p, 0))

    def paths_exercised(self) -> List[str]:
        seen = []
        for d in self.path_decisions:
            for a in d["attempts"]:
                if a.get("ok") and a["path"] not in seen:
                    seen.append(a["path"])
        return seen

    def totals(self) -> Dict[str, Any]:
        in_tok = sum(c["input_tokens"] for c in self.llm_calls)
        out_tok = sum(c["output_tokens"] for c in self.llm_calls)
        cost = sum(c["cost_usd"] for c in self.llm_calls)
        end = self.ended_at or time.time()
        return {
            "turns": len(self.steps),
            "llm_calls": len(self.llm_calls),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "est_cost_usd": round(cost, 6),
            "browser_actions": len(self.actions),
            "screenshots": len(self.screenshots),
            "duration_sec": round(end - self.started_at, 2),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "plan": self.plan,
            "plan_mermaid": self.plan_mermaid,
            "plan_source": self.plan_source,
            "browser_path": self.headline_path(),
            "paths_exercised": self.paths_exercised(),
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "actions": self.actions,
            "screenshots": self.screenshots,
            "page_states": self.page_states,
            "path_decisions": self.path_decisions,
            "events": self.events,
            "final": self.final,
            "totals": self.totals(),
        }

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, default=str))

    def _rel(self) -> float:
        return round(time.time() - self.started_at, 3)
