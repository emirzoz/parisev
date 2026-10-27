"""Airbnb ilan sayfasından pyairbnb'nin boş döndürdüğü alanları okur → raw/airbnb/<id>_page.json

Başlık, "2 yatak odası · 3 yatak" özeti, uyku düzeni, rezervasyon kutusundaki vergili toplam,
iptal politikası, ev kuralları.
Kullanım: py scripts/02b_airbnb_page.py [--ids L14] [--force]
"""
import argparse
import csv
import json
import random
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "airbnb"
QUERY = "check_in=2026-11-13&check_out=2026-11-22&adults=3&currency=TRY&locale=tr"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

EXTRACT_JS = r"""
() => {
  const sec = id => { const e = document.querySelector(`[data-section-id^="${id}"]`); return e ? e.innerText.trim() : null; };
  return {
    title: document.querySelector('h1')?.innerText.trim() || null,
    overview: sec('OVERVIEW'),
    sleeping: sec('SLEEPING_ARRANGEMENT'),
    book_it: sec('BOOK_IT_SIDEBAR'),
    policies: sec('POLICIES'),
    description: sec('DESCRIPTION'),
    unavailable: /(bu tarihler|those dates).{0,40}(müsait değil|not available)/i.test(document.body.innerText),
    blocked: /captcha|are you a robot|robot misiniz/i.test(document.body.innerText.slice(0, 3000)),
  };
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with (ROOT / "data" / "listings_input.csv").open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["platform"] == "Airbnb"]
    if args.ids:
        rows = [r for r in rows if r["id"] in args.ids]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(ROOT / ".pw-profile"), headless=True, locale="tr-TR",
            viewport={"width": 1366, "height": 900}, user_agent=UA,
        )
        page = ctx.new_page()
        for i, r in enumerate(rows):
            out = RAW / f"{r['id']}_page.json"
            if out.exists() and not args.force:
                continue
            if i:
                time.sleep(random.uniform(3, 8))
            page.goto(f"https://www.airbnb.com.tr/rooms/{r['listing_key']}?{QUERY}", wait_until="domcontentloaded", timeout=60000)
            try:  # rezervasyon kutusu fiyatı geç yüklüyor
                page.wait_for_selector('[data-section-id^="BOOK_IT_SIDEBAR"]', timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(3500)
            d = page.evaluate(EXTRACT_JS)
            if d["blocked"]:
                print(f"{r['id']} BOT KONTROLÜ — durduruldu")
                break
            d.update(id=r["id"], fetched_at=datetime.now().isoformat(timespec="seconds"))
            out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{r['id']} {(d['title'] or '')[:40]!r} | {(d['overview'] or '').replace(chr(10), ' ')[:90]} | "
                  f"kutu={'var' if d['book_it'] else 'yok'} müsait_değil={d['unavailable']}")
        ctx.close()


if __name__ == "__main__":
    main()
