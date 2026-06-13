"""Report skill == the Replay Viewer.

Gathers all 8 required elements into a single payload and renders a first draft
of replay.html + report.md. (run.py re-renders after the trace is finalised so
the committed artifacts include final totals.)"""
from __future__ import annotations

from typing import Any, Dict

from orchestrator.skill import Skill
from skills.report.render import render_replay_html, render_report_md


class ReportSkill(Skill):
    name = "report"
    description = "Assemble the replay payload (all 8 elements) and render the replay viewer."
    reads = ("comparison", "qa", "raw_records", "browser_path")
    writes = ("report",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        comparison = ctx.get("comparison", {})
        qa = ctx.get("qa", {})
        payload = {
            "goal": ctx.goal,
            "comparison": comparison,
            "qa": qa,
            "summary": comparison.get("notes", ""),
            "browser_path": ctx.get("browser_path", trace.headline_path()),
            "paths_exercised": trace.paths_exercised(),
        }
        if "raw_records" not in trace.final:
            trace.set_final(raw_records=ctx.get("raw_records") or [])
        trace.set_final(comparison=comparison, qa=qa)
        ctx.put("report", payload)

        try:
            t = trace.to_dict()
            (ctx.artifacts_dir / "replay.html").write_text(render_replay_html(t, payload))
            (ctx.artifacts_dir / "report.md").write_text(render_report_md(t, payload))
        except Exception as e:  # pragma: no cover
            trace.log(f"draft render failed: {e!r}", "warn")

        return {"summary": f"replay payload assembled ({len(comparison.get('rows', []))} rows, 8 sections)"}
