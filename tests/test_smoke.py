"""Offline smoke tests -- no network, no LLM. Run: python tests/test_smoke.py

Covers the deterministic core (DAG, trace/cost, HF parsers, planner fallback,
distiller -> QA -> report). The live browser interaction is covered by an actual
run (see README) and by tests/probe_hf*.py.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from gateway import LLMGateway
from orchestrator import Context, Trace
from orchestrator.dag import DAG
from skills import DistillerSkill, PlannerSkill, QASkill, ReportSkill
from skills.browser.recipe_hf import HFRecipe
from skills.report.render import render_replay_html, render_report_md


def make_ctx(goal="Compare the top 3 Hugging Face text-generation models by likes"):
    cfg = Config()
    cfg.api_key = ""  # force LLM-free, deterministic
    run_dir = Path(tempfile.mkdtemp(prefix="ba_test_"))
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    trace = Trace(goal, "test", pricing=cfg.pricing)
    gw = LLMGateway(cfg, trace)
    ctx = Context(goal=goal, config=cfg, gateway=gw, artifacts_dir=run_dir, run_id="test")
    return cfg, gw, trace, ctx


def test_dag_topo_and_cycle():
    plan = {"nodes": [{"id": "a", "skill": "x"},
                      {"id": "b", "skill": "y", "deps": ["a"]},
                      {"id": "c", "skill": "z", "deps": ["b"]}], "edges": []}
    order = [n.id for n in DAG.from_dict(plan).topo_order()]
    assert order == ["a", "b", "c"], order
    try:
        DAG.from_dict({"nodes": [{"id": "a", "skill": "x", "deps": ["b"]},
                                 {"id": "b", "skill": "y", "deps": ["a"]}]})
        assert False, "cycle not detected"
    except ValueError:
        pass


def test_trace_cost():
    t = Trace("g", "r", pricing={"m": (10.0, 30.0), "_default": (1, 1)})
    t.record_llm("m", 1_000_000, 1_000_000, "x")
    tot = t.totals()
    assert abs(tot["est_cost_usd"] - 40.0) < 1e-6, tot
    assert tot["llm_calls"] == 1 and tot["total_tokens"] == 2_000_000, tot


def test_listing_parse():
    cfg, *_ = make_ctx()
    html = """<html><body>
      <article><a href="/orgA/Model-One"><h4>orgA/Model-One</h4> Text Generation • 7B</a></article>
      <article><a href="/orgB/Model-Two"><h4>orgB/Model-Two</h4> Text Generation • 13B</a></article>
      <article><a href="/login">Sign in</a></article>
    </body></html>"""
    rows = HFRecipe(cfg).parse_listing_static(html, top_n=5)
    ids = [r["id"] for r in rows]
    assert ids == ["orgA/Model-One", "orgB/Model-Two"], ids
    assert rows[0]["rank"] == 1 and rows[0]["url"].endswith("/orgA/Model-One")


def test_model_parse():
    cfg, *_ = make_ctx()
    props = ('{"model": {"id":"orgA/Model-One","likes":9876,"downloads":1234567,'
             '"downloadsAllTime":9999999,"pipeline_tag":"text-generation",'
             '"library_name":"transformers","lastModified":"2025-01-01T00:00:00.000Z",'
             '"createdAt":"2024-12-01T00:00:00.000Z","cardData":{"license":"apache-2.0"},'
             '"safetensors":{"total":7000000000},"tags":["transformers","license:apache-2.0"]}}')
    html = f"<html><body><div data-target='ModelHeader' data-props='{props}'></div></body></html>"
    m = HFRecipe(cfg).parse_model_static(html)
    assert m and m["likes"] == 9876, m
    assert m["downloads_last_month"] == 1234567
    assert m["params"] == "7.0B", m["params"]
    assert m["license"] == "apache-2.0"
    assert m["pipeline_tag"] == "text-generation"
    assert m["last_modified"] == "2025-01-01"


def test_planner_fallback():
    cfg, gw, trace, ctx = make_ctx()
    ctx.put("catalogue_manifest", [{"name": n, "description": ""}
            for n in ("planner", "researcher", "browser", "distiller", "qa", "report")])
    plan = PlannerSkill().run(ctx, trace, goal=ctx.goal)
    assert plan["source"] == "fallback"
    DAG.from_dict(plan)  # must be a valid, acyclic DAG
    used = {n["skill"] for n in plan["nodes"]}
    assert {"browser", "report"} <= used, used
    bn = next(n for n in plan["nodes"] if n["skill"] == "browser")
    assert bn["params"].get("top_n") == cfg.top_n


def test_pipeline_offline():
    cfg, gw, trace, ctx = make_ctx()
    recs = [
        {"rank": 1, "id": "a/x", "url": "https://h/a/x", "likes": 1000, "downloads_last_month": 2_000_000,
         "params": "7B", "license": "mit", "pipeline_tag": "text-generation", "last_modified": "2025-01-01",
         "likes_a11y": 1000, "likes_vision": "1k"},
        {"rank": 2, "id": "b/y", "url": "https://h/b/y", "likes": 500, "downloads_last_month": 50_000,
         "params": "13B", "license": "apache-2.0", "pipeline_tag": "text-generation", "last_modified": "2025-02-01"},
        {"rank": 3, "id": "c/z", "url": "https://h/c/z", "likes": 100, "downloads_last_month": 1000,
         "params": "3B", "license": "other", "pipeline_tag": "text-generation", "last_modified": "2025-03-01"},
    ]
    ctx.put("raw_records", recs)
    DistillerSkill().run(ctx, trace)
    comp = ctx.get("comparison")
    assert len(comp["rows"]) == 3 and comp["rows"][0]["likes"] == "1,000", comp["rows"][0]
    QASkill().run(ctx, trace)
    qa = ctx.get("qa")
    assert qa["passed"] is True, qa
    ReportSkill().run(ctx, trace)
    rep = ctx.get("report")
    assert {"goal", "comparison", "qa", "browser_path"} <= set(rep)
    t = trace.to_dict()
    md = render_report_md(t, rep)
    html = render_replay_html(t, rep)
    assert "Final comparison table" in md and "Turn count" in md
    assert "<html" in html and "Browser-Agent Replay" in html
    assert (ctx.artifacts_dir / "replay.html").exists()


def run():
    tests = [test_dag_topo_and_cycle, test_trace_cost, test_listing_parse,
             test_model_parse, test_planner_fallback, test_pipeline_offline]
    results = []
    for fn in tests:
        try:
            fn()
            results.append((fn.__name__, "PASS", ""))
        except AssertionError as e:
            results.append((fn.__name__, "FAIL", str(e)))
        except Exception as e:  # noqa
            results.append((fn.__name__, "ERROR", repr(e)))
    for n, s, m in results:
        print(f"[{s}] {n} {(' -> ' + m) if m else ''}")
    ok = all(s == "PASS" for _, s, _ in results)
    print("\n" + ("ALL TESTS PASS ✅" if ok else "SOME TESTS FAILED ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
