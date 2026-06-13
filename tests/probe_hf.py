"""One-off probe to learn Hugging Face's live DOM so the recipe uses real
selectors. Not part of the agent; just a scouting tool. Run:  python tests/probe_hf.py
"""
import json
import re
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def section(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.set_default_timeout(20000)
    page = ctx.new_page()

    section("LISTING (filtered+sorted via URL): /models?pipeline_tag=text-generation&sort=likes")
    page.goto("https://huggingface.co/models?pipeline_tag=text-generation&sort=likes",
              wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    print("url:", page.url, "| title:", page.title())
    for sel in ["article", "article a", "a[href^='/']", "div[data-target]"]:
        try:
            print(f"  count {sel!r}:", page.locator(sel).count())
        except Exception as e:
            print(f"  count {sel!r}: ERR {e}")
    # model card anchors
    hrefs = page.eval_on_selector_all(
        "article a[href^='/']",
        "els => els.slice(0,8).map(e => ({href:e.getAttribute('href'), text:(e.innerText||'').trim().slice(0,60)}))",
    )
    print("  first article anchors:", json.dumps(hrefs, indent=2))
    # data-target components (HF embeds JSON props)
    dts = page.eval_on_selector_all(
        "div[data-target]", "els => Array.from(new Set(els.slice(0,40).map(e=>e.getAttribute('data-target'))))"
    )
    print("  data-target kinds:", dts)
    # one article's text + outerHTML head
    if page.locator("article").count():
        art = page.locator("article").first
        print("  article[0] text:", re.sub(r"\s+", " ", art.inner_text())[:200])
        print("  article[0] html[:600]:", art.evaluate("e=>e.outerHTML")[:600])

    section("CONTROLS on bare /models (sort + task filter)")
    page.goto("https://huggingface.co/models", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    print("selects:", page.locator("select").count())
    for i in range(min(page.locator("select").count(), 4)):
        s = page.locator("select").nth(i)
        print(f"  select[{i}] html:", s.evaluate("e=>e.outerHTML")[:400])
    # sort-ish text
    for kw in ["Trending", "Most likes", "Sort", "Text Generation", "Tasks"]:
        loc = page.get_by_text(kw, exact=False)
        print(f"  get_by_text({kw!r}).count():", loc.count())
    # buttons near top
    btns = page.eval_on_selector_all(
        "button", "els => els.slice(0,25).map(e => (e.innerText||'').trim()).filter(Boolean).slice(0,25)"
    )
    print("  button texts:", json.dumps(btns[:25]))
    # links with Text Generation
    tg = page.eval_on_selector_all(
        "a", "els => els.map(e=>({href:e.getAttribute('href'),t:(e.innerText||'').trim()})).filter(x=>/text.gener/i.test(x.t)||/text-generation/i.test(x.href||'')).slice(0,6)"
    )
    print("  text-generation links:", json.dumps(tg, indent=2))

    section("MODEL PAGE header (likes/downloads/license/updated)")
    target = hrefs[0]["href"] if hrefs else "/openai-community/gpt2"
    page.goto("https://huggingface.co" + target, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    print("url:", page.url, "| title:", page.title())
    body = re.sub(r"\s+", " ", page.locator("body").inner_text())
    for kw in ["likes", "Downloads", "downloads", "License", "Updated", "Safetensors", "Text Generation"]:
        m = re.search(r".{0,30}" + kw + r".{0,30}", body)
        print(f"  ctx {kw!r}:", (m.group(0) if m else "—"))
    dts2 = page.eval_on_selector_all(
        "div[data-target]", "els => Array.from(new Set(els.map(e=>e.getAttribute('data-target')))).slice(0,40)"
    )
    print("  model-page data-target kinds:", dts2)
    # like button
    print("  like button candidates:")
    for sel in ["button:has-text('like')", "[title*='like' i]", "header a[href$='/likers']", "a[href$='/likers']"]:
        try:
            print(f"    {sel!r}:", page.locator(sel).count())
        except Exception as e:
            print(f"    {sel!r}: ERR")
    b.close()
print("\nPROBE_DONE")
