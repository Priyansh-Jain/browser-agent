"""Probe 2: embedded JSON (data-props) + the real click flow for sort/filter."""
import json, re
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def sec(t): print("\n" + "=" * 66 + f"\n{t}\n" + "=" * 66)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.set_default_timeout(20000)
    page = ctx.new_page()

    sec("ModelList data-props (listing)")
    page.goto("https://huggingface.co/models?pipeline_tag=text-generation&sort=likes", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    dp = page.get_attribute("div[data-target='ModelList']", "data-props")
    if dp:
        data = json.loads(dp)
        print("top-level keys:", list(data.keys()))
        # find the models array
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                print(f"  list key {k!r} len={len(v)} sample keys:", list(v[0].keys()))
                print("  sample[0]:", json.dumps(v[0])[:500])
                break
    else:
        print("no data-props on ModelList")

    sec("SORT click flow on bare /models")
    page.goto("https://huggingface.co/models", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    # the sort control usually shows current value 'Trending'
    for opener in ["text=Trending", "button:has-text('Trending')", "text=Sort"]:
        try:
            loc = page.locator(opener).first
            if loc.count():
                print(f"opener {opener!r} found; clicking")
                loc.click()
                page.wait_for_timeout(700)
                break
        except Exception as e:
            print(f"  opener {opener!r} err {e}")
    print("after open -> Most likes count:", page.get_by_text("Most likes", exact=False).count())
    opts = page.eval_on_selector_all(
        "[role='option'],[role='menuitem'],li,button,a",
        "els=>els.map(e=>(e.innerText||'').trim()).filter(t=>/likes|downloads|trending|recently|created/i.test(t)).slice(0,12)")
    print("menu option texts:", json.dumps(opts))
    # try clicking Most likes
    ml = page.get_by_text("Most likes", exact=False).first
    if ml.count():
        ml.click(); page.wait_for_timeout(1200)
    print("url after Most likes click:", page.url)

    sec("FILTER click flow (Tasks -> Text Generation)")
    page.goto("https://huggingface.co/models", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    tasks_btn = page.get_by_role("button", name=re.compile("^Tasks$", re.I))
    print("Tasks button count:", tasks_btn.count())
    if tasks_btn.count():
        tasks_btn.first.click(); page.wait_for_timeout(700)
    tg_link = page.get_by_role("link", name=re.compile("^Text Generation$", re.I))
    print("TG link (role) count:", tg_link.count())
    tg_css = page.locator("a[href*='pipeline_tag=text-generation']")
    print("TG link (css href) count:", tg_css.count(), "| first visible:",
          tg_css.first.is_visible() if tg_css.count() else "n/a")
    if tg_css.count():
        tg_css.first.click(); page.wait_for_timeout(1200)
    print("url after TG click:", page.url)

    sec("MODEL header data-props + like button")
    page.goto("https://huggingface.co/deepseek-ai/DeepSeek-R1", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    mh = page.get_attribute("div[data-target='ModelHeader']", "data-props")
    if mh:
        d = json.loads(mh)
        print("ModelHeader keys:", list(d.keys()))
        # drill into likely 'model' object
        for k in ("model", "repo", "card"):
            if isinstance(d.get(k), dict):
                m = d[k]
                print(f"  {k} keys:", list(m.keys())[:40])
                for fld in ("likes", "downloads", "downloadsAllTime", "pipeline_tag", "id", "license", "lastModified"):
                    if fld in m:
                        print(f"    {k}.{fld} =", json.dumps(m[fld])[:80])
    else:
        print("no data-props on ModelHeader")
    # like button text
    lb = page.locator("button:has-text('like')").first
    print("like button text:", (lb.inner_text() if lb.count() else "—").replace("\n", " ")[:60])
    # downloads-last-month
    body = re.sub(r"\s+", " ", page.locator("body").inner_text())
    m = re.search(r"Downloads last month\s*([\d,\.kKmM]+)", body)
    print("downloads last month:", m.group(1) if m else "not found on page")
    b.close()
print("\nPROBE2_DONE")
