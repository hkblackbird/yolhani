# Yolhanı statik site

Google'da çıkması için Yolhanı'nın statik sürümü: ana sayfa, 81 il sayfası, 4 rehber sayfası (öğretmenevleri, kamp alanları,
kamu misafirhaneleri, pansiyon ve hosteller), hakkında, `sitemap.xml`, `robots.txt`, paylaşım görselleri ve uygulama simgeleri.

Canlı site: https://hkblackbird.github.io/yolhani/
Yorum ve puanlar claude.ai'deki uygulamada kalır; her il sayfası oraya bağlanır.

## Klasörler

- `data/yolhani.json`: uygulamadan dışarı aktarılan yer verisi (81 il, 3.204 yer)
- `tools/build.py`: siteyi üreten betik
- `tools/site.css`: stil dosyası
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
