# Sürüm geçmişi

## 0.1.1 — 2 Kasım 2026

Dönüştürmenin "Kayıpsız kopya oluşturuluyor" adımında takılı kalması ve iptal edilememesi düzeltildi.

- **Ayrı süreç:** Kayıpsız kopya ve çalışma kopyası artık ayrı bir süreçte hazırlanıyor. Bozuk ya da alışılmadık bir dosyada çözücü çökse veya takılsa bile uygulama çalışmaya devam ediyor.
- **Takılma bekçisi:** 3 dakika boyunca ilerleme gelmezse işlem durduruluyor ve bir kez hataya dayanıklı modla yeniden deneniyor. O da başarısız olursa anlaşılır bir hata ve teşhis paketi gösteriliyor.
- **İptal:**
  - Video satırına ve dönüştürme ekranına "İptal" düğmesi eklendi.
  - İptal, çalışan işlemi hemen durduruyor; sıradaki işler hiç başlamadan iptal ediliyor.
- **Yeniden dene:** Hata ya da yarıda kalma durumunda video satırında ve dönüştürme ekranında "Yeniden dene" düğmesi var.
- **Açılışta kurtarma:** Uygulama kapandığı ya da motor yeniden başladığı için yarıda kalan dönüştürmeler, kalıcı "Dönüştürülüyor" durumu yerine "yarıda kaldı" olarak işaretleniyor. Yarım analiz kalıntıları siliniyor.
- **İlerleme:** Tüm adımlar düzenli ilerleme bildiriyor ve yüzde olarak gösteriliyor. Ham akışlarda B-frame kontrolü önce yalnızca ilk ~600 paketle yapılıyor; dosyanın tamamı gereksiz yere çözülmüyor.

## 0.1.0 — 2 Kasım 2026

İlk sürüm.
