"""Booking ilanlarını Playwright ile açar → raw/booking/<id>.json

Kullanım: py scripts/03_booking.py [--ids L06] [--force] [--headed]
"""
import argparse
import csv
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "booking"
QUERY = ("checkin=2026-11-13&checkout=2026-11-22&group_adults=3&no_rooms=1"
         "&group_children=0&selected_currency=TRY&lang=tr")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

EXTRACT_JS = r"""
() => {
  const t = s => { const e = document.querySelector(s); return e ? e.innerText.trim() : null; };
  const latlng = document.querySelector('[data-atlas-latlng]')?.getAttribute('data-atlas-latlng');
  // #hprt-table artık yok; oda tablosu ilk <table>, her <tr> bir fiyat seçeneği (oda tipi hücresi rowspan'li).
  const table = document.querySelector('table');
  const rooms = table ? [...table.querySelectorAll('tbody tr')].map(tr => tr.innerText.replace(/\s+/g, ' ').trim()) : [];
  const subscores = [...document.querySelectorAll('[data-testid="review-subscore"]')].map(e => e.innerText.replace(/\s+/g, ' ').trim());
  const reviews = [...document.querySelectorAll('[data-testid="featuredreview-text"], [data-testid="review-card"]')].map(e => e.innerText.trim());
  return {
    title: t('h2.pp-header__title') || t('[data-testid="property-header"] h2') || document.title,
    address: t('[data-testid="PropertyHeaderAddressDesktop-wrapper"]') || t('.hp_address_subtitle'),
    latlng,
    score: t('[data-testid="review-score-component"]') || t('[data-testid="review-score-right-component"]'),
    subscores, rooms, reviews,
    policies: t('#hp_policies_box') || t('[data-testid="property-section--content"]'),
    final_url: location.href,
    blocked: /captcha|are you a robot|robot misiniz/i.test(document.body.innerText.slice(0, 3000)),
  };
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    with (ROOT / "data" / "listings_input.csv").open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["platform"] == "Booking"]
    if args.ids:
        rows = [r for r in rows if r["id"] in args.ids]

    RAW.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(ROOT / ".pw-profile"), headless=not args.headed, locale="tr-TR",
            viewport={"width": 1366, "height": 900},
            # HeadlessChrome UA'sında Booking tarihleri URL'den düşürüyor → fiyat sütunu gelmiyor
            user_agent=UA,
        )
        page = ctx.new_page()
        for i, r in enumerate(rows):
            out = RAW / f"{r['id']}.json"
            if out.exists() and not args.force:
                print(f"{r['id']} var, atlandı")
                continue
            if i:
                time.sleep(random.uniform(3, 8))
            page.goto(f"{r['url']}?{QUERY}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            d = page.evaluate(EXTRACT_JS)
            if d["blocked"]:
                print(f"{r['id']} BOT KONTROLÜ — durduruldu (--headed ile açıp elle çöz)")
                break
            lat = lng = None
            if d["latlng"]:
                lat, lng = map(float, d["latlng"].split(","))
            else:
                m = re.search(r"b_map_center_latitude\s*=\s*([\d.]+).*?b_map_center_longitude\s*=\s*([\d.]+)",
                              page.content(), re.S)
                if m:
                    lat, lng = float(m.group(1)), float(m.group(2))
            d.update(id=r["id"], url=r["url"], lat=lat, lng=lng, fetched_at=datetime.now().isoformat(timespec="seconds"))
            out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{r['id']} {lat},{lng} puan={(d['score'] or '').splitlines()[:1]} "
                  f"oda_satırı={len(d['rooms'])} yorum={len(d['reviews'])} adres={d['address']}")
        ctx.close()


if __name__ == "__main__":
    main()
