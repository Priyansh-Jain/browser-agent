"""Offline DEMO gateway.

A drop-in stand-in for LLMGateway used when DEMO_MODE=1 and no real
ANTHROPIC_API_KEY is set. It returns sensible, data-aware canned responses so a
single command lights up every element of the report -- an LLM-authored plan, a
distiller/QA narrative, and a working vision read -- with realistic token/cost
accounting. It is clearly a mock (see the warning logged at startup); supply a
real key and the live LLMGateway is used instead with zero code changes.
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional


def _json_in(text: str):
    i, j = text.find("["), text.rfind("]")
    if 0 <= i < j:
        try:
            return json.loads(text[i:j + 1])
        except Exception:
            return None
    return None


class MockGateway:
    available = True

    def __init__(self, config: Any, trace: Any = None) -> None:
        self.config = config
        self.trace = trace
        self.model = config.llm_model
        self.vision_model = config.vision_model
        self.reason_unavailable = ""
        self.next_vision_likes: Optional[Any] = None  # set by the Browser skill

    # ---- usage metering (so the cost summary is non-zero + realistic) ----
    def _meter(self, prompt_len: int, reply: str, purpose: str, image: bool = False) -> None:
        if not self.trace:
            return
        in_tok = max(60, prompt_len // 4) + (1100 if image else 0)
        out_tok = max(20, len(reply) // 4)
        self.trace.record_llm(self.model if not image else self.vision_model,
                              in_tok, out_tok, purpose + " (demo)")

    # ---- planner ----
    def json(self, prompt: str, system: str = "", purpose: str = "", **kw: Any):
        if "plan" in purpose:
            plan = {
                "nodes": [
                    {"id": "research", "skill": "researcher", "title": "Resolve candidate URLs"},
                    {"id": "browse", "skill": "browser",
                     "title": "Interact (filter/sort/open) + extract via cheapest path",
                     "params": {}, "deps": ["research"]},
                    {"id": "distill", "skill": "distiller", "title": "Normalise into comparison rows",
                     "deps": ["browse"]},
                    {"id": "qa", "skill": "qa", "title": "Validate (complete? ranked? correct task?)",
                     "deps": ["distill"]},
                    {"id": "report", "skill": "report", "title": "Assemble replay viewer",
                     "deps": ["qa"]},
                ],
                "edges": [],
            }
            self._meter(len(prompt), json.dumps(plan), "plan")
            return plan
        self._meter(len(prompt), "{}", purpose)
        return {}

    # ---- text completions ----
    def complete(self, prompt: str, system: str = "", purpose: str = "", **kw: Any) -> str:
        text = self._reply_for(purpose, prompt)
        self._meter(len(prompt), text, purpose)
        return text

    def _reply_for(self, purpose: str, prompt: str) -> str:
        if purpose.startswith("research"):
            return ("Hugging Face's Models hub is the authoritative, JavaScript-rendered catalogue "
                    "for this task; the ranking only exists after we apply the Text Generation task "
                    "filter and sort by Most likes through the UI, then open each model page.")
        if purpose.startswith("distill"):
            data = _json_in(prompt)
            if isinstance(data, list) and data:
                ids = [d.get("id") for d in data]
                lics = sorted({str(d.get("license")) for d in data if d.get("license")})
                return (f"{data[0].get('id')} is the clear community favourite with "
                        f"{data[0].get('likes')} likes, ahead of {', '.join(ids[1:]) or 'the field'}. "
                        f"The shortlist spans {data[-1].get('params')}–{data[0].get('params')} "
                        f"parameters across {', '.join(lics) or 'varied'} licenses, so the most-liked "
                        f"model is not necessarily the smallest or most-downloaded.")
            return ("The most-liked model leads on community popularity, while the others trade off "
                    "on monthly downloads and parameter size.")
        if purpose.startswith("qa"):
            return ("All structural checks pass: the requested number of text-generation models were "
                    "collected, correctly ranked by descending likes, with cross-path agreement "
                    "between the static-extract and accessibility readings. The comparison is "
                    "trustworthy for ranking by popularity.")
        return ""

    # ---- vision (set-of-marks read) ----
    def vision(self, prompt: str, image_path: str, system: str = "", purpose: str = "vision", **kw: Any) -> str:
        # choose a plausible mark (one whose text contains a number), and report
        # the likes value the caller already established from the page.
        mark = 0
        for line in prompt.splitlines():
            m = re.match(r"\s*\[(\d+)\]\s*(.*)", line)
            if m and re.search(r"\d", m.group(2)):
                mark = int(m.group(1))
                break
        likes = self.next_vision_likes
        if likes is None:
            m = re.search(r"([\d.,]+\s*[kKmM]?)", prompt)
            likes = m.group(1).strip() if m else "unknown"
        reply = json.dumps({"mark": mark, "likes": str(likes)})
        self._meter(len(prompt), reply, "vision:likes", image=True)
        return reply
