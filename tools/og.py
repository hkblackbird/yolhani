"""Paylaşım görsellerini (1200x630 PNG) ve uygulama simgelerini Chrome ile üretir.

build.py'nin yazdığı tools/og.json dosyasını okur, docs/og/<ad>.png dosyalarını oluşturur.
Simgeler tools/ klasörüne yazılır; build.py bunları docs/assets/ altına kopyalar.

Kullanım: python3 tools/og.py [ad ...]   (ad verilmezse hepsi)
"""
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
ARCH = '<path d="M4 21V11a8 8 0 0 1 16 0v10"/><path d="M9 21v-6a3 3 0 0 1 6 0v6"/><path d="M2 21h20"/>'
FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@700&family=Work+Sans:wght@500;600&display=swap">'


def shot(markup, out, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(markup)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}",
                    "--virtual-time-budget=4000", f"--screenshot={out}", f"file://{f.name}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path(f.name).unlink()


def og_markup(title, sub):
    e = html.escape
    return f"""<!doctype html><meta charset="utf-8">{FONTS}<style>
body{{margin:0;width:1200px;height:630px;background:linear-gradient(160deg,#6b4426,#4f3219);color:#fdfbf7;font-family:"Work Sans",sans-serif;position:relative;overflow:hidden}}
.arch{{position:absolute;right:70px;bottom:-60px;width:330px;height:430px;border:44px solid rgba(255,255,255,.07);border-bottom:0;border-radius:165px 165px 0 0}}
.box{{position:absolute;left:84px;top:78px;right:420px;bottom:78px;display:flex;flex-direction:column;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:16px;font:700 38px "Zilla Slab",serif}}
.mark{{width:58px;height:58px;border-radius:15px;background:#fdfbf7;color:#6b4426;display:grid;place-items:center}}
h1{{font:700 66px/1.08 "Zilla Slab",serif;margin:0}}
p{{font-size:28px;font-weight:500;opacity:.85;margin:18px 0 0}}
.tag{{font-size:22px;letter-spacing:.14em;text-transform:uppercase;opacity:.7;font-weight:600}}
</style><div class="arch"></div><div class="box">
<div class="brand"><span class="mark"><svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">{ARCH}</svg></span>Yolhanı</div>
<div><h1>{e(title)}</h1><p>{e(sub)}</p></div><div class="tag">Yol üstündeki ucuz konaklama</div></div>"""


def icon_markup(size):
    return f"""<!doctype html><style>body{{margin:0;width:{size}px;height:{size}px;background:#6b4426;display:grid;place-items:center}}</style>
<svg width="{size * .62:.0f}" height="{size * .62:.0f}" viewBox="0 0 24 24" fill="none" stroke="#fdfbf7" stroke-width="2.2" stroke-linecap="round">{ARCH}</svg>"""


def main():
    og = json.loads((ROOT / "tools" / "og.json").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(og)
    out = ROOT / "docs" / "og"
    out.mkdir(parents=True, exist_ok=True)
    for i, k in enumerate(names, 1):
        png = out / f"{k}.png"
        shot(og_markup(*og[k]), png, 1200, 630)
        # JPEG çok daha küçük; sosyal medya önizlemeleri için yeterli kalite
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82", str(png), "--out", str(out / f"{k}.jpg")],
                       check=True, stdout=subprocess.DEVNULL)
        png.unlink()
        print(f"\r{i}/{len(names)} {k}      ", end="", flush=True)
    print()
    # Simgeler: Chrome en az 500 piksel genişlikte açıldığı için önce büyük çizilip sips ile küçültülür
    tmp = ROOT / "tools" / "_icon.png"
    shot(icon_markup(512), tmp, 512, 512)
    subprocess.run(["sips", "-c", "512", "512", "--cropOffset", "0", "0", str(tmp), "--out", str(ROOT / "tools" / "icon-512.png")], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["sips", "-z", "180", "180", str(ROOT / "tools" / "icon-512.png"), "--out", str(ROOT / "tools" / "apple-touch-icon.png")], check=True, stdout=subprocess.DEVNULL)
    tmp.unlink()
    (ROOT / "tools" / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#6b4426"/>'
        f'<g transform="translate(5 5) scale(.917)" fill="none" stroke="#fdfbf7" stroke-width="2.4" stroke-linecap="round">{ARCH}</g></svg>', encoding="utf-8")
    print("görseller hazır")


if __name__ == "__main__":
    main()
