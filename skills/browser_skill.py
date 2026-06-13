"""Browser skill -- the assignment's extension point.

Performs a real, multi-step browser workflow on a dynamic site (search/filter,
sort, scroll, open detail pages) and extracts data via the cheapest correct
path. All site specifics live in browser/recipe_hf.py; this skill is the generic
"drive the browser for a comparison task" behaviour.
"""
from __future__ import annotations

from typing import Any, Dict, List

from orchestrator.errors import GatewayBlocked
from orchestrator.skill import Skill

from .browser.paths import ElementNotFound, PathSelector
from .browser.recipe_hf import HFRecipe
from .browser.session import BrowserSession


class BrowserSkill(Skill):
    name = "browser"
    description = (
        "Drive a real Chromium browser to interactively search / filter / sort / "
        "scroll / open detail pages on a JavaScript-rendered site, then extract "
        "structured data via the cheapest correct path "
        "(extract -> deterministic -> a11y -> vision -> blocked). Handles bot-walls."
    )
    reads = ("candidate_urls",)
    writes = ("raw_records", "listing_url", "browser_path")

    def run(self, ctx, trace, **params) -> Dict[str, Any]:
        cfg = ctx.config
        top_n = int(params.get("top_n", cfg.top_n))
        start_url = (ctx.get("candidate_urls") or [cfg.target_url])[0]

        recipe = HFRecipe(cfg)
        session = BrowserSession(cfg, trace, ctx.artifacts_dir)
        selector = PathSelector(session, ctx.gateway, trace)
        records: List[Dict[str, Any]] = []
        listing_url = ""

        try:
            # --- open the listing ---
            session.goto(start_url, note="open models listing")
            session.page_state("landing (default sort)")
            session.shot("models landing (default trending sort)")

            # --- VISIBLE ACTION 1: filter to the task ---
            recipe.reveal_task_filter(session)
            try:
                recipe.click_task_filter(selector)
            except ElementNotFound:
                trace.log("filter UI click failed; recovering via URL", "warn")
                session.goto(f"{cfg.target_url}?pipeline_tag={recipe.task_slug}",
                             note="recovery: filter via URL param")
            session.wait(1400)
            session.shot(f"after filter -> {recipe.task_label}")

            # --- VISIBLE ACTION 2: sort by likes ---
            try:
                recipe.apply_sort(session, selector)
            except ElementNotFound:
                trace.log("sort UI click failed; will recover via URL", "warn")
            session.wait(1500)

            # ensure we really landed on filtered+sorted state
            if not recipe.url_is_filtered_sorted(session.url()):
                session.goto(recipe.canonical_url(), note="recovery: canonical filtered+sorted URL")
                session.wait(1200)
            listing_url = session.url()
            session.page_state("filtered + sorted listing")
            session.shot(f"listing: {recipe.task_label} sorted by {recipe.sort_label}")

            # --- VISIBLE ACTION 3: scroll to reveal more cards (lazy-load) ---
            session.scroll(1600, note="reveal more cards (lazy-load)")
            session.shot("after scroll")

            # --- collect top-N (extract -> deterministic) ---
            path_list, listing = selector.extract(
                f"listing: top-{top_n} model ids (sorted by {recipe.sort_label})",
                static_fn=lambda: recipe.parse_listing_static(session.html(), top_n),
                css_fn=lambda: recipe.parse_listing_css(session.page, top_n),
                validate=lambda lst: isinstance(lst, list) and len(lst) >= 1,
                primary=True,
            )
            listing = (listing or [])[:top_n]
            trace.log(f"top-{top_n} via '{path_list}': {[m['id'] for m in listing]}")

            # --- open each detail page + extract (multi-page flow) ---
            for idx, item in enumerate(listing):
                session.goto(item["url"], note=f"open model detail #{item['rank']}")
                session.page_state(f"model page: {item['id']}")
                session.shot(f"model {item['rank']}: {item['id']}")
                _path, fields = selector.extract(
                    f"model detail fields: {item['id']}",
                    static_fn=(lambda h=session.html(): recipe.parse_model_static(h)),
                    css_fn=lambda: recipe.parse_model_css(session.page),
                    a11y_fn=lambda: recipe.a11y_read_likes(session.page),
                    validate=lambda d: isinstance(d, dict) and d.get("likes") is not None,
                    primary=True,
                )
                rec: Dict[str, Any] = {
                    "rank": item["rank"], "id": item["id"], "url": item["url"],
                    "source_path": _path, "card_text": item.get("card_text", ""),
                }
                if isinstance(fields, dict):
                    rec.update(fields)
                rec["id"] = item["id"]

                if idx == 0:
                    self._demo_a11y(recipe, session, trace, rec)
                    self._demo_vision(recipe, session, ctx, trace, rec)
                records.append(rec)

        except GatewayBlocked:
            session.shot("blocked / bot-wall")
            session.page_state("blocked")
            raise
        finally:
            session.close()

        ctx.put("raw_records", records)
        ctx.put("listing_url", listing_url)
        ctx.put("browser_path", trace.headline_path())
        return {
            "summary": f"{len(records)} model(s) collected; primary path='{trace.headline_path()}'",
            "records": records,
            "listing_url": listing_url,
        }

    # ---- capability demonstrations (clearly labelled, non-critical-path) ----
    def _demo_a11y(self, recipe, session, trace, rec) -> None:
        res = recipe.a11y_read_likes(session.page)
        ok = bool(res and res.get("likes"))
        trace.record_path_decision(
            f"a11y capability check: likes for {rec['id']}",
            [{"path": "a11y", "ok": ok,
              "note": (f"read {res['raw']} via {res['via']}" if ok else "no bare-number control found")}],
            "a11y" if ok else "failed", primary=False,
        )
        if ok:
            rec["likes_a11y"] = res["likes"]

    _VISION_SELECTOR = ("header button, header a, "
                        "[data-target='ModelHeader'] button, [data-target='ModelHeader'] a")

    def _demo_vision(self, recipe, session, ctx, trace, rec) -> None:
        """Always build the set-of-marks overlay (the vision-path *input*) so the
        report can show it; run the actual model read only when a key exists."""
        import json as _json
        import re as _re

        from .browser.setofmarks import annotate

        intent = f"vision capability check: likes for {rec['id']}"
        img = ctx.artifacts_dir / "screenshots" / f"vision_marks_{rec['rank']}.png"
        marks = annotate(session, self._VISION_SELECTOR, img)
        if marks:
            trace.record_screenshot(
                f"screenshots/{img.name}",
                f"set-of-marks vision overlay — {len(marks)} candidate marks",
                session.url(),
            )

        if not (ctx.config.force_vision_demo and ctx.gateway.available):
            trace.record_path_decision(
                intent,
                [{"path": "vision", "ok": False,
                  "note": f"overlay built ({len(marks)} marks); LLM read skipped (no ANTHROPIC_API_KEY)"}],
                "skipped", primary=False,
            )
            return

        listing = "\n".join(f"[{m['id']}] {m['text']}" for m in marks)
        prompt = (
            "This Hugging Face model-page screenshot has numbered pink boxes (marks). "
            "Marks and their visible text:\n" + listing +
            "\n\nWhich mark is the model's 'likes' counter (the number beside the heart / "
            'like button)? Respond ONLY as JSON: {"mark": <id>, "likes": "<value as shown>"}.'
        )
        if hasattr(ctx.gateway, "next_vision_likes"):  # demo gateway hint
            ctx.gateway.next_vision_likes = rec.get("likes")
        raw = ctx.gateway.vision(prompt, str(img), purpose="vision:likes")
        likes = None
        if raw:
            m = _re.search(r"\{.*\}", raw, _re.S)
            if m:
                try:
                    likes = _json.loads(m.group(0)).get("likes")
                except Exception:
                    likes = None
        ok = likes is not None
        trace.record_path_decision(
            intent,
            [{"path": "vision", "ok": ok,
              "note": (f"set-of-marks LLM read likes={likes}" if ok else "vision LLM read failed/empty")}],
            "vision" if ok else "failed", primary=False,
        )
        if ok:
            rec["likes_vision"] = likes
