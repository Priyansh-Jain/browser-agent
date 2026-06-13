"""Hugging Face site recipe -- the only place that knows HF's DOM.

This is a Browser-skill *extension*: to support another site you add another
recipe; you never touch the orchestrator or the path cascade. Selectors here
were verified against the live site (see tests/probe_hf*.py).
"""
from __future__ import annotations

import html as _html
import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .paths import PathSelector

_NON_MODEL_FIRST_SEG = {
    "models", "datasets", "spaces", "docs", "blog", "pricing", "login", "join",
    "settings", "organizations", "new", "search", "posts", "papers", "collections",
    "tasks", "enterprise", "chat", "huggingface", "brand", "terms", "privacy",
}


def _is_model_href(href: str) -> bool:
    if not href or not href.startswith("/") or "?" in href or "#" in href:
        return False
    segs = [s for s in href.strip("/").split("/") if s]
    if not (1 <= len(segs) <= 2):
        return False
    return segs[0] not in _NON_MODEL_FIRST_SEG


def _parse_human(s: str) -> Optional[int]:
    s = (s or "").replace(",", "").strip()
    m = re.fullmatch(r"([\d.]+)\s*([kKmMbB]?)", s)
    if not m:
        return None
    mult = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2).lower()]
    return int(float(m.group(1)) * mult)


def humanize_params(n: Optional[int]) -> Optional[str]:
    if not n:
        return None
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            return f"{v:.0f}{suf}" if v >= 10 else f"{v:.1f}{suf}"
    return str(n)


def humanize_int(n: Optional[int]) -> Optional[str]:
    return humanize_params(n) if n else (0 if n == 0 else None)


def _date(iso: Any) -> Optional[str]:
    return iso[:10] if isinstance(iso, str) and len(iso) >= 10 else None


def _license(m: Dict[str, Any]) -> Optional[str]:
    cd = m.get("cardData") or {}
    lic = cd.get("license")
    if isinstance(lic, list) and lic:
        lic = lic[0]
    if isinstance(lic, str) and lic:
        return lic
    for t in m.get("tags") or []:
        if isinstance(t, str) and t.startswith("license:"):
            return t.split(":", 1)[1]
    return None


def _params(m: Dict[str, Any]) -> Optional[str]:
    st = m.get("safetensors") or {}
    return humanize_params(st.get("total")) if isinstance(st, dict) else None


def _model_fields(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": m.get("id"),
        "likes": m.get("likes"),
        "downloads_last_month": m.get("downloads"),
        "downloads_all_time": m.get("downloadsAllTime"),
        "pipeline_tag": m.get("pipeline_tag"),
        "library": m.get("library_name"),
        "license": _license(m),
        "params": _params(m),
        "last_modified": _date(m.get("lastModified")),
        "created_at": _date(m.get("createdAt")),
        "tags": [t for t in (m.get("tags") or []) if isinstance(t, str)][:10],
    }


class HFRecipe:
    name = "huggingface"

    def __init__(self, config):
        self.config = config
        self.task_label = config.task_filter_label   # "Text Generation"
        self.task_slug = config.task_filter           # "text-generation"
        self.sort_label = config.sort_label            # "Most likes"
        self.sort_slug = config.sort_by                # "likes"

    # ----- interactions (visible browser actions) -----
    def reveal_task_filter(self, session) -> None:
        """Expand the 'Tasks' facet (best-effort; harmless if already open)."""
        try:
            btn = session.page.get_by_role("button", name=re.compile(r"^Tasks$", re.I))
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                session.page.wait_for_timeout(500)
                session.trace.record_action("click", target="expand Tasks facet", path="deterministic",
                                             url=session.url(), note="reveal hidden filter list")
        except Exception as e:
            session.trace.log(f"reveal_task_filter: {type(e).__name__}", "info")

    def click_task_filter(self, selector: PathSelector) -> str:
        return selector.click(
            f"filter: {self.task_label} task",
            css=[f"a[href*='pipeline_tag={self.task_slug}']"],
            role="link",
            name=re.compile(rf"^{re.escape(self.task_label)}$", re.I),
            primary=False,
        )

    def apply_sort(self, session, selector: PathSelector) -> str:
        # open the sort dropdown (shows current value, e.g. "Trending")
        selector.click(
            "open sort menu",
            css=["button:has-text('Trending')", "text=Trending", "button:has-text('Sort')"],
            role="button",
            name=re.compile(r"(Trending|Sort)", re.I),
            primary=False,
        )
        session.page.wait_for_timeout(500)
        # pick the option
        return selector.click(
            f"sort: {self.sort_label}",
            css=[f"text={self.sort_label}", f"a:has-text('{self.sort_label}')",
                 f"button:has-text('{self.sort_label}')"],
            role="link",
            name=re.compile(rf"^{re.escape(self.sort_label)}$", re.I),
            primary=False,
        )

    def canonical_url(self) -> str:
        return f"{self.config.target_url}?pipeline_tag={self.task_slug}&sort={self.sort_slug}"

    def url_is_filtered_sorted(self, url: str) -> bool:
        return f"pipeline_tag={self.task_slug}" in url and f"sort={self.sort_slug}" in url

    # ----- listing extraction (extract -> deterministic cascade) -----
    def parse_listing_static(self, html: str, top_n: int) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        out: List[Dict[str, Any]] = []
        for art in soup.select("article"):
            a = art.select_one("a[href]")
            href = a.get("href") if a else None
            if not _is_model_href(href or ""):
                continue
            mid = href.strip("/")
            txt = " ".join(art.get_text(" ", strip=True).split())
            out.append({
                "rank": len(out) + 1,
                "id": mid,
                "url": f"{self.config.base_url}/{mid}",
                "card_text": txt[:160],
            })
            if len(out) >= top_n:
                break
        return out

    def parse_listing_css(self, page, top_n: int) -> List[Dict[str, Any]]:
        rows = page.eval_on_selector_all(
            "article a[href]",
            "els => els.map(e => ({href: e.getAttribute('href'), text: (e.innerText||'').trim()}))",
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            if not _is_model_href(r.get("href") or ""):
                continue
            mid = r["href"].strip("/")
            out.append({
                "rank": len(out) + 1, "id": mid,
                "url": f"{self.config.base_url}/{mid}",
                "card_text": " ".join((r.get("text") or "").split())[:160],
            })
            if len(out) >= top_n:
                break
        return out

    # ----- model-page extraction (extract -> deterministic -> a11y -> vision) -----
    def parse_model_static(self, html: str) -> Optional[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        el = soup.select_one("div[data-target='ModelHeader']")
        props = el.get("data-props") if el else None
        if not props:
            m = re.search(r'data-target="ModelHeader"[^>]*data-props="([^"]+)"', html)
            props = _html.unescape(m.group(1)) if m else None
        if not props:
            return None
        try:
            d = json.loads(props)
        except Exception:
            return None
        m = d.get("model") or {}
        return _model_fields(m) if m else None

    def parse_model_css(self, page) -> Optional[Dict[str, Any]]:
        out: Dict[str, Any] = {}
        try:
            body = " ".join(page.locator("body").inner_text().split())
        except Exception:
            body = ""
        md = re.search(r"Downloads last month\s*([\d,]+)", body)
        if md:
            out["downloads_last_month"] = int(md.group(1).replace(",", ""))
        try:
            head = " ".join(page.locator("[data-target='ModelHeader']").first.inner_text().split())
        except Exception:
            head = body
        ml = re.search(r"\blike\b\s*([\d.,]+[kKmM]?)", head, re.I)
        if ml:
            out["likes"] = _parse_human(ml.group(1))
        return out or None

    def a11y_read_likes(self, page) -> Optional[Dict[str, Any]]:
        """Use ARIA roles (the accessibility tree) to find the bare-number like
        control. Best-effort cross-check, clearly a demo of the a11y path."""
        for role in ("button", "link"):
            loc = page.get_by_role(role)
            for i in range(min(loc.count(), 50)):
                try:
                    nm = loc.nth(i).inner_text().strip()
                except Exception:
                    continue
                if re.fullmatch(r"[\d.,]+[kKmM]?", nm):
                    val = _parse_human(nm)
                    if val and val >= 1:
                        return {"likes": val, "raw": nm, "via": f"role={role}[{i}]"}
        return None
