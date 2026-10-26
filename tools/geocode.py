"""Kamu misafirhanelerine (koordinatı olmayan yerlere) konum bulur. OpenStreetMap Nominatim kullanır.

Nominatim kullanım kuralları: saniyede en fazla 1 istek, tanımlayıcı User-Agent, sonuçlar önbelleğe alınır.
Sonuçlar data/geocode.json'a yazılır; tekrar çalıştırıldığında yalnızca eksik olanlar sorulur.

Her sonuç için doğruluk:
  "yer"   → tesisin kendisi bulundu (ad ile)
  "adres" → adres (mahalle/cadde) bulundu
  "ilce"  → yalnızca ilçe merkezi bulundu (haritada gösterilmez, yakınlık sıralamasında kullanılır)

Kullanım: python3 -I tools/geocode.py
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geocode.json"
UA = "YolhaniKonaklama/1.0 (personal non-commercial travel guide)"
data = json.loads((ROOT / "data" / "yolhani.json").read_text(encoding="utf-8"))
cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def ask(params):
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({**params, "format": "jsonv2", "countrycodes": "tr",
                                                                    "limit": 1, "addressdetails": 1, "accept-language": "tr"})
    time.sleep(1.1)
    r = subprocess.run(["curl", "-s", "-m", "30", "-A", UA, url], capture_output=True, text=True)
    try:
        res = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return res[0] if res else None


def in_city(hit, city):
    a = hit.get("address", {})
    return city.lower() in " ".join(str(v) for v in a.values()).lower()


def clean_addr(s):
    s = re.sub(r"\b(No|Kat|Daire|D|K)\s*[:.]?\s*\d+\S*", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" ,")


todo = [(c["name"], p) for c in data["cities"].values() for p in c["places"] if not p["lat"] and p["id"] not in cache]
print(f"{len(todo)} yer sorulacak", flush=True)
for i, (city, p) in enumerate(todo, 1):
    ilce = p["ilce"] if p["ilce"] and "Merkez" not in p["ilce"] else ""
    hit, kind = None, None
    h = ask({"q": f"{p['name']}, {ilce + ', ' if ilce else ''}{city}"})
    if h and in_city(h, city):
        hit, kind = h, "yer"
    if not hit and p["addr"]:
        h = ask({"q": f"{clean_addr(p['addr'])}, {city}"})
        if h and in_city(h, city):
            hit, kind = h, "adres"
    if not hit:
        h = ask({"q": f"{ilce or city}, {city}"})
        if h and in_city(h, city):
            hit, kind = h, "ilce"
    cache[p["id"]] = {"lat": round(float(hit["lat"]), 5), "lon": round(float(hit["lon"]), 5), "kind": kind} if hit else None
    if i % 20 == 0 or i == len(todo):
        OUT.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"{i}/{len(todo)}", flush=True)
print("bitti", flush=True)
