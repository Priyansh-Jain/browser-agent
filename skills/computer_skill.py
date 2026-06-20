"""Computer-Use catalogue skills -- the desktop analogue of the Browser skill.

Three skills register into the catalogue (the orchestrator stays frozen):

  * ``computer_use`` -- runs ONE real task through the five-layer cascade and
    records its trajectory directory. Dispatches to a recipe in
    ``skills/computer/tasks/``.
  * ``planner`` -- emits a DAG: one ``computer_use`` node per task + a terminal
    ``report_cu`` node (LLM-authored when a key exists, deterministic otherwise).
  * ``report_cu`` -- assembles the replay payload and verifies the three task
    constraints (>=1 vision, >=1 Electron page path, >=1 zero-vision).
"""
from __future__ import annotations

from typing import Any, Dict, List

from orchestrator.dag import DAG
from orchestrator.errors import SkillError
from orchestrator.skill import Skill

from .computer.cascade import Cascade
from .computer.recorder import Recorder
from .computer.tasks import task_calculator, task_canvas, task_electron


class ComputerUseSkill(Skill):
    name = "computer_use"
    description = (
        "Drive ONE real desktop/app task through the five-layer control cascade "
        "(L1 deterministic → page CDP via electron_debugging_port → L2a hotkeys → "
        "L2b a11y/text-LLM → L3 vision → L4 blocked), recording a trajectory "
        "directory (frames + jsonl + meta). task ∈ {calculator, electron_cursor, canvas_vision}."
    )
    writes = ("cu_results",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        task = params.get("task")
        traj_root = ctx.artifacts_dir / "trajectory"
        recorder = Recorder(trace, traj_root, task or "unknown")
        cascade = Cascade(trace, recorder)

        if task not in ("calculator", "electron_cursor", "canvas_vision"):
            raise SkillError(f"unknown computer-use task {task!r}")
        try:
            if task == "calculator":
                result = task_calculator.run(ctx, trace, recorder, cascade)
            elif task == "electron_cursor":
                result = task_electron.run(ctx, trace, recorder, cascade, port=int(params.get("port", 9223)))
            else:  # canvas_vision
                result = task_canvas.run(ctx, trace, recorder, cascade,
                                         n=str(params.get("n", "7")), tile=int(params.get("tile", 4)))
        except Exception as e:  # noqa: BLE001 - never let one task abort the run before report_cu
            trace.log(f"task {task!r} crashed: {e!r}", "error")
            try:
                recorder.stop_recording(status="error", verdict={"passed": False, "error": repr(e)})
            except Exception:
                pass
            result = {
                "task": task, "title": f"{task} (crashed)", "status": "fail",
                "headline_layer": None, "vision_calls": 0,
                "checks": [{"name": "task ran without error", "ok": False, "detail": repr(e)[:200]}],
                "observations": {"error": repr(e)}, "trajectory_dir": f"trajectory/{task}",
            }

        results: List[dict] = ctx.get("cu_results", [])
        results.append(result)
        ctx.put("cu_results", results)
        return {
            "summary": f"{task}: {result['status']} · headline={result.get('headline_layer')} "
                       f"· vision_calls={result.get('vision_calls')}",
            "status": result["status"],
            "headline_layer": result.get("headline_layer"),
            "vision_calls": result.get("vision_calls"),
        }


def _fallback_plan() -> Dict[str, Any]:
    return {
        "source": "fallback",
        "nodes": [
            {"id": "calc", "skill": "computer_use",
             "title": "Calculator via deterministic hotkeys (L2a · zero vision)",
             "params": {"task": "calculator"}},
            {"id": "canvas", "skill": "computer_use",
             "title": "Canvas game read via vision (forces L3)",
             "params": {"task": "canvas_vision", "n": "7", "tile": 4}},
            {"id": "electron", "skill": "computer_use",
             "title": "Cursor over electron_debugging_port (page path)",
             "params": {"task": "electron_cursor", "port": 9223}},
            {"id": "report", "skill": "report_cu", "title": "Assemble CU replay + verify constraints",
             "params": {}, "deps": ["calc", "canvas", "electron"]},
        ],
        "edges": [],
    }


class PlannerCUSkill(Skill):
    name = "planner"
    description = "Decompose the goal into a DAG of computer_use task nodes + a terminal report_cu node."
    writes = ("plan",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        plan = self._llm_plan(ctx, trace)
        if plan is None:
            plan = _fallback_plan()
            trace.log("planner(cu): using deterministic fallback plan", "info")
        else:
            trace.log("planner(cu): using LLM-generated plan", "info")
        return plan

    def _llm_plan(self, ctx, trace):
        if not getattr(ctx.gateway, "available", False):
            return None
        manifest = ctx.get("catalogue_manifest", [])
        known = {m["name"] for m in manifest}
        cat = "\n".join(f"- {m['name']}: {m['description']}" for m in manifest)
        prompt = (
            f"User goal: {ctx.goal}\n\nAvailable skills (use ONLY these names):\n{cat}\n\n"
            "Produce a DAG that runs three computer_use tasks (calculator, canvas_vision, "
            "electron_cursor) then a terminal report_cu. JSON: "
            '{"nodes":[{"id","skill","title","params","deps"}],"edges":[]}.'
        )
        data = ctx.gateway.json(prompt, purpose="cu:plan")
        if not isinstance(data, dict):
            return None
        try:
            nodes = data.get("nodes")
            assert isinstance(nodes, list) and nodes
            used = {n["skill"] for n in nodes}
            assert {"computer_use", "report_cu"} <= used and used <= known
            DAG.from_dict(data)
        except Exception as e:  # noqa: BLE001
            trace.log(f"planner(cu): LLM plan rejected ({e}); falling back", "warn")
            return None
        data["source"] = "llm"
        return data


class ReportCUSkill(Skill):
    name = "report_cu"
    description = "Assemble the computer-use replay payload and verify the three task constraints."
    reads = ("cu_results",)
    writes = ("cu_report",)

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        tasks: List[dict] = ctx.get("cu_results", [])
        vision_t = next((r for r in tasks if r.get("vision_calls", 0) >= 1), None)
        electron_t = next((r for r in tasks if r.get("headline_layer") == "page"), None)
        zero_t = next((r for r in tasks if r.get("status") == "ok" and r.get("vision_calls", 0) == 0), None)

        constraints = [
            {"name": "≥1 task uses vision (L3)", "ok": vision_t is not None,
             "detail": f"{vision_t['task']}: {vision_t['vision_calls']} vision call(s)" if vision_t else "none"},
            {"name": "≥1 task uses the Electron page path", "ok": electron_t is not None,
             "detail": f"{electron_t['task']}: headline layer = page (CDP via debug port)" if electron_t else "none"},
            {"name": "≥1 task completes with ZERO vision calls", "ok": zero_t is not None,
             "detail": f"{zero_t['task']}: status=ok, vision_calls=0" if zero_t else "none"},
        ]
        n_ok = sum(1 for r in tasks if r.get("status") == "ok")
        all_met = all(c["ok"] for c in constraints)
        payload = {
            "goal": ctx.goal, "tasks": tasks, "constraints": constraints,
            "summary": f"{n_ok}/{len(tasks)} tasks passed; constraints "
                       + ("ALL MET" if all_met else "NOT ALL MET"),
        }
        ctx.put("cu_report", payload)
        trace.set_final(cu_tasks=len(tasks), cu_passed=n_ok, constraints_met=all_met)
        return {"summary": payload["summary"], "constraints_met": all_met}
