#!/usr/bin/env python3
"""Composition root.

Builds the skill catalogue, wires the (frozen) orchestrator, runs the goal, and
writes the deliverables: trace.json, trace.zip, replay.html, report.md, and a
top-level README.md. This file does I/O and wiring only -- no task logic.

    python run.py "Compare the top 3 Hugging Face text-generation models by likes"
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from config import ROOT, Config
from gateway import LLMGateway
from orchestrator import Context, Orchestrator, SkillCatalogue, Trace
from skills import (BrowserSkill, DistillerSkill, PlannerSkill, QASkill,
                    ReportSkill, ResearcherSkill)
from skills.report.render import render_readme, render_replay_html, render_report_md

DEFAULT_GOAL = "Compare the top 3 Hugging Face text-generation models, ranked by likes."


def build_catalogue() -> SkillCatalogue:
    cat = SkillCatalogue()
    for skill in (PlannerSkill(), ResearcherSkill(), BrowserSkill(),
                  DistillerSkill(), QASkill(), ReportSkill()):
        cat.register(skill)
    return cat


def make_gateway(cfg, trace):
    """Real key -> live Anthropic. Else DEMO_MODE -> offline mock gateway. Else
    deterministic (LLM-free). Returns (gateway, mode_key, human_label)."""
    if cfg.api_key:
        return LLMGateway(cfg, trace), "live", f"live Anthropic ({cfg.llm_model})"
    if cfg.demo_mode:
        from gateway.mock_gateway import MockGateway
        trace.log("DEMO MODE: LLM gateway responses are MOCKED offline "
                  "(set ANTHROPIC_API_KEY for live calls).", "warn")
        return MockGateway(cfg, trace), "demo", f"DEMO/mock gateway ({cfg.llm_model}) — offline canned responses"
    gw = LLMGateway(cfg, trace)
    return gw, "off", f"DISABLED — {gw.reason_unavailable} (deterministic mode)"


def main() -> int:
    goal = " ".join(sys.argv[1:]).strip() or DEFAULT_GOAL
    cfg = Config()
    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_dir = ROOT / "artifacts" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    trace = Trace(goal, run_id, pricing=cfg.pricing)
    gateway, llm_mode, llm_label = make_gateway(cfg, trace)
    ctx = Context(goal=goal, config=cfg, gateway=gateway, artifacts_dir=run_dir, run_id=run_id)

    catalogue = build_catalogue()
    ctx.put("catalogue_manifest", catalogue.manifest())

    print(f"▶ goal : {goal}")
    print(f"▶ LLM  : {llm_label}")
    print(f"▶ env  : headless={cfg.headless}  vision_demo={cfg.force_vision_demo and gateway.available}")
    print(f"▶ out  : {run_dir}\n")

    err = None
    try:
        Orchestrator(catalogue).run(ctx, trace)
    except Exception as e:  # keep partial artifacts even on hard failure
        err = e
        trace.log(f"run aborted: {e!r}", "error")

    if trace.ended_at is None:
        trace.finish()
    trace.set_final(llm_mode=llm_mode)

    payload = ctx.get("report") or {
        "goal": goal, "comparison": ctx.get("comparison", {}), "qa": ctx.get("qa", {}),
        "summary": "", "browser_path": trace.headline_path(),
        "paths_exercised": trace.paths_exercised(),
    }
    t = trace.to_dict()
    trace.save(run_dir / "trace.json")
    (run_dir / "replay.html").write_text(render_replay_html(t, payload))
    (run_dir / "report.md").write_text(render_report_md(t, payload))

    latest = ROOT / "artifacts" / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(run_dir, latest)

    body = render_report_md(t, payload, img_prefix="artifacts/latest/screenshots/")
    (ROOT / "README.md").write_text(render_readme(body, t))

    _print_summary(t, payload, run_dir)
    if err:
        raise err
    return 0


def _print_summary(t, payload, run_dir) -> None:
    tot = t["totals"]
    comp = payload.get("comparison", {})
    print("\n" + "=" * 66)
    print(f"PRIMARY BROWSER PATH : {t['browser_path']}   "
          f"(exercised: {', '.join(t.get('paths_exercised', [])) or '—'})")
    print(f"TURNS={tot['turns']}  ACTIONS={tot['browser_actions']}  "
          f"LLM_CALLS={tot['llm_calls']}  TOKENS={tot['total_tokens']:,}  "
          f"COST=${tot['est_cost_usd']:.4f}  TIME={tot['duration_sec']}s")
    print("-" * 66)
    cols = comp.get("columns", [])
    if cols and comp.get("rows"):
        hdr = " | ".join(c["label"] for c in cols)
        print(hdr)
        print("-" * len(hdr))
        for r in comp["rows"]:
            print(" | ".join(str(r.get(c["key"], "")) for c in cols))
    else:
        print("(no comparison rows produced)")
    print("-" * 66)
    print(f"replay : {run_dir / 'replay.html'}")
    print(f"trace  : {run_dir / 'trace.json'}  |  {run_dir / 'trace.zip'}")
    print(f"README : {ROOT / 'README.md'}   (mirror: artifacts/latest/)")
    print("=" * 66)


if __name__ == "__main__":
    sys.exit(main())
