"""Harita altlığı için coğrafi verileri indirir → data/geo/

- IDFM: raylı hat izleri + istasyonlar (resmi renklerle)
- geo.api.gouv.fr: Paris arrondissement'ları + çevre belediyelerin sınırları
- Overpass (OSM): Seine ve Marne
Artifact sayfaları dış harita karolarını yükleyemediği için altlık bu vektörlerden çiziliyor.
Kullanım: py scripts/00_fetch_geo.py [--force]
"""
import gzip
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo"
IDFM = "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/{}/exports/geojson"
BBOX = (48.68, 2.10, 49.00, 2.60)  # 04_geo.py ile aynı
UA = {"User-Agent": "paris-konaklama-arastirma/0.1"}


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def simplify(ring, step=3, nd=4):
    pts = [[round(lat, nd), round(lng, nd)] for lng, lat in ring[::step]]
    return pts + [pts[0]] if pts and pts[0] != pts[-1] else pts


def in_bbox(lat, lng):
    return BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lng <= BBOX[3]


def communes():
    out = []
    urls = ["https://geo.api.gouv.fr/communes?codeDepartement=75&type=arrondissement-municipal&fields=nom&format=geojson&geometry=contour"]
    urls += [f"https://geo.api.gouv.fr/communes?codeDepartement={d}&fields=nom&format=geojson&geometry=contour"
             for d in ("92", "93", "94", "91", "95", "78", "77")]
    for u in urls:
        for f in json.loads(get(u))["features"]:
            g = f["geometry"]
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            rings = [simplify(p[0]) for p in polys]
            if any(in_bbox(*pt) for r in rings for pt in r):
                out.append({"n": f["properties"]["nom"], "paris": "75" in u, "r": rings})
    return out


def rivers():
    q = (f'[out:json][timeout:120];way["waterway"="river"]["name"~"^(La )?(Seine|Marne)$"]'
         f'({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;')
    for host in ("https://overpass-api.de", "https://overpass.kumi.systems", "https://overpass.private.coffee"):
        try:
            d = json.loads(get(f"{host}/api/interpreter", urllib.parse.urlencode({"data": q}).encode()))
            break
        except Exception as e:  # Overpass sunucuları sık sık 502/429 veriyor; nehirler opsiyonel
            print(f"overpass {host}: {e}")
    else:
        return []
    return [[[round(p["lat"], 4), round(p["lon"], 4)] for p in w["geometry"]] for w in d["elements"]]


def main():
    force = "--force" in sys.argv
    GEO.mkdir(parents=True, exist_ok=True)
    for name, ds in (("traces", "traces-du-reseau-ferre-idf"), ("gares", "emplacement-des-gares-idf")):
        f = GEO / f"{name}.geojson"
        if force or not f.exists():
            f.write_bytes(get(IDFM.format(ds)))
    base = GEO / "base.json"
    if force or not base.exists():
        b = {"communes": communes(), "rivers": rivers()}
        base.write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for f in sorted(GEO.iterdir()):
        print(f"{f.name}: {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
