"""raw/ verilerini birleştirir, Mines'e mesafe + en yakın istasyonları ve sıralama skorunu hesaplar.

Çıktılar:
  data/listings_enriched.json  — ilan başına bir obje (AGENTS.md şemasının alt kümesi), skora göre sıralı
  out/site/data.js             — harita sayfasının okuduğu veri (ilanlar + hatlar + istasyonlar)
Kullanım: py scripts/04_geo.py
"""
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MINES = json.loads((ROOT / "data" / "constants.json").read_text(encoding="utf-8"))["mines"]
BBOX = (48.68, 2.10, 49.00, 2.60)  # lat_min, lng_min, lat_max, lng_max
MODES = {"METRO", "RER", "TRAMWAY", "TRAIN"}
BUDGET_TRY = 65000
GUESTS = 3
# 27.10.2026: 9 Airbnb ilanında ödeme ekranı / ilan sayfası oranı 1,149–1,162 (ort. 1,154)
AIRBNB_CHECKOUT_FACTOR = 1.154


def haversine_km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def in_bbox(lat, lng):
    return BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lng <= BBOX[3]


def tl(s):
    """'TL 51.063' / '₺61,880' → 51063"""
    return int(re.sub(r"\D", "", s)) if s and re.search(r"\d", s) else None


def load_stations():
    gj = json.loads((ROOT / "data" / "geo" / "gares.geojson").read_text(encoding="utf-8"))
    by_name = {}
    for f in gj["features"]:
        pr = f["properties"]
        if pr["mode"] not in MODES:
            continue
        lng, lat = f["geometry"]["coordinates"]
        if not in_bbox(lat, lng):
            continue
        name = pr["nom_zdc"] or pr["nom_gares"]
        s = by_name.setdefault(name, {"name": name, "lat": lat, "lng": lng, "lines": []})
        if pr["res_com"] not in s["lines"]:
            s["lines"].append(pr["res_com"])
    return list(by_name.values())


def load_lines():
    gj = json.loads((ROOT / "data" / "geo" / "traces.geojson").read_text(encoding="utf-8"))
    feats = []
    for f in gj["features"]:
        pr = f["properties"]
        if pr["mode"] not in MODES or not f.get("geometry"):
            continue
        coords = f["geometry"]["coordinates"]
        parts = [coords] if f["geometry"]["type"] == "LineString" else coords
        if not any(in_bbox(c[1], c[0]) for part in parts for c in part):
            continue
        feats.append({
            "mode": pr["mode"], "line": pr["res_com"], "color": "#" + (pr["colourweb_hexa"] or "888888"),
            "paths": [[[round(c[1], 5), round(c[0], 5)] for c in part] for part in parts],
        })
    return feats


# ---------- Airbnb ----------

def review_text(r):
    loc = r.get("localizedReview") or {}
    return re.sub(r"<br\s*/?>", " ", loc.get("comments") or r.get("comments") or "").strip()


def low_reviews(reviews, since="2024-11-01", max_stars=3):
    """Son 2 yıldaki <=3 yıldızlı yorumlar — asıl uyarılar buradan çıkıyor."""
    out = [{"date": r["createdAt"][:10], "stars": int(r["rating"]), "text": review_text(r)[:420]}
           for r in reviews
           if r.get("rating") and int(r["rating"]) <= max_stars and (r.get("createdAt") or "") >= since]
    return sorted(out, key=lambda x: x["date"], reverse=True)


def airbnb_page(pid):
    f = ROOT / "raw" / "airbnb" / f"{pid}_page.json"
    if not f.exists():
        return {}
    p = json.loads(f.read_text(encoding="utf-8"))
    ov, pol = p.get("overview") or "", p.get("policies") or ""
    num = lambda rx: int(m.group(1)) if (m := re.search(rx, ov)) else None
    sleeping = p.get("sleeping") or ""
    sleeping = re.sub(r"^Nerede uyuyacaksınız\?\s*(\d+/\d+ sayfa\s*\d+ / \d+\s*)?", "", sleeping).replace("\n", " ").strip()
    book = p.get("book_it") or ""
    cancel = re.search(r"(Ücretsiz iptal[^.\n]*\.|Bu rezervasyon iade edilmez[^.\n]*\.|[^.\n]*iptal[^.\n]*\.)", pol)
    free_until = re.search(r"Ücretsiz iptal için son tarih ([^\n]+?)(?:\s+Rezerve|\n|$)", book)
    checkin = re.search(r"Giriş(?: zamanı)?:?\s*([^\n]+)", pol)
    # rezervasyon kutusundaki toplam, kullanıcının ödeme ekranında göreceği rakam
    book_price = re.search(r"₺([\d.]+)\s*(?:Fiyat dökümünü|\(9 gece)", book)
    return {
        "book_price": tl(book_price.group(1)) if book_price else None,
        "free_cancel_until": free_until.group(1).strip() if free_until else None,
        "title": p.get("title"),
        "place": ov.split("\n")[0] if ov else None,
        "bedrooms": num(r"(\d+)\s*yatak odası") if "stüdyo" not in ov.lower() else 0,
        "beds": num(r"(\d+)\s*yatak\b"),
        "max_guests_page": num(r"(\d+)\s*misafir"),
        "bed_layout": sleeping or None,
        "cancellation": cancel.group(1).strip() if cancel else None,
        "checkin_time": checkin.group(1).strip() if checkin else None,
        "unavailable": p.get("unavailable") or "Bu tarihler uygun değil" in book,
    }


def from_airbnb(row, d):
    c, rt = d.get("coordinates") or {}, d.get("rating") or {}
    pm = (d.get("price") or {}).get("main") or {}
    reviews = d.get("reviews") or []
    pg = airbnb_page(row["id"])
    return {
        "lat": c.get("latitude"), "lng": c.get("longitude"), "location_precision": "approx",
        "title": pg.get("title") or row["gpt_name"], "address": pg.get("place"),
        # Airbnb TR sayfası: "Fiyatlara tüm ücretler dâhildir" → toplam zaten vergi/ücret dahil
        "price_total_try": None if pg.get("unavailable") else (pg.get("book_price") or tl(pm.get("price"))),
        "price_base_try": None, "price_tax_try": None,
        "price_note": "13–22 Kasım müsait değil" if pg.get("unavailable") else "tüm ücretler dahil",
        "rating": rt.get("guest_satisfaction"), "rating_scale": 5,
        "review_count": int(rt["review_count"]) if rt.get("review_count") else None,
        "max_guests": d.get("person_capacity") or pg.get("max_guests_page"),
        "bedrooms": pg.get("bedrooms"), "beds": pg.get("beds"), "bed_layout": pg.get("bed_layout"),
        "room_option": None,
        "cancellation": (f"Ücretsiz iptal son gün: {pg['free_cancel_until']}" if pg.get("free_cancel_until")
                         else pg.get("cancellation")),
        "checkin_time": pg.get("checkin_time"),
        "low_reviews": low_reviews(reviews),
    }


# ---------- Booking ----------

def booking_address(text):
    # adres kutusu "…, Fransa" sonrasında harita/ulaşım metnini de içeriyor
    if not text:
        return None
    m = re.match(r"(.+?Fransa)", text.replace("\n", " "))
    return m.group(1).strip() if m else text.splitlines()[0]


def booking_options(rows):
    """Oda tablosu satırlarını seçeneklere çevirir; oda tipi hücresi rowspan'li, sonraki satırlar miras alır."""
    opts, room = [], None
    for t in rows:
        m_room = re.match(r"(.+?(?:Daire|Stüdyo|Oda|Suit|Apartman|Ev|Villa)[^0-9•]*)", t)
        if "Yatak Odası" in t or "m²" in t or (m_room and "Konuk sayısı" not in t[:5]):
            layout = re.findall(r"(Yatak Odası \d+: [^Y]+?)(?= Yatak Odası| Oturma| Özel| Banyo| Ortak|$|\d+ m²)", t)
            room = {
                "type": m_room.group(1).strip() if m_room else None,
                "bedrooms": len(re.findall(r"Yatak Odası \d+:", t)) or (1 if re.search(r"Tek Yatak Odalı|1 Yatak Odalı", t) else None),
                "layout": "; ".join(x.strip() for x in layout) or None,
            }
        cap = re.search(r"Azami kişi sayısı:\s*(\d+)", t)
        price = re.search(r"Fiyat\s*TL\s*([\d.]+)", t) or re.search(r"TL\s*([\d.]+)", t)
        tax = re.search(r"\+\s*TL\s*([\d.]+)\s*vergi", t)
        if not price:
            continue
        cancel = re.search(r"(\d{1,2} \w+ \d{4} öncesinde ücretsiz iptal|Ücretsiz iptal|İade edilmez|iade edilemez)", t)
        opts.append({
            **(room or {}), "max_guests": int(cap.group(1)) if cap else None,
            "price": tl(price.group(1)), "tax": tl(tax.group(1)) if tax else 0,
            "cancellation": cancel.group(1).strip() if cancel else None,
        })
    return opts


def from_booking(row, d):
    m = re.search(r"([\d,]+)\D+([\d.]+)\s*değerlendirme", d.get("score") or "")
    opts = booking_options(d.get("rooms") or [])
    fit = [o for o in opts if (o["max_guests"] or GUESTS) >= GUESTS]
    # önce 2+ yatak odalı seçenekler, sonra en ucuz vergi dahil toplam
    best = min(fit, key=lambda o: ((o.get("bedrooms") or 0) < 2, o["price"] + o["tax"])) if fit else None
    return {
        "lat": d.get("lat"), "lng": d.get("lng"), "location_precision": "exact",
        "title": (d.get("title") or row["gpt_name"]).split(",")[0], "address": booking_address(d.get("address")),
        "price_total_try": best["price"] + best["tax"] if best else None,
        "price_base_try": best["price"] if best else None, "price_tax_try": best["tax"] if best else None,
        "price_note": "vergi ve masraflar dahil" if best else "3 kişilik müsait seçenek bulunamadı",
        "rating": float(m.group(1).replace(",", ".")) if m else None, "rating_scale": 10,
        "review_count": int(m.group(2).replace(".", "")) if m else None,
        "max_guests": best["max_guests"] if best else None,
        "bedrooms": best.get("bedrooms") if best else None, "beds": None,
        "bed_layout": best.get("layout") if best else None,
        "room_option": best.get("type") if best else None,
        "cancellation": best.get("cancellation") if best else None, "checkin_time": None,
        "low_reviews": None,  # Booking yorum puanları henüz çekilmiyor
    }


# ---------- skor ----------

def lin(x, good, bad):
    """good'da 1, bad'de 0, arası doğrusal."""
    if x is None:
        return None
    return max(0.0, min(1.0, (x - bad) / (good - bad)))


def rooms_status(r):
    """2 ayrı (kapılı) yatak odası var mı? Salondaki çekyat/kanepe sayılmaz."""
    b, layout, notes = r.get("bedrooms") or 0, r.get("bed_layout") or "", (r.get("notes") or "").lower()
    if b < 2:
        return "yok"
    if layout.startswith("Yaşam alanı") or any(k in notes for k in ("asma kat", "kapısız", "geçiş alanı")):
        return "şüpheli"
    if re.search(r"2\. yatak odası|Yatak Odası 2", layout):
        return "onaylı"
    return "doğrulanmalı"


def score(r):
    """Öncelik sırası: 2 ayrı yatak odası > yorumlar + puan > ulaşım süresi > fiyat; bütçe üstü ve 40 dk üstü cezalı."""
    parts = {}
    parts["oda"] = {"onaylı": 40, "doğrulanmalı": 32, "şüpheli": 18, "yok": 0}[r["rooms_status"]]

    # az yorumlu ilanın puanı platform ortalamasına çekilir (15 sanal yorumluk ağırlık)
    rt, n = r.get("rating"), r.get("review_count") or 0
    prior, good, bad = (4.7, 4.95, 4.3) if r["rating_scale"] == 5 else (8.0, 9.2, 6.5)
    if rt:
        r["rating_adj"] = round((n * rt + 15 * prior) / (n + 15), 2)
        parts["puan"] = round(15 * lin(r["rating_adj"], good, bad))
    else:
        parts["puan"] = 5
    # kötü yorum cezası adet değil oran: son 2 yılın 3★ altı yorumları toplam yorumun %8'ine ulaşınca 0
    low = r.get("low_reviews")
    parts["yorum"] = 6 if low is None else round(10 * max(0.0, 1 - len(low) / max(n, 1) / 0.08))
    if "izinsiz giriş" in (r.get("notes") or ""):
        parts["yorum"] -= 5  # yorumlarda güvenlik iddiası

    t = r.get("transit_min")
    if t is not None:
        # kapıdan kapıya 15 dk → 20 puan, 40 dk → 0; 40 dk sonrası her dakika −0,5
        parts["ulaşım"] = round(20 * lin(t, 15, 40)) - (round((t - 40) * 0.5) if t > 40 else 0)
    else:
        parts["ulaşım"] = round(15 * (lin(r.get("dist_mines_km"), 3, 18) or 0))

    pr = r.get("price_total_try")
    if pr is None:
        parts["fiyat"] = 4
    elif pr <= BUDGET_TRY:
        parts["fiyat"] = round(3 + 12 * lin(pr, 45000, BUDGET_TRY))
    else:
        parts["fiyat"] = -min(15, round((pr - BUDGET_TRY) / 1000 * 2))  # bütçe üstü her 1.000 TL −2

    total = max(0, sum(parts.values()))
    if pr is None:
        total = min(total, 45)  # fiyatı/müsaitliği belli olmayan ilan üst sıralara çıkmasın
    return total, parts


def main():
    with (ROOT / "data" / "listings_input.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    ex = ROOT / "data" / "excluded.csv"  # kullanıcının elediği ilanlar; ham veri silinmez
    if ex.exists():
        with ex.open(encoding="utf-8") as f:
            excluded = {e["id"] for e in csv.DictReader(f)}
        rows = [r for r in rows if r["id"] not in excluded]
    stations = load_stations()
    transit = {}
    tf = ROOT / "data" / "transit_manual.csv"
    if tf.exists():
        with tf.open(encoding="utf-8") as f:
            transit = {t["id"]: t for t in csv.DictReader(f)}
    checked = {}
    cf = ROOT / "data" / "price_checked.csv"
    if cf.exists():
        with cf.open(encoding="utf-8") as f:
            checked = {c["id"]: c for c in csv.DictReader(f)}
    out = []
    for row in rows:
        src = ROOT / "raw" / row["platform"].lower() / f"{row['id']}.json"
        if not src.exists():
            continue
        d = json.loads(src.read_text(encoding="utf-8"))
        rec = {"id": row["id"], "platform": row["platform"], "url": row["url"], "notes": row.get("notes") or None}
        rec.update(from_airbnb(row, d) if row["platform"] == "Airbnb" else from_booking(row, d))
        if rec["lat"] is not None:
            rec["dist_mines_km"] = round(haversine_km(rec["lat"], rec["lng"], MINES["lat"], MINES["lng"]), 1)
            near = sorted(stations, key=lambda s: haversine_km(rec["lat"], rec["lng"], s["lat"], s["lng"]))[:3]
            rec["nearest_stations"] = [
                {"name": s["name"], "lines": s["lines"],
                 "dist_m": int(round(haversine_km(rec["lat"], rec["lng"], s["lat"], s["lng"]) * 1000, -1))} for s in near]
            rec["gmaps_transit_url"] = (
                "https://www.google.com/maps/dir/?api=1&travelmode=transit"
                f"&origin={rec['lat']},{rec['lng']}&destination={MINES['lat']},{MINES['lng']}")
        # fiyat: ödeme ekranında teyit edilen > ilan sayfası (Airbnb'de ödemede ~%15 ek çıkıyor → tahmini)
        rec["price_listed_try"] = rec["price_total_try"]
        pc = checked.get(row["id"])
        if pc:
            rec["price_total_try"], rec["price_source"] = int(pc["price_checkout_try"]), "ödeme ekranı ✓"
        elif rec["price_total_try"] is not None and row["platform"] == "Airbnb":
            rec["price_total_try"] = int(round(rec["price_total_try"] * AIRBNB_CHECKOUT_FACTOR, -1))
            rec["price_source"] = "tahmini (ilan fiyatı +%15)"
        else:
            rec["price_source"] = "ilan sayfası" if rec["price_total_try"] is not None else None
        t = transit.get(row["id"])
        rec["transit_min"] = int(t["transit_min"]) if t else None
        rec["transit_source"] = t["source"] if t else None
        rec["rooms_status"] = rooms_status(rec)
        rec["score"], rec["score_parts"] = score(rec)
        rec["over_budget"] = rec["price_total_try"] is not None and rec["price_total_try"] > BUDGET_TRY
        out.append(rec)
    out.sort(key=lambda r: -r["score"])
    for i, r in enumerate(out, 1):
        r["rank"] = i

    (ROOT / "data" / "listings_enriched.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    site = ROOT / "out" / "site"
    site.mkdir(parents=True, exist_ok=True)
    payload = {"mines": MINES, "budget": BUDGET_TRY, "total": len(rows), "listings": out, "lines": load_lines(),
               "stations": [{"n": s["name"], "a": round(s["lat"], 5), "o": round(s["lng"], 5), "l": s["lines"]} for s in stations]}
    (site / "data.js").write_text("window.PARIS_DATA=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";",
                                  encoding="utf-8")
    for r in out:
        ns = (r.get("nearest_stations") or [{}])[0]
        print(f"{r['rank']:>2} {r['id']} {r['score']:>3} {r['platform']:7} {r.get('dist_mines_km')}km {ns.get('name')} "
              f"{ns.get('dist_m')}m ₺{r['price_total_try']} oda={r['bedrooms']} puan={r['rating']}/{r['rating_scale']} "
              f"düşük={None if r['low_reviews'] is None else len(r['low_reviews'])} {r['score_parts']}")
    missing = {k: sum(1 for r in out if r.get(k) is None) for k in ("lat", "price_total_try", "bedrooms", "rating")}
    print(f"{len(out)}/{len(rows)} ilan · eksik: {missing} · data.js {(site / 'data.js').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
