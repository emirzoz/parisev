"""Airbnb ilanlarını pyairbnb ile çeker → raw/airbnb/<id>.json

Kullanım: py scripts/02_airbnb.py [--ids L14 L18] [--force]
"""
import argparse
import csv
import json
import random
import time
from datetime import date
from pathlib import Path

import pyairbnb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "airbnb"
CHECK_IN, CHECK_OUT, ADULTS = date(2026, 11, 13), date(2026, 11, 22), 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with (ROOT / "data" / "listings_input.csv").open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["platform"] == "Airbnb"]
    if args.ids:
        rows = [r for r in rows if r["id"] in args.ids]

    RAW.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(rows):
        out = RAW / f"{r['id']}.json"
        if out.exists() and not args.force:
            print(f"{r['id']} var, atlandı")
            continue
        if i:
            time.sleep(random.uniform(3, 8))
        try:
            d = pyairbnb.get_details(
                room_url=f"https://www.airbnb.com/rooms/{r['listing_key']}",
                currency="TRY", adults=ADULTS, language="en",
                check_in=CHECK_IN, check_out=CHECK_OUT,
            )
        except Exception as e:  # ilan kaldırılmış / bloklanmış olabilir
            print(f"{r['id']} HATA: {e}")
            continue
        out.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        c, rt, pm = d.get("coordinates") or {}, d.get("rating") or {}, (d.get("price") or {}).get("main") or {}
        print(f"{r['id']} {c.get('latitude')},{c.get('longitude')} "
              f"puan={rt.get('guest_satisfaction')}/{rt.get('review_count')} "
              f"fiyat={pm.get('price')} kapasite={d.get('person_capacity')} yorum={len(d.get('reviews') or [])}")


if __name__ == "__main__":
    main()
