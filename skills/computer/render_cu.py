"""Render the computer-use Trace into the deliverables: a CU replay.html and
report.md. Mirrors skills/report/render.py but speaks the five-layer cascade
(and points at the trajectory directories that are the submitted evidence)."""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List

from .layers import LAYER_COST, LAYER_LABEL

LAYER_COLORS = {
    "L1": "#16a34a", "page": "#0ea5e9", "L2a": "#2563eb", "L2b-ax": "#9333ea",
    "L2b-llm": "#a855f7", "L3": "#e11d48", "L4": "#dc2626",
    "blocked": "#dc2626", "failed": "#dc2626", "n/a": "#6b7280",
}
_OK = {True: "✅", False: "❌", None: "⏭️"}


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


def mesc(s: Any) -> str:
    return str(s if s is not None else "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _layer_chip(p: str) -> str:
    return f'<span class="badge" style="background:{LAYER_COLORS.get(p, "#555")}">{esc(p)}</span>'


# ============================== Markdown ==============================
def render_cu_md(t: Dict[str, Any], payload: Dict[str, Any]) -> str:
    e = mesc
    tot = t["totals"]
    L: List[str] = []

    L.append("## 1. Goal\n")
    L.append(f"> {e(t['goal'])}\n")

    L.append("## 2. Plan (DAG of catalogue skills)\n")
    L.append(f"_Plan source: **{t.get('plan_source')}**._\n")
    L.append("```mermaid")
    L.append(t.get("plan_mermaid", ""))
    L.append("```\n")

    L.append("## 3. Constraint satisfaction\n")
    L.append("| Constraint | Status | Evidence |")
    L.append("|---|---|---|")
    for c in payload.get("constraints", []):
        L.append(f"| {e(c['name'])} | {'✅' if c['ok'] else '❌'} | {e(c['detail'])} |")
    L.append("")

    L.append("## 4. Five-layer cascade — per-intent ladder\n")
    L.append("Legend (cheapest → costliest): " +
             " · ".join(f"`{k}`={LAYER_COST[k]}" for k in ("L1", "page", "L2a", "L2b-ax", "L3", "L4")) + "\n")
    L.append("| Task-intent | Chosen | Ladder tried (✅ ok · ❌ failed · ⏭️ not reached) |")
    L.append("|---|---|---|")
    for d in t["path_decisions"]:
        ladder = " · ".join(
            f"{_OK.get(a['ok'])} {a['layer']}" + (f" _({a['note']})_" if a.get("note") else "")
            for a in d["attempts"]
        )
        star = " ⭐" if d.get("primary") else ""
        L.append(f"| {e(d['intent'])}{star} | `{d['chosen']}` | {ladder} |")
    L.append("")

    L.append("## 5. Actions taken\n")
    L.append("| # | Action | Layer | Target/Intent | Detail |")
    L.append("|---|---|---|---|---|")
    for a in t["actions"]:
        L.append(f"| {a['i']} | {e(a['kind'])} | {e(a.get('path', ''))} | "
                 f"{e(a.get('target', ''))} | {e(a.get('value', ''))} |")
    L.append("")

    L.append("## 6. Per-task verification\n")
    for r in payload.get("tasks", []):
        v = "✅ PASS" if r["status"] == "ok" else ("🚧 BLOCKED" if r["status"] == "blocked" else "❌ FAIL")
        L.append(f"### {e(r['task'])} — {v}")
        L.append(f"_{e(r['title'])}_\n")
        L.append(f"- headline layer: `{r.get('headline_layer')}` · vision calls: **{r.get('vision_calls')}** "
                 f"· trajectory: `{r.get('trajectory_dir')}/`\n")
        L.append("| Check | Result | Detail |")
        L.append("|---|---|---|")
        for c in r.get("checks", []):
            L.append(f"| {e(c['name'])} | {'✅' if c['ok'] else '❌'} | {e(c.get('detail', ''))} |")
        L.append("")

    L.append("## 7. Trajectory frames\n")
    for s in t["screenshots"]:
        L.append(f"**{e(s['caption'])}**\n")
        L.append(f"![{e(s['caption'])}]({s['path']})\n")

    L.append("## 8. Turns & cost\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Turns (DAG steps) | **{tot['turns']}** |")
    L.append(f"| Actions | {tot['browser_actions']} |")
    L.append(f"| Trajectory frames | {tot['screenshots']} |")
    L.append(f"| LLM / vision calls | {tot['llm_calls']} |")
    L.append(f"| Est. cost (USD) | ${tot['est_cost_usd']:.4f} |")
    L.append(f"| Wall-clock | {tot['duration_sec']} s |")
    if t.get("final", {}).get("llm_mode") == "demo":
        L.append("\n> ℹ️ Vision / text-judge calls used the offline **demo gateway** (mocked). "
                 "Set `ANTHROPIC_API_KEY` to make every call live with zero code changes.")
    return "\n".join(L)


# ============================== HTML ==============================
def render_cu_html(t: Dict[str, Any], payload: Dict[str, Any]) -> str:
    tot = t["totals"]
    stat_cards = "".join(
        f'<div class="stat"><div class="n">{v}</div><div class="l">{esc(k)}</div></div>'
        for k, v in [("turns", tot["turns"]), ("actions", tot["browser_actions"]),
                     ("frames", tot["screenshots"]), ("LLM/vision", tot["llm_calls"]),
                     ("cost", f"${tot['est_cost_usd']:.4f}"), ("seconds", tot["duration_sec"])]
    )
    cons = "".join(
        f"<tr><td>{esc(c['name'])}</td><td>{'✅' if c['ok'] else '❌'}</td><td class='u'>{esc(c['detail'])}</td></tr>"
        for c in payload.get("constraints", [])
    )
    pd_rows = ""
    for d in t["path_decisions"]:
        ladder = " ".join(
            f'<span class="lad {("ok" if a["ok"] else ("no" if a["ok"] is False else "skip"))}">'
            f'{_OK.get(a["ok"])} {esc(a["layer"])}</span>'
            + (f'<span class="note">{esc(a["note"])}</span>' if a.get("note") else "")
            for a in d["attempts"]
        )
        star = " ⭐" if d.get("primary") else ""
        pd_rows += f"<tr><td>{esc(d['intent'])}{star}</td><td>{_layer_chip(d['chosen'])}</td><td>{ladder}</td></tr>"

    act_rows = "".join(
        f"<tr><td>{a['i']}</td><td><b>{esc(a['kind'])}</b></td><td>{_layer_chip(a.get('path','') or 'n/a')}</td>"
        f"<td>{esc(a.get('target',''))}</td><td>{esc(a.get('value',''))}</td></tr>"
        for a in t["actions"]
    )

    tasks_html = ""
    for r in payload.get("tasks", []):
        verdict = "✅ PASS" if r["status"] == "ok" else ("🚧 BLOCKED" if r["status"] == "blocked" else "❌ FAIL")
        checks = "".join(
            f"<tr><td>{esc(c['name'])}</td><td>{'✅' if c['ok'] else '❌'}</td><td class='u'>{esc(c.get('detail',''))}</td></tr>"
            for c in r.get("checks", [])
        )
        tasks_html += (
            f"<h3>{esc(r['task'])} — {verdict}</h3>"
            f"<p class='sub'>{esc(r['title'])}<br>headline layer {_layer_chip(r.get('headline_layer') or 'n/a')} · "
            f"vision calls <b>{r.get('vision_calls')}</b> · trajectory <code>{esc(r.get('trajectory_dir'))}/</code></p>"
            f"<table><thead><tr><th>Check</th><th>OK</th><th>Detail</th></tr></thead><tbody>{checks}</tbody></table>"
        )

    shots = "".join(
        f'<figure><img src="{esc(s["path"])}" loading="lazy"/><figcaption>{esc(s["caption"])}</figcaption></figure>'
        for s in t["screenshots"]
    )
    events = "".join(f"<div class='ev {esc(e['level'])}'>[{e['t']}s] {esc(e['msg'])}</div>" for e in t["events"])
    demo_note = ('<p class="sub">ℹ️ Vision / text-judge calls used the offline <b>demo gateway</b> (mocked); '
                 'set <code>ANTHROPIC_API_KEY</code> for live calls.</p>'
                 if t.get("final", {}).get("llm_mode") == "demo" else "")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Computer-Use Replay — {esc(t['goal'])[:60]}</title>
<style>
:root{{--bg:#0b1020;--card:#141b30;--mut:#8aa0c6;--bd:#243154;--tx:#e7edf8;--ac:#5b9dff}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.55 -apple-system,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--tx)}}
.wrap{{max-width:1140px;margin:0 auto;padding:24px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:18px;margin:30px 0 10px;border-bottom:1px solid var(--bd);padding-bottom:6px}}
h3{{margin:18px 0 6px}}.goal{{background:var(--card);border:1px solid var(--bd);border-left:4px solid var(--ac);padding:12px 16px;border-radius:10px;margin:10px 0}}
.sub{{color:var(--mut);font-size:13px}}
.stats{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}
.stat{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 16px;min-width:104px;text-align:center}}
.stat .n{{font-size:22px;font-weight:700}}.stat .l{{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden;font-size:13.5px;margin:6px 0}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}}
th{{background:#0f1730;color:var(--mut);text-transform:uppercase;font-size:11px;letter-spacing:.05em}}
tr:last-child td{{border-bottom:none}}.u{{color:var(--mut);font-size:12px}}
.badge{{display:inline-block;color:#fff;border-radius:20px;padding:1px 10px;font-size:12px;font-weight:600}}
.lad{{display:inline-block;border-radius:6px;padding:1px 7px;margin:1px;font-size:12px;border:1px solid var(--bd)}}
.lad.ok{{color:#7ef0a6;border-color:#1f6e42}}.lad.no{{color:#ff9b9b;border-color:#6e2020}}.lad.skip{{color:#9fb0d6;border-color:#33406b}}
.note{{color:var(--mut);font-size:11px;margin:0 6px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}}
figure{{margin:0;background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}}
figure img{{width:100%;display:block;border-bottom:1px solid var(--bd)}}figcaption{{padding:8px 10px;font-size:12.5px}}
.mermaid{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px}}
.ev{{font:12px/1.5 ui-monospace,Menlo,monospace;color:var(--mut)}}.ev.warn{{color:#ffce7a}}.ev.error{{color:#ff9b9b}}
details{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;margin:8px 0}}
code{{background:#0a1226;border:1px solid var(--bd);border-radius:5px;padding:1px 5px;font-size:12.5px}}a{{color:var(--ac)}}
</style></head><body><div class="wrap">
<h1>🖥️ Computer-Use Replay</h1>
<div class="sub">run <code>{esc(t['run_id'])}</code> · plan <b>{esc(t.get('plan_source'))}</b> · five-layer cascade: L1 → page → L2a → L2b → L3 → L4</div>
<div class="stats">{stat_cards}</div>

<h2>1 · Goal</h2><div class="goal">{esc(t['goal'])}</div>

<h2>2 · Plan (DAG of catalogue skills)</h2>
<pre class="mermaid">{esc(t.get('plan_mermaid',''))}</pre>

<h2>3 · Constraint satisfaction</h2>
<table><thead><tr><th>Constraint</th><th>OK</th><th>Evidence</th></tr></thead><tbody>{cons}</tbody></table>

<h2>4 · Five-layer cascade — per-intent ladder</h2>
<table><thead><tr><th>Task-intent</th><th>Chosen</th><th>Ladder (✅ ok · ❌ failed · ⏭️ not reached)</th></tr></thead><tbody>{pd_rows}</tbody></table>

<h2>5 · Actions taken</h2>
<table><thead><tr><th>#</th><th>Action</th><th>Layer</th><th>Target/Intent</th><th>Detail</th></tr></thead><tbody>{act_rows}</tbody></table>

<h2>6 · Per-task verification</h2>{tasks_html}

<h2>7 · Trajectory frames</h2><div class="gallery">{shots}</div>

<h2>8 · Turns &amp; cost</h2><div class="stats">{stat_cards}</div>{demo_note}

<details><summary>Event log ({len(t['events'])})</summary>{events}</details>
<p class="sub" style="margin-top:24px">Computer-Use skill · five-layer cascade · trajectory directories under <code>trajectory/</code> are the submitted evidence.</p>
</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{startOnLoad:true, theme:'dark'}});
</script>
</body></html>"""
