"""Yolhanı statik site üreticisi.

data/yolhani.json dosyasından ana sayfa, 81 il sayfası, 4 rehber sayfası, hakkında,
sitemap.xml, robots.txt ve manifest üretir. Çıktı docs/ klasörüne yazılır
(GitHub Pages bu klasörden yayın yapar). Paylaşım görselleri tools/og.py ile docs/og/ altına üretilir
ve yeniden üretimde silinmez.

Kullanım:
    python3 tools/build.py https://hkblackbird.github.io/yolhani
    python3 tools/og.py            # paylaşım görsellerini (yeniden) üretmek için
Alan adı alınınca adresi değiştirip yeniden çalıştırmak yeterli:
    python3 tools/build.py https://yolhani.com
"""
import html
import json
import math
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://hkblackbird.github.io/yolhani").rstrip("/")
APP = "https://claude.ai/artifact/96B435W52N7zqGfSPT3tTZ"   # yorum ve puanların olduğu uygulama
REPO = "https://github.com/hkblackbird/yolhani"
TODAY = date.today()
GSV = "nefGFNmlp75A9iaJx1VpqBjrkocaucwtCmEYyNWSkT4"   # Google Search Console doğrulama kodu
AYLAR = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
TODAY_TR = f"{TODAY.day} {AYLAR[TODAY.month - 1]} {TODAY.year}"

data = json.loads((ROOT / "data" / "yolhani.json").read_text(encoding="utf-8"))
CITIES = data["cities"]
KM_TYPES = {t["k"]: t for t in data["kmTypes"]}
MAP = data["map"]
LABELS = data["labels"]
TYPES = {t["name"]: t for t in data["types"]}

e = lambda s: html.escape(str(s or ""), quote=True)
num = lambda n: f"{n:,}".replace(",", ".")
TR_ORDER = "abcçdefgğhıijklmnoöprsştuüvyz"


def tr_key(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    return [TR_ORDER.index(ch) if ch in TR_ORDER else 100 + ord(ch) for ch in s]


# ---------- Türler ----------
# Her yer bir gruba girer; il sayfasındaki bölümler ve rehber sayfaları bu gruplardan oluşur.
GROUPS = [
    # anahtar, bölüm başlığı, kısa ad, ikon, eşleşen tür kodları
    ("ogretmenevi", "Öğretmenevleri", "Öğretmenevi", "ogr", {"ogr"}),
    ("kamp", "Kamp alanları ve tabiat parkları", "Kamp alanı", "kamp", {"kamp"}),
    ("pansiyon", "Pansiyon ve hosteller", "Pansiyon / hostel", "pans", {"pans"}),
    ("belediye", "Belediye tesisleri ve uygulama otelleri", "Belediye / uygulama oteli", "bel", {"bel", "uyg"}),
    ("misafirhane", "Kamu misafirhaneleri", "Kamu misafirhanesi", "kamu",
     {"dsi", "ptt", "kgm", "met", "tcdd", "ogm", "uni", "dhmi", "oz", "mal", "teias", "kamu", "gezgin"}),
    ("mensup", "Polisevi, orduevi ve adliye tesisleri", "Mensup tesisi", "mensup", {"pol", "ord", "adl"}),
]
GROUP_OF = {k: g for g in GROUPS for k in g[4]}

ICONS = {
    "ogr": '<path d="M2 9.5 12 4.5l10 5-10 5z"/><path d="M6 11.5v5c3.5 2.2 8.5 2.2 12 0v-5"/>',
    "kamp": '<path d="M2.5 20h19"/><path d="M12 4 3.5 20"/><path d="m12 4 8.5 16"/><path d="m12 13-3 7"/><path d="m12 13 3 7"/>',
    "pans": '<path d="M3 19V7"/><path d="M3 15h18v4"/><path d="M21 15v-2.5a3 3 0 0 0-3-3h-7V15"/><circle cx="7" cy="12" r="1.6"/>',
    "bel": '<path d="M3 21h18"/><path d="M5 21V10h14v11"/><path d="m3 10 9-6 9 6"/><path d="M10 21v-5h4v5"/>',
    "kamu": '<path d="M2 21h20"/><path d="M4 21V7l8-4 8 4v14"/><path d="M8 10h2M14 10h2M8 14h2M14 14h2"/><path d="M10 21v-3h4v3"/>',
    "mensup": '<path d="M12 3 20 6v6c0 4.8-3.4 7.8-8 9-4.6-1.2-8-4.2-8-9V6z"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.4"/>',
    "phone": '<path d="M5 3h3.5l1.8 4.5-2.3 1.4a11 11 0 0 0 5.1 5.1l1.4-2.3L19 13.5V17a2 2 0 0 1-2 2A15 15 0 0 1 3 5a2 2 0 0 1 2-2z"/>',
    "route": '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8 18h6.5a3.5 3.5 0 0 0 0-7h-5a3.5 3.5 0 0 1 0-7H16"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
    "arch": '<path d="M4 21V11a8 8 0 0 1 16 0v10"/><path d="M9 21v-6a3 3 0 0 1 6 0v6"/><path d="M2 21h20"/>',
}
SPRITE = '<svg width="0" height="0" style="position:absolute" aria-hidden="true">' + "".join(
    f'<symbol id="i-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{v}</symbol>'
    for k, v in ICONS.items()) + "</svg>"
icon = lambda k, cls="ic": f'<svg class="{cls}" aria-hidden="true"><use href="#i-{k}"/></svg>'

# Ülke çapında rehber sayfaları
HUBS = [
    ("ogretmenevleri", "ogretmenevi", "Öğretmenevleri", "Öğretmenevi rehberi: 81 ilde öğretmenevleri, sivil kabul ve fiyatlar",
     "Öğretmenevleri", "ogr"),
    ("kamp-alanlari", "kamp", "Kamp alanları", "Türkiye kamp alanları: 81 ilde çadır ve karavan kamp yerleri",
     "Tabiat parkı kamp alanları", "kamp"),
    ("kamu-misafirhaneleri", "misafirhane", "Kamu misafirhaneleri", "Kamu misafirhaneleri: DSİ, PTT, Karayolları ve diğerleri",
     "DSİ misafirhaneleri", "dsi"),
    ("pansiyon-hostel", "pansiyon", "Pansiyon ve hosteller", "Ucuz pansiyon ve hosteller: 81 ilde liste",
     "Hostel, pansiyon ve köy evleri", None),
]


def issue_url(title, body):
    return f"{REPO}/issues/new?title={quote(title)}&body={quote(body)}"


def neighbours(name, k=6):
    x0, y0, _ = LABELS[name]
    near = sorted(LABELS, key=lambda n: math.hypot(LABELS[n][0] - x0, LABELS[n][1] - y0))
    return [n for n in near if n != name][:k]


SLUG = {c["name"]: k for k, c in CITIES.items()}
COUNT = {k: len(c["places"]) for k, c in CITIES.items()}
POPULAR = sorted(CITIES, key=lambda k: -COUNT[k])[:8]


# ---------- Sayfa iskeleti ----------
def search_box(rel, cls="", ph="İl, ilçe ya da yer ara"):
    return (f'<form class="q {cls}" action="{rel or "./"}" role="search"><label class="field">{icon("search")}'
            f'<input type="search" placeholder="{ph}" aria-label="İl, ilçe ya da yer ara" autocomplete="off" '
            f'role="combobox" aria-expanded="false" aria-autocomplete="list"></label>'
            f'<div class="dd" role="listbox" hidden></div></form>')


def head(title, desc, path, ld=(), og=None, search=True):
    rel = "../" * path.count("/")
    url = f"{BASE}/{path}"
    og_img = f"{BASE}/og/{og or 'yolhani'}.jpg"
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Yolhanı">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(og_img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="tr_TR">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#6b4426">
<meta name="google-site-verification" content="{e(GSV)}">
<link rel="icon" href="{rel}assets/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{rel}assets/apple-touch-icon.png">
<link rel="manifest" href="{rel}manifest.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@600;700&family=Work+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{rel}assets/site.css">
{lds}
</head>
<body>
{SPRITE}
<a class="skip" href="#icerik">İçeriğe geç</a>
<header class="top"><div class="in">
  <a class="brand" href="{rel or './'}"><span class="mark">{icon("arch")}</span>Yolhanı</a>
  {search_box(rel, "top-q") if search else ""}
  <nav aria-label="Ana menü">
    <a href="{rel}ogretmenevleri/">Öğretmenevleri</a>
    <a href="{rel}kamu-misafirhaneleri/">Misafirhaneler</a>
    <a href="{rel}kamp-alanlari/">Kamp alanları</a>
    <a href="{rel}pansiyon-hostel/">Pansiyonlar</a>
  </nav>
</div></header>
<main id="icerik" class="wrap">
"""


def foot(rel):
    pop = "".join(f'<li><a href="{rel}{k}/">{e(CITIES[k]["name"])}</a></li>' for k in POPULAR)
    allc = " ".join(f'<a href="{rel}{k}/">{e(c["name"])}</a>' for k, c in sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"])))
    return f"""</main>
<footer class="foot">
  <div class="in cols">
    <div class="about"><a class="brand" href="{rel or './'}"><span class="mark">{icon("arch")}</span>Yolhanı</a>
      <p>Yol üstündeki ucuz konaklama. Öğretmenevi, kamu misafirhanesi, kamp alanı ve pansiyonlar tek haritada; fiyat, temizlik ve sivil kabul bilgisini gezginler yazıyor.</p></div>
    <div><h2>Rehberler</h2><ul>
      <li><a href="{rel}ogretmenevleri/">Öğretmenevleri</a></li><li><a href="{rel}kamp-alanlari/">Kamp alanları</a></li>
      <li><a href="{rel}kamu-misafirhaneleri/">Kamu misafirhaneleri</a></li><li><a href="{rel}pansiyon-hostel/">Pansiyon ve hosteller</a></li></ul></div>
    <div><h2>Popüler iller</h2><ul>{pop}</ul></div>
    <div><h2>Yolhanı</h2><ul>
      <li><a href="{rel}hakkinda/">Hakkında</a></li><li><a href="{APP}" rel="noopener">Puan ver ve yorum yaz</a></li>
      <li><a href="{issue_url("Bilgi düzeltme", "Hangi sayfa ve hangi yer?\n\nDoğru bilgi:\n")}" rel="noopener">Hata bildir</a></li>
      <li><a href="{REPO}" rel="noopener">GitHub</a></li></ul></div>
  </div>
  <div class="in allcities"><h2>Tüm iller</h2><p>{allc}</p></div>
  <div class="in legal"><p>Veri: kamumisafirhaneleri.com.tr il listeleri · <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a> (ODbL) · gezgin yorumları.
  Bilgiler değişebilir; gitmeden önce tesisi arayıp sivil kabul ve fiyatı sor. Son güncelleme: {TODAY_TR}.</p></div>
</footer>
<script src="{rel}assets/ara.js" data-root="{rel}" defer></script>
</body>
</html>
"""


# ---------- Yer kartı ----------
def place_card(p, city):
    g = GROUP_OF.get(p["tk"], GROUPS[4])
    label = p["badge"] or (KM_TYPES[p["tk"]]["label"] if p["tk"] in KM_TYPES else g[2])
    who = f'<span class="who {e(p["who"])}">{e(p["whoText"])}</span>' if p["whoText"] else ""
    tel = ""
    if p["tel"]:
        digits = re.sub(r"\D", "", p["tel"]).lstrip("0")
        tel = f'<a class="act" href="tel:+90{digits}">{icon("phone")}{e(p["tel"])}</a>'
    m = re.search(r"~([\d.]+) TL", p["note"])
    price = f' · <span class="price" title="Kaynak sitenin sivil misafir için gecelik ortalaması">sivil ~{m.group(1)} TL/gece</span>' if m else ""
    note = "" if m else p["note"]
    fix = issue_url(f"Düzeltme: {p['name']} ({city})",
                    f"Yer: {p['name']}\nİl: {city}\nİlçe: {p['ilce']}\n\nYanlış olan bilgi:\n\nDoğrusu:\n")
    text = " ".join([p["name"], p["ilce"], p["addr"], label]).lower()
    return f"""<li class="place" id="p-{e(p["id"])}" data-ilce="{e(p["ilce"])}" data-q="{e(text)}">
  <div class="ph"><span class="ticon t-{g[3]}">{icon(g[3])}</span><div><h3>{e(p["name"])}</h3>
  <p class="meta">{e(label)}{f" · {e(p['ilce'])}" if p["ilce"] else ""}{price}</p></div></div>
  {who}
  {f'<p class="note">{e(note)}</p>' if note else ""}
  {f'<p class="addr">{icon("pin")}{e(p["addr"])}</p>' if p["addr"] else ""}
  <div class="acts">{tel}<a class="act" href="{e(p["map"])}" rel="noopener">{icon("route")}Yol tarifi</a>
  <a class="fix" href="{e(fix)}" rel="noopener nofollow" title="Bu yerin bilgisi hatalıysa bildir">Düzelt</a></div>
</li>"""


def place_ld(p, city):
    t = "Campground" if p["tk"] == "kamp" else "Hostel" if p["badge"] == "Hostel" else "LodgingBusiness"
    d = {"@type": t, "name": p["name"], "address": {"@type": "PostalAddress", "addressRegion": city, "addressCountry": "TR"}}
    if p["ilce"]:
        d["address"]["addressLocality"] = p["ilce"]
    if p["addr"]:
        d["address"]["streetAddress"] = p["addr"]
    if p["tel"]:
        d["telephone"] = p["tel"]
    if p["lat"]:
        d["geo"] = {"@type": "GeoCoordinates", "latitude": p["lat"], "longitude": p["lon"]}
    return d


# ---------- İl sayfası ----------
FILTER_JS = """<script>
(() => {
  const q = document.getElementById("f-q"), sel = document.getElementById("f-ilce"), out = document.getElementById("f-n");
  if (!q) return;
  const items = [...document.querySelectorAll(".place")];
  const run = () => {
    const t = q.value.trim().toLocaleLowerCase("tr"), d = sel.value; let n = 0;
    for (const li of items) { const ok = (!d || li.dataset.ilce === d) && (!t || li.dataset.q.includes(t)); li.hidden = !ok; n += ok; }
    for (const s of document.querySelectorAll("section.group")) s.hidden = !s.querySelector(".place:not([hidden])");
    out.textContent = (t || d) ? n + " yer gösteriliyor" : "";
  };
  q.addEventListener("input", run); sel.addEventListener("change", run);
  document.getElementById("filters").hidden = false;
  const ps = new URLSearchParams(location.search), il = ps.get("ilce");
  if (il && [...sel.options].some(o => o.value === il)) sel.value = il; else if (il) q.value = il;
  if (ps.get("q")) q.value = ps.get("q");
  if (il || ps.get("q")) run();
})();
</script>"""


def city_page(key, c):
    name, loc, places = c["name"], c["loc"], c["places"]
    n = len(places)
    by_group = {g[0]: [p for p in places if GROUP_OF.get(p["tk"], GROUPS[4])[0] == g[0]] for g in GROUPS}
    cnt = {k: len(v) for k, v in by_group.items()}
    kamu = cnt["misafirhane"] + cnt["belediye"]
    free = sum(1 for p in by_group["kamp"] if p["note"].startswith("Ücretsiz"))
    ilceler = Counter(p["ilce"] for p in places if p["ilce"] and p["ilce"] != "Merkez")
    top = ilceler.most_common(3)

    title = f"{loc} Ucuz Konaklama: Öğretmenevi, Misafirhane, Kamp | Yolhanı"
    desc = (f"{loc} {n} ucuz konaklama yeri: {cnt['ogretmenevi']} öğretmenevi, {kamu} kamu misafirhanesi (DSİ, PTT, Karayolları…), "
            f"{cnt['kamp']} kamp alanı, {cnt['pansiyon']} pansiyon ve hostel. Adres, telefon ve gezgin yorumları.")
    # O ilin verisinden yazılan, her ilde farklı giriş metni
    intro = [f"{loc} otel yerine kalabileceğin {n} yer listeleniyor."]
    if top:
        intro.append("En çok seçenek " + ", ".join(f"{i} ({k})" for i, k in top[:-1]) +
                     (" ve " if len(top) > 1 else "") + f"{top[-1][0]} ({top[-1][1]}) ilçelerinde.")
    if cnt["ogretmenevi"]:
        intro.append(f"{cnt['ogretmenevi']} öğretmenevi boş oda olduğunda sivil misafir de kabul edebilir.")
    if cnt["kamp"]:
        intro.append(f"{cnt['kamp']} kamp alanından {free} tanesi ücretsiz olarak işaretli." if free else f"{cnt['kamp']} kamp alanı var.")
    if c["note"]:
        intro.append(c["note"])

    ogr_avg, dsi_avg = KM_TYPES["ogr"]["sivil"], KM_TYPES["dsi"]["sivil"]
    faq = [f for f in [
        (f"{loc} öğretmenevinde sivil kalınabilir mi?",
         f"{loc} {cnt['ogretmenevi']} öğretmenevi var. Öncelik öğretmenlerindir; boş oda varsa çoğu öğretmenevi sivil misafir de kabul eder, "
         "ancak sivil fiyatı daha yüksektir. Gitmeden önce telefonla arayıp sor.") if cnt["ogretmenevi"] else None,
        (f"{loc} ücretsiz kamp alanı var mı?",
         (f"OpenStreetMap verisine göre {loc} {cnt['kamp']} kamp alanı var; bunlardan {free} tanesi ücretsiz olarak işaretli. "
          if cnt["kamp"] else f"{loc} kayıtlı kamp alanı henüz yok. ") + "Serbest kampta orman ve koruma alanı kurallarına dikkat et."),
        (f"{name} kamu misafirhanesi fiyatları ne kadar?",
         f"Kaynak sitenin 2026 ortalamasına göre sivil misafirler için öğretmenevlerinde gecelik ~{ogr_avg} TL'den, "
         f"DSİ misafirhanelerinde ~{dsi_avg} TL'den başlıyor. Gerçek fiyat tesise göre değişir; gezgin yorumlarındaki ödenen ücretlere bak."),
        (f"{loc} kamu misafirhanesinde kimler kalabilir?",
         "Kamu misafirhanelerinde öncelik o kurumun ve diğer kurumların personeline verilir. Polisevi, orduevi ve adliye tesisleri "
         "çoğunlukla sadece mensuplarına açıktır. Belediye tesisleri ve meslek liselerinin uygulama otelleri genelde herkese açıktır."),
    ] if f]

    toc, secs = [], []
    for gk, label, short, ic, _ in GROUPS:
        items = sorted(by_group[gk], key=lambda p: (tr_key(p["ilce"] or "zzz"), tr_key(p["name"])))
        if not items:
            continue
        h = f"{name} {label[0].lower() + label[1:]}" if gk != "mensup" else label
        toc.append(f'<a href="#{gk}"><span class="ticon t-{ic}">{icon(ic)}</span>{e(label)}<b>{len(items)}</b></a>')
        secs.append(f'<section class="group" id="{gk}"><h2>{e(h)} <small>{len(items)}</small></h2>'
                    f'<ul class="places">{"".join(place_card(p, name) for p in items)}</ul></section>')

    opts = "".join(f'<option value="{e(i)}">{e(i)} ({k})</option>' for i, k in sorted(ilceler.items(), key=lambda kv: tr_key(kv[0])))
    near = "".join(f'<li><a href="../{SLUG[m]}/">{e(m)}</a> <span>{COUNT[SLUG[m]]}</span></li>' for m in neighbours(name))
    ld = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{key}/"}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"{loc} ucuz konaklama", "numberOfItems": n,
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": place_ld(p, name)} for i, p in enumerate(places[:200])]},
    ]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>{e(name)}</nav>
<section class="hero city">
  <div class="hero-text">
    <h1>{e(loc)} ucuz konaklama</h1>
    <p class="lead">{e(" ".join(intro))}</p>
    <p class="hero-link"><a href="{APP}#{key}" rel="noopener">{e(name)} için gezgin puanları ve yorumları →</a></p>
  </div>
</section>
<div class="layout">
  <aside class="side">
    <nav class="toc" aria-label="Bölümler"><h2>Bu sayfada</h2>{"".join(toc)}<a href="#sss">Sık sorulan sorular</a></nav>
    <div class="near"><h2>Yakındaki iller</h2><ul>{near}</ul></div>
  </aside>
  <div class="content">
    <form class="filters" id="filters" hidden role="search" onsubmit="return false">
      <label class="field">{icon("search")}<input id="f-q" type="search" placeholder="{e(name)} içinde ara: ad, ilçe, adres…" aria-label="Bu ilde ara"></label>
      <select id="f-ilce" aria-label="İlçe"><option value="">Tüm ilçeler</option>{opts}</select>
      <span id="f-n" class="count" aria-live="polite"></span>
    </form>
    {"".join(secs)}
    <section id="sss" class="faq"><h2>Sık sorulan sorular</h2>
    {"".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)}
    </section>
    <section class="callout">
      <div><h2>Burada kaldın mı?</h2><p>Ödediğin ücreti, temizliği ve sivil kabul edilip edilmediğini yaz; sonraki gezgin buna göre karar versin.</p></div>
      <a class="btn" href="{APP}#{key}" rel="noopener">{icon("star")}{e(name)} için puan ver</a>
    </section>
  </div>
</div>
{FILTER_JS}
"""
    return head(title, desc, f"{key}/", ld, og=key) + body + foot("../")


# ---------- Ana sayfa ----------
def totals():
    allp = [p for c in CITIES.values() for p in c["places"]]
    grp = Counter(GROUP_OF.get(p["tk"], GROUPS[4])[0] for p in allp)
    return len(allp), grp


def home_page():
    total, grp = totals()
    kamu = grp["ogretmenevi"] + grp["misafirhane"] + grp["belediye"] + grp["mensup"]
    title = "Yolhanı: Türkiye'de Ucuz Konaklama Haritası (Öğretmenevi, Misafirhane, Kamp)"
    desc = (f"81 ilde {num(total)} ucuz konaklama yeri: {num(kamu)} öğretmenevi ve kamu misafirhanesi, {num(grp['kamp'])} kamp alanı, "
            f"{num(grp['pansiyon'])} pansiyon ve hostel. Gezginlerin fiyat, temizlik ve sivil kabul yorumları.")
    paths = "".join(f'<a href="{SLUG[n]}/" aria-label="{e(n)}, {COUNT[SLUG[n]]} yer"><path d="{d}"><title>{e(n)} · {COUNT[SLUG[n]]} yer</title></path></a>'
                    for n, d in MAP["il"].items())
    labels = "".join(f'<text x="{x}" y="{y}" font-size="{max(4, min(8.5, r * .55)):.1f}"><tspan x="{x}" dy="-0.15em">{e(n)}</tspan>'
                     f'<tspan class="n" x="{x}" dy="1.1em">{COUNT[SLUG[n]]}</tspan></text>' for n, (x, y, r) in LABELS.items())
    cities = sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"]))
    lis = "".join(f'<li><a href="{k}/">{e(c["name"])}</a><span>{COUNT[k]}</span></li>' for k, c in cities)
    dl = "".join(f'<option value="{e(c["name"])}">' for _, c in cities)
    hubs = "".join(f"""<a class="hub" href="{slug}/"><span class="ticon t-{ic}">{icon(ic)}</span>
      <b>{e(label)}</b><span>{num(grp[gk])} yer · 81 il</span></a>"""
                   for slug, gk, label, _, _, _ in HUBS for ic in [GROUPS[[g[0] for g in GROUPS].index(gk)][3]])
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "Yolhanı", "url": f"{BASE}/", "inLanguage": "tr"},
          {"@context": "https://schema.org", "@type": "Organization", "name": "Yolhanı", "url": f"{BASE}/", "logo": f"{BASE}/assets/apple-touch-icon.png"}]
    body = f"""<section class="hero home">
  <div class="hero-text">
    <h1>Türkiye'de otelden ucuza nerede kalınır?</h1>
    <p class="lead">Öğretmenevi, DSİ ve PTT misafirhanesi, kamp alanı, pansiyon: 81 ilde {num(total)} yer tek yerde. Fiyatı, temizliği ve sivil kabul edilip edilmediğini orada kalan gezginler yazıyor.</p>
    {search_box("", "hero-q", "İl, ilçe ya da yer adı yaz. Örn. Kaş, Sivas DSİ")}

  </div>
</section>
<section class="map card-box"><div class="sec-head"><h2>Haritadan il seç</h2><p>Sayılar o ildeki yer sayısı</p></div>
<div class="mapscroll"><svg viewBox="0 0 {MAP['w']} {MAP['h']}" role="img" aria-label="Türkiye il haritası">{paths}<g class="labels">{labels}</g></svg></div>
</section>
<section><div class="sec-head"><h2>Ne tür bir yer arıyorsun?</h2></div><div class="hubs">{hubs}</div></section>
<section id="iller"><div class="sec-head"><h2>İllere göre ucuz konaklama</h2></div><ul class="cities">{lis}</ul></section>
"""
    return head(title, desc, "", ld, search=False) + body + foot("")


# ---------- Rehber sayfaları ----------
def hub_page(slug, gk, label, title, tname, kmk):
    total, grp = totals()
    t = TYPES.get(tname, {})
    rows = []
    for k, c in sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"])):
        m = sum(1 for p in c["places"] if GROUP_OF.get(p["tk"], GROUPS[4])[0] == gk)
        if m:
            rows.append(f'<li><a href="../{k}/#{gk}">{e(c["name"])}</a><span>{m}</span></li>')
    price = f"Kaynak sitenin 2026 ortalamasına göre sivil misafirler için gecelik ~{KM_TYPES.get(kmk, {}).get('sivil')} TL'den başlıyor." if KM_TYPES.get(kmk, {}).get("sivil") else ""
    desc = f"{label}: Türkiye'de {num(grp[gk])} yer, {len(rows)} il. Kimler kalabilir, nasıl yer ayırtılır, fiyatlar ve il il liste."
    facts = [("Kimler kalabilir?", t.get("whoText", "")), ("Nasıl ayırtılır?", t.get("book", "")), ("İpucu", t.get("tip", "")), ("Fiyat", price)]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>{e(label)}</nav>
<section class="hero">
  <div class="hero-text"><h1>{e(title.split(":")[0])}</h1>
  <p class="lead">{e(t.get("desc", ""))} Türkiye'de {num(grp[gk])} yer, {len(rows)} ilde listeleniyor.</p></div>
</section>
<section class="facts">{"".join(f'<div><h2>{e(q)}</h2><p>{e(a)}</p></div>' for q, a in facts if a)}</section>
<section><div class="sec-head"><h2>İl il {e(label.lower())}</h2></div><ul class="cities">{"".join(rows)}</ul></section>
"""
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
        {"@type": "ListItem", "position": 2, "name": label, "item": f"{BASE}/{slug}/"}]}]
    return head(f"{title} | Yolhanı", desc, f"{slug}/", ld, og=slug) + body + foot("../")


def about_page():
    total, grp = totals()
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>Hakkında</nav>
<section class="hero"><div class="hero-text"><h1>Yol üstündeki ucuz konaklama</h1>
<p class="lead">Yolhanı, gezenlerin otel yerine kalabileceği ucuz yerleri tek yerde toplar. Adı eski yol hanlarından geliyor: kervanların ve yolcuların ucuza gecelediği, yol üstündeki konaklama yerleri.</p></div></section>
<section class="prose">
<h2>Ne var?</h2>
<p>81 ilde {num(total)} yer: {num(grp['ogretmenevi'])} öğretmenevi, {num(grp['misafirhane'] + grp['belediye'])} kamu misafirhanesi ve belediye tesisi, {num(grp['kamp'])} kamp alanı, {num(grp['pansiyon'])} pansiyon ve hostel.</p>
<h2>Nasıl çalışır?</h2>
<p>Kaldığın yeri <a href="{APP}" rel="noopener">uygulamada</a> puanla: genel, temizlik ve güvenlik. Ödediğin ücreti, sivil olarak kabul edilip edilmediğini ve yerin hâlâ açık olup olmadığını yaz. Uygunsuz yorumlar üç gezgin bildirince gizlenir.</p>
<h2>Bilgi hatalı mı?</h2>
<p>Her yerin kartındaki "Düzelt" bağlantısıyla ya da <a href="{issue_url("Bilgi düzeltme", "Hangi sayfa ve hangi yer?\n\nDoğru bilgi:\n")}" rel="noopener">buradan</a> bildir. Düzeltmeler bir sonraki güncellemede siteye girer.</p>
<h2>Veri kaynakları</h2>
<ul><li>Kamu misafirhaneleri: kamumisafirhaneleri.com.tr il listeleri</li>
<li>Kamp alanları, pansiyon ve hosteller: <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a>, ODbL lisansı</li>
<li>İl sınırları: tr-geojson (cihadturhan)</li>
<li>Fiyat, temizlik ve sivil kabul bilgisi: gezgin yorumları</li></ul>
<h2>Gizlilik</h2>
<p>Bu site çerez kullanmaz, ziyaretçi takibi yapmaz ve kişisel veri toplamaz. Yazı tipleri Google Fonts'tan yüklenir.</p>
</section>
"""
    return head("Hakkında | Yolhanı", "Yolhanı nedir, nasıl çalışır, veriler nereden geliyor ve hatalı bilgiyi nasıl bildirirsin.", "hakkinda/", og="yolhani") + body + foot("../")


def page404():
    s = (head("Sayfa bulunamadı | Yolhanı", "Aradığın sayfa bulunamadı.", "404.html")
         + f'<section class="hero"><div class="hero-text"><h1>Bu yol bir yere çıkmıyor</h1>'
           f'<p class="lead">Aradığın sayfa bulunamadı. Ana sayfadan ilini seçebilirsin.</p>'
           f'<div class="hero-acts"><a class="btn light" href="{BASE}/">Ana sayfaya dön</a></div></div></section>'
         + foot(f"{BASE}/"))
    # 404 her adreste açılabildiği için göreli bağlantılar tam adrese çevrilir
    return re.sub(r'(href|src|action)="(?!https?:|#|tel:|mailto:)([^"]*)"', lambda m: f'{m.group(1)}="{BASE}/{m.group(2).lstrip("./")}"', s)


def search_index():
    """Hızlı arama dizini: il listesi, tür adları ve her yer için [ad, il sırası, ilçe, tür sırası, id]."""
    cities = sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"]))
    label = lambda p: p["badge"] or GROUP_OF.get(p["tk"], GROUPS[4])[2]
    types = sorted({label(p) for _, c in cities for p in c["places"]}, key=tr_key)
    ti = {t: i for i, t in enumerate(types)}
    ps = [[p["name"], ci, p["ilce"], ti[label(p)], p["id"]]
          for ci, (_, c) in enumerate(cities) for p in sorted(c["places"], key=lambda p: (tr_key(p["ilce"]), tr_key(p["name"])))]
    return json.dumps({"c": [[k, c["name"], COUNT[k]] for k, c in cities], "t": types, "p": ps}, ensure_ascii=False, separators=(",", ":"))


# ---------- Üretim ----------
def write(path, text):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def main():
    # og/ klasörü (paylaşım görselleri) korunur, geri kalan her şey baştan üretilir
    if OUT.exists():
        for child in OUT.iterdir():
            if child.name != "og":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    for f in ("site.css", "ara.js"):
        shutil.copy(ROOT / "tools" / f, OUT / "assets" / f)
    for f in ("icon.svg", "apple-touch-icon.png", "icon-512.png"):
        if (ROOT / "tools" / f).exists():
            shutil.copy(ROOT / "tools" / f, OUT / "assets" / f)
    write("manifest.webmanifest", json.dumps({
        "name": "Yolhanı", "short_name": "Yolhanı", "lang": "tr", "start_url": "./", "display": "standalone",
        "background_color": "#f3f4ef", "theme_color": "#6b4426",
        "icons": [{"src": "assets/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
                  {"src": "assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "assets/icon.svg", "sizes": "any", "type": "image/svg+xml"}]}, ensure_ascii=False))
    write("index.html", home_page())
    write("ara.json", search_index())
    write("hakkinda/index.html", about_page())
    urls = [("", "1.0"), ("hakkinda/", "0.3")]
    for h in HUBS:
        write(f"{h[0]}/index.html", hub_page(*h))
        urls.append((f"{h[0]}/", "0.8"))
    for key, c in CITIES.items():
        write(f"{key}/index.html", city_page(key, c))
        urls.append((f"{key}/", "0.7"))
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"  <url><loc>{BASE}/{u}</loc><lastmod>{TODAY.isoformat()}</lastmod><priority>{pr}</priority></url>\n" for u, pr in urls)
          + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    write("404.html", page404())
    write(".nojekyll", "")
    # paylaşım görseli şablonları (tools/og.py bunları PNG'ye çevirir)
    og = {"yolhani": ("Türkiye'de otelden ucuza nerede kalınır?", f"81 il · {num(totals()[0])} yer")}
    og.update({h[0]: (h[2], f"{num(totals()[1][h[1]])} yer · 81 il") for h in HUBS})
    og.update({k: (f"{c['loc']} ucuz konaklama", f"{len(c['places'])} yer · öğretmenevi, misafirhane, kamp, pansiyon") for k, c in CITIES.items()})
    (ROOT / "tools" / "og.json").write_text(json.dumps(og, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(urls)} sayfa üretildi → {OUT}")


if __name__ == "__main__":
    main()
