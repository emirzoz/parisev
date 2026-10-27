"""site/template.html + verileri tek dosyalık out/site/index.html'e birleştirir, docs/'a kopyalar.

Önce 04_geo.py (out/site/data.js) ve 03b_images.py (out/site/img/) çalışmış olmalı.
docs/ GitHub Pages'in yayınladığı klasör.
Kullanım: py scripts/06_build_site.py
"""
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo"
SITE = ROOT / "out" / "site"
DOCS = ROOT / "docs"


def main():
    html = (ROOT / "site" / "template.html").read_text(encoding="utf-8")
    data = (SITE / "data.js").read_text(encoding="utf-8")
    base = json.loads((GEO / "base.json").read_text(encoding="utf-8"))
    base["landmarks"] = json.loads((ROOT / "data" / "landmarks.json").read_text(encoding="utf-8"))
    base = "window.PARIS_BASE=" + json.dumps(base, ensure_ascii=False, separators=(",", ":")) + ";"
    html = html.replace("/*LEAFLET_CSS*/", (GEO / "leaflet.css").read_text(encoding="utf-8"))
    html = html.replace("/*DATA*/", data + "\n" + base)
    out = SITE / "index.html"
    out.write_text(html, encoding="utf-8")

    excluded = set()
    ex = ROOT / "data" / "excluded.csv"
    if ex.exists():
        with ex.open(encoding="utf-8") as f:
            excluded = {e["id"] for e in csv.DictReader(f)}
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, DOCS / "index.html")
    for old in (DOCS / "img").glob("*.jpg"):
        old.unlink()
    for img in (SITE / "img").glob("*.jpg"):
        if img.stem not in excluded:
            shutil.copy2(img, DOCS / "img" / img.name)
    (DOCS / ".nojekyll").touch()
    print(f"{out} — {out.stat().st_size // 1024} KB · docs/ güncellendi")


if __name__ == "__main__":
    main()
