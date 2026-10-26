# Yolhanı statik site

Google'da çıkması için Yolhanı'nın statik sürümü (~2.440 sayfa): ana sayfa, 81 il sayfası, il-tür sayfaları
(ör. `antalya/ogretmenevleri/`), telefonu ya da adresi olan her yer için yer sayfası (ör. `antalya/akseki-ogretmenevi/`),
4 rehber sayfası, hakkında, kaydettiklerim, `sitemap.xml`, `robots.txt`, paylaşım görselleri ve uygulama simgeleri.

Canlı site: https://hkblackbird.github.io/yolhani/

## Klasörler

- `data/yolhani.json`: uygulamadan dışarı aktarılan yer verisi (81 il, 3.204 yer)
- `tools/build.py`: siteyi üreten betik
- `tools/site.css`: stil dosyası
- `tools/ara.js`: hızlı arama (il, ilçe ve yer adı); `docs/ara.json` dizinini kullanır
- `tools/fonts/`, `tools/fonts.css`: siteyle birlikte yayınlanan yazı tipleri (Zilla Slab, Work Sans; OFL)
- `tools/form.json` (isteğe bağlı): ziyaretçi geri bildirimi için Google Form ayarı, aşağıya bak
- `data/osm_tags.json`: OSM'den web sitesi, internet, ücret, açılış saati etiketleri (Overpass)
- `tools/og.py`: paylaşım görsellerini (`docs/og/*.jpg`) ve simgeleri Chrome ile üretir
- `docs/`: üretilen site (GitHub Pages bu klasörü yayınlar)

## Siteyi yeniden üretmek

```sh
python3 tools/build.py https://hkblackbird.github.io/yolhani
python3 tools/og.py          # sayılar değiştiyse paylaşım görsellerini yenile
```

Alan adı alındığında adresi değiştirip tekrar çalıştır:

```sh
python3 tools/build.py https://yolhani.com
```

## Ziyaretçi geri bildirimi (Google Form)

`tools/form.json` varsa her yer sayfasında "Yorum yaz", kartlarda "Düzelt", il sayfalarında "Yer öner" bağlantıları
bu formu ilgili yerin adı, ili, ilçesi ve sayfa adresi önceden doldurulmuş olarak açar. Dosya yoksa yorum ve yer önerme
bağlantıları gösterilmez, "Düzelt" GitHub issue açar.

```json
{"url": "https://docs.google.com/forms/d/e/FORM_ID/viewform",
 "entries": {"tur": "entry.111", "ad": "entry.222", "il": "entry.333", "ilce": "entry.444", "sayfa": "entry.555"},
 "tur": {"yorum": "Yorum / puan", "duzelt": "Bilgi düzeltme", "ekle": "Yeni yer önerisi"}}
```

`entry.*` numaraları formdaki "Önceden doldurulmuş bağlantı al" ile alınan bağlantıdadır.

## GitHub Pages'te yayınlamak

1. github.com'da hesap aç ve `yolhani` adında **public** bir depo oluştur.
2. Bu klasörü depoya yükle (yalnızca `docs/` yeterli; `data/` klasörünü yüklemene gerek yok).
3. Depoda **Settings → Pages → Build and deployment**: Source = *Deploy from a branch*, Branch = `main`, klasör = `/docs`.
4. Birkaç dakika sonra site `https://KULLANICIADI.github.io/yolhani/` adresinde açılır.
5. `tools/build.py`'yi kendi kullanıcı adınla yeniden çalıştırıp `docs/` klasörünü tekrar yükle (sitemap ve canonical adresleri doğru olsun diye).

## Google Search Console

1. search.google.com/search-console → *Mülk ekle* → *URL ön eki* → site adresini yaz.
2. Doğrulama için "HTML etiketi" yöntemini seç; verilen `<meta name="google-site-verification" ...>` etiketini `tools/build.py` içindeki `head()` fonksiyonuna ekleyip siteyi yeniden üret ve yükle.
3. *Site haritaları* bölümüne `sitemap.xml` yaz ve gönder.

## Veri ve lisans notları

- Kamp alanı, pansiyon ve hostel verisi © OpenStreetMap katkıcıları, ODbL lisansı. Sayfalarda atıf var.
  `data/yolhani.json` dosyasını herkese açık paylaşırsan, ODbL gereği o veri dosyası da ODbL lisanslı olmalı.
- Kamu misafirhanesi listesi kamumisafirhaneleri.com.tr'den derlendi. Herkese açık yayından önce
  site sahibinden izin almak ya da bilgileri resmi kaynaklardan doğrulamak iyi olur.
