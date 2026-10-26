"""Yolhanı statik site üreticisi.

data/yolhani.json dosyasından ana sayfa, 81 il sayfası, 4 rehber sayfası, hakkında,
sitemap.xml, robots.txt, manifest ve site içi arama dizinini (ara.json) üretir. Çıktı docs/ klasörüne yazılır
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
# Her yer bir gruba girer; il sayfasındaki tablolar ve rehber sayfaları bu gruplardan oluşur.
GROUPS = [
    # anahtar, bölüm başlığı, kısa ad, eşleşen tür kodları
    ("ogretmenevi", "Öğretmenevleri", "Öğretmenevi", {"ogr"}),
    ("kamp", "Kamp alanları ve tabiat parkları", "Kamp alanı", {"kamp"}),
    ("pansiyon", "Pansiyon ve hosteller", "Pansiyon / hostel", {"pans"}),
    ("belediye", "Belediye tesisleri ve uygulama otelleri", "Belediye tesisi", {"bel", "uyg"}),
    ("misafirhane", "Kamu misafirhaneleri", "Kamu misafirhanesi",
     {"dsi", "ptt", "kgm", "met", "tcdd", "ogm", "uni", "dhmi", "oz", "mal", "teias", "kamu", "gezgin"}),
    ("mensup", "Polisevi, orduevi ve adliye tesisleri", "Mensup tesisi", {"pol", "ord", "adl"}),
]
GROUP_OF = {k: g for g in GROUPS for k in g[3]}
GKEYS = [g[0] for g in GROUPS]
group = lambda p: GROUP_OF.get(p["tk"], GROUPS[4])

# Tablodaki "Kimler kalabilir" sütunu için kısa yazımlar (tam metin title'da durur)
WHO_SHORT = {
    "Herkes": "Herkes",
    "Genelde herkese açık": "Herkes",
    "Herkes; tesis yok, kendi suyunu ve çöpünü düşün": "Herkes (tesis yok)",
    "Öğretmenlere öncelik, boşsa sivil": "Boşsa sivil",
    "Kamu personeline öncelik; sivil kabulü kuruma göre değişir": "Kuruma göre",
    "Bakanlık personeline öncelik, sonra herkes": "Boşsa sivil",
    "Çoğunlukla sadece mensupları ve yakınları": "Mensuplar",
}
LOGO = ('<svg class="logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V11a8 8 0 0 1 16 0v10"/>'
        '<path d="M9 21v-6a3 3 0 0 1 6 0v6"/><path d="M2 21h20"/></svg>')

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
SORTED = sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"]))
FIX_ALL = issue_url("Bilgi düzeltme", "Hangi sayfa ve hangi yer?\n\nDoğru bilgi:\n")


# ---------- Sayfa iskeleti ----------
def head(title, desc, path, ld=(), og=None, search=True):
    rel = "../" * path.count("/")
    url = f"{BASE}/{path}"
    og_img = f"{BASE}/og/{og or 'yolhani'}.jpg"
    lds = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    box = (f'<form class="q" action="{rel or "./"}" role="search"><input name="q" type="search" placeholder="Yer, il veya ilçe ara" '
           f'aria-label="Yer, il veya ilçe ara" autocomplete="off"><button>Ara</button><div class="dd" hidden></div></form>') if search else ""
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
<meta name="theme-color" content="#ffffff">
<meta name="google-site-verification" content="{e(GSV)}">
<link rel="icon" href="{rel}assets/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{rel}assets/apple-touch-icon.png">
<link rel="manifest" href="{rel}manifest.webmanifest">
<link rel="stylesheet" href="{rel}assets/site.css">
{lds}
</head>
<body>
<a class="skip" href="#icerik">İçeriğe geç</a>
<header class="top"><div class="in">
  <a class="brand" href="{rel or './'}">{LOGO}Yolhanı</a>
  {box}
  <nav aria-label="Ana menü">
    <a href="{rel}ogretmenevleri/">Öğretmenevleri</a>
    <a href="{rel}kamu-misafirhaneleri/">Misafirhaneler</a>
    <a href="{rel}kamp-alanlari/">Kamp alanları</a>
    <a href="{rel}pansiyon-hostel/">Pansiyonlar</a>
  </nav>
</div></header>
<main id="icerik" class="in">
"""


def foot(rel):
    allc = " ".join(f'<a href="{rel}{k}/">{e(c["name"])}</a>' for k, c in SORTED)
    return f"""</main>
<footer class="foot"><div class="in">
  <p class="iller"><b>İller:</b> {allc}</p>
  <p><a href="{rel}hakkinda/">Hakkında</a> · <a href="{APP}" rel="noopener">Yorum yaz</a> · <a href="{FIX_ALL}" rel="noopener">Hata bildir</a> · <a href="{REPO}" rel="noopener">GitHub</a></p>
  <p>Veri: kamumisafirhaneleri.com.tr il listeleri, <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a> (ODbL) ve gezgin yorumları.
  Bilgiler değişebilir; gitmeden önce tesisi arayıp sivil kabul ve fiyatı sor. Son güncelleme: {TODAY_TR}.</p>
</div></footer>
<script src="{rel}assets/ara.js" data-root="{rel}" defer></script>
</body>
</html>
"""


# ---------- Yer satırı ----------
def price(p):
    m = re.search(r"~([\d.]+) TL", p["note"])
    return f"~{m.group(1)} TL" if m else ""


def tel_link(t):
    if not t:
        return ""
    digits = re.sub(r"\D", "", t).lstrip("0")
    return f'<a href="tel:+90{digits}">{e(t)}</a>'


def place_row(p):
    label = p["badge"] or (KM_TYPES[p["tk"]]["label"] if p["tk"] in KM_TYPES else group(p)[2])
    fiyat = price(p)
    sub = " · ".join(x for x in [label, p["addr"], "" if fiyat else p["note"]] if x)
    who = WHO_SHORT.get(p["whoText"], p["whoText"])
    text = " ".join([p["name"], p["ilce"], p["addr"], label]).lower()
    return (f'<tr id="p-{e(p["id"])}" data-ilce="{e(p["ilce"])}" data-q="{e(text)}">'
            f'<td class="ad"><b>{e(p["name"])}</b><small>{e(sub)}</small></td>'
            f'<td class="ilce">{e(p["ilce"]) or "Merkez"}</td>'
            f'<td class="kim {e(p["who"])}" title="{e(p["whoText"])}">{e(who)}</td>'
            + (f'<td class="fiyat">{e(fiyat)}</td>' if fiyat else '<td class="fiyat bos">–</td>') +
            f'<td class="tel">{tel_link(p["tel"])}</td>'
            f'<td class="yol"><a href="{e(p["map"])}" rel="noopener">Harita</a></td></tr>')


def place_ld(p, key, city):
    t = "Campground" if p["tk"] == "kamp" else "Hostel" if p["badge"] == "Hostel" else "LodgingBusiness"
    d = {"@type": t, "name": p["name"], "url": f"{BASE}/{key}/#p-{p['id']}",
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


TABLE_HEAD = ('<thead><tr><th>Ad</th><th>İlçe</th><th title="Sivil misafir kabulü">Kimler kalabilir</th>'
              '<th title="Kaynak sitenin sivil misafir için gecelik ortalaması">Ort. fiyat</th><th>Telefon</th><th></th></tr></thead>')


# ---------- İl sayfası ----------
FILTER_JS = """<script>
(() => {
  const q = document.getElementById("f-q"), il = document.getElementById("f-ilce"), tur = document.getElementById("f-tur"), out = document.getElementById("f-n");
  const rows = [...document.querySelectorAll("tr[data-q]")], secs = [...document.querySelectorAll("section.grup")];
  const run = () => {
    const t = q.value.trim().toLocaleLowerCase("tr"), d = il.value, g = tur.value; let n = 0;
    for (const s of secs) {
      let m = 0;
      for (const r of s.querySelectorAll("tr[data-q]")) {
        const ok = (!g || s.id === g) && (!d || r.dataset.ilce === d) && (!t || r.dataset.q.includes(t));
        r.hidden = !ok; m += ok;
      }
      s.hidden = !m; n += m;
    }
    out.textContent = (t || d || g) ? n + " / " + rows.length + " yer" : rows.length + " yer";
  };
  // Aramadan gelen ?ilce= ve ?q= süzgeci doldurur; süzgeç değişince adres de güncellenir
  const ps = new URLSearchParams(location.search);
  if (ps.get("ilce") && [...il.options].some(o => o.value === ps.get("ilce"))) il.value = ps.get("ilce");
  else if (ps.get("ilce")) q.value = ps.get("ilce");
  if (ps.get("q")) q.value = ps.get("q");
  const sync = () => {
    const u = new URL(location.href); u.search = "";
    if (il.value) u.searchParams.set("ilce", il.value);
    if (q.value.trim()) u.searchParams.set("q", q.value.trim());
    history.replaceState(null, "", u);
  };
  for (const el of [q, il, tur]) el.addEventListener("input", () => { run(); sync(); });
  document.getElementById("filtre").hidden = false; run();
})();
</script>"""


def city_page(key, c):
    name, loc, places = c["name"], c["loc"], c["places"]
    n = len(places)
    by_group = {k: [p for p in places if group(p)[0] == k] for k in GKEYS}
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

    jump, secs, turs = [], [], []
    for gk, label, _, _ in GROUPS:
        items = sorted(by_group[gk], key=lambda p: (tr_key(p["ilce"] or "zzz"), tr_key(p["name"])))
        if not items:
            continue
        h = f"{name} {label[0].lower() + label[1:]}" if gk != "mensup" else label
        jump.append(f'<a href="#{gk}">{e(label)}</a> ({len(items)})')
        turs.append(f'<option value="{gk}">{e(label)} ({len(items)})</option>')
        secs.append(f'<section class="grup" id="{gk}"><h2>{e(h)} <span>{len(items)}</span></h2>'
                    f'<table class="liste">{TABLE_HEAD}<tbody>{"".join(place_row(p) for p in items)}</tbody></table></section>')

    opts = "".join(f'<option value="{e(i)}">{e(i)} ({k})</option>' for i, k in sorted(ilceler.items(), key=lambda kv: tr_key(kv[0])))
    near = ", ".join(f'<a href="../{SLUG[m]}/">{e(m)}</a> ({COUNT[SLUG[m]]})' for m in neighbours(name))
    ld = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{key}/"}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"{loc} ucuz konaklama", "numberOfItems": n,
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": place_ld(p, key, name)} for i, p in enumerate(places[:200])]},
    ]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Ana sayfa</a> › {e(name)}</nav>
<h1>{e(loc)} ucuz konaklama</h1>
<p class="giris">{e(" ".join(intro))}</p>
<p class="atla">{" · ".join(jump)}</p>
<form class="filtre" id="filtre" hidden role="search" onsubmit="return false">
  <input id="f-q" type="search" placeholder="Bu listede ara" aria-label="{e(name)} listesinde ara">
  <select id="f-tur" aria-label="Tür"><option value="">Tüm türler</option>{"".join(turs)}</select>
  <select id="f-ilce" aria-label="İlçe"><option value="">Tüm ilçeler</option>{opts}</select>
  <span id="f-n" aria-live="polite"></span>
</form>
{"".join(secs)}
<p class="not">Fiyatlar kaynak sitenin sivil misafir için gecelik ortalamasıdır. {e(name)} için gezgin puanları ve yorumları <a href="{APP}#{key}" rel="noopener">uygulamada</a>; kaldıysan ödediğin ücreti sen de yaz.
Listede yanlış ya da eksik bilgi varsa <a href="{e(issue_url(f"Düzeltme: {name}", f"İl: {name}\\nYer:\\n\\nYanlış olan bilgi:\\n\\nDoğrusu:\\n"))}" rel="noopener">bildir</a>.</p>
<section class="sss" id="sss"><h2>Sık sorulan sorular</h2>
{"".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in faq)}
</section>
<p class="yakin"><b>Yakındaki iller:</b> {near}</p>
{FILTER_JS}
"""
    return head(title, desc, f"{key}/", ld, og=key) + body + foot("../")


# ---------- Ana sayfa ----------
def totals():
    allp = [p for c in CITIES.values() for p in c["places"]]
    grp = Counter(group(p)[0] for p in allp)
    return len(allp), grp


def home_page():
    total, grp = totals()
    kamu = grp["ogretmenevi"] + grp["misafirhane"] + grp["belediye"] + grp["mensup"]
    title = "Yolhanı: Türkiye'de Ucuz Konaklama Rehberi (Öğretmenevi, Misafirhane, Kamp)"
    desc = (f"81 ilde {num(total)} ucuz konaklama yeri: {num(kamu)} öğretmenevi ve kamu misafirhanesi, {num(grp['kamp'])} kamp alanı, "
            f"{num(grp['pansiyon'])} pansiyon ve hostel. Ada, ile veya ilçeye göre ara; adres ve telefon.")
    tone = lambda k: 1 if COUNT[k] < 20 else 2 if COUNT[k] < 35 else 3 if COUNT[k] < 70 else 4
    paths = "".join(f'<a href="{SLUG[n]}/" aria-label="{e(n)}, {COUNT[SLUG[n]]} yer"><path class="t{tone(SLUG[n])}" d="{d}"><title>{e(n)} · {COUNT[SLUG[n]]} yer</title></path></a>'
                    for n, d in MAP["il"].items())
    labels = "".join(f'<text x="{x}" y="{y}" font-size="{max(4, min(8, r * .5)):.1f}">{e(n)}</text>' for n, (x, y, r) in LABELS.items())
    rows = []
    for k, c in SORTED:
        g = Counter(group(p)[0] for p in c["places"])
        cells = [g["ogretmenevi"], g["misafirhane"] + g["belediye"], g["kamp"], g["pansiyon"], COUNT[k]]
        rows.append(f'<tr><td><a href="{k}/">{e(c["name"])}</a></td>' + "".join(f"<td>{v or '–'}</td>" for v in cells) + "</tr>")
    turs = "".join(f'<option value="{i}">{e(g[1])}</option>' for i, g in enumerate(GROUPS) if g[0] != "mensup")
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "Yolhanı", "url": f"{BASE}/", "inLanguage": "tr",
           "potentialAction": {"@type": "SearchAction", "target": f"{BASE}/?q={{search_term_string}}",
                               "query-input": "required name=search_term_string"}},
          {"@context": "https://schema.org", "@type": "Organization", "name": "Yolhanı", "url": f"{BASE}/", "logo": f"{BASE}/assets/apple-touch-icon.png"}]
    body = f"""<h1>Türkiye'de ucuz konaklama rehberi</h1>
<p class="giris">81 ilde {num(total)} yer: {num(grp['ogretmenevi'])} öğretmenevi, {num(grp['misafirhane'] + grp['belediye'])} kamu misafirhanesi ve belediye tesisi,
{num(grp['kamp'])} kamp alanı, {num(grp['pansiyon'])} pansiyon ve hostel. Adres ve telefonlar listede; fiyat ve sivil kabul bilgisini orada kalan gezginler yazıyor.</p>
<form class="ara" id="ara" action="./" role="search">
  <input id="ara-q" name="q" type="search" placeholder="Ör. Kaş, Antalya öğretmenevi, DSİ Sivas" aria-label="Yer, il veya ilçe ara" autocomplete="off">
  <select id="ara-t" name="t" aria-label="Tür"><option value="">Tüm türler</option>{turs}</select>
  <button>Ara</button>
</form>
<div id="sonuc" aria-live="polite"></div>
<section class="iller" id="iller"><h2>İllere göre</h2>
<div class="iki">
<table class="sayilar"><thead><tr><th>İl</th><th>Öğretmenevi</th><th>Misafirhane</th><th>Kamp</th><th>Pansiyon</th><th>Toplam</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
<div class="harita"><svg viewBox="0 0 {MAP['w']} {MAP['h']}" role="img" aria-label="Türkiye il haritası">{paths}<g class="etiket">{labels}</g></svg>
<p class="lejant">Yer sayısı: <i class="t1"></i>20’den az <i class="t2"></i>20–34 <i class="t3"></i>35–69 <i class="t4"></i>70 ve üstü</p></div>
</div>
</section>
<section class="bilgi"><h2>Hangi yerde kimler kalabilir?</h2>
<p><a href="ogretmenevleri/">Öğretmenevleri</a> önce öğretmenlere açıktır; boş oda varsa çoğu sivil misafir de alır, sivil fiyatı biraz yüksektir.
<a href="kamu-misafirhaneleri/">Kamu misafirhanelerinde</a> (DSİ, PTT, Karayolları, üniversite) öncelik personeldedir, sivil kabul kuruma göre değişir.
Polisevi, orduevi ve adliye tesisleri çoğunlukla yalnızca mensuplarına açıktır. Belediye tesisleri, uygulama otelleri,
<a href="kamp-alanlari/">kamp alanları</a> ve <a href="pansiyon-hostel/">pansiyonlar</a> herkese açıktır.</p>
<p>Hangisi olursa olsun gitmeden önce telefonla arayıp boş yer, sivil kabul ve fiyatı sormak en garantisi.</p>
</section>
"""
    return head(title, desc, "", ld, search=False) + body + foot("")


# ---------- Rehber sayfaları ----------
HUB_JS = """<script>
(() => {
  const q = document.getElementById("h-q"), il = document.getElementById("h-il"), out = document.getElementById("h-n");
  const rows = [...document.querySelectorAll("table.hub tbody tr")];
  const run = () => {
    const t = q.value.trim().toLocaleLowerCase("tr"), c = il.value; let n = 0;
    for (const r of rows) { const ok = (!c || r.dataset.il === c) && (!t || r.dataset.q.includes(t)); r.hidden = !ok; n += ok; }
    out.textContent = (t || c) ? n + " / " + rows.length + " yer" : rows.length + " yer";
  };
  q.addEventListener("input", run); il.addEventListener("input", run);
  document.getElementById("filtre").hidden = false; run();
})();
</script>"""


def hub_page(slug, gk, label, title, tname, kmk):
    total, grp = totals()
    t = TYPES.get(tname, {})
    rows = []
    for k, c in SORTED:
        m = sum(1 for p in c["places"] if group(p)[0] == gk)
        if m:
            rows.append(f'<li><a href="../{k}/#{gk}">{e(c["name"])}</a> <span>{m}</span></li>')
    items = [(k, c["name"], p) for k, c in SORTED
             for p in sorted(c["places"], key=lambda p: (tr_key(p["ilce"]), tr_key(p["name"]))) if group(p)[0] == gk]
    avg = KM_TYPES.get(kmk, {}).get("sivil")
    pr = f"Kaynak sitenin 2026 ortalamasına göre sivil misafirler için gecelik ~{avg} TL'den başlıyor." if avg else ""
    desc = f"{label}: Türkiye'de {num(grp[gk])} yer, {len(rows)} il. Kimler kalabilir, nasıl yer ayırtılır, fiyatlar ve il il liste."
    facts = [("Kimler kalabilir", t.get("whoText", "")), ("Nasıl ayırtılır", t.get("book", "")), ("İpucu", t.get("tip", "")), ("Fiyat", pr)]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Ana sayfa</a> › {e(label)}</nav>
<h1>{e(title.split(":")[0])}</h1>
<p class="giris">{e(t.get("desc", ""))} Türkiye'de {num(grp[gk])} yer, {len(rows)} ilde listeleniyor.</p>
<dl class="ozet">{"".join(f'<dt>{e(q)}</dt><dd>{e(a)}</dd>' for q, a in facts if a)}</dl>
<section><h2>İl il {e(label.lower())}</h2><ul class="ilsay">{"".join(rows)}</ul></section>
<section id="tumu"><h2>Tüm {e(label.lower())} <span class="sayi">{num(len(items))}</span></h2>
<form class="filtre" id="filtre" hidden role="search" onsubmit="return false">
  <input id="h-q" type="search" placeholder="Ad veya ilçe ara" aria-label="Listede ara">
  <select id="h-il" aria-label="İl"><option value="">Tüm iller</option>{"".join(f'<option value="{e(c["name"])}">{e(c["name"])}</option>' for _, c in SORTED)}</select>
  <span id="h-n" aria-live="polite"></span>
</form>
<table class="liste hub"><thead><tr><th>Ad</th><th>İl</th><th>İlçe</th><th>Telefon</th></tr></thead><tbody>
{"".join(f'<tr data-il="{e(cn)}" data-q="{e((p["name"] + " " + p["ilce"]).lower())}"><td class="ad"><a href="../{k}/#p-{e(p["id"])}">{e(p["name"])}</a></td>'
         f'<td>{e(cn)}</td><td>{e(p["ilce"]) or "Merkez"}</td><td class="tel">{tel_link(p["tel"])}</td></tr>' for k, cn, p in items)}
</tbody></table>
</section>
{HUB_JS}
"""
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
        {"@type": "ListItem", "position": 2, "name": label, "item": f"{BASE}/{slug}/"}]}]
    return head(f"{title} | Yolhanı", desc, f"{slug}/", ld, og=slug) + body + foot("../")


def about_page():
    total, grp = totals()
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Ana sayfa</a> › Hakkında</nav>
<div class="metin">
<h1>Hakkında</h1>
<p>Yolhanı, gezenlerin otel yerine kalabileceği ucuz yerleri tek yerde toplar. Adı eski yol hanlarından geliyor: yolcuların ucuza gecelediği, yol üstündeki konaklama yerleri.</p>
<h2>Ne var?</h2>
<p>81 ilde {num(total)} yer: {num(grp['ogretmenevi'])} öğretmenevi, {num(grp['misafirhane'] + grp['belediye'])} kamu misafirhanesi ve belediye tesisi, {num(grp['kamp'])} kamp alanı, {num(grp['pansiyon'])} pansiyon ve hostel.</p>
<h2>Yorumlar</h2>
<p>Kaldığın yeri <a href="{APP}" rel="noopener">uygulamada</a> puanla: genel, temizlik ve güvenlik. Ödediğin ücreti, sivil olarak kabul edilip edilmediğini ve yerin hâlâ açık olup olmadığını yaz. Uygunsuz yorumlar üç kişi bildirince gizlenir.</p>
<h2>Bilgi hatalı mı?</h2>
<p><a href="{FIX_ALL}" rel="noopener">Buradan</a> bildir. Düzeltmeler bir sonraki güncellemede siteye girer.</p>
<h2>Veri kaynakları</h2>
<ul><li>Kamu misafirhaneleri: kamumisafirhaneleri.com.tr il listeleri</li>
<li>Kamp alanları, pansiyon ve hosteller: <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a>, ODbL lisansı</li>
<li>İl sınırları: tr-geojson (cihadturhan)</li>
<li>Fiyat, temizlik ve sivil kabul bilgisi: gezgin yorumları</li></ul>
<h2>Gizlilik</h2>
<p>Bu site çerez kullanmaz, ziyaretçi takibi yapmaz ve kişisel veri toplamaz.</p>
</div>
"""
    return head("Hakkında | Yolhanı", "Yolhanı nedir, nasıl çalışır, veriler nereden geliyor ve hatalı bilgiyi nasıl bildirirsin.", "hakkinda/", og="yolhani") + body + foot("../")


def page404():
    s = (head("Sayfa bulunamadı | Yolhanı", "Aradığın sayfa bulunamadı.", "404.html")
         + f'<h1>Sayfa bulunamadı</h1><p class="giris">Aradığın sayfa taşınmış ya da hiç yokmuş. Yukarıdaki kutudan ara ya da '
           f'<a href="{BASE}/">ana sayfadan</a> ilini seç.</p>'
         + foot(f"{BASE}/"))
    # 404 her adreste açılabildiği için göreli bağlantılar tam adrese çevrilir
    return re.sub(r'(href|src|action)="(?!https?:|#|tel:|mailto:)([^"]*)"', lambda m: f'{m.group(1)}="{BASE}/{m.group(2).lstrip("./")}"', s)


def search_index():
    """Site içi arama için küçük dizin: il listesi, tür adları ve her yer için [ad, il, ilçe, tür, id, grup]."""
    badges = sorted({p["badge"] or group(p)[2] for c in CITIES.values() for p in c["places"]}, key=tr_key)
    bi = {b: i for i, b in enumerate(badges)}
    cities = [[k, c["name"], COUNT[k]] for k, c in SORTED]
    ps = []
    for ci, (k, c) in enumerate(SORTED):
        for p in sorted(c["places"], key=lambda p: (tr_key(p["ilce"]), tr_key(p["name"]))):
            ps.append([p["name"], ci, p["ilce"], bi[p["badge"] or group(p)[2]], p["id"], GKEYS.index(group(p)[0])])
    return json.dumps({"c": cities, "t": badges, "p": ps}, ensure_ascii=False, separators=(",", ":"))


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
        "background_color": "#ffffff", "theme_color": "#ffffff",
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
