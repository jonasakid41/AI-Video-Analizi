# AI Video Analizi — Ürün ve Teknik Plan

> **Sürüm:** v0.3 · **Tarih:** 2 Kasım 2026 · **Durum:** İlk derleme (v0.1.0) tamamlandı — bkz. §0.2
> Model adları, sayılar ve fiyatlar 2 Kasım 2026'da OpenRouter'ın canlı model listesinden alındı. Bu bilgiler sık değişir.
> **v0.2 değişiklikleri:** Ekip kararları işlendi (§0.1). Plan; ücretsiz, girişsiz, taşınabilir, tamamen yerel bir uygulamaya göre güncellendi. Sunucu, kullanıcı/rol, KVKK süreci ve ticari entegrasyonlar kapsamdan çıkarıldı.

---

## 0. Özet

- **Ürün:** Ücretsiz bir Windows masaüstü uygulaması. Kullanmak için giriş veya hesap gerekmez; herkes kullanabilir. Polisler, güvenlik yöneticileri ve kamera kaydı inceleyen herkes için tasarlanır.
  - **Yükle ve sor:** Kullanıcı kamera kaydını yükler ve Türkçe soru sorarak ilgili anları bulur. Örnek: *"14:00–15:00 arası giriş kapısından kırmızı montlu biri girdi mi?"*
  - **Saati düzelt:** Hatalı kamera saati düzeltilir; tüm sonuçlar gerçek saatle gösterilir.
  - **İyileştir:** Gerekirse bulunan kare veya kesit netleştirilip büyütülür.
- **Tamamen yerel ve taşınabilir:**
  - Sunucu yoktur, hesap yoktur, telemetri yoktur.
  - Tüm veriler (vakalar, analizler, sorgu geçmişi, ayarlar) **exe'nin yanındaki `data/` klasöründe** durur.
  - Dışarıya giden tek bağlantı, kullanıcının seçtiği **AI API'sidir**. Kullanıcı kendi OpenRouter anahtarını girer.
- **Teknoloji:**
  - **Arayüz:** Tauri 2 + React/TypeScript.
  - **Analiz motoru:** Python 3.12. Uygulamayla birlikte açılıp kapanan yerel bir alt süreçtir; sunucu değildir.
  - **Yardımcı katmanlar:** FFmpeg, ONNX Runtime ve SQLite.
- **Temel tasarım kararı:** Videonun tamamı AI'a gönderilmez.
  1. Önce dizüstü bilgisayarın GPU'sunda hızlı bir **yerel ön-analiz** yapılır: hareket, kişi/araç tespiti, takip ve görsel arama indeksi.
  2. Sonra yalnızca **aday kareler ve kısa kesitler** seçilen modele doğrulatılır.

  Böylece maliyet ve süre kat kat düşer.
- **Saat düzeltme:** Bulgular videonun kendi zaman ekseninde (PTS) saklanır. Gerçek saat her gösterimde hesaplanır. Düzeltme değişince yeniden analiz gerekmez.
- **İyileştirme:** Klasik filtreler (deterministik) ve AI ile büyütme (Real-ESRGAN) ayrı tutulur. AI ile büyütülmüş çıktılar *"AI ile iyileştirilmiştir"* damgası taşır.
- **Süre tahmini (1–2 geliştirici + AI destekli kodlama):**
  - **MVP:** ~10–12 hafta.
  - **v1:** ~13–17 hafta.

### 0.1 Alınan kararlar (2 Kasım 2026)

| # | Konu | Karar | Plana etkisi |
|---|---|---|---|
| 1 | Örnek kayıtlar | Şimdilik gerçek kayıt yok. Hedef, normal bir medya oynatıcıdan daha geniş format desteği; zamanla artırılacak. | Dönüştürücü FFmpeg tabanlı olacak, ek olarak VLC'nin açamadığı yaygın durumları da çözecek (§4.1). Test seti **sentetik olarak üretilecek** ve açık örnek arşivleri kullanılacak. Üretici SDK'sı ve ticari araç entegrasyonu "ileride". |
| 2 | Buluta gönderim | Uygun; kayıtlar zaten kesit halinde. | Bulut analizi varsayılan olarak açık. Hukuk süreci kaldırıldı. İlk açılışta kısa bir bilgilendirme gösterilecek (§4.9). |
| 3 | Donanım | Dizüstü bilgisayar + ortalama bir NVIDIA GPU. | Video çözme/kodlama NVDEC/NVENC ile yapılacak. AI çıkarımı DirectML ile her GPU'da çalışacak. VRAM'e (~4–8 GB) göre model boyutu seçilecek. Pil ve ısınma için önlemler alınacak (§4.4). |
| 4 | Dağıtım | Tek bilgisayar. Sunucu ve arka uç hiç olmayacak. API dışında gereksinim yok. | Çok kullanıcılı yapı, sunucu modu, roller ve güncelleme sunucusu kapsamdan tamamen çıkarıldı. |
| 5 | Ürün modeli | Tamamen ücretsiz ve girişsiz. Hiçbir şey kayıt altına alınmayacak. Yalnızca video analizleri ve araştırma kayıtları **yerelde, exe'nin yanında** tutulacak. | Uygulama **taşınabilir** olacak (ZIP'ten çıkar ve çalıştır). Her kullanıcı kendi API anahtarını kullanacak (BYOK). Hesap, telemetri, bulut senkronizasyonu yok. Lisans yükümlülükleri ücretsiz dağıtımda da geçerli (§6). |
| 6 | Arayüz dili | Tamamen Türkçe. | Arayüz, mesajlar, rapor ve belgeler Türkçe. |
| 7 | Plaka / yüz | Plaka okuma, yüz tanıma ve ayrıntıları olacak. | v1'e alındı: yüz tespiti + kişi gruplama + fotoğrafla yüz arama; Türk plakası okuma + kısmi plaka arama. Sonuçlar "ipucu" olarak işaretlenir. |
| 8 | Lisans | Tamamen açık kaynak. | GPL-3.0-or-later (PyAV'ın içindeki FFmpeg GPL bileşenler taşıdığı için). |

### 0.2 Uygulama durumu — v0.1.0 ilk derleme

Tüm fazlar (0–5) ilk sürüm olarak uygulandı; taşınabilir paket `dist/AIVideoAnalizi/` olarak üretiliyor. Uygulama sırasında plandan bilinçli sapmalar:

| Planda | Uygulamada | Neden |
|---|---|---|
| Ayrı `ffmpeg.exe` | PyAV içindeki FFmpeg 9 kitaplıkları | Tek süreç, ek exe yok. NVENC/QSV/AMF ve Windows Media Foundation kodlayıcıları ile `dhav` demuxer'ı içinde geliyor. |
| RF-DETR | YOLOX-S / YOLOX-Tiny (Apache-2.0) | Hazır ONNX dosyası var. RF-DETR'ı ONNX'e dönüştürmek PyTorch gerektiriyor; ileride eklenebilir. |
| SigLIP 2 | CLIP ViT-B/32 (MIT) | Hazır ONNX ve tokenizer var. Türkçe sorular planlayıcıda İngilizce görsel tarife çevriliyor. |
| sqlite-vec | Vektörler SQLite'ta BLOB, arama numpy ile | Ek bağımlılık yok; vaka ölçeğinde anlık çalışıyor. |
| Vaka başına `case.sqlite` | Tek `data/aiva.sqlite` | Daha basit. Vakalar `data/cases/<id>/` altında ayrı klasörlerde duruyor. |
| — | Yüz: YuNet + SFace (OpenCV); plaka: RapidOCR (PP-OCRv6) + Türk plaka biçimi düzeltmesi | Açık lisanslı. InsightFace modelleri ticari olmayan lisanslı olduğu için kullanılmadı. |

**v0.1.0 yayımından önce eklenenler**

- **Model karşılaştırma aracı** (plandaki "değerlendirme aracı"): Sonuçlar ✓/✗ ile işaretlenir, aynı adaylar 1–5 modele doğrulatılır. Model başına isabet, duyarlılık, maliyet ve süre çıkar; "kullan" ile doğrulayıcı model değiştirilir.
- **Ortak kamera zaman çizelgesi:** Vakadaki tüm kayıtlar gerçek saat ekseninde kamera başına bir şerittir. Ardışık kesitler, boşluklar ve AI sonuçları görünür. Kesit bitince aynı kameranın sonraki kesiti otomatik oynar.
- **Kod incelemesi ve düzeltmeleri:**
  - Yarıda kalan kopyalar artık "orijinal" sayılmıyor; yeniden dönüştürmede SHA-256 doğrulanıyor.
  - Silmeden önce çalışan işler durduruluyor.
  - İptal edilen analiz yarım sonuç bırakmıyor.
  - Motor çökerse otomatik yeniden başlatılıyor, arayüz yeniden bağlanıyor.
  - Çelişkili saat referansları reddediliyor.
  - Eski "konuma git" istekleri başka videoya uygulanmıyor.
  - WebSocket zamanlayıcı sızıntısı ve gereksiz sorgular giderildi.

**Test durumu**

- **Motor (84 test):**
  - Sentetik 19 dosyalık biçim seti: codec/kap kombinasyonları, yanlış uzantı, sahte üretici başlığı, ham akış, kesik ve bozuk dosyalar.
  - Saat eşleme ve ekran saati okuma (+222 sn kayma, 600 sn sıçrama).
  - Uçtan uca API akışı: dönüştürme → analiz → plaka → saat → yerel ve sahte modelli soru → bulgu → iyileştirme → dışa aktarma → PDF.
  - Gerçek yaya videosu (`vtest.avi`, DivX 3): 80 sn kayıt RTX 4060'ta ~4 sn'de analiz edildi.
- **Birim testleri (motor):** Plaka biçimi, yerel planlayıcı, renk, takip, DPAPI, katalog ve OpenRouter hata eşlemesi.
- **0.1.1 ile eklenen motor testleri:**
  - Ayrı süreçte çalışan işçi: çökme, takılma, iptal ve açılışta kurtarma.
  - Hareket türleri: sallanan ağaçlı sentetik videoda ağaç hareketi önemsiz sayılıyor, yaya olayları etiketleniyor.
  - Dinamik arama: aday bulunamazsa kare adayları ve ikinci tur devreye giriyor.
  - Araç kopyalarının birleştirilmesi.
- **0.1.2 ile eklenen motor testleri (toplam 95):**
  - Güncelleme: sahte GitHub ile sürüm denetimi, yönlendirmeli indirme, SHA-256 uyuşmazlığı, özeti olmayan paket, zararlı ZIP yolu, açılış temizliği.
  - Şemaya uymayan model planı ve doğrulama cevabının düzeltilmesi; eski kayıtların okunurken düzeltilmesi.
- **0.1.3–0.1.7 ile eklenen motor testleri (toplam 120):**
  - CLI araçları (sahte süreçle): Claude Code'a satır içi görüntü ve JSON şeması, .cmd kabuğu, Codex'e görüntü/şema dosyası, Gemini'ye @dosya, kullanım sınırı ve oturum hataları, çevrimdışı katalog, "Kullan".
  - Uzak kişiler: gerçek yaya videosu 1920×1080 tuvalde küçültülünce eski kurallarla 1 kısa iz, yeni kurallarla 19 iz (16'sı ≥3 kare) bulundu.
  - Siyah-beyaz/karanlık kayıt: renksiz oranı, tonla tarif, renk koşulunun adayları elememesi, modele verilen not.
  - Dedektörün tanımadığı hareketin doğrulama adayı olması.
  - AV1 videonun dönüştürülmesi; işçi süreç hatasının türü ve ayrıntısıyla taşınması.
  - Hikvision IMKH + MPEG-PS (H.265, G.711, bölünmüş PES): dönüştürme, eşit damgalarda kare atılmaması, kamera saatinin geri atlaması ve 33 bit sayaç taşması.
  - Yapay zekâ taraması ve ön incelemesi: sahte model ızgara görüntülerini açıp kutunun göründüğü kareleri renginden bulur; tarama yerel analizin aday yapmadığı anı bulur, ön inceleme notları soruda kullanılır, "Neler oldu?" notları içerir.
  - Parçalı tarama: duran uzak kişiler (1080p) yalnızca parçalı taramayla bulunur; kopuk iz birleştirme; yapay zekânın yerelden fazla saydığı anların işaretlenmesi.
- **CLI (elle, gerçek Claude Code):** Siyah-beyaz gece kaydında "Kırmızı montlu biri geçti mi?" doğrulamalı modda yanıtlandı. 3 çağrı yapıldı, OpenRouter ücreti 0. Paketlenmiş uygulamada "Test et" 2,6 sn'de yanıt verdi.
- **Arayüz (14 test):**
  - Tip kontrolü.
  - Saat eşlemenin motorla aynı sonucu verdiği doğrulandı.
  - Tüm sekme ve pencereler sahte motor verisiyle jsdom'da çizildi.
  - Eksik alanlı plan çökme yapmıyor; çizim hatası yalnızca kendi bölümünü kapatıyor ve günlüğe yazılıyor.
  - Güncelleme bölümü: yeni sürüm, indirilmiş paket ve sürüm notları.
- **Güncelleyici (paketlenmiş uygulamada elle):**
  - Gerçek GitHub'dan 563 MB paket indirildi, SHA-256 doğrulandı ve uzun Türkçe yollu bir klasöre açıldı.
  - Arayüzden "Yeniden başlat ve kur" → onay → dosya değişimi → yeni sürüm açıldı ve "Güncelleme tamamlandı" bildirimi göründü.
  - Kilitli dosyayla başarısızlık: eski sürüm geri yüklendi ve hata bildirimi gösterildi.
  - WebView2 çizim süreci sonlandırıldı: sayfa kendiliğinden yeniden yüklendi.
- **Paket:**
  - Paketlenmiş motorda duman testi yapıldı.
  - Taşınabilir uygulama örnek bir vakayla açıldı ve pencere görüntüsüyle kontrol edildi.

**Henüz doğrulanmayanlar**

- Gerçek bir OpenRouter anahtarıyla canlı model çağrıları: sahte yanıtlarla test edildi.
- Gerçek DVR dışa aktarımları: sentetik ve açık örneklerle test edildi.
- Arayüzün elle kullanım testi.

---

## 1. Kapsam

### 1.1 Kullanıcılar
- **Soruşturmacı / analist:** Kayıt inceler, bulgu çıkarır, rapor üretir.
- **Güvenlik / tesis yöneticisi:** Olay sonrası hızlı inceleme yapar.
- **Genel kullanıcı:** Kendi kamera kaydında bir şey arayan herkes. Uygulama ücretsiz ve girişsizdir.

### 1.2 Ana senaryolar
1. **Açılmayan dosya:** Kullanıcı farklı bir DVR'dan alınmış, VLC'nin açamadığı bir dosyayı sürükleyip bırakır. Uygulama formatı içeriğe bakarak tanır, dönüştürür ve oynatır. Aynı kameranın ardışık kesitleri tek bir zaman çizelgesinde birleştirilebilir.
2. **Hızlı özet:** Yükleme bitince uygulama şunları gösterir:
   - Hangi saatlerde hareket olduğu
   - Kaç kişi ve araç geçtiği
   - Kayıtta boşluk olup olmadığı
3. **Soru + alan:** Kullanıcı doğal dilde soru sorabilir, bir alan (ROI) çizebilir veya ikisini birlikte kullanabilir. Örnekler: *"Bu alana kim girdi?"*, *"Bu çizgiyi geçen araçlar?"*
4. **Saat hatası:** Örneğin kamera saati 3 dk 42 sn ileri. Kullanıcı bir referans noktası girer. Bundan sonra tüm zamanlar, sorgular ve rapor düzeltilmiş saatle çalışır.
5. **İyileştir ve dışa aktar:** Bulunan anın karesi veya kesiti iyileştirilip dışa aktarılır. Ardından PDF rapor üretilir.

### 1.3 Kapsam dışı
- **Hiçbir sürümde olmayacaklar (tasarım ilkesi):**
  - Sunucu / bulut arka ucu
  - Hesap ve giriş
  - Telemetri ve kullanım istatistiği
  - Otomatik güncelleme sunucusu
  - AI API'si dışında herhangi bir ağ bağlantısı
- **v1'de olmayanlar:**
  - Canlı kamera akışı
  - Yüz tanıma / kimlik eşleştirme
  - Üretici SDK'larıyla şifreli format çözme

---

## 2. Teknoloji seçimi

### 2.1 Seçilen yığın

| Katman | Seçim | Neden |
|---|---|---|
| Masaüstü kabuğu | **Tauri 2** | Windows 10/11'deki WebView2'yi kullandığı için uygulama küçüktür. Kurulum gerektirmeden taşınabilir exe olarak çalışabilir. Python motorunu "sidecar" olarak başlatır. |
| Arayüz | **React + TypeScript + Vite**, Tailwind + shadcn/ui, Zustand, TanStack Query | Modern, koyu temalı arayüz hızlı kurulur. AI kod asistanları en verimli bu ekosistemde çalışır. |
| Analiz motoru | **Python 3.12**, FastAPI + WebSocket, Pydantic. PyInstaller **onedir** ile paketlenir. | Görüntü işleme / AI kütüphanelerinin neredeyse tamamı Python'dadır. *onedir* modu, her açılışta `%TEMP%`'e dosya açmaz. |
| Video | **FFmpeg / FFprobe** (ayrı exe) + **PyAV** (kare erişimi) | Neredeyse her codec'i destekler. NVIDIA **NVDEC / NVENC** ile çözme ve kodlama donanımda yapılır. |
| Yerel çıkarım | **ONNX Runtime + DirectML** (her GPU'da çalışır), yedek olarak CPU | NVIDIA, AMD ve Intel GPU'larda ek CUDA kurulumu gerektirmez; ücretsiz ve herkese açık bir ürün için doğru seçim. DirectML bakım modunda ama destekleniyor. EP katmanı soyut tutulur; ileride CUDA paketi veya Windows ML eklenebilir. |
| Veri | **SQLite** (WAL) + **sqlite-vec**, `data/` klasöründe | Kurulum gerektirmez. Her vaka tek dosyadır ve taşınabilir. Vektör arama da dahildir. |
| AI API | **OpenRouter** (OpenAI uyumlu), `openai` Python SDK | Tek anahtarla yüzlerce modele erişilir; ücretsiz modeller de dahil. Gelişmiş ayarlardan `base_url` değiştirilerek yerel model sunucusu kullanılabilir. |
| Rapor | Jinja2 şablon + **ReportLab** (PDF) | Ek çalışma zamanı bağımlılığı gerektirmez. |
| Dağıtım | **Taşınabilir ZIP** (GitHub Releases). İsteğe bağlı kurulum dosyası. | Çıkar ve çalıştır. Kurulum, yönetici izni veya kayıt defteri gerekmez. |

### 2.2 "AI ile kodlama" açısından dil seçimi
- **Doğru dil seçimi:** Python ve TypeScript, Claude Code gibi AI kod asistanlarının en isabetli kod ürettiği diller.
- **Tip güvenliği şart:** TypeScript `strict`, Python'da Pydantic + pyright. AI'ın ürettiği hatalar derleme ve kontrol aşamasında yakalanır.
- **Sözleşme önce gelir:** FastAPI OpenAPI şemasını üretir. `openapi-typescript` bu şemadan arayüz tiplerini otomatik oluşturur. Ön uç ile arka uç arasındaki uyumsuzluk derlemede görünür.
- **Rust kodu minimal kalır:** Tauri tarafında yalnızca pencere yönetimi, sidecar başlatma ve veri klasörü yönetimi olur.
- **Repo düzeni:** Küçük ve testli modüller, doldurulmuş bir `CLAUDE.md` ve modül başına README.

### 2.3 Değerlendirilen alternatifler

| Seçenek | Artı | Eksi | Karar |
|---|---|---|---|
| **Tauri 2 + React/TS + Python motor** | Modern arayüz, en güçlü AI ekosistemi, küçük ve taşınabilir paket. | İki süreç ve üç dil (Rust kısmı çok ince). | ✅ **Seçildi** |
| PySide6 (Qt) + tek Python | Tek dil, tek süreç; mpv ile güçlü yerel oynatıcı. | Arayüz bileşen ekosistemi zayıf; AI asistanları QML'de daha az verimli. | Yedek |
| Electron + React + Python | Olgun bir ekosistem. | Paket ~150 MB daha büyük, bellek kullanımı yüksek. | Önerilmez |
| C# .NET (WPF / WinUI 3) | En iyi Windows entegrasyonu. | Görüntü işleme / AI kütüphaneleri Python kadar zengin değil. | Önerilmez |

> **Oynatıcı neden web tabanlı olabiliyor?** Dönüştürücü her girdiyi standart bir **H.264 MP4 çalışma kopyasına** (proxy) çevirir. Bu nedenle oynatıcının egzotik formatları tanıması gerekmez. Kare-doğru işlemler kayıpsız kopya üzerinden motor tarafında yapılır.

---

## 3. Mimari

```
┌───────────────────────────────────────────────────────────────┐
│  ARAYÜZ — Tauri 2 + React/TypeScript (WebView2)               │
│  Oynatıcı · Zaman çizelgesi · ROI · Sor paneli · Rapor        │
└───────────────────────────────────────────────────────────────┘
        │ REST + WebSocket                    ▲ proxy video
        │ (127.0.0.1 + oturum token'ı)        │ (HTTP Range)
        ▼                                     │
┌───────────────────────────────────────────────────────────────┐
│  ANALİZ MOTORU — Python 3.12 · FastAPI (engine.exe sidecar)   │
│                                                               │
│  Giriş  →  Dönüştürücü  →  Saat     →  Ön-analiz  →  AI Sorgu │
│  (hash,    (eklentili     eşleme      (hareket,     (planla,  │
│   probe)    strateji)     (OCR/elle)   tespit, iz,   doğrula) │
│                                        embedding)             │
│                                                               │
│  İyileştirme · Rapor · İşlem geçmişi · İş kuyruğu (SQLite)    │
└───────────────────────────────────────────────────────────────┘
     │                    │                         │ HTTPS (tek dış bağlantı)
  FFmpeg/FFprobe      ONNX Runtime              OpenRouter API
  NVDEC / NVENC       (DirectML → CPU)          (gelişmiş: yerel OpenAI-
                      RF-DETR · SigLIP 2         uyumlu sunucu)
     │                Real-ESRGAN · OCR
  data/ (exe'nin yanında): vakalar · orijinaller · proxy'ler · case.sqlite · ayarlar
```

**Motor bir "sunucu" değildir**
- Uygulama açılınca başlar, kapanınca kapanır.
- Yalnızca `127.0.0.1` (loopback) adresini dinler. Ağa ve internete açılmaz; Windows Güvenlik Duvarı uyarısı çıkmaz.
- Tauri başlangıçta tek kullanımlık bir **oturum token'ı** üretir. Böylece makinedeki başka programlar motoru çağıramaz.

**Neden iki ayrı süreç?**
- Ağır işler (dönüştürme, analiz) arayüzü dondurmaz.
- Motor çökerse arayüz açık kalır, iş kuyruğu kaldığı yerden devam eder.

**İş kuyruğu**
- İşler SQLite tablosunda tutulur.
- Ayrı süreçler halinde çalışan worker'lar: GPU worker'ı ve CPU worker'ları (FFmpeg).
- İşler iptal edilebilir ve yeniden başlatılabilir. İlerleme WebSocket ile anlık gösterilir.
- Dizüstü bilgisayar VRAM'i sınırlı olduğu için GPU işleri **sırayla** çalışır.

### 3.1 Taşınabilir uygulama klasörü

```
AIVideoAnalizi/                     # ZIP'ten çıkarılan klasör — USB'ye veya başka diske taşınabilir
  AIVideoAnalizi.exe                # Tauri arayüzü
  engine/                           # Python motoru (PyInstaller onedir çıktısı)
  ffmpeg/                           # ffmpeg.exe, ffprobe.exe
  models/                           # ONNX ağırlıkları (pakete dahil — internet gerekmez)
  THIRD_PARTY_NOTICES.txt           # açık kaynak lisans bildirimleri
  data/                             # TÜM kullanıcı verisi yalnızca burada
    settings.json                   # ayarlar (API anahtarı Windows DPAPI ile şifreli)
    webview/                        # WebView2 önbelleği (%LOCALAPPDATA% yerine)
    tmp/                            # geçici dosyalar (%TEMP% yerine)
    logs/                           # yalnızca yerel hata günlüğü, dönüşümlü
    cases/
      2026-1452_otopark/
        case.sqlite                 # meta veri, tespitler, bulgular, sorgu geçmişi
        evidence/<sha256>/
          original/…                # orijinal dosya(lar) — salt-okunur, asla değişmez
          evidence.mkv              # kayıpsız yeniden paketlenmiş kopya (mümkünse)
          proxy.mp4                 # çalışma kopyası (H.264, sabit fps, 1 sn GOP)
          thumbs/  sprites/         # zaman çizelgesi önizlemeleri
        exports/                    # kareler, klipler, raporlar (+ .json yan dosyaları)
```

**Taşınabilirlik kuralları**
- **Klasör dışına yazmaz:** Uygulama `data/` dışında hiçbir yere yazmaz. Tauri'nin WebView2 veri klasörü de `data/webview` olarak ayarlanır (`data_directory`).
- **Yazma izni:** Açılışta exe klasörüne yazma izni kontrol edilir. Örneğin `C:\Program Files` altında izin yoktur. Bu durumda uygulama kullanıcıya iki seçenek sunar:
  - klasörü yazılabilir bir yere taşımak (Masaüstü, `D:\`, USB), ya da
  - verileri `%LOCALAPPDATA%` altına yazmak.
- **Silme:** "Verileri sil" seçeneği tek bir vakayı veya tüm `data/` klasörünü siler. Klasörü elle silmek de yeterlidir; başka iz kalmaz.
- **Güncelleme:** Yeni sürüm yeni bir ZIP'tir. Eski `data/` klasörü yeni klasöre kopyalanır; şema migration'ları açılışta otomatik çalışır.

### 3.2 Depo (repo) yapısı

```
ai-video-analizi/
  app/                  # Tauri + React
    src/                # arayüz (bileşenler, sayfalar, API istemcisi)
    src-tauri/          # Rust kabuk: pencere, sidecar başlatma, data/ klasörü yönetimi
  engine/               # Python analiz motoru
    api/                # FastAPI uçları, WebSocket
    jobs/               # iş kuyruğu, worker'lar
    ingest/             # hash, probe, metadata
    convert/            # dönüştürücü çekirdeği + plugins/
    media/              # FFmpeg/PyAV sarmalayıcı, kare sunucusu
    timecorr/           # zaman eşleme, ekran saati (OSD) OCR'ı
    analyze/            # hareket, tespit, takip, embedding, OCR
    ai/                 # OpenRouter istemcisi, model kataloğu, maliyet, prompt'lar
    enhance/            # klasik filtreler, upscale
    report/             # PDF / JSON dışa aktarma
    history/            # işlem geçmişi
    storage/            # SQLite şeması, migration'lar, data/ yolları
  models/               # ONNX ağırlıkları (git dışında, indirme betiğiyle)
  tools/ffmpeg/         # paketlenen ffmpeg / ffprobe
  testdata/
    generate.py         # sentetik test videosu üreticisi (§4.1)
    corpus/             # üretilen ve indirilen örnekler (git dışında)
  docs/
```

### 3.3 Temel veri modeli

| Tablo | İçerik |
|---|---|
| `cases` | Vaka bilgileri |
| `evidence` | SHA-256, boyut, orijinal ad, probe JSON, kamera adı |
| `derivatives` | evidence.mkv, proxy, sprite dosyaları ve bunları üreten komut/parametreler |
| `time_mappings` | Sürümlü zaman eşleme (referans noktaları, saat dilimi, gerekçe) |
| `segments` | Aktif segmentler, kayıt boşlukları, birleştirilmiş kesitler |
| `detections` | `evidence_id`, `t_media`, `frame_no`, sınıf, bbox, güven, `track_id` |
| `tracks` | Takip izleri (giriş/çıkış zamanı, ROI olayları) |
| `embeddings` | sqlite-vec vektörleri (kare / kırpıntı) |
| `ocr_readings` | Ekran saati okumaları (zaman eşleme için) |
| `rois` | Alanlar / çizgiler (kamera başına) |
| `queries`, `ai_calls` | **Araştırma geçmişi:** soru, plan; model id, gönderilen kare hash'leri, yanıt, token, maliyet |
| `findings` | Bulgu, kullanıcı onayı / notu |
| `history` | İşlem geçmişi (ne zaman, hangi işlem, hangi parametreler). Kullanıcı kimliği tutulmaz. |

---

## 4. Modüller

### 4.1 Giriş ve dinamik dönüştürücü

**Hedef (v1):** Normal bir medya oynatıcının açtığı her şeyi açmak, **artı** onların açamadığı yaygın CCTV durumlarını çözmek.

| Grup | Kapsam |
|---|---|
| **VLC düzeyi** (FFmpeg) | Konteynerler: MP4/MOV/3GP, MKV/WebM, AVI, WMV/ASF, FLV, MPEG-PS/VOB, MPEG-TS/M2TS, MXF, OGG. Codec'ler: H.264, H.265, MPEG-2/4, MJPEG, VP8/9, AV1, WMV, Xvid/DivX… |
| **VLC'nin ötesi** | Uzantısı yanlış veya hiç olmayan dosyalar (içerikten tanıma). Ham H.264/H.265 akışları (`.264`, `.h264`, `.h265`) ve fps tahmini. Başında tescilli başlık veya çöp veri olan dosyalar (otomatik başlık atlama). Kesik / kısmen bozuk dosyalar (toleranslı çözme). Dahua `DHAV`, Hikvision MPEG-PS-in-MP4 (şifresiz). Aynı kameranın **ardışık kesitlerini** boşluklar korunarak tek zaman çizelgesinde birleştirme. |
| **İleride** (eklentiyle) | Üretici SDK'ları, şifreli dışa aktarımlar, `moov` atomu eksik MP4 onarımı, çok kanallı DVR dosyalarını kanallara ayırma |

**1) Delil kaydı**
- SHA-256 hesaplanır.
- Orijinal dosya `data/cases/.../original/` klasörüne salt-okunur olarak kopyalanır ve **asla değiştirilmez**.
- İşlem geçmişine kaydedilir.

**2) Tanıma (sniff)**
Uygulama uzantıya değil **içeriğe** bakar: önce baştaki imza baytları (magic bytes), sonra ffprobe, gerekirse sezgisel tarama.

| İmza | Muhtemel kaynak | İlk strateji |
|---|---|---|
| `DHAV` | Dahua / Amcrest / Lorex `.dav` | FFmpeg `dhav` demuxer (FFmpeg ≥ 4.2) |
| `IMKH` / `4HKH` başlık | Hikvision dışa aktarımları | Toleranslı remux |
| `00 00 01 BA` | MPEG-PS | Demuxer'ı zorla: `-f mpeg` |
| Her 188 baytta `0x47` | MPEG-TS | Standart |
| `00 00 00 01` + NAL tipleri | Ham H.264/H.265 | `-f h264` / `-f hevc`; fps SPS'ten okunur, yoksa ekran saatinden tahmin edilir, o da yoksa kullanıcıya sorulur |
| `ftyp` / `RIFF` / EBML / ASF GUID | MP4-MOV / AVI / MKV / WMV-ASF | Standart |
| Tanınmayan | — | Başlık atlama + NAL tarama → teşhis paketi |

**3) Strateji zinciri**
- Her strateji önce dosyanın ilk ~10 saniyesinde denenir.
- Başarı ölçütleri: çözme hatası eşiğin altında, süre ve kare sayısı tutarlı, zaman damgaları sıralı.

1. **Doğrudan remux** (`-c copy`). Sonuç `evidence.mkv` olur; kalite kaybı olmaz.
2. **Toleranslı mod.** `-err_detect ignore_err -fflags +genpts+discardcorrupt` bayrakları kullanılır, demuxer zorlanır, fps varsayılır.
3. **Başlık atlama / NAL carving.** Dosyada ilk geçerli MPEG-PS paketi veya H.264/H.265 NAL dizisi aranır, öncesindeki tescilli başlık atlanır ve akış çıkarılır.
4. **Teşhis paketi.** Paket şunları içerir: ilk 4 KB'ın hex dökümü, ffprobe çıktısı, denenen stratejiler ve hatalar.
   - *İsteğe bağlı AI desteği:* Bu teşhis **metni** bir metin modeline gönderilir ve yeni bir strateji önerisi istenir. Öneri kullanıcı onayıyla denenir. Başarılı olursa yerel bir kural olarak saklanır; dönüştürücü kullanıldıkça "öğrenir".
   - Kullanıcı isterse teşhis paketini (video değil) elle paylaşabilir. Paylaşılan paketler yeni format desteği eklemek için kaynak olur. Otomatik gönderim **yoktur**.

**Eklenti arayüzü:**
```python
class ConverterPlugin(Protocol):
    name: str
    def sniff(self, path: Path, head: bytes, probe: ProbeResult | None) -> float: ...  # 0–1 güven
    def convert(self, path: Path, out_dir: Path, opts: ConvertOptions) -> ConvertResult: ...
```
Yeni bir format eklemek için bir eklenti yazılır ve test setine örnek dosya eklenir.

**4) Çıktılar**
- **`evidence.mkv`:** Kayıpsız kopya; mümkün olan her durumda üretilir.
- **`proxy.mp4`:** Çalışma kopyası. Özellikleri:
  - H.264, yuv420p, sabit fps
  - **GOP = 1 sn**, B-frame yok, `+faststart`
  - En fazla 1080p

  Kodlama **NVENC** ile yapılır. NVIDIA olmayan makinelerde QSV/AMF, onlar da yoksa OpenH264 kullanılır.
- **Önizlemeler:** Zaman çizelgesi için sprite şeritleri ve küçük resimler.
- **Arşiv sıkıştırma (isteğe bağlı):** H.265 (NVENC). Orijinalin yerine **geçmez**.

```
ffmpeg -hwaccel cuda -i evidence.mkv -map 0:v:0 -map 0:a? \
  -vf "scale='min(1920,iw)':-2:flags=lanczos,format=yuv420p" -fps_mode cfr -r <fps> \
  -c:v h264_nvenc -preset p5 -cq 23 -g <fps> -bf 0 \
  -c:a aac -b:a 96k -movflags +faststart proxy.mp4
```

**5) Doğrulama**
- Tam çözme testi yapılır: `ffmpeg -v error -i proxy.mp4 -f null -`.
- Süre ve kare sayısı orijinalle karşılaştırılır.
- PTS sıçramaları **kayıt boşluğu** olarak işaretlenir.

**6) Test seti (gerçek kayıt olmadan)**
- **Sentetik üretici (`testdata/generate.py`):** FFmpeg ile yaklaşık 50 varyasyon üretir:
  - **Codec × konteyner:** Tüm kombinasyonlar.
  - **Tipik CCTV özellikleri:** CIF/D1/720p/1080p çözünürlük, 5–15 fps, interlaced görüntü.
  - **Yanlış veya eksik uzantı.**
  - **Taklit tescilli başlık:** Başına rastgele başlık baytları eklenmiş dosyalar.
  - **Ham `.264` / `.h265` akışları.**
  - **Kesik ve bozuk dosyalar.**
  - **Değişken fps (VFR).**
  - **Saat ve boşluk testleri:** Görüntüye *bilerek yanlış* bir saat yazılır (`drawtext`). Kayıtta boşluk olan ardışık kesitler de üretilir. Böylece saat düzeltme ve OCR uçtan uca test edilir.
- **Açık örnek arşivleri:** `samples.ffmpeg.org` gibi kaynaklardan egzotik formatlar.
- **AI değerlendirme videoları:** Ekip üyelerinin rızasıyla senaryolu kısa test videoları çekilir (otopark, koridor, kapı girişi), yanında doğru cevabı bilinen 30–50 soru hazırlanır. Lisansı uygun açık gözetim veri setleri de kullanılabilir.

### 4.2 Oynatıcı ve zaman çizelgesi
- **Oynatma:** HTML5 video (proxy) üzerinde bir canvas katmanı çalışır: tespit kutuları, ROI ve maskeler. `requestVideoFrameCallback` ile kare senkronu sağlanır.
- **Kontroller:**
  - Yakınlaştırma/kaydırma ve büyüteç
  - Kare kare ileri/geri
  - J/K/L hız kontrolü
  - Yer imleri
- **Çok şeritli zaman çizelgesi:**
  - Aktivite ısı haritası
  - Sınıf şeritleri (kişi, araç)
  - AI bulgu işaretleri ve yer imleri
  - Kayıt boşlukları (taralı)
  - Kesit sınırları
- **Çift saat:** Düzeltilmiş saat büyük, kamera saati küçük ve gri gösterilir.
- **Kare-doğru dışa aktarma:** Proxy'den değil, `evidence.mkv` dosyasından motor tarafında yapılır.

### 4.3 Saat düzeltme

Uygulama üç zaman eksenini birbirinden ayırır:

| Eksen | Tanım | Kaynak |
|---|---|---|
| **Medya zamanı** `t_m` | Video içindeki konum (sn, PTS) | Dosyanın kendisi; değişmez |
| **Kamera zamanı** `t_k` | Kameranın o an "sandığı" saat | Ekran saati (OSD) OCR'ı, dosya adı, metadata veya elle |
| **Gerçek zaman** `t_g` | Gerçek yerel saat | `t_k` + düzeltme |

**`t_m → t_k` eşlemesi: medya zamanından kamera saatine**
- **Ekran saati OCR'ı:**
  - Görüntüdeki tarih/saat bölgesi otomatik bulunur; bulunamazsa kullanıcı işaretler.
  - Bu bölge her N saniyede bir okunur ve parça parça doğrusal bir eşleme kurulur.
  - Saatteki sıçramalar **kayıt boşluğu** demektir. Bu durum hareket tetiklemeli ve kesitli kayıtlarda çok sık görülür.
- **Yedek kaynaklar:** Dosya adı kalıpları (ör. `CH01_20261028143000`), metadata `creation_time` veya elle girilen başlangıç saati.
- **Ardışık kesitler:** Her kesitin kendi eşlemesi olur. Birleştirilmiş zaman çizelgesi bu eşlemelerden kurulur.

**`t_k → t_g` düzeltmesi: kamera saatinden gerçek saate**
- **Tek referans:** Sabit fark. Örnek: kamera 3 dk 42 sn ileride.
- **İki referans:** Fark + kayma (drift). Örnek: saat günde 2 sn geri kalıyor.
- **Çok referans:** Parça parça düzeltme. Örnek: elektrik kesintisinden sonra saat sıfırlanmış.
- **Saat dilimi ve yaz saati** seçilebilir.
- **Önerilen referans kaynakları:**
  - DVR ekranı ile güvenilir bir saat yan yana fotoğraflanır.
  - Saati doğru başka bir kameradaki aynı olay kullanılır.
  - Zamanı bilinen bir olay kullanılır.

**Kurallar**
- Tüm tespit ve bulgular `t_m` ve kare numarası ile saklanır. `t_g` her gösterimde hesaplanır. Düzeltme değişince **yeniden analiz gerekmez**.
- Sorgulardaki saat aralıkları ters eşlemeyle `t_m`'ye çevrilir.
- AI'a giden her kare **düzeltilmiş saatle** etiketlenir. Prompt'a *"görüntüdeki saat yazısını dikkate alma, verilen saati kullan"* talimatı eklenir.
- Düzeltmeler sürümlüdür ve gerekçesiyle saklanır. Rapor hem kamera saatini hem gerçek saati gösterir.

```python
@dataclass
class TimeMapping:
    media_to_camera: list[tuple[float, datetime]]     # OCR / elle, parça parça doğrusal
    camera_to_real: list[tuple[datetime, datetime]]   # düzeltme referansları
    tz: ZoneInfo

    def to_real(self, t_media: float) -> datetime: ...
    def to_media(self, t_real: datetime) -> list[float]: ...  # saat sıfırlanması/yaz saati yüzünden birden fazla olabilir
```

### 4.4 Hızlı ön-analiz (yerelde, dizüstü GPU'da)

1. **Hızlı tarama:** NVDEC ile yalnızca anahtar kareler çözülür (PyAV `skip_frame="NONKEY"`). Örnek: 2 sn GOP'lu 24 saatlik bir kayıtta ~**43.200** kare çözülür; tam çözmede bu sayı 25 fps ile ~**2,16 milyon** olurdu.
2. **Hareket / aktivite:** OpenCV MOG2 ile bir aktivite skoru hesaplanır ve aktif segmentler bulunur. Durağan saatler sonraki adımlarda atlanır.
3. **Nesne tespiti:** Aktif segmentler 2–5 fps ile örneklenir ve **RF-DETR S/M** (ONNX, DirectML) çalıştırılır. Tespit edilen sınıflar: kişi, araç, motosiklet, bisiklet, çanta…
4. **Takip:** ByteTrack (`supervision`) şunları çıkarır:
   - İzin giriş ve çıkış zamanı
   - ROI'ye giriş/çıkış olayları
   - Çizgi geçme olayları
5. **Görsel arama indeksi:** Kare ve kırpıntılar için **SigLIP 2 (base)** embedding'leri üretilip sqlite-vec'e yazılır.
6. **OCR:** RapidOCR ile ekran saati okunur (§4.3). Plaka okuma v2'de, isteğe bağlı.
7. **Hızlı Özet:** Aktivite haritası, sayımlar, olay listesi, kayıt boşlukları. İsteğe bağlı olarak olay listesi (yalnızca metin) bir LLM'e kısa özet olarak yazdırılır.

**Dizüstü bilgisayar önlemleri**
- **İlk açılışta donanım testi:** GPU ve VRAM tespit edilir, kısa bir hız ölçümü yapılır.
- **VRAM'e göre ayar:** Model varyantı ve batch boyutu VRAM'e göre seçilir (4 GB → küçük varyantlar; 8 GB → orta).
- **Sıralı çalışma:** GPU modelleri aynı anda değil sırayla yüklenir.
- **Pil:** Bilgisayar pildeyse ağır analizlerden önce uyarı verilir. İsteğe bağlı olarak "pilde düşük hız" modu kullanılır.
- **Hedefler:** Performans hedefleri Faz 0'da ekibin dizüstü bilgisayarında ölçülüp sabitlenecek.

### 4.5 AI sorgu ("Sor") — OpenRouter

```
Türkçe soru (+ seçili alan / zaman aralığı)
   │
   ▼ 1) Sorgu planlayıcı — ucuz metin modeli, JSON şema çıktısı
   │     { time_range, rois, classes, visual_queries_en, event, verify_question }
   ▼ 2) Aday bulma — YEREL: SQL filtre (zaman/sınıf/ROI) + vektör benzerliği
   │     50–200 aday kare/kırpıntı, iz bazında tekilleştirilmiş
   ▼ 3) Doğrulama — seçilen görsel model, 8–16 karelik paketler
   │     { candidate_id, match, confidence, bbox, explanation }
   ▼ 4) (İsteğe bağlı) Derin video analizi — video destekli model, kısa kesitler
   │     "kavga", "düşme", "bir şey bırakma" gibi hareket gerektiren sorular
   ▼ 5) Sonuç kartları → tıkla-git · Doğrula/Reddet · "Bu kişiyi takip et" · Rapora ekle
```

**Planlayıcı çıktısı örneği**
Soru: *"14:00–15:00 arası giriş kapısına kırmızı montlu biri girdi mi?"*
```json
{
  "time_range": { "start": "2026-10-28T14:00:00+03:00", "end": "2026-10-28T15:00:00+03:00" },
  "rois": ["giris_kapisi"],
  "classes": ["person"],
  "event": "roi_entry",
  "visual_queries_en": ["a person wearing a red jacket"],
  "verify_question": "Bu karede kırmızı mont/ceket giymiş bir kişi var mı? Varsa konumunu ver."
}
```

**Tam tarama modu:** Yerel modelin kaçırabileceği alışılmadık nesneler için kullanılır. Her N saniyede bir kare ucuz bir modele gönderilir. Çalıştırmadan **önce** tahmini maliyet gösterilir ve onay istenir.

**Neden önce yerel ön-analiz?** Yaklaşık değerler aşağıda; Faz 0'da ölçülecek.

| Yöntem | 1 saatlik kayıt için girdi | Not |
|---|---|---|
| Videonun tamamını video modeline göndermek | ~1 milyon token mertebesi (Gemini video dokümanlarındaki ~300 token/sn varsayılan oranına göre) | Her soruda tekrarlanır. Uzun kayıtlar tek isteğe sığmaz. |
| Ön-analiz + ~100 aday kare doğrulama | ~30–110 bin token | Yaklaşık 10–30 kat daha az; yanıt saniyeler içinde gelir |

#### API anahtarı ve model seçimi
- **Kendi anahtarını getir (BYOK):** Her kullanıcı kendi OpenRouter anahtarını girer; ücreti varsa kendi hesabından ödenir. Uygulamanın kendisi ücretsizdir ve ortada bir aracı sunucu yoktur.
- **Anahtarın saklanması:** Anahtar `data/settings.json` içinde **Windows DPAPI** ile şifreli tutulur. Yalnızca aynı Windows kullanıcısı çözebilir. Klasör başka bir bilgisayara kopyalanırsa anahtarın yeniden girilmesi gerekir; bu, USB kaybolursa anahtarı korur.
- **Canlı katalog:** `GET https://openrouter.ai/api/v1/models` uç noktası anahtar istemez; sonuç `data/` altında günlük önbelleğe alınır.
  - **Filtreler:** `architecture.input_modalities` içinde `image` / `video` olanlar; `supported_parameters` içinde `structured_outputs` / `response_format` olanlar.
  - **Fiyat:** `pricing` alanlarından tahmini maliyet hesaplanır.
- **Bugünkü durum (2 Kasım 2026):**
  - Toplam 452 model; **305**'i görsel, **90**'ı video girdisi kabul ediyor.
  - **Ücretsiz modeller:** 8'i ücretsiz görsel model, bunların 4'ü video da kabul ediyor.
- **Rol bazlı seçim:** Kullanıcı her rol için ayrı model seçer:
  - **Planlayıcı:** metin
  - **Kare doğrulayıcı:** görsel
  - **Video analisti:** video
  - **Rapor yazarı:** metin

  Hazır profiller sunulur: **Ücretsiz** / Ekonomik / Dengeli / En yüksek doğruluk.
- **Başlangıç adayları:** Bugünkü listeden test için seçildi; bu bir kalite iddiası değildir.

  | Model | Girdi | Fiyat ($ / 1M token, girdi / çıktı) |
  |---|---|---|
  | `nvidia/nemotron-3.5-super-vl:free` | metin, görsel, video (JSON şema destekli) | 0 / 0 |
  | `google/gemma-4-31b-it:free` | metin, görsel, video | 0 / 0 |
  | `qwen/qwen3.8-flash` | metin, görsel, video | 0,15 / 0,47 |
  | `google/gemini-3.5-flash-lite` | metin, görsel, video, ses | 0,30 / 2,50 |
  | `google/gemini-3.8-flash` | metin, görsel, video, ses | 0,825 / 4,125 |
  | `google/gemini-4-argon` | metin, görsel, video, ses | 2,00 / 10,00 |

  Ücretsiz modellerin hız sınırları (rate limit) vardır ve veri politikaları sağlayıcıya göre değişir. `data_collection: "deny"` açıkken bazı ücretsiz uç noktalar devre dışı kalabilir; Faz 0'da test edilecek. Uygulama böyle bir durumu kullanıcıya açıkça söyler.
- **Değerlendirme aracı (kalıcı özellik):** Test videoları ve etiketli sorularla her modelin isabet, kaçırma, maliyet ve süre tablosu çıkarılır. Sonuçlar yerelde saklanır. Model kataloğu her ay değiştiği için bu araç ürünün parçasıdır.
- **Veri gönderim varsayılanları:**
  - Bulut analizi açıktır.
  - Doğrulama için ROI kırpıntısı + küçük bağlam karesi gönderilir. Derin analiz için kısa video kesitleri gönderilir.
  - `provider.data_collection: "deny"` varsayılan olarak açıktır; görüntüler model eğitiminde kullanılmaz.
  - `zdr: true` isteğe bağlı bir anahtardır.
- **Maliyet takibi:** Yanıttaki `usage` alanından maliyet izlenir ve isteğe bağlı vaka bütçe limiti uygulanır.
- **Tekrarlanabilirlik:** Her AI çağrısı **yerelde** kaydedilir: model id, prompt, kare hash'leri, yanıt, token ve maliyet. Bu kayıtlar araştırma geçmişini oluşturur.
- **Gelişmiş: yerel model sunucusu:** `base_url` Ollama, LM Studio veya vLLM'e çevrilebilir (açık ağırlıklı Gemma / Qwen modelleri). Varsayılan değildir.

```python
client = OpenAI(base_url=settings.ai.base_url,              # varsayılan: "https://openrouter.ai/api/v1"
                api_key=secrets.load("openrouter"))         # data/settings.json, DPAPI ile şifreli

resp = client.chat.completions.create(
    model=settings.roles.verifier,                          # ör. "qwen/qwen3.8-flash"
    messages=[
        {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": f"Aday {c.id} — {c.real_time:%Y-%m-%d %H:%M:%S} (düzeltilmiş saat). Soru: {plan.verify_question}"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{c.jpeg_b64}"}},
            # … paketteki diğer adaylar
        ]},
    ],
    response_format={"type": "json_schema",
                     "json_schema": {"name": "verify", "strict": True, "schema": VERIFY_SCHEMA}},
    extra_body={"provider": {"data_collection": "deny", "zdr": settings.ai.zdr}},
)
```

**Video kesiti gönderme:**
- İçerik parçası: `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}`
- Desteklenen formatlar: mp4, mpeg, mov, webm.
- Gemini modelleri için ek `processing` seçeneği vardır:
  - `agentic`: Model, uzun videoda ilgili anlara kendisi gider.
  - `static`: Sabit fps ile örnekleme yapılır; kısa kesitlerde daha hızlıdır.

### 4.6 Alan (ROI) araçları
- **Çizim türleri:** Çokgen alan, yönlü çizgi ve dikdörtgen. Alanlar kamera başına kaydedilir ve adlandırılır (ör. "Giriş kapısı").
- **Kurallar:**
  - Alana giriş / çıkış
  - Alanda bekleme (N sn'den uzun)
  - Çizgi geçme (yönlü)
  - Bırakılan / kaldırılan nesne (v2)
- **Soruda "bu alanda" ifadesi:** Planlayıcıya ROI kimliği gider. AI'a yalnızca ROI kırpıntısı ve küçük bir bağlam karesi gönderilir. Bu yaklaşım maliyeti düşürür, isabeti artırır.

### 4.7 İyileştirme ve büyütme (upscale)

| Tür | Yöntemler | Durum |
|---|---|---|
| **Klasik** (deterministik, tekrarlanabilir) | Deinterlace (`bwdif`), gürültü azaltma (`hqdn3d`, `nlmeans`), keskinleştirme (`unsharp`), parlaklık/kontrast/gama/seviyeler, sabitleme (`vidstab`), kırpma + Lanczos/bikübik yeniden boyutlandırma. **Çok kareli birleştirme:** Durağan nesnede (ör. park etmiş aracın plakası) kareler hizalanıp ortalanır; gürültü gerçek bilgiyle azalır. | Raporlanabilir; işlem zinciri ve parametreler kaydedilir |
| **AI büyütme** | **Real-ESRGAN** (ONNX, x2/x4, VRAM'e göre döşemeli işleme). Kare, kırpıntı ve kısa klipler için kullanılır. | Görünür filigran taşır: *"AI ile iyileştirilmiştir — ipucudur, delil değildir"*. Yan dosyada işlem zinciri bulunur. |

- **Yüz "restorasyon" modelleri dahil edilmez** (GFPGAN, CodeFormer vb.). Bu modeller gerçekte olmayan yüz detayı üretir. Örnekler:
  - Washington'daki *State v. Puloka* (2024) davasında AI ile iyileştirilmiş video delil olarak kabul edilmedi.
  - SWGDE, makine öğrenmesi tabanlı iyileştirmede uygulanan işlemlerin tespit edilip tekrarlanmasının zor olduğu konusunda uyarıyor.
- Her zaman **yan yana görünüm** (orijinal ↔ iyileştirilmiş) sunulur. Dışa aktarmada orijinal kare de pakete eklenir.

### 4.8 Bütünlük, geçmiş ve rapor
- **Hash:** SHA-256 alım anında hesaplanır, rapor anında yeniden doğrulanır.
- **İşlem geçmişi:** Hangi dönüştürme, düzeltme, iyileştirme ve AI çağrısı ne zaman ve hangi parametrelerle yapıldı, kaydedilir. Kullanıcı kimliği tutulmaz. Hepsi yalnızca vaka veritabanında, yerelde durur.
- **Kullanıcı onayı:** AI çıktısı yalnızca **adaydır**. Kullanıcı "Doğrulandı" demeden rapora girmez.
- **PDF rapor içeriği:**
  - Vaka bilgisi
  - Dosya listesi ve hash'ler
  - Saat düzeltmenin gerekçesi
  - Bulgular: kare, kamera saati ve düzeltilmiş saat, güven skoru, not
  - Kullanılan modeller ve iyileştirme zinciri
- **Klip dışa aktarma:** Paket üç parçadan oluşur:
  - Üzerine düzeltilmiş saat yazılmış çalışma kopyası
  - Yeniden kodlanmamış orijinal kesit
  - JSON yan dosyası
- **Konumlandırma:** Bu uygulama hızlı inceleme ve ön eleme aracıdır. Mahkemeye sunulacak iyileştirmeler için sertifikalı adli video iş akışları referans alınmalı.

### 4.9 Gizlilik ve güvenlik
- **Hiçbir şey dışarı gitmez; istisnalar kullanıcının başlattığı AI çağrıları ve güncelleme denetimidir:** Hesap, telemetri, kullanım istatistiği ve hata raporu gönderimi yoktur. Güncelleme, kullanıcı "Güncellemeleri denetle" dediğinde GitHub'dan yalnızca sürüm bilgisi sorularak denetlenir. Açılışta otomatik denetim seçimlidir ve varsayılan olarak kapalıdır (v0.1.2).
- **İlk açılış bilgilendirmesi:** Tek ekranlık bir bildirim gösterilir: *"Soru sorduğunuzda seçilen kareler veya kesitler, seçtiğiniz AI sağlayıcısına gönderilir. Başka hiçbir veri bilgisayarınızdan çıkmaz. Kayıtları kullanmaya ilişkin yasal sorumluluk kullanıcıya aittir."* Kullanıcı bunu bir kez onaylar.
- **Motor erişimi:** Yalnızca `127.0.0.1`, rastgele port ve oturum token'ı.
- **API anahtarı:** DPAPI ile şifreli. Arayüzde maskeli gösterilir, günlüklere yazılmaz.
- **USB ile taşıma:** USB'de kullanılacaksa BitLocker To Go önerilir (uygulama içinde ipucu olarak gösterilir).
- **Açık kaynak önerisi:** Kaynak kodu açık yayınlanırsa (ör. Apache-2.0) "veri dışarı gitmiyor" iddiası herkes tarafından doğrulanabilir. Bu, polis ve kurum kullanıcılarının güvenini ciddi biçimde artırır. Kod imzalama da ücretsiz hale gelir (bkz. Faz 5). *Karar sizde.*

---

## 5. Arayüz tasarımı

**İlkeler**
- **Tema:** Varsayılan koyu tema, yüksek kontrast.
- **Dil:** Türkçe arayüz; i18n altyapısı hazır.
- **Saat gösterimi:** Düzeltilmiş saat her yerde birincil, kamera saati ikincil.
- **Durum çipleri:** Her dosyanın durumu görünür: *Dönüştürülüyor %*, *Analiz edildi*, *Saat düzeltilmedi ⚠*.
- **Sonuç kartları:** Her AI sonucunda küçük resim, saat, güven skoru ve tek tıkla videoya gitme bulunur.
- **Maliyet görünürlüğü:** Her AI işleminden önce tahmini maliyet gösterilir; ücretsiz modelde "Ücretsiz" yazar.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ AI Video Analizi   Vaka: 2026/1452 Otopark      Profil: Dengeli ▾   ⚙                    │
├────────────────┬──────────────────────────────────────────────────┬──────────────────────┤
│ DELİLLER       │                                                  │ Sor|Bulgu|İyileş|Saat│
│ ● CAM01 Hazır  │                                                  │ ──────────────────── │
│ ◐ CAM02 %64    │             VİDEO OYNATICI                       │ Alan: Giriş kapısı   │
│ ▲ CAM03 Saat?  │  (tespit kutuları · ROI çizimi · büyüteç)        │ Aralık: 14:00–15:00  │
│                │                                                  │                      │
│ + Video ekle   │  14:35:52 düzeltilmiş  (kamera 14:32:10)         │ > Kırmızı montlu     │
│                │  |◀  ◀  ▶  ▶|  1x   [Kare] [Klip] [Yer imi]      │   biri girdi mi?     │
│                ├──────────────────────────────────────────────────┤ ──────────────────── │
│ ALANLAR        │ Aktivite  ▁▂▇█▅▁▁▁▃▇▂▁▁▁▅▆▂                      │ [▣] 14:41:07  %92    │
│ ▭ Giriş kapısı │ Kişi      ▮ ▮▮   ▮       ▮▮                      │ [▣] 14:52:30  %71    │
│ ╱ Bariyer      │ Araç        ▮▮▮        ▮                         │ [▣] 14:58:02  %40    │
│                │ AI bulgu       ◆           ◆                     │ Doğrula · Reddet     │
│                │ Boşluk               ░░░░                        │ Maliyet: ~$0,04      │
└────────────────┴──────────────────────────────────────────────────┴──────────────────────┘
```

**Ekranlar**
1. **İlk açılış sihirbazı (3 adım):**
   1. Bilgilendirme ve onay
   2. OpenRouter anahtarı (veya "şimdilik atla" — yerel analiz anahtarsız da çalışır)
   3. Donanım testi
2. **Vakalar:** Liste, arama, yeni vaka, vaka silme.
3. **Vaka çalışma alanı:** Yukarıdaki düzen.
   - **Sağ panel sekmeleri:** Sor, Bulgular, İyileştir, Saat, Bilgi.
   - **Bilgi sekmesi:** Metadata, hash'ler, dönüştürme günlüğü.
4. **Yükleme / dönüştürme:** Sürükle-bırak; dosya ve klasör desteklenir. Her dosya için ilerleme ve kullanılan strateji gösterilir. Aynı kameranın ardışık kesitleri için "birleştir" önerisi sunulur. Hata olursa teşhis paketi kaydedilebilir.
5. **Saat düzeltme sihirbazı:**
   1. Ekran saati bölgesi seçilir.
   2. Referans noktaları girilir.
   3. Fark ve kayma grafiği önizlenir.
   4. Gerekçe yazılıp kaydedilir.
6. **Araştırma geçmişi:** Vaka içindeki sorular, sonuçları, kullanılan modeller ve maliyetler.
7. **Rapor oluşturucu:** Onaylı bulgular seçilir, önizleme yapılır, PDF/JSON dışa aktarılır.
8. **Ayarlar:**
   - API anahtarı
   - Rol bazlı model seçimi (canlı katalog, fiyat, yetenek filtresi, ücretsiz filtresi)
   - Veri gönderim tercihleri
   - GPU / performans
   - Veri klasörü ve "Verileri sil"
   - Model değerlendirme aracı

**Klavye kısayolları**

| Kısayol | İşlev |
|---|---|
| `Space` | Oynat / durdur |
| `←` / `→` | 1 kare geri / ileri |
| `Shift` + `←` / `→` | 1 sn geri / ileri |
| `J` / `K` / `L` | Hız kontrolü |
| `B` | Yer imi |
| `E` | Kare dışa aktar |
| `R` | ROI çiz |
| `Ctrl+K` | Soru kutusu |

---

## 6. Lisans kontrol listesi

Ücretsiz dağıtımda da açık kaynak bileşenlerin lisans koşulları geçerlidir. Bu koşulların karşılanması için uygulamayla birlikte `THIRD_PARTY_NOTICES.txt` dağıtılır.

| Bileşen | Lisans | Not |
|---|---|---|
| FFmpeg | LGPL 2.1 (LGPL derlemesi) | Ayrı exe olarak çağrılır. Kodlama NVENC/QSV/AMF + OpenH264 ile yapılır; GPL bileşeni (libx264) gerekmez. Bildirim dosyasında kaynak bağlantısı verilir. |
| RF-DETR N/S/M/L | Apache 2.0 | XL/2XL varyantları **PML 1.0** lisanslıdır; kullanılmayacak. |
| Ultralytics YOLO | **AGPL-3.0** | Ücretsiz olsa da tüm uygulamanın kaynağını AGPL ile açmayı zorunlu kılar → **kullanılmayacak**. RF-DETR yeterli. |
| Real-ESRGAN | BSD-3-Clause | ✓ |
| SigLIP 2 | Apache 2.0 | ✓ |
| RapidOCR / PaddleOCR | Apache 2.0 | ✓ |
| supervision (ByteTrack) | MIT | ✓ |
| ONNX Runtime (DirectML) | MIT | ✓ |
| sqlite-vec | MIT / Apache 2.0 | ✓ |
| Tauri, React, shadcn/ui | MIT / Apache 2.0 | ✓ |
| CodeFormer | Ticari olmayan (S-Lab) | Kullanılmayacak (ayrıca bkz. §4.7) |

---

## 7. Yol haritası

| Faz | Süre (tahmini) | İçerik | Bitti sayılır… |
|---|---|---|---|
| **0 · Keşif & PoC** | 1–2 hafta | Repo iskeleti ve `CLAUDE.md`. Sentetik test videosu üreticisi + açık örnekler. Dönüştürücü denemesi. Senaryolu test videolarının çekilmesi ve 30 soruluk set. 4–6 modelin (ücretsizler dahil) karşılaştırılması. Ücretsiz uç noktaların `data_collection: deny` ile davranışı. Dizüstü bilgisayarda performans ölçümü. | Sentetik setin ≥ %90'ı açılıyor. Model karşılaştırma tablosu ve performans hedefleri çıktı. |
| **1 · Temel** | 3–4 hafta | Tauri + React kabuk ve Python motor sidecar. Taşınabilir `data/` yapısı. Vaka yönetimi, hash, işlem geçmişi. Dönüştürücü v1 (strateji zinciri, DHAV/Hikvision, ardışık kesit birleştirme). NVENC ile proxy. Oynatıcı ve temel zaman çizelgesi. | ZIP'ten çalışan uygulamada dosya sürüklenince izlenebilir proxy oluşuyor. |
| **2 · Saat & Hızlı analiz** | 3 hafta | Zaman eşleme (sabit / kayma / parçalı), ekran saati OCR'ı. Hareket, tespit + takip, embedding indeksi. Hızlı Özet. Donanım testi ve VRAM ayarları. | Sentetik "yanlış saatli" videoda düzeltme uçtan uca doğru çalışıyor. Hızlı özet hedef sürede çıkıyor. |
| **3 · AI Sor** | 3 hafta | OpenRouter istemcisi, BYOK, DPAPI. Canlı katalog, rol ve profil seçimi (Ücretsiz dahil). Maliyet tahmini. Planlayıcı, doğrulayıcı, video derin analiz. ROI araçları, sonuç paneli, araştırma geçmişi. | Test setinde hedef isabete ulaşılıyor. Her sorunun maliyeti görünüyor. |
| **4 · İyileştirme & Rapor** | 2–3 hafta | Klasik filtreler, Real-ESRGAN. Kare/klip dışa aktarma, PDF rapor. | Bir vaka uçtan uca raporlanabiliyor. |
| **5 · Yayın** | 1–2 hafta | Taşınabilir ZIP (modeller dahil). `THIRD_PARTY_NOTICES`. Kod imzalama: açık kaynaksa SignPath Foundation (ücretsiz), değilse Microsoft Trusted Signing (düşük aylık ücret). GitHub Releases. Gerçek kullanıcılarla test. | İmzalı ZIP yayınlandı. Temiz bir Windows 10/11 makinede çıkar-çalıştır testi geçti. |

**MVP = Faz 0–3 (~10–12 hafta)** · **v1 = Faz 0–5 (~13–17 hafta)**
**v2 adayları:**
- Çok kameralı ortak zaman çizelgesi
- Plaka okuma
- Bırakılan nesne tespiti
- Şifreli/üretici formatları için eklentiler
- `moov` eksik MP4 onarımı
- İsteğe bağlı CUDA hızlandırma paketi
- İngilizce arayüz

---

## 8. Riskler ve önlemler

| Risk | Etki | Önlem |
|---|---|---|
| Gerçek DVR örneği olmadan geliştirme | Sahada bazı dosyalar açılmayabilir | Sentetik + açık örnek seti, eklenti mimarisi, kullanıcının elle paylaşabileceği teşhis paketi |
| AI'ın uydurması veya kaçırması | Yanlış ya da eksik bulgu | İki aşama: yerel tespit + model doğrulama. Güven skoru, zorunlu kullanıcı onayı, değerlendirme seti. |
| Ücretsiz modellerin hız sınırı veya veri politikası | Yavaşlık, devre dışı uç noktalar | Açık uyarı, otomatik yeniden deneme ve bekleme, ücretli profile tek tıkla geçiş |
| Maliyet artışı (ücretli modeller) | Kullanıcının bütçesi aşılır | Ön-filtre, işlemden önce maliyet onayı, vaka bütçe limiti |
| Dizüstü bilgisayar: VRAM, ısınma, pil | Yavaş analiz, çökme | Donanım testi, VRAM'e göre model varyantı, sıralı GPU işleri, pil uyarısı |
| Exe yazma izni olmayan klasörde (Program Files) | Veri kaydedilemez | Açılışta kontrol, taşıma önerisi veya `%LOCALAPPDATA%` seçeneği |
| WebView2 eksik veya eski (eski Windows 10, kilitli kurum makinesi) | Arayüz açılmaz | Açılışta kontrol ve yönlendirme. İsteğe bağlı olarak sabit WebView2 içeren "tam paket" ZIP. |
| İmzasız exe | SmartScreen uyarısı, güven kaybı | Kod imzalama (Faz 5) |
| AI ile iyileştirilmiş görüntünün gerçek sanılması | Yanlış yönlendirme | Filigran, ayrı etiket, raporda açık ayrım, yüz restorasyonu yok |
| Model kataloğunun değişmesi | Model kalkar veya fiyatı değişir | Dinamik katalog, rol başına yedek model, kayıtlı değerlendirme sonuçları |

---

## 9. Açık sorular

Aşağıdaki iki konu henüz yanıtlanmadı. Yanıt gelene kadar varsayılanlarla ilerlenir.

1. **Arayüz dili:** Yalnızca Türkçe mi? → *Varsayılan: Türkçe; i18n hazır.*
2. **Plaka okuma / yüz arama:** İhtiyaç var mı? → *Varsayılan: plaka okuma v2; yüz arama ve tanıma yok.*
3. **Açık kaynak:** Kaynak kodu açık yayınlanacak mı? → *Öneri: evet (§4.9). Kod imzalama ve güven açısından avantajlı.*

## 10. İlk adımlar (Faz 0)

1. Repo iskeletini kurmak: `app/` (Tauri + React), `engine/` (Python), `testdata/`, doldurulmuş `CLAUDE.md`.
2. Geliştirme ortamını hazırlamak: Node.js LTS, Rust (rustup), Python 3.12, FFmpeg (LGPL derlemesi).
3. Sentetik test videosu üreticisini (`testdata/generate.py`) ve dönüştürücü PoC'sini yazmak.
4. Ekipte kısa senaryolu test videoları çekmek ve doğru cevabı bilinen 30 soru hazırlamak.
5. Model karşılaştırma betiğini yazmak (ücretsiz modeller dahil) ve dizüstü bilgisayarda performans ölçmek.

---

## Kaynaklar
- [OpenRouter — Video Inputs](https://openrouter.ai/docs/guides/overview/multimodal/videos)
- [OpenRouter — Multimodal Overview](https://openrouter.ai/docs/guides/overview/multimodal/overview)
- [OpenRouter — Models API (canlı liste)](https://openrouter.ai/api/v1/models)
- [OpenRouter — Zero Data Retention](https://openrouter.ai/blog/insights/zero-data-retention/)
- [ONNX Runtime — DirectML EP (sustained engineering notu)](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [Microsoft — Windows ML supported execution providers](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers?tabs=winml2)
- [Roboflow — RF-DETR (GitHub, lisans tablosu)](https://github.com/roboflow/rf-detr)
- [Roboflow — RF-DETR ticari kullanım (Apache 2.0)](https://blog.roboflow.com/rf-detr-is-free-to-use-commercially/)
- [IPCamTalk — DAV → MP4 dönüştürme (FFmpeg dhav)](https://ipcamtalk.com/threads/recommend-dav-to-mp4-converter-please.30193/page-2)
- [IPCamTalk — Hikvision MP4 → standart MP4](https://ipcamtalk.com/threads/converting-hikvision-mp4-to-standard-mp4-or-other-format.30315/post-425628)
- [Amped — DVRConv ve Engine güncellemesi (şifreli IMKH)](https://blog.ampedsoftware.com/2026/07/29/dvrconv-and-engine-update-41489)
- [ABA — Court excludes AI-enhanced videos (State v. Puloka)](https://www.americanbar.org/groups/litigation/resources/litigation-news/2024/fall/court-excludes-aienhanced-videos-trial-evidence/)
- [Criminal Legal News — When AI invents the pixels (SWGDE uyarıları)](https://www.criminallegalnews.org/news/2025/dec/15/when-ai-invents-the-pixels-challenging-ai-enhanced-video-evidence-in-criminal-cases/)
