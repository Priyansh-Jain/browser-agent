# Architecture note

## 1. Design constraint → design choice

The assignment requires that **the orchestrator must not be modified**; new
behaviour plugs in through the **skill catalogue** or as a **Browser-skill
extension**. The architecture is built around that constraint:

- `orchestrator/` is a **generic, frozen engine**. It knows only how to (1) ask
  the *planner* skill for a DAG, (2) run that DAG's nodes in topological order,
  dispatching each to a skill resolved **by name** from the catalogue, and
  (3) record every turn into the `Trace`. It contains **zero** references to
  browsers, Hugging Face, CSS, or comparison tables. Adding a new task or a new
  site never edits this directory.
- Everything task- or site-specific is a **Skill** in `skills/`. Skills read and
  write a shared **blackboard** (`Context.bb`) rather than being wired together
  by the orchestrator — so the data-flow graph is owned by the *plan*, not the
  engine.

```
run.py (composition root)
  builds Catalogue{planner, researcher, browser, distiller, qa, report}
  └─▶ Orchestrator.run(ctx, trace)        # FROZEN
        planner ─ emits DAG of skill calls (LLM + deterministic fallback)
        for node in topo(DAG):
            catalogue.get(node.skill).run(ctx, trace, **node.params)
```

## 2. The "cheapest correct path?" cascade

The Browser skill (`skills/browser/`) is the extension point. For each
*interaction* or *extraction* it asks the `PathSelector` for the cheapest path
that actually returns valid data, recording the full attempt ladder:

| Path | Mechanism | Cost | Used here for |
|---|---|---|---|
| **extract** | parse static HTML / embedded JSON (`bs4`) | 1 | top-N listing & per-model fields (HF is SSR + embeds `data-props`) |
| **deterministic** | CSS selectors on the live DOM | 2 | clicking the task filter, opening + choosing the sort option |
| **a11y** | ARIA role + accessible name (`get_by_role`) / accessibility tree | 3 | fallback control location; cross-check of the like count |
| **vision** | set-of-marks screenshot → vision model | 4 | fallback / labelled capability demo (reads likes from the overlay) |
| **blocked** | detect 401/403/407/429/503 + bot-wall markers → recover or report | 5 | resilience; raises `GatewayBlocked`, orchestrator marks the step |

Cheapest-correct means the cascade stops at the first path that yields valid
data. On Hugging Face that is usually `extract`, **but the data only becomes the
*right* data after the visible browser interactions** (filter → sort → open each
detail page). That is precisely what `web_search`/`fetch_url` cannot do: a plain
fetch of `/models` returns the default *Trending* listing, not *Text-Generation
ranked by likes with per-model detail*.

Adding another site = add another recipe (e.g. `recipe_amazon.py`) implementing
the same per-intent hooks. The cascade, the session, the orchestrator, and the
reporting are all reused unchanged.

## 3. Single metered LLM gateway

All model calls go through `gateway/llm_gateway.py`. It (a) meters token usage
straight into the `Trace` for the cost summary, (b) is provider-swappable, and
(c) **degrades gracefully**: with no `ANTHROPIC_API_KEY` every method returns
`None` and each skill falls back to a deterministic path (rule-based planner,
rule-based distiller/QA, vision overlay built but not read). So the pipeline
runs end-to-end with or without a key.

## 4. Trace = single source of truth

`orchestrator/trace.py` accumulates the plan, every step (turn), every browser
action, every screenshot/page-state, every path decision, and every LLM call
(with tokens → estimated USD via a configurable pricing table). `report` +
`skills/report/render.py` turn it into the three deliverables. The eight
required report elements map directly onto trace fields:

| # | Required element | Source |
|---|---|---|
| 1 | Original user goal | `trace.goal` |
| 2 | Planner DAG | `trace.plan` → Mermaid |
| 3 | Browser path chosen | `trace.headline_path()` + `path_decisions` |
| 4 | Browser actions taken | `trace.actions` |
| 5 | Screenshots / page-state logs | `trace.screenshots`, `trace.page_states` |
| 6 | Extracted data | `trace.final.raw_records` |
| 7 | Final comparison table | `comparison` (Distiller) |
| 8 | Turn count & cost summary | `trace.totals()` |

## 5. Outputs

Per run, written to `artifacts/run-<ts>/` and mirrored to `artifacts/latest/`:

- `replay.html` — self-contained interactive **Replay Viewer** (all 8 elements).
- `report.md` — the same, GitHub-rendered (Mermaid DAG + embedded screenshots).
- `trace.json` — the full structured trace/log.
- `trace.zip` — Playwright's own trace; open with `playwright show-trace` for
  frame-by-frame time-travel replay.
- `screenshots/` — page-state captures incl. the set-of-marks vision overlay.

`README.md` is regenerated from the latest run so it always shows a real run.
