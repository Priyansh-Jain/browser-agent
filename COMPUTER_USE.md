# Computer-Use skill — Session 9 catalogue

The desktop-control sibling of the Browser skill. It drives **three real tasks on
macOS** through a **five-layer control cascade**, applying the same
"cheapest-correct-path" discipline the Browser skill uses for data extraction —
only here the ladder is about *control*, not scraping. Every run is recorded with
`start_recording` into a **trajectory directory** that is the submitted evidence.

It plugs into the **same frozen orchestrator**: `run_cu.py` registers three new
skills into a `SkillCatalogue` and runs them through the unchanged
`orchestrator/` engine. Nothing under `orchestrator/` was edited.

```
run_cu.py (composition root)
  builds Catalogue{planner(cu), computer_use, report_cu}
  └─▶ Orchestrator.run(ctx, trace)            # FROZEN — identical to the browser path
        planner ─ emits a DAG: one computer_use node per task + report_cu
        for node in topo(DAG):
            computer_use.run(task=…)  ──▶  Cascade + Recorder  ──▶  trajectory/<task>/
```

## The five-layer cascade (cheapest → costliest)

For every *intent* (an interaction or a read) the `Cascade` tries layers in cost
order and stops at the first that works, recording the **full ladder** — including
the rungs it never had to reach, so the replay shows *why* (e.g.) vision was
unnecessary. See `skills/computer/layers.py` + `cascade.py`.

| Layer | Mechanism | Used by |
|---|---|---|
| **L1** deterministic | app lifecycle / menus / AppleScript verbs (`osascript`) | launch & focus, deterministic clicks |
| **page** | Electron CDP DOM over `electron_debugging_port` (Playwright `connect_over_cdp`) | the whole Cursor task |
| **L2a** hotkeys | deterministic keystrokes — System Events (native) or CDP keyboard (Electron) | Calculator arithmetic |
| **L2b** a11y + text-LLM | accessibility tree / DOM text read, plus a *cheap text* judge | verification / cross-checks |
| **L3** vision | set-of-marks screenshot → vision model | the canvas game (no ARIA) |
| **L4** blocked | permission denied / element absent → record + escalate | graceful degrade |

## The three tasks (and the constraints they satisfy)

| Task | Headline layer | Vision calls | Constraint satisfied |
|---|---|---|---|
| **Calculator** (`task_calculator.py`) | **L2a** hotkeys | **0** | *zero-vision* task ✅ |
| **Cursor / Electron** (`task_electron.py`) | **page** (CDP) | **0** | *Electron page path* ✅ (and zero-vision) |
| **Canvas game** (`task_canvas.py`) | **L3** vision | **1** | *uses vision* ✅ |

- **Calculator** — launches Calculator (L1), types `123+654=` via deterministic
  keystrokes (L2a), then reads the result the cheapest way that works (clipboard
  copy) and cross-checks it against the accessibility tree (L2b). The vision rung
  (L3) is in the ladder but **never reached** — "zero vision" is *measured* (a
  counter), not merely asserted.
- **Cursor / Electron** — launches Cursor with `--remote-debugging-port` into a
  throwaway profile, attaches Playwright over CDP (the **page** path), composes a
  multi-line draft in an **untitled** buffer (no file saved → zero side effects),
  then verifies strongly: reads every Monaco `.view-line` back from the DOM and
  requires exact line-by-line agreement (L2b), plus a cheap text-LLM judge.
- **Canvas game** — opens a local `<canvas>` whose number exists only as pixels.
  The cheap L2b DOM/AX read provably returns nothing, so the cascade **escalates
  to L3 vision** (set-of-marks → vision model). The model's read drives the
  click, and the puzzle only reports `solved` when the *vision-identified* tile is
  the one bearing the number — so a pass is genuine evidence the read was right.

## Run it

```bash
source .venv/bin/activate            # playwright + PIL already installed
python run_cu.py                     # headless canvas; Calculator & Cursor are GUI apps
# or, visible + auto-open the replay viewer (good for screen-recording):
./demo_cu.sh
```

- **No `ANTHROPIC_API_KEY`?** The run uses the repo's offline **mock gateway**, so
  the vision read and text-judge are still exercised end-to-end (canned). Export a
  key and every call goes live with **zero code changes** (same pattern as the
  browser demo).
- **Calculator needs macOS Accessibility.** Synthetic keystrokes and AX reads are
  gated by **System Settings → Privacy & Security → Accessibility**. Grant it to
  the terminal / host app running this, and Calculator runs live; without it the
  task records a clean **L4 blocked** trajectory with remediation (the other two
  tasks need no special permission).

## Evidence: the trajectory directory

Per run, written to `artifacts/cu-run-<ts>/` and mirrored to `artifacts/cu-latest/`:

```
artifacts/cu-latest/
  replay.html          # interactive replay: cascade ladder, actions, frames, verdicts
  report.md            # same, GitHub-rendered
  trace.json           # full unified trace (single source of truth)
  trajectory/<task>/
    frames/0001_*.png  # one ordered frame per observable step (+ the set-of-marks overlay)
    trajectory.jsonl   # one JSON line per frame / cascade decision / action
    meta.json          # task, status, layers_used, verification verdict
```

## Files

| Path | Role |
|---|---|
| `skills/computer/layers.py` | the five-layer vocabulary + cost ladder |
| `skills/computer/cascade.py` | cheapest-correct cascade; records the ladder per intent |
| `skills/computer/recorder.py` | `start_recording` / `stop_recording` → the trajectory directory |
| `skills/computer/macos.py` | native backend (`osascript`): L1 verbs, L2a keystrokes, L2b AX reads |
| `skills/computer/electron.py` | the **page** path: launch + `connect_over_cdp` + DOM verbs |
| `skills/computer/canvasgame.py` + `assets/canvas_game.html` | the no-ARIA vision target |
| `skills/computer/vision.py` | set-of-marks overlay from explicit box geometry |
| `skills/computer/tasks/*.py` | the three task recipes |
| `skills/computer/render_cu.py` | renders `replay.html` + `report.md` |
| `skills/computer_skill.py` | the catalogue skills: `computer_use`, `planner`, `report_cu` |
| `run_cu.py` / `demo_cu.sh` | composition root + one-command demo |
