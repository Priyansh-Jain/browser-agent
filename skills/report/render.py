"""Render the Trace into the deliverables: replay.html (interactive viewer),
report.md (the 8 required elements, GitHub-rendered), and README.md."""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List

PATH_COLORS = {
    "extract": "#16a34a", "deterministic": "#2563eb", "a11y": "#9333ea",
    "vision": "#e11d48", "blocked": "#dc2626", "skipped": "#6b7280",
    "failed": "#dc2626", "n/a": "#6b7280", "failed ": "#dc2626",
}


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def mesc(s: Any) -> str:
    """Markdown-safe escaping: only the cell separator needs escaping; GitHub
    renders the rest (', &, ->) literally, so don't HTML-escape it."""
    return str(s if s is not None else "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _img(path: str, prefix: str) -> str:
    return prefix + str(path).split("screenshots/")[-1]


def _short_url(u: str) -> str:
    u = (u or "").replace("https://", "").replace("http://", "")
    return u if len(u) <= 70 else u[:67] + "..."


# ============================== Markdown ==============================
def render_report_md(t: Dict[str, Any], report: Dict[str, Any], img_prefix: str = "screenshots/") -> str:
    esc = mesc  # markdown context -> use markdown-safe escaping throughout
    tot = t["totals"]
    comp = report.get("comparison", {})
    qa = report.get("qa", {})
    L: List[str] = []

    L.append("## 1. Original user goal\n")
    L.append(f"> {t['goal']}\n")

    L.append("## 2. Planner DAG\n")
    L.append(f"_Plan produced by: **{t.get('plan_source')}** planner._\n")
    L.append("```mermaid")
    L.append(t.get("plan_mermaid", ""))
    L.append("```\n")

    L.append("## 3. Browser path chosen\n")
    ex = ", ".join(f"`{p}`" for p in t.get("paths_exercised", [])) or "n/a"
    L.append(f"**Primary data path: `{t['browser_path']}`**  ·  all paths exercised this run: {ex}\n")
    L.append("| Intent | Chosen | Cascade ladder (cheapest → costliest) |")
    L.append("|---|---|---|")
    for d in t["path_decisions"]:
        ladder = " · ".join(
            ("✅ " if a["ok"] else "❌ ") + a["path"] + (f" _({a['note']})_" if a.get("note") else "")
            for a in d["attempts"]
        )
        star = " ⭐" if d.get("primary") else ""
        L.append(f"| {esc(d['intent'])}{star} | `{d['chosen']}` | {ladder} |")
    L.append("")

    L.append("## 4. Browser actions taken\n")
    L.append("| # | Action | Path | Target | Detail | URL |")
    L.append("|---|---|---|---|---|---|")
    for a in t["actions"]:
        detail = a.get("value") or a.get("note") or ""
        L.append(
            f"| {a['i']} | {esc(a['kind'])} | {esc(a.get('path', ''))} | "
            f"{esc(a.get('target', ''))} | {esc(detail)} | {esc(_short_url(a.get('url', '')))} |"
        )
    L.append("")

    L.append("## 5. Screenshots & page-state logs\n")
    for s in t["screenshots"]:
        L.append(f"**{esc(s['caption'])}** — `{esc(_short_url(s.get('url', '')))}`\n")
        L.append(f"![{esc(s['caption'])}]({_img(s['path'], img_prefix)})\n")
    L.append("_Page-state log:_\n")
    L.append("| t (s) | URL | Title | Note |")
    L.append("|---|---|---|---|")
    for p in t["page_states"]:
        L.append(f"| {p['t']} | {esc(_short_url(p['url']))} | {esc(p['title'])} | {esc(p['note'])} |")
    L.append("")

    L.append("## 6. Extracted data (raw, per model)\n")
    L.append("```json")
    L.append(json.dumps(t.get("final", {}).get("raw_records", []), indent=2)[:4500])
    L.append("```\n")

    L.append("## 7. Final comparison table\n")
    L.append(_md_table(comp))
    if comp.get("winner"):
        L.append(f"\n**🏆 Most-liked:** {esc(comp['winner'])}")
    if comp.get("notes"):
        L.append(f"\n\n> {esc(comp['notes'])}")
    L.append("")

    L.append("## 8. Turn count & cost summary\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Turns (executed DAG steps) | **{tot['turns']}** |")
    L.append(f"| Browser actions | {tot['browser_actions']} |")
    L.append(f"| Screenshots captured | {tot['screenshots']} |")
    L.append(f"| LLM calls | {tot['llm_calls']} |")
    L.append(f"| Input tokens | {tot['input_tokens']:,} |")
    L.append(f"| Output tokens | {tot['output_tokens']:,} |")
    L.append(f"| **Estimated cost (USD)** | **${tot['est_cost_usd']:.4f}** |")
    L.append(f"| Wall-clock duration | {tot['duration_sec']} s |")
    L.append("")
    if t.get("final", {}).get("llm_mode") == "demo":
        L.append("> ℹ️ _LLM calls in this run used the offline **demo gateway** (mocked responses); "
                 "token counts & cost are estimated from listed model prices. Export "
                 "`ANTHROPIC_API_KEY` to make every call fully live._")
        L.append("")

    L.append("## QA / Critic\n")
    L.append(f"**Verdict: {'✅ PASS' if qa.get('passed') else '⚠️ NEEDS REVIEW'}**\n")
    L.append("| Check | Result | Detail |")
    L.append("|---|---|---|")
    for c in qa.get("checks", []):
        L.append(f"| {esc(c['name'])} | {'✅' if c['ok'] else '❌'} | {esc(c.get('detail', ''))} |")
    if qa.get("critique"):
        L.append(f"\n> {esc(qa['critique'])}")
    return "\n".join(L)


def _md_table(comp: Dict[str, Any]) -> str:
    cols = comp.get("columns", [])
    rows = comp.get("rows", [])
    if not cols:
        return "_no data_"
    head = "| " + " | ".join(c["label"] for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    out = [head, sep]
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c["key"], "")
            if c["key"] == "id" and r.get("url"):
                v = f"[{v}]({r['url']})"
            cells.append(mesc(v) if c["key"] != "id" else v)
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def render_readme(body_md: str, t: Dict[str, Any]) -> str:
    tot = t["totals"]
    return f"""# Browser-Agent — Session 9 (llm_gatewayV9)

A **browser-capable agent** that completes a real comparison task on a dynamic,
JavaScript-rendered website and produces a full **replay view** of the run.

It demonstrates what Session 8's `web_search` + `fetch_url` **cannot** do:
it opens a real Chromium browser and performs visible, multi-step interactions
(filter → sort → scroll → open detail pages) before extracting data via the
**cheapest correct path** (`extract → deterministic → a11y → vision → blocked`).

> **Demo task:** _{esc(t['goal'])}_
> **Primary browser path chosen:** `{t['browser_path']}` · **Turns:** {tot['turns']} ·
> **Browser actions:** {tot['browser_actions']} · **Est. cost:** ${tot['est_cost_usd']:.4f}

---

## 🖥️ Companion: Computer-Use skill (five-layer cascade)

The same catalogue and **frozen orchestrator** now also drive **real desktop apps**.
`run_cu.py` registers three new skills (`planner`, `computer_use`, `report_cu`) and
solves three macOS tasks through a **five-layer control cascade** —
`L1 deterministic → page (Electron CDP) → L2a hotkeys → L2b a11y/text-LLM → L3 vision → L4 blocked` —
recording each run with `start_recording` into a **trajectory directory** (the evidence).

| Task | Headline layer | Vision calls | Constraint |
|---|---|---|---|
| Calculator (`123+654=`) | **L2a** hotkeys | 0 | zero-vision ✅ _(runs live once macOS Accessibility is granted)_ |
| Cursor (Electron) | **page** — CDP over `electron_debugging_port` | 0 | Electron page path ✅ |
| Canvas game (no ARIA) | **L3** vision (set-of-marks) | 1 | uses vision ✅ |

```bash
python run_cu.py          # or: ./demo_cu.sh   (visible run, auto-opens the replay)
```

Per-run evidence lands in `artifacts/cu-latest/` — `replay.html`, `report.md`, `trace.json`,
and `trajectory/<task>/` (ordered `frames/` + `trajectory.jsonl` + `meta.json`).
Full write-up: [`COMPUTER_USE.md`](COMPUTER_USE.md).

---

## What makes this not "passive scraping"

`fetch_url("https://huggingface.co/models")` returns the **default Trending**
listing as static HTML. The data this task needs — *Text-Generation models
ranked by likes, with per-model detail* — only exists **after** you:

1. **filter** the catalogue to the Text-Generation task (click),
2. **sort** it by *Most likes* (open dropdown → click), and
3. **open each top model's detail page** (multi-page navigation).

Those are exactly the ≥3 visible browser actions the rubric requires, and they
change the result set. See the [replay](#sample-run--all-8-required-elements) below.

## Architecture (orchestrator is frozen)

```
User goal
  └─▶ Planner ───────── emits a DAG of skill calls (LLM, with deterministic fallback)
        └─▶ Researcher ── resolves candidate URLs
              └─▶ Browser skill ── interact + "cheapest correct path?"
                     ├ extract        (static / embedded JSON)
                     ├ deterministic  (CSS selectors)
                     ├ a11y           (accessibility tree / ARIA roles)
                     ├ vision         (set-of-marks screenshot)
                     └ blocked        (recover or report)
                    └─▶ Distiller ── normalise into comparison rows
                          └─▶ QA / Critic ── validate (sorted? complete?)
                                └─▶ Replay Viewer ── this report
```

The **orchestrator (`orchestrator/`) is generic and never edited** for a new
task: it only knows how to ask the planner for a DAG and run skills from the
**catalogue**. All task/site behaviour is added as skills — the Browser skill
and its `recipe_hf.py` extension. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Repository layout

| Path | Role |
|---|---|
| `orchestrator/` | **Frozen** engine: DAG executor, catalogue, trace, cost meter |
| `gateway/llm_gateway.py` | Single metered choke-point for all Anthropic calls (graceful no-key fallback) |
| `skills/planner_skill.py` | Emits the plan DAG from the catalogue |
| `skills/researcher_skill.py` | Resolves candidate URLs |
| `skills/browser_skill.py` + `skills/browser/` | **The extension point**: session, path cascade, HF recipe, set-of-marks |
| `skills/distiller_skill.py` / `qa_skill.py` / `report_skill.py` | Normalise → validate → assemble the replay payload |
| `skills/report/render.py` | Renders `replay.html`, `report.md`, this README |
| `run.py` | Composition root: builds the catalogue + runs the orchestrator |
| `skills/computer_skill.py` + `skills/computer/` | **Computer-Use extension**: five-layer cascade, recorder, macOS/Electron/canvas backends, task recipes |
| `run_cu.py` · `demo_cu.sh` · `COMPUTER_USE.md` | Computer-Use composition root, one-command demo, write-up |
| `artifacts/latest/` | Newest run: `replay.html`, `trace.json`, `trace.zip`, `report.md`, `screenshots/` |
| `artifacts/cu-latest/` | Newest **computer-use** run: `replay.html`, `report.md`, `trace.json`, `trajectory/` |

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

**One command for a recordable demo:**

```bash
./demo.sh
```

Opens a **visible** Chromium window, drives the full flow live, and opens the
Replay Viewer with all 8 elements. It uses your `ANTHROPIC_API_KEY` if set
(fully live); otherwise an offline **demo gateway** populates the LLM plan,
vision read, and cost summary so nothing is blank for the recording.

Or run it explicitly:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # optional; LLM-free / demo-gateway without it
HEADLESS=0 SLOW_MO=400 python run.py "Compare the top 3 Hugging Face text-generation models by likes"
```

Outputs land in `artifacts/run-<timestamp>/` and are mirrored to
`artifacts/latest/`. Open `artifacts/latest/replay.html` for the interactive
viewer, or `playwright show-trace artifacts/latest/trace.zip` for Playwright's
own time-travel replay.

---

## Sample run — all 8 required elements

_Auto-generated from the latest run's `trace.json`._

{body_md}
"""


# ============================== HTML viewer ==============================
def render_replay_html(t: Dict[str, Any], report: Dict[str, Any], img_prefix: str = "screenshots/") -> str:
    tot = t["totals"]
    comp = report.get("comparison", {})
    qa = report.get("qa", {})

    def badge(p: str) -> str:
        return f'<span class="badge" style="background:{PATH_COLORS.get(p, "#555")}">{esc(p)}</span>'

    stat_cards = "".join(
        f'<div class="stat"><div class="n">{v}</div><div class="l">{esc(k)}</div></div>'
        for k, v in [
            ("turns", tot["turns"]),
            ("browser actions", tot["browser_actions"]),
            ("screenshots", tot["screenshots"]),
            ("LLM calls", tot["llm_calls"]),
            ("tokens", f"{tot['total_tokens']:,}"),
            ("est. cost", f"${tot['est_cost_usd']:.4f}"),
            ("seconds", tot["duration_sec"]),
        ]
    )

    # path decisions
    pd_rows = ""
    for d in t["path_decisions"]:
        ladder = " ".join(
            f'<span class="lad {"ok" if a["ok"] else "no"}">{esc(a["path"])}</span>'
            + (f'<span class="note">{esc(a["note"])}</span>' if a.get("note") else "")
            for a in d["attempts"]
        )
        star = " ⭐" if d.get("primary") else ""
        pd_rows += f"<tr><td>{esc(d['intent'])}{star}</td><td>{badge(d['chosen'])}</td><td>{ladder}</td></tr>"

    act_rows = "".join(
        f"<tr><td>{a['i']}</td><td><b>{esc(a['kind'])}</b></td><td>{badge(a.get('path','') or 'n/a')}</td>"
        f"<td>{esc(a.get('target',''))}</td><td>{esc(a.get('value') or a.get('note') or '')}</td>"
        f"<td class='u'>{esc(_short_url(a.get('url','')))}</td></tr>"
        for a in t["actions"]
    )

    shots = "".join(
        f'<figure><img src="{esc(_img(s["path"], img_prefix))}" loading="lazy"/>'
        f'<figcaption>{esc(s["caption"])}<br><span class="u">{esc(_short_url(s.get("url","")))}</span></figcaption></figure>'
        for s in t["screenshots"]
    )

    ps_rows = "".join(
        f"<tr><td>{p['t']}</td><td class='u'>{esc(_short_url(p['url']))}</td><td>{esc(p['title'])}</td><td>{esc(p['note'])}</td></tr>"
        for p in t["page_states"]
    )

    # comparison table
    cols = comp.get("columns", [])
    chead = "".join(f"<th>{esc(c['label'])}</th>" for c in cols)
    crows = ""
    for r in comp.get("rows", []):
        tds = ""
        for c in cols:
            v = r.get(c["key"], "")
            if c["key"] == "id" and r.get("url"):
                v = f'<a href="{esc(r["url"])}" target="_blank">{esc(v)}</a>'
            else:
                v = esc(v)
            tds += f"<td>{v}</td>"
        crows += f"<tr>{tds}</tr>"

    qa_rows = "".join(
        f"<tr><td>{esc(c['name'])}</td><td>{'✅' if c['ok'] else '❌'}</td><td>{esc(c.get('detail',''))}</td></tr>"
        for c in qa.get("checks", [])
    )
    qa_verdict = "✅ PASS" if qa.get("passed") else "⚠️ NEEDS REVIEW"

    llm_rows = "".join(
        f"<tr><td>{esc(c['purpose'])}</td><td>{esc(c['model'])}</td><td>{c['input_tokens']}</td>"
        f"<td>{c['output_tokens']}</td><td>${c['cost_usd']:.5f}</td></tr>"
        for c in t["llm_calls"]
    ) or "<tr><td colspan=5><i>No LLM calls (ran in deterministic / LLM-free mode).</i></td></tr>"

    raw_json = esc(json.dumps(t.get("final", {}).get("raw_records", []), indent=2))
    events = "".join(f"<div class='ev {esc(e['level'])}'>[{e['t']}s] {esc(e['msg'])}</div>" for e in t["events"])
    demo_note = ('<p class="sub">ℹ️ LLM calls used the offline <b>demo gateway</b> (mocked responses); '
                 'tokens &amp; cost are estimated from listed prices. Set <code>ANTHROPIC_API_KEY</code> for live calls.</p>'
                 if t.get("final", {}).get("llm_mode") == "demo" else "")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Replay — {esc(t['goal'])[:60]}</title>
<style>
:root{{--bg:#0b1020;--card:#141b30;--mut:#8aa0c6;--bd:#243154;--tx:#e7edf8;--ac:#5b9dff}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial;background:var(--bg);color:var(--tx)}}
.wrap{{max-width:1140px;margin:0 auto;padding:24px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:18px;margin:30px 0 10px;border-bottom:1px solid var(--bd);padding-bottom:6px}}
.goal{{background:var(--card);border:1px solid var(--bd);border-left:4px solid var(--ac);padding:12px 16px;border-radius:10px;margin:10px 0}}
.sub{{color:var(--mut);font-size:13px}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}
.stat{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 16px;min-width:104px;text-align:center}}
.stat .n{{font-size:22px;font-weight:700}}.stat .l{{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden;font-size:13.5px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}}
th{{background:#0f1730;color:var(--mut);text-transform:uppercase;font-size:11px;letter-spacing:.05em}}
tr:last-child td{{border-bottom:none}}.u{{color:var(--mut);font-size:12px;word-break:break-all}}
.badge{{display:inline-block;color:#fff;border-radius:20px;padding:1px 10px;font-size:12px;font-weight:600}}
.lad{{display:inline-block;border-radius:6px;padding:1px 7px;margin:1px;font-size:12px;border:1px solid var(--bd)}}
.lad.ok{{color:#7ef0a6;border-color:#1f6e42}}.lad.no{{color:#ff9b9b;border-color:#6e2020}}
.note{{color:var(--mut);font-size:11px;margin:0 6px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}}
figure{{margin:0;background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}}
figure img{{width:100%;display:block;border-bottom:1px solid var(--bd)}}
figcaption{{padding:8px 10px;font-size:12.5px}}
pre{{background:#0a1226;border:1px solid var(--bd);border-radius:10px;padding:14px;overflow:auto;font-size:12.5px}}
.mermaid{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px}}
.verdict{{font-size:18px;font-weight:700;margin:6px 0}}
.ev{{font:12px/1.5 ui-monospace,Menlo,monospace;color:var(--mut)}}.ev.warn{{color:#ffce7a}}.ev.error{{color:#ff9b9b}}
details{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;margin:8px 0}}
a{{color:var(--ac)}}
</style></head><body><div class="wrap">
<h1>🛰️ Browser-Agent Replay</h1>
<div class="sub">run <code>{esc(t['run_id'])}</code> · plan source <b>{esc(t.get('plan_source'))}</b> · primary path {badge(t['browser_path'])}</div>

<h2>1 · Original user goal</h2>
<div class="goal">{esc(t['goal'])}</div>
<div class="stats">{stat_cards}</div>

<h2>2 · Planner DAG</h2>
<pre class="mermaid">{esc(t.get('plan_mermaid',''))}</pre>

<h2>3 · Browser path chosen — “cheapest correct path?”</h2>
<p>Primary data path: {badge(t['browser_path'])} &nbsp; Paths exercised: {' '.join(badge(p) for p in t.get('paths_exercised',[])) or '—'}</p>
<table><thead><tr><th>Intent</th><th>Chosen</th><th>Cascade ladder (cheap → costly)</th></tr></thead><tbody>{pd_rows}</tbody></table>

<h2>4 · Browser actions taken</h2>
<table><thead><tr><th>#</th><th>Action</th><th>Path</th><th>Target</th><th>Detail</th><th>URL</th></tr></thead><tbody>{act_rows}</tbody></table>

<h2>5 · Screenshots &amp; page-state log</h2>
<div class="gallery">{shots}</div>
<h3 class="sub">page-state log</h3>
<table><thead><tr><th>t(s)</th><th>URL</th><th>Title</th><th>Note</th></tr></thead><tbody>{ps_rows}</tbody></table>

<h2>6 · Extracted data (raw, per model)</h2>
<pre>{raw_json}</pre>

<h2>7 · Final comparison table</h2>
<table><thead><tr>{chead}</tr></thead><tbody>{crows}</tbody></table>
<p class="sub">🏆 {esc(comp.get('winner',''))}<br>{esc(comp.get('notes',''))}</p>

<h2>8 · Turn count &amp; cost summary</h2>
<div class="stats">{stat_cards}</div>
<table><thead><tr><th>Purpose</th><th>Model</th><th>In</th><th>Out</th><th>Cost</th></tr></thead><tbody>{llm_rows}</tbody></table>
{demo_note}

<h2>QA / Critic — verdict: {qa_verdict}</h2>
<table><thead><tr><th>Check</th><th>OK</th><th>Detail</th></tr></thead><tbody>{qa_rows}</tbody></table>
<p class="sub">{esc(qa.get('critique',''))}</p>

<details><summary>Event log ({len(t['events'])})</summary>{events}</details>
<p class="sub" style="margin-top:24px">Generated by browser-agent · llm_gatewayV9 / Session9Code · open <code>trace.zip</code> with <code>playwright show-trace</code> for frame-by-frame replay.</p>
</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{startOnLoad:true, theme:'dark'}});
</script>
</body></html>"""
