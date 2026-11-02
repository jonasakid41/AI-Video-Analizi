# AI Video Analizi

## Proje hakkında

- Amaç: Polislerin, güvenlik yöneticilerinin ve kamera kaydı inceleyen herkesin kullanabileceği ücretsiz, açık kaynaklı ve girişsiz bir Windows uygulaması. Kullanıcı kamera kayıtlarını yükler (VLC'nin açamadığı DVR biçimleri dahil) ve Türkçe soru sorarak ilgili anları bulur. Uygulama hatalı kamera saatini düzeltir, yüz ve plaka analizi yapar, kareleri iyileştirir ve PDF rapor üretir.
- Teknolojiler: Tauri 2 (Rust) + React 19 / TypeScript / Tailwind 4 arayüz; Python 3.13 analiz motoru (FastAPI, PyAV, ONNX Runtime DirectML, OpenCV, RapidOCR, ReportLab); AI tarafında OpenRouter (OpenAI uyumlu).
- Plan ve kararlar: `docs/PLAN.md`

## Çalıştırma

```powershell
cd app; npx tauri dev                                    # geliştirme (motor engine\.venv ile)
cd engine; .venv\Scripts\python -m pytest                # motor testleri
cd app; npx tsc --noEmit -p .; npx vitest run            # arayüz testleri
engine\.venv\Scripts\python scripts\build_release.py     # dist\AIVideoAnalizi (taşınabilir) + zip
```

## Notlar

- **Arayüz dili:** Arayüz tamamen Türkçedir. Kod tanımlayıcıları İngilizcedir; yorumlar ve kullanıcıya dönen mesajlar Türkçedir.
- **Tasarım ilkeleri:**
  - Sunucu, hesap ve telemetri yoktur.
  - Tüm veri `data/` klasöründedir (exe'nin yanında, geliştirmede depo kökünde).
  - Dışarıya giden tek bağlantı, kullanıcının başlattığı OpenRouter istekleridir.
  - API anahtarı Windows DPAPI ile şifrelenir (`aiva/vault.py`).
- **Zaman ekseni:** Tespit ve bulgular medya zamanı (`t`, sn) ile saklanır. Gerçek saat `TimeMapping` ile gösterim anında hesaplanır. Python tarafı `aiva/timecorr/mapping.py`, istemci kopyası `app/src/lib/time.ts`; ikisi aynı sonucu vermeli.
- **Video:** FFmpeg ayrı exe olarak değil, PyAV'ın içindeki kitaplıklarla kullanılır. Kare iş parçacıklı çözücüyü kapatmadan önce mutlaka boşaltmak gerekir; aksi halde kilitlenebilir. Bu yüzden çözme işlemleri `media/frames.py: decoding()` üzerinden yapılmalıdır.
- **Türkçe karakterli yollar:** `cv2.imread`/`imwrite` ve OpenCV model yükleme Türkçe karakterli Windows yollarında başarısız olur. Bunun yerine `util.imread/imwrite` kullanılmalı, modeller bayt olarak yüklenmeli.
- **Kare parametresi:** Medya isteklerinde token `?k=` ile gider; `t` her zaman zaman parametresidir.
- **Lisans:** Lisans GPL-3.0'dır. AGPL (Ultralytics) ya da ticari olmayan lisanslı modeller eklenmemeli. Yüz "restorasyonu" modelleri bilerek yoktur.
- **Python kodu yazarken:** Bash heredoc ile ters eğik çizgi içeren Python kodu yazılmamalı; kaçış karakterleri bozuluyor. Dosya araçları kullanılmalı.
