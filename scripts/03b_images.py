"""Her ilan için bir kapak fotoğrafı indirir, 4:3 küçük JPEG yapar → out/site/img/<id>.jpg

Airbnb: pyairbnb'nin images listesinin ilki. Booking: sayfadaki og:image.
Artifact sayfası dış görselleri yükleyemediği için fotoğraflar sayfayla birlikte yayınlanıyor.
Kullanım: py scripts/03b_images.py [--force]
"""
import csv
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "site" / "img"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
SIZE = (360, 270)


def thumb(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    # ortadan 4:3 kırp
    w, h = im.size
    tw = min(w, int(h * 4 / 3))
    th = int(tw * 3 / 4)
    im = im.crop(((w - tw) // 2, (h - th) // 2, (w - tw) // 2 + tw, (h - th) // 2 + th)).resize(SIZE, Image.LANCZOS)
    im.save(dest, "JPEG", quality=72, optimize=True, progressive=True)


def main():
    force = "--force" in sys.argv
    with (ROOT / "data" / "listings_input.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows if force or not (OUT / f"{r['id']}.jpg").exists()]

    urls = {}
    for r in todo:
        if r["platform"] == "Airbnb":
            imgs = json.loads((ROOT / "raw" / "airbnb" / f"{r['id']}.json").read_text(encoding="utf-8")).get("images") or []
            if imgs:
                urls[r["id"]] = imgs[0]["url"].split("?")[0] + "?im_w=480"
    booking = [r for r in todo if r["platform"] == "Booking"]
    if booking:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(ROOT / ".pw-profile"), headless=True, locale="tr-TR", user_agent=UA)
            page = ctx.new_page()
            for r in booking:
                page.goto(r["url"], wait_until="domcontentloaded", timeout=60000)
                og = page.evaluate("() => document.querySelector('meta[property=\"og:image\"]')?.content")
                if og:
                    urls[r["id"]] = og
                time.sleep(2)
            ctx.close()

    for r in todo:
        u = urls.get(r["id"])
        if not u:
            print(f"{r['id']} fotoğraf bulunamadı")
            continue
        try:
            thumb(u, OUT / f"{r['id']}.jpg")
        except Exception as e:
            print(f"{r['id']} HATA: {e}")
    files = sorted(OUT.glob("*.jpg"))
    print(f"{len(files)} fotoğraf, toplam {sum(f.stat().st_size for f in files) // 1024} KB")


if __name__ == "__main__":
    main()
