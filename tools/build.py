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
import hashlib
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
REPO = "https://github.com/hkblackbird/yolhani"
TODAY = date.today()
# Tarayıcı önbelleği eski stil/betik dosyasını tutmasın diye bağlantılara içerik özeti eklenir
ASSET_V = hashlib.sha1(b"".join((ROOT / "tools" / f).read_bytes() for f in ("fonts.css", "site.css", "ara.js"))).hexdigest()[:8]
GSV = "nefGFNmlp75A9iaJx1VpqBjrkocaucwtCmEYyNWSkT4"   # Google Search Console doğrulama kodu
AYLAR = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
TODAY_TR = f"{TODAY.day} {AYLAR[TODAY.month - 1]} {TODAY.year}"

data = json.loads((ROOT / "data" / "yolhani.json").read_text(encoding="utf-8"))
CITIES = data["cities"]

# ---------- Veri temizliği ----------
# OSM'de bazı kayıtların adı aslında bir açıklama ("place for 2 tents") ya da kapandığını söylüyor ("geschlossen").
CLOSED = re.compile(r"geschlossen|nicht mehr|strictly forbidden|verboten|\bclosed\b", re.I)
DESCRIPTIVE = re.compile(r"^(place for|flat spot|level spot|wild camping|free camp|camping with|picnic tables|under trees|with bees|big!|"
                         r"camp,|camp$|camping$|n camp$|peter$|small forest|piknik alanı|ücretsiz kamp alanı)", re.I)


def tr_upper_first(s):
    return ({"i": "İ", "ı": "I"}.get(s[0], s[0].upper()) + s[1:]) if s else s


def tel_fmt(t):
    d = re.sub(r"\D", "", t or "")
    d = d[2:] if d.startswith("90") and len(d) == 12 else d
    d = "0" + d if len(d) == 10 else d
    if len(d) == 11 and d.startswith("0") and d[1] in "2345789":
        return f"{d[:4]} {d[4:7]} {d[7:9]} {d[9:]}"
    return ""   # eksik ya da hatalı numara gösterilmez


for _c in CITIES.values():
    keep = []
    for _p in _c["places"]:
        if CLOSED.search(_p["name"]):
            continue
        _p["name"] = re.sub(r"\s+\d{5}\b.*$", "", _p["name"]).strip()          # "… 07571 Demre Antalya Türkiye"
        if DESCRIPTIVE.search(_p["name"].strip()) or (_p["tk"] == "kamp" and re.search(r"\. \w|\bvar$", _p["name"])):
            desc = _p["name"].strip()
            _p["name"] = f'{_p["ilce"] or _c["name"]} kamp noktası'
            if desc.lower() not in ("camp", "camping", "big!", "peter", "n camp"):
                _p["note"] = (_p["note"] + " " if _p["note"] else "") + f"OSM notu: “{desc}”"
        _p["name"] = tr_upper_first(_p["name"].strip())
        _p["tel"] = tel_fmt(_p["tel"])
        keep.append(_p)
    _c["places"] = keep

# Kamu misafirhanelerinin konumu: tools/geocode.py (Nominatim) sonuçları. "yer" ve "adres" haritada gösterilir,
# "ilce" yalnızca "yakınımdakiler" sıralamasında kullanılır.
GEO = json.loads((ROOT / "data" / "geocode.json").read_text(encoding="utf-8")) if (ROOT / "data" / "geocode.json").exists() else {}
for _c in CITIES.values():
    for _p in _c["places"]:
        _p["geo"] = "osm" if _p["lat"] else ""
        g = GEO.get(_p["id"])
        if g and not _p["lat"]:
            if g["kind"] in ("yer", "adres"):
                _p["lat"], _p["lon"], _p["geo"] = g["lat"], g["lon"], g["kind"]
            else:
                _p["alat"], _p["alon"] = g["lat"], g["lon"]

# Kaynak sitenin 2026 tür ortalamaları: kamu personeli fiyatı (sivil fiyat KM_TYPES içinde)
KAMU_FIYAT = {"pol": 785, "ogr": 600, "dsi": 700, "tcdd": 600, "kgm": 640, "mal": 600, "met": 750, "dhmi": 400, "ord": 350,
              "oz": 400, "teias": 630, "ogm": 606, "ptt": 750, "adl": 850, "uni": 750}

# İlçe düzeltmesi: büyükşehirlerde "Merkez" ilçe yoktur; diğer illerde merkez ilçe "Merkez", "Nevşehir Merkez" ya da
# il adıyla yazılmış, tek ada indirilir. Boş ilçeler önce adresten, sonra en yakın kayıttan (10 km içinde) bulunur.
BUYUKSEHIR = set("Adana Ankara Antalya Aydın Balıkesir Bursa Denizli Diyarbakır Erzurum Eskişehir Gaziantep Hatay İstanbul İzmir "
                 "Kahramanmaraş Kayseri Kocaeli Konya Malatya Manisa Mardin Mersin Muğla Ordu Sakarya Samsun Şanlıurfa Tekirdağ "
                 "Trabzon Van".split())
ADDR_WORDS = re.compile(r"mah|cad|sok|bulvar|no\b|no:|blok|kat|\d|yolu|köyü|mevki|km|sitesi|kampüs|yerleşke", re.I)


def km(a, b):
    return math.hypot((a["lat"] - b["lat"]) * 111, (a["lon"] - b["lon"]) * 111 * math.cos(math.radians(a["lat"])))


# Adres ve addan çıkarılamayan, ilçesi kesin bilinen birkaç kayıt (ad başlangıcı → ilçe)
ILCE_ELLE = {"Bursa TEDAŞ": "Osmangazi", "Pazaryolu Öğretmenevi": "Pazaryolu", "Mahmudiye Öğretmenevi": "Mahmudiye",
             "DHMİ Hatay Havalimanı": "Antakya", "DSİ KOS Şube": "Kazımkarabekir", "Kazımkarabekir Öğretmen": "Kazımkarabekir",
             "Ondokuz Mayıs Öğretmenevi": "19 Mayıs"}

for _c in CITIES.values():
    city, bs = _c["name"], _c["name"] in BUYUKSEHIR
    merkez = {city, f"{city} Merkez", "Merkez", f"{city} merkez"}
    known = {q["ilce"] for q in _c["places"] if q["ilce"] and q["ilce"] not in merkez}
    for _p in _c["places"]:
        v = (_p["ilce"] or "").strip()
        elle = next((i for k, i in ILCE_ELLE.items() if _p["name"].startswith(k)), None)
        if elle:
            _p["ilce"] = elle
            continue
        if v in merkez and not bs:
            _p["ilce"] = "Merkez"
            continue
        if v and v not in merkez:
            continue
        found = ""
        addr = _p["addr"] or ""
        # "Akkışla Öğretmenevi", "Şişli Öğretmenevi ve ASO": ad ilçeyle başlıyorsa
        m = re.match(r"(.+?) (Öğretmenevi|Polisevi|Uygulama Oteli)", _p["name"])
        lead = m.group(1).strip() if m else ""
        named = [k for k in known if re.match(rf"{re.escape(k)}\b", _p["name"])]
        hits = [(addr.rfind(k), k) for k in known if re.search(rf"(^|[\s,/.-]){re.escape(k)}([\s,/.]|$)", addr)]
        if named:
            found = max(named, key=len)
        elif hits:
            found = max(hits)[1]
        elif lead and len(lead.split()) == 1 and lead not in merkez and not ADDR_WORDS.search(lead) and _p["tk"] == "ogr":
            found = lead
        elif re.search(r"\b\d{5} ([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)", addr) and re.search(r"\b\d{5} ([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)", addr).group(1) not in merkez:
            found = re.search(r"\b\d{5} ([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)", addr).group(1)
        elif addr:
            last = addr.split(",")[-1].strip()
            if last and len(last.split()) <= 2 and not ADDR_WORDS.search(last) and last not in merkez:
                found = last
        if not found and _p["lat"]:
            near = [(km(_p, q), q["ilce"]) for q in _c["places"] if q["lat"] and q["ilce"] and q["ilce"] not in merkez and q is not _p]
            if near and min(near)[0] < 10:
                found = min(near)[1]
        if not found and not bs and (not addr or re.search(rf"Merkez|{re.escape(city)}", addr) or v in merkez):
            found = "Merkez"
        _p["ilce"] = found
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


# ---------- Tekrar eden kayıtlar ----------
# Öğretmenevleri ve bazı misafirhaneler hem kamu listesinde hem OSM'de (çoğu zaman "pansiyon" diye) var. Aynı ilçede adı aynı
# olan kayıtlar birleştirilir: tür ve telefon kamu listesinden, kesin konum OSM'den gelir. Adı "… kamp noktası" olanlar
# ayrı yerlerdir, birleştirilmez.
def name_key(city, name):
    s = name.replace("İ", "i").replace("I", "ı").lower()
    for a, b in zip("çğıöşüâ", "cgiosua"):
        s = s.replace(a, b)
    s = re.sub(r"ogretmen ?evi", "ogretmenevi", s)
    s = re.sub(r"\b(ve )?(aksam sanat okulu|aso)( mudurlugu)?\b|\bmudurlugu\b|\bsube\b", "", s)
    cn = city.replace("İ", "i").lower()
    for a, b in zip("çğıöşü", "cgiosu"):
        cn = cn.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", re.sub(rf"\b{cn}\b", "", s))


is_osm = lambda p: "openstreetmap.org" in (p["src"] or "")
MERGED = 0
for _c in CITIES.values():
    by = {}
    for _p in _c["places"]:
        if _p["name"].endswith("kamp noktası"):
            continue
        by.setdefault((_p["ilce"], name_key(_c["name"], _p["name"])), []).append(_p)
    drop = set()
    for grp in by.values():
        if len(grp) < 2:
            continue
        km_ = [q for q in grp if not is_osm(q)]
        osm_ = [q for q in grp if is_osm(q)]
        keep = max(km_ or osm_, key=lambda q: (bool(q["tel"]), len(q["addr"] or "")))
        for q in grp:
            if q is keep:
                continue
            # İki OSM kaydı ancak birbirine yakınsa (500 m) aynı yerdir
            if is_osm(q) and is_osm(keep) and q["lat"] and keep["lat"] and km(q, keep) > .5:
                continue
            if is_osm(q):
                if q["lat"] and keep.get("geo") != "osm":
                    keep["lat"], keep["lon"], keep["geo"] = q["lat"], q["lon"], "osm"
                    keep["map"] = q["map"]
                keep.setdefault("osm", q["src"])
            keep["tel"] = keep["tel"] or q["tel"]
            keep["addr"] = keep["addr"] or q["addr"]
            drop.add(q["id"])
    MERGED += len(drop)
    _c["places"] = [q for q in _c["places"] if q["id"] not in drop]

# OSM'de "pansiyon" diye işaretlenmiş kamu tesisleri doğru türe alınır. Adında kurum geçmeyen "Konukevi"ler özel
# pansiyon olabilir, dokunulmaz. Öğrenci yurdu ve hasta yakını konukevleri gezgine açık olmadığı için listeden çıkar.
KURUM = re.compile(r"Belediye|Üniversite|Üniv\.|DSİ|Dsi|PTT|Karayolları|Orman|OGM|Maliye|DHMİ|TEDAŞ|TEİAŞ|İLBANK|İlbank|TPAO|Valilik|"
                   r"Kaymakamlı|Bakanlı|Müdürlüğü|Ceza İnfaz|Kavakçılık|İsdemir|KÜMAŞ|Demiryol|Maden|\b(AÇÜ|AGÜ|PAÜ|İZÜ)\b")
NOT_LODGING = re.compile(r"\b(Erkek|Bayan|Kız)\b.*(Konuk|Yurd|Yurt)|Hasta|Palyatif|Hastane", re.I)
for _c in CITIES.values():
    _c["places"] = [q for q in _c["places"] if not (is_osm(q) and NOT_LODGING.search(q["name"]))]
for _c in CITIES.values():
    for _p in _c["places"]:
        if is_osm(_p) and _p["tk"] == "pans":
            n = _p["name"]
            if re.search(r"Öğretmen ?[Ee]vi", n, re.I):
                _p.update(tk="ogr", badge="Öğretmenevi", who="prio", whoText="Öğretmenlere öncelik, boşsa sivil", note="")
            elif re.search(r"Polis ?evi|Orduevi|Askeri|Askerî|Jandarma", n, re.I):
                _p.update(tk="pol" if re.search("Polis", n, re.I) else "ord", badge="Polisevi" if re.search("Polis", n, re.I) else "Orduevi / askeri tesis",
                          who="closed", whoText="Çoğunlukla sadece mensupları ve yakınları", note="")
            elif re.search(r"Misafirhane|Konuk ?[Ee]vi|Sosyal Tesis", n, re.I) and re.search(KURUM, n):
                _p.update(tk="kamu", badge="Kamu misafirhanesi", who="prio",
                          whoText="Kamu personeline öncelik; sivil kabulü kuruma göre değişir", note="")

# Adresten bulunan konumların denetimi: ilçedeki OSM kayıtlarının ortasına 25 km'den uzaksa yanlış eşleşme sayılır
_cent = {}
for _c in CITIES.values():
    for _p in _c["places"]:
        if _p.get("geo") == "osm" and _p["ilce"]:
            _cent.setdefault((_c["name"], _p["ilce"]), []).append((_p["lat"], _p["lon"]))
GEO_DROPPED = 0
for _c in CITIES.values():
    for _p in _c["places"]:
        pts = _cent.get((_c["name"], _p["ilce"]))
        if _p.get("geo") in ("adres", "yer") and pts and len(pts) >= 2:
            mid = {"lat": sorted(x[0] for x in pts)[len(pts) // 2], "lon": sorted(x[1] for x in pts)[len(pts) // 2]}
            if km(_p, mid) > 25:
                _p["alat"], _p["alon"] = _p["lat"], _p["lon"]
                _p["lat"] = _p["lon"] = None
                _p["geo"] = ""
                GEO_DROPPED += 1

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
GKEYS = [g[0] for g in GROUPS]

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
    "bookmark": '<path d="M6 3.5h12v17l-6-4.2-6 4.2z"/>',
    "map": '<path d="m3 6.5 6-2.5 6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>',
    "share": '<circle cx="18" cy="5.5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="18.5" r="2.5"/><path d="m8.2 10.8 7.6-4.1M8.2 13.2l7.6 4.1"/>',
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


# Ziyaretçi geri bildirimi (yorum, düzeltme, yeni yer) Google Form ile toplanır. tools/form.json yoksa
# yorum ve yer ekleme bağlantıları gösterilmez, düzeltme GitHub'a gider. Biçim için README'ye bak.
FORM = json.loads((ROOT / "tools" / "form.json").read_text(encoding="utf-8")) if (ROOT / "tools" / "form.json").exists() else None


def feedback(kind, name="", city="", ilce="", page=""):
    """kind: yorum | duzelt | ekle. Form yoksa yalnızca düzeltme için GitHub bağlantısı döner."""
    if FORM:
        f = FORM["entries"]
        q = {f["tur"]: FORM["tur"][kind], f["ad"]: name, f["il"]: city, f["ilce"]: ilce, f["sayfa"]: page}
        return FORM["url"] + "?usp=pp_url&" + "&".join(f"{k}={quote(v)}" for k, v in q.items() if v)
    if kind == "duzelt":
        return issue_url(f"Düzeltme: {name} ({city})" if name else "Bilgi düzeltme",
                         (f"Yer: {name}\nİl: {city}\nİlçe: {ilce}\nSayfa: {page}\n\n" if name else "Hangi sayfa ve hangi yer?\n\n") + "Yanlış olan bilgi:\n\nDoğrusu:\n")
    return None


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


def head(title, desc, path, ld=(), og=None, search=True, index=True):
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
<meta name="robots" content="{"max-image-preview:large" if index else "noindex"}">
<meta name="google-site-verification" content="{e(GSV)}">
<link rel="icon" href="{rel}assets/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{rel}assets/apple-touch-icon.png">
<link rel="manifest" href="{rel}manifest.webmanifest">
<link rel="preload" href="{rel}assets/fonts/worksans-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{rel}assets/fonts/zillaslab-700-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{rel}assets/site.css?v={ASSET_V}">
{lds}
</head>
<body>
{SPRITE}
<a class="skip" href="#icerik">İçeriğe geç</a>
<header class="top"><div class="in">
  <a class="brand" href="{rel or './'}"><span class="mark">{icon("arch")}</span>Yolhanı</a>
  {search_box(rel, "top-q") if search else ""}
  <nav aria-label="Ana menü">
    <a href="{rel}yakinimda/">{icon("pin")}Yakınımda</a>
    <a href="{rel}ogretmenevleri/">Öğretmenevleri</a>
    <a href="{rel}kamu-misafirhaneleri/">Misafirhaneler</a>
    <a href="{rel}kamp-alanlari/">Kamp alanları</a>
    <a href="{rel}pansiyon-hostel/">Pansiyonlar</a>
    <a href="{rel}kaydettiklerim/" id="kayit-link" hidden>{icon("bookmark")}Kaydettiklerim <b></b></a>
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
      <p>Yol üstündeki ucuz konaklama. Öğretmenevi, kamu misafirhanesi, kamp alanı ve pansiyonlar tek haritada; adres, telefon ve kimlerin kalabildiği bilgisiyle.</p></div>
    <div><h2>Rehberler</h2><ul>
      <li><a href="{rel}ogretmenevleri/">Öğretmenevleri</a></li><li><a href="{rel}kamp-alanlari/">Kamp alanları</a></li>
      <li><a href="{rel}kamu-misafirhaneleri/">Kamu misafirhaneleri</a></li><li><a href="{rel}pansiyon-hostel/">Pansiyon ve hosteller</a></li>
      <li><a href="{rel}ucretsiz-kamp/">Ücretsiz kamp</a></li><li><a href="{rel}fiyatlar/">Fiyatlar 2026</a></li>
      <li><a href="{rel}yakinimda/">Yakınımdakiler</a></li></ul></div>
    <div><h2>Popüler iller</h2><ul>{pop}</ul></div>
    <div><h2>Yolhanı</h2><ul>
      <li><a href="{rel}hakkinda/">Hakkında</a></li>
      {f'<li><a href="{e(feedback("yorum"))}" rel="noopener">Yorum yaz</a></li><li><a href="{e(feedback("ekle"))}" rel="noopener">Yer öner</a></li>' if FORM else ""}
      <li><a href="{e(feedback("duzelt"))}" rel="noopener nofollow">Hata bildir</a></li></ul></div>
  </div>
  <div class="in allcities"><h2>Tüm iller</h2><p>{allc}</p></div>
  <div class="in legal"><p>Veri: kamumisafirhaneleri.com.tr il listeleri · <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a> (ODbL).
  Bilgiler değişebilir; gitmeden önce tesisi arayıp sivil kabul ve fiyatı sor. Son güncelleme: {TODAY_TR}.</p></div>
</footer>
<script src="{rel}assets/ara.js?v={ASSET_V}" data-root="{rel}" defer></script>
</body>
</html>
"""


# ---------- Yer kartı ----------
def place_card(p, city, rel="../", show_who=True):
    g = GROUP_OF.get(p["tk"], GROUPS[4])
    label = p["badge"] or (KM_TYPES[p["tk"]]["label"] if p["tk"] in KM_TYPES else g[2])
    who = f'<span class="who {e(p["who"])}">{e(p["whoText"])}</span>' if p["whoText"] and show_who and p["whoText"] != "Herkes" else ""
    tel = ""
    if p["tel"]:
        digits = re.sub(r"\D", "", p["tel"]).lstrip("0")
        tel = f'<a class="act" href="tel:+90{digits}">{icon("phone")}{e(p["tel"])}</a>'
    m = re.search(r"~([\d.]+) TL", p["note"])
    note = "" if m else p["note"]
    geo = (f' data-lat="{p["lat"]}" data-lon="{p["lon"]}"' + (' data-approx="1"' if p.get("geo") == "adres" else "")) if p["lat"] else ""
    return f"""<li class="place" id="p-{e(p["id"])}" data-ilce="{e(p["ilce"])}" data-who="{e(p["who"])}"{geo}
  data-name="{e(p["name"])}" data-label="{e(label)}" data-tel="{e(p["tel"])}">
  <div class="ph"><span class="ticon t-{g[3]}">{icon(g[3])}</span><div><h3>{f'<a href="{rel}{PAGE[p["id"]]}">{e(p["name"])}</a>' if p["id"] in PAGE else e(p["name"])}</h3>
  <p class="meta">{e(label)}{f" · {e(p['ilce'])}" if p["ilce"] else ""}</p></div>
  <button class="save" type="button" aria-pressed="false" title="Kaydet" aria-label="{e(p["name"])} kaydet">{icon("bookmark")}</button></div>
  {who}
  {f'<p class="note">{e(note)}</p>' if note else ""}
  {f'<p class="addr">{icon("pin")}{e(p["addr"])}</p>' if p["addr"] else ""}
  <div class="acts">{tel}<a class="act" href="{e(p["map"])}" rel="noopener">{icon("route")}Yol tarifi</a>
  {f'<a class="fix" href="{rel}{PAGE[p["id"]]}">Ayrıntılar</a>' if p["id"] in PAGE else ""}</div>
</li>"""


def place_ld(p, city):
    t = "Campground" if p["tk"] == "kamp" else "Hostel" if p["badge"] == "Hostel" else "LodgingBusiness"
    d = {"@type": t, "name": p["name"], **({"url": f"{BASE}/{PAGE[p['id']]}"} if p["id"] in PAGE else {}), "address": {"@type": "PostalAddress", "addressRegion": city, "addressCountry": "TR"}}
    if p["ilce"]:
        d["address"]["addressLocality"] = p["ilce"]
    if p["addr"]:
        d["address"]["streetAddress"] = p["addr"]
    if p["tel"]:
        d["telephone"] = p["tel"]
    if p["lat"]:
        d["geo"] = {"@type": "GeoCoordinates", "latitude": p["lat"], "longitude": p["lon"]}
    return d


def callout(review, add):
    """'Burada kaldın mı?' kutusu; form yoksa hiç gösterilmez."""
    if not review:
        return ""
    return f"""<section class="callout">
      <div><h2>Burada kaldın mı?</h2><p>Ödediğin ücreti, temizliği ve sivil kabul edilip edilmediğini yaz; sonraki gezgin buna göre karar versin.
      Listede olmayan bir yer biliyorsan <a href="{e(add)}" rel="noopener">öner</a>.</p></div>
      <a class="btn" href="{e(review)}" rel="noopener">{icon("star")}Yorum yaz</a>
    </section>"""


# ---------- İl sayfası ----------
FILTER_JS = """<script>
(() => {
  const q = document.getElementById("f-q"), sel = document.getElementById("f-ilce"), kim = document.getElementById("f-kim"), out = document.getElementById("f-n");
  if (!q) return;
  const items = [...document.querySelectorAll(".place")];
  for (const li of items) li.dataset.q = li.textContent.replace(/\\s+/g, " ").toLocaleLowerCase("tr");
  const allow = { herkes: ["open"], sivil: ["open", "prio"] };
  const run = () => {
    const t = q.value.trim().toLocaleLowerCase("tr"), d = sel.value, k = allow[kim.value]; let n = 0;
    for (const li of items) {
      const ok = (!d || li.dataset.ilce === d) && (!t || li.dataset.q.includes(t)) && (!k || k.includes(li.dataset.who));
      li.hidden = !ok; n += ok;
    }
    for (const s of document.querySelectorAll(".isub, section.group")) s.hidden = !s.querySelector(".place:not([hidden])");
    out.textContent = (t || d || k) ? n + " yer gösteriliyor" : "";
    document.body.classList.toggle("filtering", !!(t || d || k));
    if (window.yolhaniMap) window.yolhaniMap();
  };
  for (const el of [q, sel, kim]) el.addEventListener("input", run);
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
    ilceler = Counter(p["ilce"] for p in places if p["ilce"])
    top = [(i, k) for i, k in ilceler.most_common(4) if i != "Merkez"][:3]

    title = f"{loc} Ucuz Konaklama: Öğretmenevi, Misafirhane, Kamp | Yolhanı"
    desc = (f"{loc} {n} ucuz konaklama yeri: {cnt['ogretmenevi']} öğretmenevi, {kamu} kamu misafirhanesi (DSİ, PTT, Karayolları…), "
            f"{cnt['kamp']} kamp alanı, {cnt['pansiyon']} pansiyon ve hostel. Adres, telefon ve yol tarifi.")
    # O ilin verisinden yazılan, her ilde farklı giriş metni
    intro = [f"{loc} otel yerine kalabileceğin {n} yer listeleniyor."]
    if top:
        intro.append("En çok seçenek " + (", ".join(i for i, _ in top[:-1]) + " ve " + top[-1][0] + " ilçelerinde."
                                           if len(top) > 1 else locative(top[-1][0]) + "."))
    if cnt["ogretmenevi"]:
        intro.append(f"{cnt['ogretmenevi']} öğretmenevi boş oda olduğunda sivil misafir de kabul edebilir." if cnt["ogretmenevi"] > 1
                     else "İldeki öğretmenevi boş oda olduğunda sivil misafir de kabul edebilir.")
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
         f"DSİ misafirhanelerinde ~{dsi_avg} TL'den başlıyor. Gerçek fiyat tesise ve döneme göre değişir; kesin fiyatı tesisi arayarak öğren."),
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
        more = f'<a class="more" href="{GSLUG[gk]}/">Ayrı sayfada aç →</a>' if (key, gk) in GPAGE else ""
        secs.append(f'<section class="group" id="{gk}"><div class="ghead"><h2>{e(h)} <small>{len(items)}</small></h2>{more}</div>{section_note(items, "../")}'
                    f'{cards_by_ilce(items, key, c, "../")}</section>')

    opts = "".join(f'<option value="{e(i)}">{e(ilce_name(c, i))} ({k})</option>' for i, k in sorted(ilceler.items(), key=lambda kv: tr_key(kv[0])))
    near = "".join(f'<li><a href="../{SLUG[m]}/">{e(m)}</a> <span>{COUNT[SLUG[m]]}</span></li>' for m in neighbours(name))
    ld = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{key}/"}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"{loc} ucuz konaklama", "numberOfItems": n,
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": place_ld(p, name)} for i, p in enumerate(places[:60])]},
    ]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>{e(name)}</nav>
<section class="hero city">
  <div class="hero-text">
    <h1>{e(loc)} ucuz konaklama</h1>
    <p class="lead">{e(" ".join(intro))}</p>
    <p class="updated">Son güncelleme {TODAY_TR}. Fiyat ve kabul koşulları değişebilir; gitmeden önce tesisi ara.</p>
  </div>
</section>
<div class="layout" data-city="{key}" data-cityname="{e(name)}">
  <aside class="side">
    <nav class="toc" aria-label="Bölümler"><h2>Bu sayfada</h2>{"".join(toc)}<a href="#sss">Sık sorulan sorular</a></nav>
    <div class="near"><h2>Yakındaki iller</h2><ul>{near}</ul></div>
  </aside>
  <div class="content">
    <nav class="ilceler" aria-label="İlçeler"><h2>İlçeler</h2><p class="ilist">{ilce_links(key, c, "../")}</p></nav>
    <form class="filters" id="filters" hidden role="search" onsubmit="return false">
      <label class="field">{icon("search")}<input id="f-q" type="search" placeholder="{e(name)} içinde yer ara" aria-label="Bu ilde ara"></label>
      <select id="f-ilce" aria-label="İlçe"><option value="">Tüm ilçeler</option>{opts}</select>
      <select id="f-kim" aria-label="Kimler kalabilir"><option value="">Herkes / tüm yerler</option><option value="sivil">Sivil kabul edebilir</option><option value="herkes">Yalnızca herkese açık</option></select>
      <button class="btn ghost-d" id="f-map" type="button" aria-expanded="false" aria-controls="harita">{icon("map")}<span>Haritada göster</span></button>
      <span id="f-n" class="count" aria-live="polite"></span>
    </form>
    <div id="harita" class="citymap" hidden><div id="harita-in"></div><p id="harita-not" class="count"></p></div>
    {"".join(secs)}
    <section id="sss" class="faq"><h2>Sık sorulan sorular</h2>
    {"".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq)}
    </section>
    {callout(feedback("yorum", city=name, page=f"{BASE}/{key}/"), feedback("ekle", city=name, page=f"{BASE}/{key}/"))}
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
            f"{num(grp['pansiyon'])} pansiyon ve hostel; adres, telefon ve sivil kabul bilgisi.")
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
    gcount = {kg: sum(1 for p in CITIES[kg[0]]["places"] if GROUP_OF.get(p["tk"], GROUPS[4])[0] == kg[1]) for kg in GPAGE}
    glabel = {g[0]: g[1][0].lower() + g[1][1:] for g in GROUPS}
    top = "".join(f'<li><a href="{GPAGE[kg]}">{e(CITIES[kg[0]]["name"])} {e(glabel[kg[1]])}</a><span>{n}</span></li>'
                  for kg, n in sorted(gcount.items(), key=lambda x: -x[1])[:16])
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "Yolhanı", "url": f"{BASE}/", "inLanguage": "tr"},
          {"@context": "https://schema.org", "@type": "Organization", "name": "Yolhanı", "url": f"{BASE}/", "logo": f"{BASE}/assets/apple-touch-icon.png"}]
    body = f"""<section class="hero home">
  <div class="hero-text">
    <h1>Türkiye'de otelden ucuza nerede kalınır?</h1>
    <p class="lead">Öğretmenevi, DSİ ve PTT misafirhanesi, kamp alanı, pansiyon: 81 ilde {num(total)} yer; adresi, telefonu ve sivil misafir kabul edip etmediğiyle.</p>
    {search_box("", "hero-q", "İl, ilçe ya da yer adı yaz. Örn. Kaş, Sivas DSİ")}
    <p class="hero-link"><a href="yakinimda/">{icon("pin")}ya da bulunduğun yere en yakın yerleri göster</a></p>

  </div>
</section>
<section class="map card-box"><div class="sec-head"><h2>Haritadan il seç</h2><p>Sayılar o ildeki yer sayısı</p></div>
<div class="mapscroll"><svg viewBox="0 0 {MAP['w']} {MAP['h']}" role="img" aria-label="Türkiye il haritası">{paths}<g class="labels">{labels}</g></svg></div>
</section>
<section><div class="sec-head"><h2>Ne tür bir yer arıyorsun?</h2></div><div class="hubs">{hubs}</div>
<p class="morelinks"><a href="yakinimda/">{icon("pin")}Yakınımdaki yerler</a><a href="ucretsiz-kamp/">Ücretsiz kamp alanları</a><a href="fiyatlar/">Öğretmenevi ve misafirhane fiyatları 2026</a></p></section>
<section id="iller"><div class="sec-head"><h2>İllere göre ucuz konaklama</h2></div><ul class="cities">{lis}</ul></section>
<section><div class="sec-head"><h2>En çok seçenek olan listeler</h2></div><ul class="cities">{top}</ul></section>
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
            u = GPAGE.get((k, gk), f"{k}/#{gk}")
            rows.append(f'<li><a href="../{u}">{e(c["name"])}</a><span>{m}</span></li>')
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
<h2>Bilgiler nereden geliyor?</h2>
<p>Kamu misafirhanelerinin listesi kurumların yayımladığı bilgilerden, kamp alanı ve pansiyonlar OpenStreetMap'ten derlenir. Aynı yer iki kaynakta da geçiyorsa tek kayıtta birleştirilir; telefon numaraları il alan koduna göre denetlenir.
Fiyatlar tesis bazında değil, tür bazında Türkiye ortalamasıdır.</p>{'<p>Kaldığın bir yer için ödediğin ücreti ve sivil kabul edilip edilmediğini "Yorum yaz" ile bildirebilirsin; gelen bilgiler kontrol edildikten sonra eklenir.</p>' if FORM else ""}
<h2>Bilgi hatalı mı?</h2>
<p>Her yerin kartındaki "Düzelt" bağlantısıyla ya da <a href="{e(feedback("duzelt"))}" rel="noopener nofollow">buradan</a> bildir. Düzeltmeler bir sonraki güncellemede siteye girer.</p>
<h2>Veri kaynakları</h2>
<ul><li>Kamu misafirhaneleri: kamumisafirhaneleri.com.tr il listeleri</li>
<li>Kamp alanları, pansiyon ve hosteller: <a href="https://www.openstreetmap.org/copyright" rel="noopener">© OpenStreetMap katkıcıları</a>, ODbL lisansı</li>
<li>İl sınırları: tr-geojson (cihadturhan)</li>
<li>Ortalama fiyatlar: kamumisafirhaneleri.com.tr 2026 tür ortalamaları</li></ul>
<h2>Gizlilik</h2>
<p>Bu site çerez kullanmaz, ziyaretçi takibi yapmaz ve kişisel veri toplamaz. "Kaydettiklerim" listesi yalnızca senin tarayıcında tutulur.
Bir haritayı açtığında harita karoları OpenStreetMap sunucularından, harita kitaplığı cdnjs'den yüklenir.{" Yorum ve öneri formu Google Forms üzerinden çalışır." if FORM else ""}</p>
</section>
"""
    return head("Hakkında | Yolhanı", "Yolhanı nedir, nasıl çalışır, veriler nereden geliyor ve hatalı bilgiyi nasıl bildirirsin.", "hakkinda/", og="yolhani") + body + foot("../")


def saved_page():
    body = """<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>Kaydettiklerim</nav>
<section class="hero"><div class="hero-text"><h1>Kaydettiklerim</h1>
<p class="lead">Kartlardaki kaydet işaretiyle eklediğin yerler. Liste yalnızca bu tarayıcıda tutulur; başka biriyle paylaşılmaz.</p></div></section>
<section><div id="kayitlar" class="saved"><p class="empty">Henüz kaydettiğin bir yer yok. Bir il sayfasında kartın sağ üstündeki işarete bas.</p></div></section>
"""
    return head("Kaydettiklerim | Yolhanı", "Kaydettiğin konaklama yerleri.", "kaydettiklerim/", index=False) + body + foot("../")


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
    ps = [[p["name"], ci, p["ilce"], ti[label(p)], p["id"], PAGE.get(p["id"], ""),
           round(p["lat"] or p.get("alat") or 0, 4), round(p["lon"] or p.get("alon") or 0, 4), p["tel"], p["who"],
           "i" if not p["lat"] and p.get("alat") else "", GKEYS.index(GROUP_OF.get(p["tk"], GROUPS[4])[0])]
          for ci, (_, c) in enumerate(cities) for p in sorted(c["places"], key=lambda p: (tr_key(p["ilce"]), tr_key(p["name"])))]
    ci = {k: i for i, (k, _) in enumerate(cities)}
    ilces = {f"{ci[k]}|{i}": u for (k, i), u in IPAGE.items()}
    return json.dumps({"c": [[k, c["name"], COUNT[k]] for k, c in cities], "t": types, "p": ps, "i": ilces}, ensure_ascii=False, separators=(",", ":"))


# ---------- Yer sayfaları ve il-tür sayfaları ----------
# "Akseki Öğretmenevi telefon", "Antalya öğretmenevleri" gibi aramalar için ayrı sayfalar.
# Yer sayfası yalnızca telefonu, adresi ya da web sitesi olan yerler için üretilir; bilgisi sadece ad ve konumdan
# ibaret olan yerler il sayfasındaki kartta kalır (içi boş sayfa üretmemek için).
GSLUG = {"ogretmenevi": "ogretmenevleri", "kamp": "kamp-alanlari", "pansiyon": "pansiyon-hostel",
         "belediye": "belediye-tesisleri", "misafirhane": "kamu-misafirhaneleri", "mensup": "polisevi-orduevi"}
OSM = {}
if (ROOT / "data" / "osm_tags.json").exists():
    for el in json.loads((ROOT / "data" / "osm_tags.json").read_text(encoding="utf-8"))["elements"]:
        OSM[f"https://www.openstreetmap.org/{el['type']}/{el['id']}"] = el.get("tags", {})


def slugify(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in zip("çğıöşüâîû", "cgiosuaiu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:70].strip("-") or "yer"


def extras(p):
    t = OSM.get(p.get("osm") or p["src"] or "", {})
    out = {}
    w = t.get("website") or t.get("contact:website")
    if w and w.startswith("http"):
        out["web"] = w
    ia = t.get("internet_access")
    if ia:
        out["internet"] = "Yok" if ia == "no" else "Var (Wi-Fi)" if ia in ("wlan", "yes", "wifi") else "Var"
    if t.get("fee") in ("yes", "no"):
        out["fee"] = "Ücretli" if t["fee"] == "yes" else "Ücretsiz"
    if t.get("opening_hours"):
        out["hours"] = t["opening_hours"].replace("Mo", "Pzt").replace("Su", "Paz").replace("off", "kapalı")
    return out


IPAGE = {}       # (il, ilçe) → "il/ilce-slug/"
PAGE = {}        # yer id → "il/slug/"
GPAGE = {}       # (il, grup) → "il/grup-slug/"
for key, c in CITIES.items():
    used = set(GSLUG.values())
    for ilce, n in Counter(p["ilce"] for p in c["places"] if p["ilce"]).items():
        if n >= 3 and slugify(ilce) not in used:
            IPAGE[(key, ilce)] = f"{key}/{slugify(ilce)}/"
            used.add(slugify(ilce))
    for p in sorted(c["places"], key=lambda p: tr_key(p["name"])):
        if not (p["tel"] or p["addr"] or extras(p).get("web")):
            continue
        s = slugify(p["name"])
        if s in used:
            s = slugify(f"{p['name']} {p['ilce']}")
        base, i = s, 2
        while s in used:
            s, i = f"{base}-{i}", i + 1
        used.add(s)
        PAGE[p["id"]] = f"{key}/{s}/"
    cnt = Counter(GROUP_OF.get(p["tk"], GROUPS[4])[0] for p in c["places"])
    for gk, n in cnt.items():
        if n >= 2:
            GPAGE[(key, gk)] = f"{key}/{GSLUG[gk]}/"


def tinfo(p):
    """Yerin türüne uyan genel bilgi (kimler kalabilir, nasıl ayırtılır, ipucu)."""
    gk = GROUP_OF.get(p["tk"], GROUPS[4])[0]
    if gk == "kamp":
        park = re.search(r"Tabiat|Milli Park|Millî Park|Orman|Mesire", p["name"])
        return TYPES.get("Tabiat parkı kamp alanları" if park else "Özel kamp alanları (camping)", {})
    return TYPES.get({"ogretmenevi": "Öğretmenevleri", "pansiyon": "Hostel, pansiyon ve köy evleri",
                      "mensup": "Orduevleri ve polisevleri"}.get(gk, "DSİ misafirhaneleri" if p["tk"] == "dsi" else "Belediye ve kamu misafirhaneleri"), {})


def label_of(p):
    return p["badge"] or (KM_TYPES[p["tk"]]["label"] if p["tk"] in KM_TYPES else GROUP_OF.get(p["tk"], GROUPS[4])[2])


def tel_href(t):
    return "tel:+90" + re.sub(r"\D", "", t).lstrip("0")


MAP_JS = """<script>
(() => {
  const el = document.getElementById("yer-harita"); if (!el) return;
  const go = () => {
    const c = document.createElement("link"); c.rel = "stylesheet"; c.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"; document.head.append(c);
    const j = document.createElement("script"); j.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
    j.onload = () => {
      const ll = [+el.dataset.lat, +el.dataset.lon], m = L.map(el, { scrollWheelZoom: false }).setView(ll, 14);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(m);
      L.circleMarker(ll, { radius: 9, weight: 3, color: "#fff", fillColor: "#6b4426", fillOpacity: 1 }).addTo(m);
    };
    document.head.append(j);
  };
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(es => { if (es.some(x => x.isIntersecting)) { io.disconnect(); go(); } }, { rootMargin: "200px" });
    io.observe(el);
  } else go();
})();
</script>"""


def ilce_name(c, ilce):
    return f"{c['name']} Merkez" if ilce == "Merkez" else ilce or "İlçe belirtilmemiş"


def locative(name):
    """Kaş → Kaş'ta, Kemer → Kemer'de (ünlü uyumu ve sert ünsüz benzeşmesi)."""
    if name.endswith(" Merkez"):
        return name[:-7] + " merkezinde"
    w = name.split()[-1].lower()
    v = next((ch for ch in reversed(w) if ch in "aıoueiöüâîû"), "e")
    return name + "'" + ("t" if w[-1] in "fstkçşhp" else "d") + ("a" if v in "aıouâû" else "e")


def common_who(items):
    s = {p["whoText"] for p in items}
    return s.pop() if len(s) == 1 else ""


def section_note(items, rel):
    """Bölümdeki herkes için aynı olan kabul koşulu ve tür ortalaması fiyatı: kartlarda tekrar etmek yerine bölüm başında bir kez."""
    who = common_who(items)
    avgs = Counter(p["tk"] for p in items if KM_TYPES.get(p["tk"], {}).get("sivil"))
    out = ""
    if who and who != "Herkes":
        out += f'<b>Kimler kalabilir:</b> {e(who)}. '
    if avgs:
        parts = [f'{KM_TYPES[t]["label"].replace(" misafirhanesi", "")} ~{num(KM_TYPES[t]["sivil"])} TL' for t, _ in avgs.most_common(4)]
        out += (f'Sivil misafir için gecelik fiyat, Türkiye ortalaması: {e(", ".join(parts))}\'den başlıyor. '
                f'Tesise göre değişir; kesin fiyatı telefonla sor. <a href="{rel}fiyatlar/">Kamu personeli ve sivil fiyat tablosu</a>.')
    return f'<p class="pnote">{out}</p>' if out else ""


def cards_by_ilce(items, key, c, rel):
    """Uzun listeleri ilçe başlıklarına böler; kısa listeler tek parça kalır."""
    sw = not common_who(items)
    ilce_order = sorted({p["ilce"] for p in items}, key=lambda i: (not i, tr_key(i)))
    if len(items) <= 12 or len(ilce_order) < 2 or len(items) / len(ilce_order) < 3:
        return f'<ul class="places">{"".join(place_card(p, c["name"], rel, sw) for p in items)}</ul>'
    out = []
    for i in ilce_order:
        sub = [p for p in items if p["ilce"] == i]
        link = f'<a href="{rel}{IPAGE[(key, i)]}">{e(ilce_name(c, i))}</a>' if (key, i) in IPAGE else e(ilce_name(c, i))
        out.append(f'<div class="isub"><h3 class="ih">{link} <small>{len(sub)}</small></h3>'
                   f'<ul class="places">{"".join(place_card(p, c["name"], rel, sw) for p in sub)}</ul></div>')
    return "".join(out)


def ilce_links(key, c, rel, skip=None):
    cnt = Counter(p["ilce"] for p in c["places"] if p["ilce"])
    return " ".join(
        f'<a href="{rel}{IPAGE[(key, i)]}">{e(ilce_name(c, i))} <span>{n}</span></a>' if (key, i) in IPAGE
        else f'<a href="{rel}{key}/?ilce={quote(i)}">{e(ilce_name(c, i))} <span>{n}</span></a>'
        for i, n in sorted(cnt.items(), key=lambda kv: tr_key(kv[0])) if i != skip)


def ilce_page(key, c, ilce):
    city, iname = c["name"], ilce_name(c, ilce)
    path = IPAGE[(key, ilce)]
    items = [p for p in c["places"] if p["ilce"] == ilce]
    n = len(items)
    cnt = Counter(GROUP_OF.get(p["tk"], GROUPS[4])[0] for p in items)
    parts = [f"{cnt[g[0]]} {g[2].lower()}" for g in GROUPS if cnt[g[0]]]
    intro = f"{locative(iname)}{'' if city in iname else f' ({city})'} otel yerine kalabileceğin {n} yer var: " + ", ".join(parts) + "."
    tels = sum(1 for p in items if p["tel"])
    if tels:
        intro += f" {tels} tanesinin telefonu listede."
    toc, secs = [], []
    for gk, label, short, ic, _ in GROUPS:
        g_items = sorted([p for p in items if GROUP_OF.get(p["tk"], GROUPS[4])[0] == gk], key=lambda p: tr_key(p["name"]))
        if not g_items:
            continue
        toc.append(f'<a href="#{gk}"><span class="ticon t-{ic}">{icon(ic)}</span>{e(label)}<b>{len(g_items)}</b></a>')
        secs.append(f'<section class="group" id="{gk}"><h2>{e(iname)} {e(label[0].lower() + label[1:])} <small>{len(g_items)}</small></h2>{section_note(g_items, "../../")}'
                    f'<ul class="places">{"".join(place_card(p, city, "../../", not common_who(g_items)) for p in g_items)}</ul></section>')
    title = f"{iname} Ucuz Konaklama: {n} Yer ({', '.join(g[2] for g in GROUPS if cnt[g[0]])[:60]}) | {city} | Yolhanı"
    if ilce != "Merkez":
        title = f"{iname} Ucuz Konaklama, {city}: {n} Yer | Pansiyon, Kamp, Misafirhane | Yolhanı"
    desc = f"{iname}, {city}: {n} ucuz konaklama yeri ({', '.join(parts)}). Adres, telefon, kimlerin kalabildiği ve yol tarifi."
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": city, "item": f"{BASE}/{key}/"},
            {"@type": "ListItem", "position": 3, "name": iname, "item": f"{BASE}/{path}"}]},
          {"@context": "https://schema.org", "@type": "ItemList", "name": f"{iname} ucuz konaklama", "numberOfItems": n,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": place_ld(p, city)} for i, p in enumerate(items[:60])]}]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../../">Yolhanı</a><span>›</span><a href="../">{e(city)}</a><span>›</span>{e(iname)}</nav>
<section class="hero city">
  <div class="hero-text">
    <h1>{e(locative(iname))} ucuz konaklama</h1>
    <p class="lead">{e(intro)}</p>
    <p class="updated">Son güncelleme {TODAY_TR}. Fiyat ve kabul koşulları değişebilir; gitmeden önce tesisi ara.</p>
  </div>
</section>
<div class="layout" data-city="{key}" data-cityname="{e(city)}">
  <aside class="side">
    <nav class="toc" aria-label="Bölümler"><h2>Bu sayfada</h2>{"".join(toc)}</nav>
    <div class="near"><h2>{e(city)} içinde diğer ilçeler</h2><p class="ilist">{ilce_links(key, c, "../../", skip=ilce)}</p>
    <p><a href="../">{e(city)} için tüm yerler →</a></p></div>
  </aside>
  <div class="content">
    <div class="maptools"><button class="btn ghost-d" id="f-map" type="button" aria-expanded="false" aria-controls="harita">{icon("map")}<span>Haritada göster</span></button></div>
    <div id="harita" class="citymap" hidden><div id="harita-in"></div><p id="harita-not" class="count"></p></div>
    {"".join(secs)}
    {callout(feedback("yorum", city=city, ilce=ilce, page=f"{BASE}/{path}"), feedback("ekle", city=city, ilce=ilce, page=f"{BASE}/{path}"))}
  </div>
</div>
"""
    return head(title, desc, path, ld, og=key) + body + foot("../../")


def place_page(key, c, p):
    name, city = p["name"], c["name"]
    g = GROUP_OF.get(p["tk"], GROUPS[4])
    label, ex, ti = label_of(p), extras(p), tinfo(p)
    path = PAGE[p["id"]]
    where = f"{p['ilce']}, {city}" if p["ilce"] and p["ilce"] != "Merkez" else f"{city} Merkez" if p["ilce"] else city
    avg = KM_TYPES.get(p["tk"], {}).get("sivil")
    m = re.search(r"~([\d.]+) TL", p["note"])
    note = "" if m else p["note"]

    rows = [("Tür", e(label)), ("Kimler kalabilir", f'<span class="who {e(p["who"])}">{e(p["whoText"])}</span>' if p["whoText"] else "")]
    rows.append(("Adres", e(p["addr"]) + (f"<br><small>{e(where)}</small>" if p["addr"] and (p["ilce"] or city) not in p["addr"] else "") if p["addr"] else e(where)))
    if p["tel"]:
        rows.append(("Telefon", f'<a href="{tel_href(p["tel"])}">{e(p["tel"])}</a>'))
    if avg:
        kamu = KAMU_FIYAT.get(p["tk"])
        rows.append(("Gecelik fiyat", f"Sivil ~{num(avg)} TL'den" + (f", kamu personeli ~{num(kamu)} TL'den" if kamu else "")
                     + ' <small>(Türkiye ortalaması, tesise göre değişir; kesin fiyatı telefonla sor. <a href="../../fiyatlar/">Tüm fiyatlar</a>)</small>'))
    elif ex.get("fee"):
        rows.append(("Ücret", e(ex["fee"])))
    if ex.get("internet"):
        rows.append(("İnternet", e(ex["internet"])))
    if ex.get("hours"):
        rows.append(("Açık olduğu zaman", e(ex["hours"])))
    if ex.get("web"):
        host = re.sub(r"^https?://(www\.)?", "", ex["web"]).split("/")[0]
        rows.append(("Web sitesi", f'<a href="{e(ex["web"])}" rel="noopener nofollow">{e(host)}</a>'))
    src_txt = ("kamumisafirhaneleri.com.tr il listesi" + (", konum OpenStreetMap" if p.get("geo") == "osm" else "")) if not is_osm(p) \
        else "OpenStreetMap katkıcıları (ODbL)"
    if note and not (ex.get("fee") and note.strip(" .") == ex["fee"]):
        rows.append(("Not", e(note.replace(ex.get("fee", "") + ". ", "") if ex.get("fee") else note)))
    rows.append(("Bilgi kaynağı", e(src_txt) + f" <small>· {TODAY_TR} itibarıyla</small>"))
    dl = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows if v)

    # Yakındaki yerler: konumu biliniyorsa uzaklığa göre, bilinmiyorsa önce aynı ilçe, sonra aynı tür
    others = [q for q in c["places"] if q["id"] != p["id"]]
    pt = lambda q: {"lat": q["lat"], "lon": q["lon"]} if q["lat"] else {"lat": q["alat"], "lon": q["alon"]} if q.get("alat") else None
    here = pt(p)
    if here:
        near = sorted((q for q in others if pt(q) and km(here, pt(q)) < 30), key=lambda q: (km(here, pt(q)), q["id"] not in PAGE))[:6]
    else:
        near = [q for q in others if p["ilce"] and q["ilce"] == p["ilce"]]
        near.sort(key=lambda q: (q["id"] not in PAGE, GROUP_OF.get(q["tk"], GROUPS[4])[0] != g[0], tr_key(q["name"])))
    if len(near) < 6:
        near += [q for q in others if q not in near and GROUP_OF.get(q["tk"], GROUPS[4])[0] == g[0] and q["id"] in PAGE][:6 - len(near)]
    near = near[:6]
    href = lambda q: "../../" + (PAGE[q["id"]] if q["id"] in PAGE else f"{key}/#p-{q['id']}")
    dist = lambda q: (f" · {km(here, pt(q)):.0f} km" if km(here, pt(q)) >= 1 else " · 1 km'den yakın") if here and q["lat"] and p["lat"] else ""
    near_html = "".join(f'<li><a href="{href(q)}">{e(q["name"])}</a><span>{e(label_of(q))}{" · " + e(q["ilce"]) if q["ilce"] else ""}{dist(q)}</span></li>' for q in near)


    ld_place = place_ld(p, city)
    ld_place.update({"@context": "https://schema.org", "url": f"{BASE}/{path}"})
    if ex.get("web"):
        ld_place["sameAs"] = ex["web"]
    crumbs = [("Yolhanı", f"{BASE}/"), (city, f"{BASE}/{key}/")]
    if (key, p["ilce"]) in IPAGE:
        crumbs.append((ilce_name(c, p["ilce"]), f"{BASE}/{IPAGE[(key, p['ilce'])]}"))
    elif (key, g[0]) in GPAGE:
        crumbs.append((g[1], f"{BASE}/{GPAGE[(key, g[0])]}"))
    crumbs.append((name, f"{BASE}/{path}"))
    ld = [ld_place,
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(crumbs)]}]
    crumb_html = '<span>›</span>'.join(f'<a href="{u.replace(BASE + "/", "../../") or "../../"}">{e(n)}</a>' for n, u in crumbs[:-1]) + f"<span>›</span>{e(name)}"
    fix = feedback("duzelt", name, city, p["ilce"], f"{BASE}/{path}")
    dup = sum(1 for q in c["places"] if q["name"] == name and q["ilce"] == p["ilce"] and q["id"] in PAGE) > 1
    title = f"{name} ({where}{', ' + label if dup else ''}): Adres, Telefon, Nasıl Gidilir | Yolhanı"
    desc = (f"{name}, {where}. {label}." + (f" Telefon: {p['tel']}." if p["tel"] else "") + (f" Adres: {p['addr']}." if p["addr"] else "")
            + " Kimler kalabilir, ortalama fiyat, yol tarifi ve yakındaki diğer ucuz konaklama yerleri.")
    geo = (f'<div id="yer-harita" class="yermap" data-lat="{p["lat"]}" data-lon="{p["lon"]}" role="img" aria-label="{e(name)} konumu"></div>'
           + ('<p class="geonote">Konum adresten bulundu, yaklaşıktır. Gitmeden önce Yol tarifi ile kontrol et.</p>' if p["geo"] == "adres" else "")) if p["lat"] else ""
    body = f"""<nav class="crumbs" aria-label="Konum">{crumb_html}</nav>
<div class="layout yer" data-city="{key}" data-cityname="{e(city)}">
<article class="place yerbox" id="p-{e(p["id"])}" data-ilce="{e(p["ilce"])}" data-name="{e(name)}" data-label="{e(label)}" data-tel="{e(p["tel"])}">
  <header class="ph"><span class="ticon t-{g[3]}">{icon(g[3])}</span><div><h1>{e(name)}</h1>
    <p class="meta">{e(label)} · {e(where)}</p></div>
    <button class="save" type="button" aria-pressed="false" title="Kaydet" aria-label="{e(name)} kaydet">{icon("bookmark")}</button></header>
  <div class="acts big">{f'<a class="btn" href="{tel_href(p["tel"])}">{icon("phone")}Ara</a>' if p["tel"] else ""}
    <a class="btn ghost-d" href="{e(p["map"])}" rel="noopener">{icon("route")}Yol tarifi</a>
    <button class="btn ghost-d" type="button" data-share>{icon("share")}<span>Paylaş</span></button></div>
  <dl class="bilgi">{dl}</dl>
  {geo}
  <p class="updated-d">Son güncelleme {TODAY_TR}. Bilgi hatalıysa <a href="{e(fix)}" rel="noopener nofollow">düzelt</a>.</p>
</article>
<aside class="side yerside">
  {f'<section class="tip"><h2>Nasıl yer ayırtılır?</h2><p>{e(ti["book"])}</p>' + (f'<p>{e(ti["tip"])}</p>' if ti.get("tip") else "") + "</section>" if ti.get("book") else ""}
  <section class="near2"><h2>{"Yakındaki yerler" if here else e(p["ilce"] or city) + " ve yakınında"}</h2><ul>{near_html}</ul>
  <p><a href="../">{e(city)} için tüm yerler →</a></p></section>
</aside>
</div>
{callout(feedback("yorum", name, city, p["ilce"], f"{BASE}/{path}"), feedback("ekle", city=city, page=f"{BASE}/{path}"))}
{MAP_JS if p["lat"] else ""}
"""
    return head(title, desc, path, ld, og=key) + body + foot("../../")


def group_page(key, c, gk):
    g = next(x for x in GROUPS if x[0] == gk)
    name, loc = c["name"], c["loc"]
    items = sorted([p for p in c["places"] if GROUP_OF.get(p["tk"], GROUPS[4])[0] == gk],
                   key=lambda p: (tr_key(p["ilce"] or "zzz"), tr_key(p["name"])))
    n, label = len(items), g[1]
    lab_l = label[0].lower() + label[1:]
    path = GPAGE[(key, gk)]
    ti = tinfo(items[0])
    ilceler = Counter(p["ilce"] for p in items if p["ilce"] and p["ilce"] != "Merkez")
    tels = sum(1 for p in items if p["tel"])
    intro = f"{loc} {n} {g[2].lower() if gk != 'mensup' else 'mensup tesisi'} listeleniyor"
    if ilceler and ilceler.most_common(1)[0][1] > 1:
        intro += f"; en çok {', '.join(i for i, k in ilceler.most_common(3) if k > 1)} ilçelerinde."
    else:
        intro += f", {len(ilceler)} farklı ilçede." if len(ilceler) > 1 else "."
    intro += f" {tels} tanesinin telefonu var." if tels else ""
    pnote = section_note(items, "../../")
    others = "".join(f'<a href="../../{GPAGE[(key, x[0])]}">{e(x[1])}</a>' for x in GROUPS if x[0] != gk and (key, x[0]) in GPAGE)
    title = f"{name} {lab_l if gk != 'mensup' else 'polisevi ve orduevleri'}: {n} yer, telefon ve adresler | Yolhanı"
    title = title[0].upper() + title[1:]
    desc = f"{loc} {n} {g[2].lower()}: adres, telefon, kimlerin kalabildiği ve ortalama fiyatlar. " + (f"{', '.join(i for i, _ in ilceler.most_common(3))} ve diğer ilçeler." if ilceler else "")
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{key}/"},
            {"@type": "ListItem", "position": 3, "name": label, "item": f"{BASE}/{path}"}]},
          {"@context": "https://schema.org", "@type": "ItemList", "name": f"{name} {lab_l}", "numberOfItems": n,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{BASE}/{PAGE[p['id']]}" if p["id"] in PAGE else f"{BASE}/{key}/#p-{p['id']}",
                                "name": p["name"]} for i, p in enumerate(items[:60])]}]
    facts = [("Kimler kalabilir?", ti.get("whoText", "")), ("Nasıl ayırtılır?", ti.get("book", "")), ("İpucu", ti.get("tip", ""))]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../../">Yolhanı</a><span>›</span><a href="../">{e(name)}</a><span>›</span>{e(label)}</nav>
<section class="hero city">
  <div class="hero-text">
    <h1>{e(name)} {e(lab_l if gk != "mensup" else "polisevi, orduevi ve adliye tesisleri")}</h1>
    <p class="lead">{e(intro)}</p>
    <p class="updated">Son güncelleme {TODAY_TR}. Fiyat ve kabul koşulları değişebilir; gitmeden önce tesisi ara.</p>
  </div>
</section>
<section class="facts">{"".join(f'<div><h2>{e(q)}</h2><p>{e(a)}</p></div>' for q, a in facts if a)}</section>
<div class="layout" data-city="{key}" data-cityname="{e(name)}">
  <aside class="side">
    <div class="near"><h2>{e(name)} içinde diğer türler</h2><div class="otypes">{others}<a href="../">Tüm yerler</a></div></div>
  </aside>
  <div class="content">
    <div class="maptools"><button class="btn ghost-d" id="f-map" type="button" aria-expanded="false" aria-controls="harita">{icon("map")}<span>Haritada göster</span></button></div>
    <div id="harita" class="citymap" hidden><div id="harita-in"></div><p id="harita-not" class="count"></p></div>
    <section class="group" id="{gk}"><h2>{e(label)} <small>{n}</small></h2>{pnote}
    {cards_by_ilce(items, key, c, "../../")}</section>
  </div>
</div>
"""
    return head(title, desc, path, ld, og=key) + body + foot("../../")


# ---------- Fiyat rehberi, ücretsiz kamp, yakınımdakiler ----------
def simple_ld(slug, label, faq=()):
    ld = [{"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Yolhanı", "item": f"{BASE}/"},
        {"@type": "ListItem", "position": 2, "name": label, "item": f"{BASE}/{slug}/"}]}]
    if faq:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    return ld


def faq_html(faq):
    return ('<section class="faq"><h2>Sık sorulan sorular</h2>'
            + "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faq) + "</section>")


def prices_page():
    allp = [p for c in CITIES.values() for p in c["places"]]
    cnt = Counter(p["tk"] for p in allp)
    hub = {"ogr": "../ogretmenevleri/", "dsi": "../kamu-misafirhaneleri/", "ptt": "../kamu-misafirhaneleri/"}
    rows = sorted([k for k in KAMU_FIYAT if KM_TYPES.get(k, {}).get("sivil")], key=lambda k: KM_TYPES[k]["sivil"])
    table = "".join(
        f'<tr><th scope="row">{f"<a href={chr(34)}{hub[k]}{chr(34)}>" if k in hub else ""}{e(KM_TYPES[k]["label"])}{"</a>" if k in hub else ""}'
        f'{" <small>(çoğunlukla mensuplara)</small>" if KM_TYPES[k]["who"] == "closed" else ""}</th>'
        f'<td>{num(KAMU_FIYAT[k])} TL</td><td>{num(KM_TYPES[k]["sivil"])} TL</td><td>{cnt[k]}</td></tr>' for k in rows)
    ogr, dsi = KM_TYPES["ogr"]["sivil"], KM_TYPES["dsi"]["sivil"]
    faq = [
        ("Öğretmenevi fiyatları 2026'da ne kadar?", f"Kaynak sitenin 2026 ortalamasına göre öğretmenevlerinde gecelik fiyat kamu personeli için ~{KAMU_FIYAT['ogr']} TL'den, "
         f"sivil misafir için ~{ogr} TL'den başlıyor. Öğretmenler için fiyat daha düşüktür; kesin fiyat ile ve tesise göre değişir."),
        ("Sivil vatandaş kamu misafirhanesinde kalabilir mi?", "Çoğunda öncelik kurum ve kamu personelindedir; boş oda olduğunda sivil misafir de kabul edilebilir, "
         "fiyatı daha yüksektir. Polisevi, orduevi ve adliye tesisleri çoğunlukla yalnızca mensuplarına açıktır."),
        ("En ucuz kamu misafirhanesi hangisi?", f"Ortalamalara göre sivil misafir için en düşük fiyatlar havalimanı ve TEİAŞ misafirhanelerinde (~{KM_TYPES['dhmi']['sivil']} TL'den), "
         f"en yüksekler TCDD (~{KM_TYPES['tcdd']['sivil']} TL'den) ve Meteoroloji (~{KM_TYPES['met']['sivil']} TL'den) misafirhanelerinde."),
        ("Fiyatlar kişi başı mı oda başı mı?", "Tesise göre değişir: öğretmenevlerinin çoğu oda başı, bazı misafirhaneler kişi başı ücret alır. Ararken mutlaka sor."),
    ]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>Fiyatlar</nav>
<section class="hero"><div class="hero-text"><h1>Öğretmenevi ve kamu misafirhanesi fiyatları 2026</h1>
<p class="lead">Gecelik konaklama fiyatları, kamu personeli ve sivil misafir için ayrı ayrı. Rakamlar Türkiye geneli ortalamadır; tesise ve şehre göre değişir.</p>
<p class="updated">Kaynak: kamumisafirhaneleri.com.tr 2026 ortalamaları. Son güncelleme {TODAY_TR}.</p></div></section>
<section class="card-box"><div class="tablewrap"><table class="prices">
<caption>Gecelik fiyat, "…TL'den başlayan" ortalama</caption>
<thead><tr><th scope="col">Tesis türü</th><th scope="col">Kamu personeli</th><th scope="col">Sivil misafir</th><th scope="col">Sitedeki yer</th></tr></thead>
<tbody>{table}</tbody></table></div>
<p class="pnote">Belediye tesisleri, uygulama otelleri, kamp alanları ve pansiyonlar için ortak bir ortalama yayımlanmıyor; bu yerlerin fiyatını tesisi arayarak öğrenebilirsin.</p></section>
<section class="facts">
<div><h2>Fiyat neye göre değişir?</h2><p>Şehir, sezon, oda tipi (tek, çift, aile) ve misafirin kim olduğu. Öğretmen ya da kurum personeli en düşük fiyatı öder; sivil misafir daha fazla.</p></div>
<div><h2>Nasıl yer ayırtılır?</h2><p>Çoğu tesiste online rezervasyon yok. Bir gün önce telefonla arayıp boş oda, sivil kabul ve güncel fiyatı sor; kimliğini yanında taşı.</p></div>
<div><h2>Tesisleri nerede bulurum?</h2><p><a href="../ogretmenevleri/">Öğretmenevleri</a> ve <a href="../kamu-misafirhaneleri/">kamu misafirhaneleri</a> il il listeleniyor; adres ve telefonlar her yerin sayfasında.</p></div>
</section>
{faq_html(faq)}
"""
    return head("Öğretmenevi ve Kamu Misafirhanesi Fiyatları 2026 (Sivil ve Kamu Personeli) | Yolhanı",
                f"2026 gecelik fiyatlar: öğretmenevi sivil ~{ogr} TL, DSİ ~{dsi} TL'den. 15 kamu misafirhanesi türünde kamu personeli ve sivil misafir fiyat tablosu.",
                "fiyatlar/", simple_ld("fiyatlar", "Fiyatlar", faq), og="yolhani") + body + foot("../")


def is_free_camp(p):
    return p["tk"] == "kamp" and (p["badge"] == "Doğal kamp noktası" or "ücretsiz" in p["note"].lower() or extras(p).get("fee") == "Ücretsiz")


def free_camp_page():
    groups = []
    total = 0
    for k, c in sorted(CITIES.items(), key=lambda kv: tr_key(kv[1]["name"])):
        items = sorted([p for p in c["places"] if is_free_camp(p)], key=lambda p: (tr_key(p["ilce"]), tr_key(p["name"])))
        if items:
            total += len(items)
            groups.append((k, c, items))
    jump = " ".join(f'<a href="#il-{k}">{e(c["name"])} <span>{len(it)}</span></a>' for k, c, it in groups)
    secs = "".join(f'<section class="group" id="il-{k}" data-city="{k}" data-cityname="{e(c["name"])}"><div class="ghead"><h2>{e(c["name"])} <small>{len(it)}</small></h2>'
                   f'<a class="more" href="../{GPAGE.get((k, "kamp"), k + "/")}">{e(c["name"])} kamp alanları →</a></div>'
                   f'<ul class="places">{"".join(place_card(p, c["name"], "../") for p in it)}</ul></section>' for k, c, it in groups)
    faq = [
        ("Türkiye'de ücretsiz kamp nerede yapılır?", f"Bu sayfada {len(groups)} ilde {total} ücretsiz kamp alanı ve doğal kamp noktası listeleniyor. "
         "Ayrıca birçok belediye yaz aylarında sahil ve göl kenarında ücretsiz ya da sembolik ücretli çadır alanı açıyor."),
        ("Serbest kamp yasal mı?", "Yasak olmayan doğal alanlarda serbest kamp yapılabilir. Orman içi, milli park ve koruma alanlarında, özel arazide ve kıyı kenar çizgisinde "
         "kısıtlamalar olabilir. Orman yangını sezonunda ateş yakmak genelde yasaktır; jandarma ya da muhtara haber vermek iyi olur."),
        ("Doğal kamp noktasında ne var?", "Çoğunda tesis yoktur: su, tuvalet ve çöp için kendi hazırlığını yap, ayrılırken alanı temiz bırak."),
    ]
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>Ücretsiz kamp</nav>
<section class="hero"><div class="hero-text"><h1>Ücretsiz kamp alanları ve serbest kamp noktaları</h1>
<p class="lead">Türkiye'de {len(groups)} ilde {total} ücretsiz kamp alanı ve doğal kamp noktası. Çoğunda tesis yok; su, tuvalet ve çöp için hazırlıklı git.</p>
<p class="updated">Kaynak: OpenStreetMap katkıcıları. Son güncelleme {TODAY_TR}. Alanların durumu değişebilir; yerel kurallara uy.</p></div></section>
<nav class="ilceler" aria-label="İller"><h2>İller</h2><p class="ilist">{jump}</p></nav>
<div class="content">{secs}</div>
{faq_html(faq)}
"""
    return head(f"Ücretsiz Kamp Alanları ve Serbest Kamp Noktaları: {total} Yer, {len(groups)} İl | Yolhanı",
                f"Türkiye'de {total} ücretsiz kamp alanı ve doğal kamp noktası, il il: konum, yol tarifi, imkânlar ve serbest kamp kuralları.",
                "ucretsiz-kamp/", simple_ld("ucretsiz-kamp", "Ücretsiz kamp", faq), og="kamp-alanlari") + body + foot("../")


def near_page():
    turs = "".join(f'<option value="{i}">{e(g[1])}</option>' for i, g in enumerate(GROUPS))
    body = f"""<nav class="crumbs" aria-label="Konum"><a href="../">Yolhanı</a><span>›</span>Yakınımdakiler</nav>
<section class="hero"><div class="hero-text"><h1>Yakınımdaki ucuz konaklama</h1>
<p class="lead">Bulunduğun yere en yakın öğretmenevi, kamu misafirhanesi, kamp alanı ve pansiyonlar, kuş uçuşu mesafesine göre.</p>
<p class="updated">Konumun yalnızca bu sayfada, senin tarayıcında kullanılır; hiçbir yere gönderilmez.</p></div></section>
<section class="card-box near-app">
  <div class="near-ctl">
    <button class="btn" type="button" id="yk-btn">{icon("pin")}Konumumu kullan</button>
    <select id="yk-tur" aria-label="Tür"><option value="">Tüm türler</option>{turs}</select>
    <label class="chk"><input type="checkbox" id="yk-sivil"> Sivil kabul edebilenler</label>
  </div>
  <p id="yk-msg" class="count" aria-live="polite">Konum izni istenecek. İzin vermek istemezsen yukarıdaki arama kutusuna il ya da ilçe yaz.</p>
  <ol id="yk-list" class="near-list"></ol>
</section>
<script>
(() => {{
  const btn = document.getElementById("yk-btn"), tur = document.getElementById("yk-tur"), siv = document.getElementById("yk-sivil");
  const msg = document.getElementById("yk-msg"), list = document.getElementById("yk-list");
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[c]);
  let idx, here;
  const dist = (a, b, c, d) => {{ const r = Math.PI / 180, x = (d - b) * r * Math.cos((a + c) / 2 * r), y = (c - a) * r; return Math.hypot(x, y) * 6371; }};
  const draw = () => {{
    if (!idx || !here) return;
    const g = tur.value, sv = siv.checked;
    const rows = idx.p.filter(p => p[6] && (g === "" || p[11] === +g) && (!sv || p[9] !== "closed"))
      .map(p => [dist(here[0], here[1], p[6], p[7]), p]).sort((a, b) => a[0] - b[0]).slice(0, 40);
    list.innerHTML = rows.map(([d, p]) => {{
      const c = idx.c[p[1]], url = "../" + (p[5] || c[0] + "/#p-" + p[4]);
      const tel = p[8] ? `<a href="tel:+90${{p[8].replace(/\\D/g, "").replace(/^0/, "")}}">${{esc(p[8])}}</a>` : "";
      const dir = `https://www.google.com/maps/dir/?api=1&destination=${{p[6]}},${{p[7]}}`;
      return `<li><span class="km">${{d < 10 ? d.toFixed(1) : Math.round(d)}} km${{p[10] === "i" ? "*" : ""}}</span><div><a class="n" href="${{url}}">${{esc(p[0])}}</a>` +
        `<span>${{esc(idx.t[p[3]])}} · ${{esc(p[2] ? p[2] + ", " : "")}}${{esc(c[1])}}</span></div><div class="acts">${{tel}}<a href="${{dir}}" rel="noopener">Yol tarifi</a></div></li>`;
    }}).join("");
    msg.textContent = rows.length ? "En yakın " + rows.length + " yer. * işaretli olanların konumu ilçe merkezine göre, yaklaşıktır." : "Bu seçimle yakında yer bulunamadı.";
  }};
  btn.addEventListener("click", () => {{
    if (!navigator.geolocation) {{ msg.textContent = "Tarayıcın konum özelliğini desteklemiyor."; return; }}
    msg.textContent = "Konum alınıyor…";
    navigator.geolocation.getCurrentPosition(async pos => {{
      here = [pos.coords.latitude, pos.coords.longitude];
      try {{ idx = idx || await (await fetch("../ara.json")).json(); }} catch {{ msg.textContent = "Liste yüklenemedi, sayfayı yenile."; return; }}
      draw();
    }}, err => {{ msg.textContent = err.code === 1 ? "Konum izni verilmedi. Yukarıdaki arama kutusuna il ya da ilçe yazabilirsin." : "Konum alınamadı, tekrar dene."; }},
    {{ enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 }});
  }});
  tur.addEventListener("change", draw); siv.addEventListener("change", draw);
}})();
</script>
"""
    return head("Yakınımdaki Ucuz Konaklama: Öğretmenevi, Misafirhane, Kamp | Yolhanı",
                "Bulunduğun yere en yakın öğretmenevi, kamu misafirhanesi, kamp alanı ve pansiyonları mesafeye göre listele; telefon ve yol tarifi.",
                "yakinimda/", simple_ld("yakinimda", "Yakınımdakiler"), og="yolhani") + body + foot("../")


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
    (OUT / "assets" / "site.css").write_text((ROOT / "tools" / "fonts.css").read_text(encoding="utf-8")
                                             + (ROOT / "tools" / "site.css").read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copy(ROOT / "tools" / "ara.js", OUT / "assets" / "ara.js")
    shutil.copytree(ROOT / "tools" / "fonts", OUT / "assets" / "fonts")
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
    for slug, fn in (("fiyatlar", prices_page), ("ucretsiz-kamp", free_camp_page), ("yakinimda", near_page)):
        write(f"{slug}/index.html", fn())
    write("kaydettiklerim/index.html", saved_page())
    urls = [("", "1.0"), ("hakkinda/", "0.3"), ("fiyatlar/", "0.8"), ("ucretsiz-kamp/", "0.8"), ("yakinimda/", "0.6")]
    for h in HUBS:
        write(f"{h[0]}/index.html", hub_page(*h))
        urls.append((f"{h[0]}/", "0.8"))
    for key, c in CITIES.items():
        write(f"{key}/index.html", city_page(key, c))
        urls.append((f"{key}/", "0.8"))
        for (k2, ilce), u in IPAGE.items():
            if k2 == key:
                write(f"{u}index.html", ilce_page(key, c, ilce))
                urls.append((u, "0.7"))
        for gk in GSLUG:
            if (key, gk) in GPAGE:
                write(f"{GPAGE[(key, gk)]}index.html", group_page(key, c, gk))
                urls.append((GPAGE[(key, gk)], "0.7"))
        for p in c["places"]:
            if p["id"] in PAGE:
                write(f"{PAGE[p['id']]}index.html", place_page(key, c, p))
                urls.append((PAGE[p["id"]], "0.5"))
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
