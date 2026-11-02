# AI Video Analizi

Kamera (CCTV/DVR) kayıtlarını bilgisayarda inceleyen, ücretsiz ve açık kaynaklı Windows uygulaması.

- **Her biçimi açar:** VLC'nin açamadığı DVR dosyaları da desteklenir: Dahua DAV, Hikvision, ham H.264/H.265, başlığı bozuk ya da uzantısı yanlış dosyalar. Dosya türü içeriğe bakılarak tanınır.
- **Delil bütünlüğü:**
  - Orijinal dosyaya dokunulmaz.
  - SHA-256 kaydedilir.
  - Kayıpsız bir kopya ve oynatma kopyası (NVENC ile) üretilir.
- **Yerel analiz:** Hareket, kişi/araç tespiti ve takibi, yüz gruplama, fotoğrafla yüz arama, Türk plakası okuma ve görsel arama yapılır. Hepsi bilgisayarda, GPU (DirectML) ile çalışır.
- **Saat düzeltme:**
  - Ekrandaki saat yazısı OCR ile okunur.
  - Kayıt boşlukları ve saat sıçramaları bulunur.
  - Gerçek saat referansıyla sabit fark ya da günlük kayma düzeltilir.
- **Türkçe soru:**
  - *"14:00–15:00 arası kırmızı montlu biri geçti mi?"* gibi sorular sorulabilir.
  - **Hızlı** mod tamamen yereldir.
  - **Doğrulamalı** ve **Derin** modlar, OpenRouter üzerinden kullanıcının seçtiği görsel/video modelini kullanır.
- **Model karşılaştırma:** Soru sonuçlarını "doğru / yanlış" diye işaretleyip aynı adayları birden çok modele doğrulatabilirsiniz. Her model için isabet, duyarlılık, maliyet ve süre tablosu çıkar.
- **Ortak zaman çizelgesi:** Tüm kameraların kayıtları gerçek saat ekseninde yan yana gösterilir. Ardışık kesitler ve kayıt boşlukları görünür; tıklayınca ilgili ana gidilir.
- **İyileştirme:** Klasik filtreler ve Real-ESRGAN ile AI büyütme vardır. AI ile büyütülen çıktılar filigranla işaretlenir.
- **Rapor:** Bulgular onaylanır ve PDF vaka raporu üretilir.
- **Uygulama içi güncelleme:** Yeni sürüm Ayarlar > Sistem'den indirilip kurulur. Paket SHA-256 ile doğrulanır, `data/` korunur ve hata olursa önceki sürüm geri yüklenir.
- **Gizlilik:** Hesap ve telemetri yoktur. Tüm veriler exe'nin yanındaki `data/` klasöründe tutulur.

Kullanıcı belgesi: [docs/BENIOKU.txt](docs/BENIOKU.txt) · Plan: [docs/PLAN.md](docs/PLAN.md)

## Mimari

```
app/                  Tauri 2 kabuk (Rust) + React/TypeScript arayüz
  src-tauri/src/main.rs   veri klasörü seçimi, motoru başlatma/durdurma, WebView2 verisini data/'ya yönlendirme
  src/                    arayüz (Türkçe)
engine/               Python 3.13 analiz motoru (FastAPI, yalnızca 127.0.0.1 + oturum token'ı)
  aiva/media/            içerik tanıma (sniff), açma stratejileri, kayıpsız kopya, proxy, kare erişimi (PyAV)
  aiva/timecorr/         zaman eşleme (medya → kamera → gerçek saat), OSD okuma, dosya adı ayrıştırma
  aiva/analyze/          YOLOX, takip, hareket, YuNet+SFace, plaka, CLIP, OCR, ONNX Runtime oturumları
  aiva/ai/               OpenRouter kataloğu/istemcisi, soru planlayıcı, yerel aday arama, model doğrulaması
  aiva/*.py              iş kuyruğu, vakalar, videolar, analiz işi, sorgu, iyileştirme, dışa aktarma, rapor
models/               ONNX modelleri (git dışında; scripts/download_models.py)
scripts/              model indirme, simge, dağıtım paketi
testdata/             gerçek test örnekleri (git dışında)
```

Motor açılınca stdout'a `AIVA_READY {"port":…, "token":…}` yazar. Arayüz bu satırla bağlanır ve tüm istekleri `x-aiva-token` başlığıyla gönderir. Video ve görsel etiketleri başlık gönderemediği için bu isteklerde token `?k=` parametresiyle gider.

## Geliştirme

Gerekenler: Python 3.13, Node.js 22+, Rust (stable), Visual Studio C++ Build Tools.

```powershell
# Motor
cd engine
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pip install --no-deps rapidocr==3.10.0     # onnxruntime CPU paketini çekmemesi için
cd ..
engine\.venv\Scripts\python scripts\download_models.py   # ~520 MB

# Arayüz
cd app
npm install
npx tauri dev            # geliştirme: motor engine\.venv ile başlatılır, veri: depo\data
```

### Testler

```powershell
cd engine; .venv\Scripts\python -m pytest            # sentetik video seti + uçtan uca API testleri
cd app; npx tsc --noEmit -p .; npx vitest run
```

Gerçek örnek testleri için `testdata/real/` klasörüne şu dosyalar konur (OpenCV ve YOLOX örnek verileri): `vtest.avi`, `dog.jpg`, `lena.jpg`, `messi5.jpg`. Bu dosyalar yoksa ilgili testler atlanır.

### Dağıtım paketi

```powershell
engine\.venv\Scripts\python scripts\build_release.py
# → dist\AIVideoAnalizi\ (taşınabilir klasör) ve dist\AIVideoAnalizi-<sürüm>-win64.zip
```

## Lisans

GPL-3.0-or-later. FFmpeg kitaplıkları (PyAV) GPL bileşenleri içerdiği için uygulamanın tamamı GPL ile dağıtılır. Ayrıntılar [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) dosyasında.
