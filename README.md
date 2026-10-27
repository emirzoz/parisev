# Paris konaklama — Mines Paris'e yakın ev araştırması

13–22 Kasım 2026, 9 gece, 3 kişi için 25 Airbnb / Booking ilanının karşılaştırması.
Hedef: Mines Paris – PSL, 60 Boulevard Saint-Michel.

**Site:** https://emirzoz.github.io/parisev/ — metro/RER/tramvay hatlı harita, skora göre renkli ilanlar, kartlarda fiyat, oda düzeni, ulaşım süresi ve düşük puanlı yorumlar.
**Tablo:** [`out/Paris_konaklama_v2.xlsx`](out/Paris_konaklama_v2.xlsx)

## Skor (100 üzerinden, önem sırasıyla)
1. 2 ayrı yatak odası — 40 (salondaki çekyat sayılmaz; oda dökümü yoksa 32, şüpheliyse 18)
2. Puan 15 + yorumlar 10 (son 2 yılın her 3★ altı yorumu −2,5; yorumlarda izinsiz giriş iddiası −5)
3. Mines'e kapıdan kapıya süre — 20 (15 dk tam, 55 dk sıfır, 1 saat üstü −5)
4. Ödeme ekranındaki vergi dahil fiyat — 15

## Veri kaynakları
- Airbnb: [`pyairbnb`](https://pypi.org/project/pyairbnb/) + ilan sayfası (Playwright). Konumlar Airbnb'nin kaydırdığı yaklaşık konum.
- Booking: ilan sayfası (Playwright), kesin adres.
- Fiyatlar ve ulaşım süreleri: elle teyit edildi (`data/price_checked.csv`, `data/transit_manual.csv`).
- Hatlar ve istasyonlar: Île-de-France Mobilités açık verisi. Sınırlar: geo.api.gouv.fr. Nehirler: © OpenStreetMap.

## Yeniden üretmek
```
py -m venv .venv && .venv\Scripts\pip install -r requirements.txt
py scripts/00_fetch_geo.py      # harita altlığı
py scripts/01_extract_input.py  # Paris_27_Ilan.xlsx → data/listings_input.csv
py scripts/02_airbnb.py; py scripts/02b_airbnb_page.py; py scripts/03_booking.py   # → raw/ (repoda yok)
py scripts/03b_images.py        # kapak fotoğrafları
py scripts/04_geo.py            # birleştir + skor
py scripts/05_build_xlsx.py; py scripts/06_build_site.py   # Excel + site (docs/)
```
Ham veri (`raw/`) yorumcu bilgileri içerdiği için repoya konmadı.
