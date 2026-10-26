"""Yolhanı statik site üreticisi.

data/yolhani.json dosyasından ana sayfa, 81 il sayfası, sitemap.xml ve robots.txt üretir.
Çıktı docs/ klasörüne yazılır (GitHub Pages bu klasörden yayın yapabilir).

Kullanım:
    python3 tools/build.py https://kullaniciadi.github.io/yolhani
Alan adı alınınca adresi değiştirip yeniden çalıştırmak yeterli:
    python3 tools/build.py https://yolhani.com
"""
import html
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://KULLANICIADI.github.io/yolhani").rstrip("/")
APP = "https://claude.ai/artifact/96B435W52N7zqGfSPT3tTZ"   # yorum ve puanların olduğu uygulama
TODAY = date.today().isoformat()
GSV = "nefGFNmlp75A9iaJx1VpqBjrkocaucwtCmEYyNWSkT4"   # Google Search Console doğrulama kodu (meta etiketindeki content değeri)

data = json.loads((ROOT / "data" / "yolhani.json").read_text(encoding="utf-8"))
CITIES = data["cities"]
KM_TYPES = {t["k"]: t for t in data["kmTypes"]}
MAP = data["map"]
LABELS = data["labels"]

e = lambda s: html.escape(str(s or ""), quote=True)

# Sayfada gösterilecek bölümler: anahtar kelime odaklı başlıklar (örn. "Antalya öğretmenevleri")
SECTIONS = [
    ("ogretmenevi", "Öğretmenevleri", lambda p: p["tk"] == "ogr"),
    ("kamp", "Kamp alanları ve tabiat parkları", lambda p: p["tk"] == "kamp"),
    ("pansiyon", "Pansiyon ve hosteller", lambda p: p["tk"] == "pans"),
    ("belediye", "Belediye tesisleri ve uygulama otelleri", lambda p: p["tk"] in ("bel", "uyg")),
    ("misafirhane", "Kamu misafirhaneleri (DSİ, PTT, Karayolları ve diğerleri)",
     lambda p: p["tk"] not in ("ogr", "kamp", "pans", "bel", "uyg", "pol", "ord", "adl")),
    ("mensup", "Polisevi, orduevi ve adliye tesisleri", lambda p: p["tk"] in ("pol", "ord", "adl")),
]


def schema_type(p):
    if p["tk"] == "kamp":
        return "Campground"
    if p["tk"] == "pans" and p["badge"] == "Hostel":
        return "Hostel"
    return "LodgingBusiness"


def place_ld(p, city):
    d = {"@type": schema_type(p), "name": p["name"],
         "address": {"@type": "PostalAddress", "addressRegion": city, "addressCountry": "TR"}}
    if p["ilce"]:
        d["address"]["addressLocality"] = p["ilce"]
    if p["addr"]:
        d["address"]["streetAddress"] = p["addr"]
    if p["tel"]:
        d["telephone"] = p["tel"]
    if p["lat"]:
        d["geo"] = {"@type": "GeoCoordinates", "latitude": p["lat"], "longitude": p["lon"]}
    return d


def head(title, desc, path, extra_ld=()):
    url = f"{BASE}/{path}"
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in extra_ld)
    rel = "../" * path.count("/")
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Yolhanı">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:locale" content="tr_TR">
<meta name="theme-color" content="#6b4426">
{f'<meta name="google-site-verification" content="{e(GSV)}">' if GSV else ""}
<link rel="icon" href="{rel}assets/icon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@500;700&family=Work+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{rel}assets/site.css">
{lds}
</head>
<body>
<header class="top"><div class="in">
  <a class="brand" href="{rel or './'}"><span class="mark" aria-hidden="true">{ARCH}</span>Yolhanı</a>
  <nav><a href="{rel}#iller">İller</a><a href="{APP}" rel="noopener">Yorum yaz</a><a href="{rel}hakkinda/">Hakkında</a></nav>
</div></header>
<main class="wrap">
"""


ARCH = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" '
        'stroke-linecap="round"><path d="M4 21V11a8 8 0 0 1 16 0v10"/><path d="M9 21v-6a3 3 0 0 1 6 0v6"/><path d="M2 21h20"/></svg>')


def foot(rel):
    links = " ".join(f'<a href="{rel}{k}/">{e(c["name"])}</a>' for k, c in sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"])))
    return f"""</main>
<footer class="foot"><div class="in">
  <p class="allcities"><b>Tüm iller:</b> {links}</p>
  <p>Veri: kamumisafirhaneleri.com.tr · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap katkıcıları</a> (ODbL) · gezgin yorumları.
  Bilgiler değişebilir; gitmeden önce tesisi arayıp sivil kabul ve fiyatı sor. Son güncelleme: {TODAY}.</p>
</div></footer>
</body>
</html>
"""


TR_ORDER = "abcçdefgğhıijklmnoöprsştuüvyz"


def tr_key(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return [TR_ORDER.index(ch) if ch in TR_ORDER else 100 + ord(ch) for ch in s]


def place_li(p):
    meta = " · ".join(x for x in [p["badge"] or p["type"], p["ilce"]] if x)
    bits = [f'<h3>{e(p["name"])}</h3>', f'<p class="meta">{e(meta)}</p>']
    if p["whoText"]:
        bits.append(f'<p class="who {e(p["who"])}">{e(p["whoText"])}</p>')
    if p["note"]:
        bits.append(f'<p>{e(p["note"])}</p>')
    dl = ""
    if p["addr"]:
        dl += f'<dt>Adres</dt><dd>{e(p["addr"])}</dd>'
    if p["tel"]:
        tel = re.sub(r"\D", "", p["tel"])
        tel = "+90" + tel.lstrip("0")
        dl += f'<dt>Telefon</dt><dd><a href="tel:{tel}">{e(p["tel"])}</a></dd>'
    if dl:
        bits.append(f"<dl>{dl}</dl>")
    links = f'<a href="{e(p["map"])}" rel="noopener">Haritada aç</a>'
    if p["src"]:
        links += f' · <a href="{e(p["src"])}" rel="noopener nofollow">{e(p["srcLabel"] or "Kaynak")}</a>'
    bits.append(f'<p class="links">{links}</p>')
    return f'<li class="place">{"".join(bits)}</li>'


def city_page(key, c):
    name, loc, places = c["name"], c["loc"], c["places"]
    n = len(places)
    cnt = Counter(p["tk"] for p in places)
    kamu = sum(v for k, v in cnt.items() if k not in ("kamp", "pans", "gezgin"))
    free_camps = sum(1 for p in places if p["tk"] == "kamp" and p["note"].startswith("Ücretsiz"))
    title = f"{loc} Ucuz Konaklama: Öğretmenevi, Misafirhane, Kamp | Yolhanı"
    desc = (f"{loc} {n} ucuz konaklama yeri: {cnt['ogr']} öğretmenevi, {kamu - cnt['ogr']} kamu misafirhanesi "
            f"(DSİ, PTT, Karayolları…), {cnt['kamp']} kamp alanı, {cnt['pans']} pansiyon ve hostel. Adres, telefon ve gezgin yorumları.")

    # Sık sorulan sorular: hem okuyucu hem Google için
    ogr_avg, dsi_avg = KM_TYPES["ogr"]["sivil"], KM_TYPES["dsi"]["sivil"]
    faq = [
        (f"{loc} öğretmenevinde sivil kalınabilir mi?",
         f"{loc} {cnt['ogr']} öğretmenevi var. Öğretmenevlerinde öncelik öğretmenlerindir; boş oda varsa çoğu sivil misafir de kabul eder, "
         f"ancak sivil fiyatı daha yüksektir. Gitmeden önce telefonla arayıp sor.") if cnt["ogr"] else None,
        (f"{loc} ücretsiz kamp alanı var mı?",
         (f"OpenStreetMap verisine göre {loc} {cnt['kamp']} kamp alanı var; bunlardan {free_camps} tanesi ücretsiz olarak işaretli. "
          if cnt["kamp"] else f"{loc} kayıtlı kamp alanı henüz yok. ")
         + "Serbest kampta orman ve koruma alanı kurallarına dikkat et."),
        (f"{name} kamu misafirhanesi fiyatları ne kadar?",
         f"Kaynak sitenin 2026 ortalamasına göre sivil misafirler için öğretmenevlerinde gecelik ~{ogr_avg} TL'den, "
         f"DSİ misafirhanelerinde ~{dsi_avg} TL'den başlıyor. Gerçek fiyat tesise göre değişir; gezgin yorumlarındaki ödenen ücretlere bak."),
    ]
    faq = [f for f in faq if f]

    secs = []
    toc = []
    for sid, label, pred in SECTIONS:
        items = sorted([p for p in places if pred(p)], key=lambda p: (tr_key(p["ilce"] or "zzz"), tr_key(p["name"])))
        if not items:
            continue
        h = f"{name} {label[0].lower() + label[1:]}" if sid != "mensup" else label
        toc.append(f'<a href="#{sid}">{e(label)} <span>{len(items)}</span></a>')
        secs.append(f'<section id="{sid}"><h2>{e(h)}</h2><ul class="places">{"".join(place_li(p) for p in items)}</ul></section>')

    ld = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{key}/"}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"{loc} ucuz konaklama", "numberOfItems": n,
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": place_ld(p, name)} for i, p in enumerate(places[:200])]},
    ]
    body = f"""<nav class="crumbs"><a href="../">Yolhanı</a> › {e(name)}</nav>
<section class="hero">
  <h1>{e(loc)} ucuz konaklama</h1>
  <p>{e(desc)}</p>
  {f'<p class="note">{e(c["note"])}</p>' if c["note"] else ""}
  <p><a class="cta" href="{APP}#{key}" rel="noopener">{e(name)} için puanları ve yorumları gör</a></p>
</section>
<nav class="toc" aria-label="Bölümler">{"".join(toc)}</nav>
{"".join(secs)}
<section id="sss"><h2>Sık sorulan sorular</h2>
{"".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)}
</section>
"""
    return head(title, desc, f"{key}/", ld) + body + foot("../")


def home_page():
    total = sum(len(c["places"]) for c in CITIES.values())
    kamu = sum(1 for c in CITIES.values() for p in c["places"] if p["tk"] not in ("kamp", "pans"))
    kamp = sum(1 for c in CITIES.values() for p in c["places"] if p["tk"] == "kamp")
    pans = sum(1 for c in CITIES.values() for p in c["places"] if p["tk"] == "pans")
    title = "Yolhanı: Türkiye'de Ucuz Konaklama Haritası (Öğretmenevi, Misafirhane, Kamp)"
    n = lambda x: f"{x:,}".replace(",", ".")
    desc = (f"81 ilde {n(total)} ucuz konaklama yeri: {n(kamu)} öğretmenevi ve kamu misafirhanesi, {n(kamp)} kamp alanı, "
            f"{n(pans)} pansiyon ve hostel. Gezginlerin fiyat, temizlik ve sivil kabul yorumları.")
    # Tıklanabilir Türkiye haritası: her il kendi sayfasına gider
    slug_of = {c["name"]: k for k, c in CITIES.items()}
    paths = "".join(f'<a href="{slug_of[n]}/" aria-label="{e(n)}"><path d="{d}"><title>{e(n)} · {len(CITIES[slug_of[n]]["places"])} yer</title></path></a>'
                    for n, d in MAP["il"].items())
    labels = "".join(
        f'<text x="{x}" y="{y}" font-size="{max(4, min(8.5, r * .55)):.1f}"><tspan x="{x}" dy="-0.15em">{e(n)}</tspan>'
        f'<tspan class="n" x="{x}" dy="1.1em">{len(CITIES[slug_of[n]]["places"])}</tspan></text>'
        for n, (x, y, r) in LABELS.items())
    cities = sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"]))
    lis = "".join(f'<li><a href="{k}/">{e(c["name"])}</a> <span>{len(c["places"])}</span></li>' for k, c in cities)
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "Yolhanı", "url": f"{BASE}/", "inLanguage": "tr"}]
    tr_num = lambda n: f"{n:,}".replace(",", ".")
    body = f"""<section class="hero">
  <p class="kicker">Yol üstündeki ucuz konaklama</p>
  <h1>Türkiye'de otelden ucuza nerede kalınır?</h1>
  <p>{e(desc)}</p>
  <dl class="stats"><div><dt>İl</dt><dd>81</dd></div><div><dt>Yer</dt><dd>{tr_num(total)}</dd></div><div><dt>Kamu misafirhanesi</dt><dd>{tr_num(kamu)}</dd></div><div><dt>Kamp alanı</dt><dd>{kamp}</dd></div></dl>
  <p><a class="cta" href="{APP}" rel="noopener">Haritalı uygulamayı aç: puanla, yorum yaz</a></p>
</section>
<section class="map"><h2>Haritadan il seç</h2>
<div class="mapscroll"><svg viewBox="0 0 {MAP['w']} {MAP['h']}" role="img" aria-label="Türkiye il haritası">{paths}<g class="labels">{labels}</g></svg></div>
</section>
<section id="iller"><h2>İllere göre ucuz konaklama</h2><ul class="cities">{lis}</ul></section>
<section><h2>Hangi yerlerde kalabilirsin?</h2>
<p>Öğretmenevleri, DSİ, PTT, Karayolları ve belediye misafirhaneleri, üniversite konukevleri ve meslek liselerinin uygulama otelleri çoğu zaman otelden ucuzdur.
Kamu personeline öncelik verirler; boş oda varsa birçoğu sivil misafir de kabul eder. Kamp alanları, tabiat parkları, pansiyon ve hosteller ise herkese açıktır.</p>
</section>
"""
    return head(title, desc, "", ld) + body + foot("")


def about_page():
    title = "Hakkında | Yolhanı"
    desc = "Yolhanı, gezenlerin otel yerine kalabileceği ucuz yerleri tek haritada toplar. Veri kaynakları ve nasıl çalıştığı."
    body = f"""<nav class="crumbs"><a href="../">Yolhanı</a> › Hakkında</nav>
<section class="hero"><h1>Hakkında</h1>
<p>Yolhanı, gezenlerin otel yerine kalabileceği ucuz yerleri tek yerde toplar: öğretmenevleri, DSİ, PTT, Karayolları ve belediye misafirhaneleri, üniversite konukevleri, kamp alanları, pansiyon ve hosteller.</p>
<p>Adı eski yol hanlarından geliyor: kervanların ve yolcuların ucuza gecelediği, yol üstündeki konaklama yerleri.</p></section>
<section><h2>Nasıl çalışır?</h2>
<p>Kaldığın yeri <a href="{APP}" rel="noopener">uygulamada</a> puanla: genel, temizlik ve güvenlik. Ödediğin ücreti, sivil olarak kabul edilip edilmediğini ve yerin hâlâ açık olup olmadığını yaz. Sonraki gezgin buna göre karar verir.</p></section>
<section><h2>Veri kaynakları</h2>
<ul><li>Kamu misafirhaneleri: kamumisafirhaneleri.com.tr il listeleri</li>
<li>Kamp alanları, pansiyon ve hosteller: <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap katkıcıları</a>, ODbL lisansı</li>
<li>İl sınırları: tr-geojson (cihadturhan)</li>
<li>Fiyat, temizlik ve sivil kabul bilgisi: gezgin yorumları</li></ul></section>
"""
    return head(title, desc, "hakkinda/") + body + foot("../")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "site.css", OUT / "assets" / "site.css")
    (OUT / "assets" / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#6b4426"/>'
        '<g transform="translate(4 4)" fill="none" stroke="#fdfbf7" stroke-width="2.4" stroke-linecap="round">'
        '<path d="M4 21V11a8 8 0 0 1 16 0v10"/><path d="M9 21v-6a3 3 0 0 1 6 0v6"/><path d="M2 21h20"/></g></svg>', encoding="utf-8")
    (OUT / "index.html").write_text(home_page(), encoding="utf-8")
    (OUT / "hakkinda").mkdir()
    (OUT / "hakkinda" / "index.html").write_text(about_page(), encoding="utf-8")
    urls = [f"{BASE}/", f"{BASE}/hakkinda/"]
    for key, c in CITIES.items():
        (OUT / key).mkdir()
        (OUT / key / "index.html").write_text(city_page(key, c), encoding="utf-8")
        urls.append(f"{BASE}/{key}/")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    # 404 sayfası her adreste açılabildiği için bağlantılar sitenin tam adresiyle yazılır
    page404 = (head("Sayfa bulunamadı | Yolhanı", "Aradığın sayfa bulunamadı.", "404.html")
               + f'<section class="hero"><h1>Sayfa bulunamadı</h1><p><a href="{BASE}/">Ana sayfaya dön</a> ve haritadan il seç.</p></section>'
               + foot(f"{BASE}/"))
    page404 = page404.replace('href="assets/', f'href="{BASE}/assets/').replace('href="#iller"', f'href="{BASE}/#iller"') \
                     .replace('href="hakkinda/"', f'href="{BASE}/hakkinda/"').replace('href="./"', f'href="{BASE}/"')
    (OUT / "404.html").write_text(page404, encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"{len(urls)} sayfa üretildi → {OUT}")


if __name__ == "__main__":
    main()
