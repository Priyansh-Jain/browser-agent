#!/usr/bin/env python3
"""Composition root for the Computer-Use skill (Session 9 catalogue).

Builds a catalogue of the CU skills, wires the **frozen** orchestrator, runs the
three desktop tasks, and writes the deliverables: trace.json, replay.html,
report.md, and the per-task **trajectory directories** that are the submitted
evidence. This file does wiring + I/O only -- no task logic, no orchestrator edit.

    python run_cu.py
    HEADLESS=0 SLOW_MO=300 python run_cu.py        # visible canvas window for recording
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from config import ROOT, Config
from gateway import LLMGateway
from orchestrator import Context, Orchestrator, SkillCatalogue, Trace
from skills.computer.render_cu import render_cu_html, render_cu_md
from skills.computer_skill import ComputerUseSkill, PlannerCUSkill, ReportCUSkill

DEFAULT_GOAL = ("Solve three real desktop tasks through the five-layer control cascade: "
                "Calculator via hotkeys (zero vision), a canvas game via vision, and a "
                "draft in Cursor over the Electron debug port.")


def build_catalogue() -> SkillCatalogue:
    cat = SkillCatalogue()
    for skill in (PlannerCUSkill(), ComputerUseSkill(), ReportCUSkill()):
        cat.register(skill)
    return cat


def make_gateway(cfg, trace):
    """Real key -> live Anthropic. Otherwise the offline mock gateway, so the
    vision read + text-judge are still exercised end-to-end (zero code change
    when a key is later supplied)."""
    if cfg.api_key:
        return LLMGateway(cfg, trace), "live", f"live Anthropic ({cfg.vision_model})"
    from gateway.mock_gateway import MockGateway
    trace.log("no ANTHROPIC_API_KEY -> offline MOCK gateway (vision/text-judge are mocked).", "warn")
    return MockGateway(cfg, trace), "demo", f"offline MOCK gateway ({cfg.vision_model}) — canned vision/judge"


def main() -> int:
    goal = " ".join(sys.argv[1:]).strip() or DEFAULT_GOAL
    cfg = Config()
    run_id = datetime.now().strftime("cu-run-%Y%m%d-%H%M%S")
    run_dir = ROOT / "artifacts" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    trace = Trace(goal, run_id, pricing=cfg.pricing)
    gateway, llm_mode, llm_label = make_gateway(cfg, trace)
    ctx = Context(goal=goal, config=cfg, gateway=gateway, artifacts_dir=run_dir, run_id=run_id)

    catalogue = build_catalogue()
    ctx.put("catalogue_manifest", catalogue.manifest())

    print(f"▶ goal : {goal}")
    print(f"▶ LLM  : {llm_label}")
    print(f"▶ env  : headless={cfg.headless}  (Calculator & Cursor are always headed GUI apps)")
    print(f"▶ out  : {run_dir}\n")

    err = None
    try:
        Orchestrator(catalogue).run(ctx, trace)
    except Exception as e:  # keep partial artifacts
        err = e
        trace.log(f"run aborted: {e!r}", "error")

    if trace.ended_at is None:
        trace.finish()
    trace.set_final(llm_mode=llm_mode)

    payload = ctx.get("cu_report") or {"goal": goal, "tasks": ctx.get("cu_results", []), "constraints": []}
    t = trace.to_dict()
    trace.save(run_dir / "trace.json")
    (run_dir / "replay.html").write_text(render_cu_html(t, payload))
    (run_dir / "report.md").write_text(render_cu_md(t, payload))

    latest = ROOT / "artifacts" / "cu-latest"
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(run_dir, latest)

    _print_summary(t, payload, run_dir)
    if err:
        raise err
    return 0


def _print_summary(t, payload, run_dir) -> None:
    tot = t["totals"]
    print("\n" + "=" * 70)
    print("COMPUTER-USE RUN SUMMARY")
    print("-" * 70)
    for r in payload.get("tasks", []):
        mark = {"ok": "✅", "blocked": "🚧", "fail": "❌"}.get(r["status"], "?")
        print(f"  {mark} {r['task']:<16} headline={str(r.get('headline_layer')):<7} "
              f"vision_calls={r.get('vision_calls')}  traj={r.get('trajectory_dir')}/")
    print("-" * 70)
    print("CONSTRAINTS:")
    for c in payload.get("constraints", []):
        print(f"  {'✅' if c['ok'] else '❌'} {c['name']}  ({c['detail']})")
    print("-" * 70)
    print(f"TURNS={tot['turns']}  ACTIONS={tot['browser_actions']}  FRAMES={tot['screenshots']}  "
          f"LLM/VISION={tot['llm_calls']}  COST=${tot['est_cost_usd']:.4f}  TIME={tot['duration_sec']}s")
    print(f"replay : {run_dir / 'replay.html'}")
    print(f"report : {run_dir / 'report.md'}")
    print(f"trace  : {run_dir / 'trace.json'}")
    print(f"evidence (trajectories): {run_dir / 'trajectory'}/   (mirror: artifacts/cu-latest/)")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
