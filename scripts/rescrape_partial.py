"""Re-fetch partial JSONs from BCN where the original scrape captured 'Loading...'.

Usage:
  python scripts/rescrape_partial.py --limit 5            # test on 5 first
  python scripts/rescrape_partial.py                       # all partials
  python scripts/rescrape_partial.py --delay 30            # use 30s delay (default 15)
"""
import argparse
import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

NORMAS_DIR = Path("data/normas_completas")


def find_partial_jsons() -> list[Path]:
    """Return JSONs whose texto_completo ends near 'Loading...'."""
    out = []
    for f in NORMAS_DIR.rglob("*.json"):
        if f.name.endswith(".bak"):
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        texto = d.get("texto_completo", "") or ""
        if "Loading..." in texto[-1000:]:
            out.append(f)
    return out


async def fetch_with_better_wait(page, id_norma: str, max_wait_s: int = 30) -> str:
    """Navigate to a norm and wait until 'Loading...' is gone, then return body text."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
    await page.goto(url, wait_until="networkidle", timeout=60000)
    await asyncio.sleep(2)

    # Try to scroll to bottom to trigger lazy load (idempotent)
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass

    # Poll until Loading... is gone OR max_wait_s elapses
    deadline = asyncio.get_event_loop().time() + max_wait_s
    while True:
        try:
            has_loading = await page.evaluate(
                "() => document.body.innerText.includes('Loading...')"
            )
        except Exception:
            has_loading = False
        if not has_loading:
            break
        if asyncio.get_event_loop().time() > deadline:
            break
        # Periodic scroll to trigger more lazy-load
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        await asyncio.sleep(1)

    # Final small wait to let any last paint settle
    await asyncio.sleep(2)

    texto = await page.evaluate("""() => {
        const cs = [document.querySelector('.cuerpo-norma'),
                    document.querySelector('#texto-norma'),
                    document.querySelector('article'),
                    document.body];
        for (const c of cs) if (c && c.innerText.length > 500) return c.innerText;
        return document.body.innerText || '';
    }""")
    return texto.strip()


async def rescrape_one(page, json_path: Path) -> dict:
    """Re-fetch one norma. Mutates the JSON file if new text is longer.
    Returns {'id_norma', 'old_len', 'new_len', 'updated'}."""
    d = json.loads(json_path.read_text())
    id_norma = str(d["id_norma"])
    old_len = len(d.get("texto_completo", "") or "")

    new_text = await fetch_with_better_wait(page, id_norma, max_wait_s=30)
    new_len = len(new_text)
    updated = False

    # Only replace if new is substantially better (more than 5% longer AND no Loading...)
    if new_len > old_len * 1.05 and "Loading..." not in new_text[-500:]:
        # Backup
        bak = json_path.with_suffix(".json.bak")
        if not bak.exists():
            shutil.copy(json_path, bak)
        d["texto_completo"] = new_text
        d["rescraped_at"] = datetime.now().isoformat()
        json_path.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        updated = True

    return {"id_norma": id_norma, "old_len": old_len, "new_len": new_len,
            "updated": updated, "still_has_loading": "Loading..." in new_text[-500:]}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Re-scrape only the first N partials (for testing)")
    ap.add_argument("--delay", type=float, default=15.0,
                    help="Delay seconds between fetches (default 15)")
    args = ap.parse_args()

    partials = find_partial_jsons()
    if args.limit:
        partials = partials[:args.limit]
    print(f"[rescrape] {len(partials)} partial JSONs to process")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        await Stealth().apply_stealth_async(ctx)
        page = await ctx.new_page()

        results = []
        for i, jp in enumerate(partials, 1):
            try:
                r = await rescrape_one(page, jp)
                tag = "OK" if r["updated"] else "--"
                print(f"  [{i}/{len(partials)}] {tag} {r['id_norma']} "
                      f"old={r['old_len']:>7d}  new={r['new_len']:>7d}  "
                      f"updated={r['updated']}  loading={r['still_has_loading']}")
                results.append(r)
            except Exception as e:
                print(f"  [{i}/{len(partials)}] ERROR {jp.name}: {e}")
                results.append({"id_norma": jp.stem, "error": str(e)})
            if i < len(partials):
                await asyncio.sleep(args.delay)
        await browser.close()

    print()
    updated_count = sum(1 for r in results if r.get("updated"))
    still_partial = sum(1 for r in results if r.get("still_has_loading"))
    total_growth = sum(r.get("new_len", 0) - r.get("old_len", 0)
                       for r in results if r.get("updated"))
    print(f"[rescrape] summary: {updated_count}/{len(results)} updated, "
          f"{still_partial} still partial, +{total_growth} chars total")


if __name__ == "__main__":
    asyncio.run(main())
