# Sürüm geçmişi

## 0.1.2 — 2 Kasım 2026

Uygulama içi güncelleme eklendi; soru sorulurken görülen siyah ekran giderildi.

- **Uygulama içi güncelleme:**
  - Ayarlar > Sistem > "Güncellemeleri denetle" ile yeni sürüm GitHub'dan indirilip kurulur. Yeni sürüm varsa üst çubukta rozet görünür.
  - İndirilen paketin SHA-256 değeri yayımlanan değerle karşılaştırılır; uyuşmazsa dosya silinir.
  - "Yeniden başlat ve kur" ile uygulama kapanır, program dosyaları değiştirilir ve yeni sürüm açılır. `data/` klasöründeki vakalar ve ayarlar korunur.
  - Bir dosya kullanımda olduğu için değişim başarısız olursa önceki sürüm otomatik geri yüklenir ve nedeni gösterilir.
  - Açılışta otomatik denetim isteğe bağlıdır ve varsayılan olarak kapalıdır.
- **Siyah ekran düzeltmesi:**
  - Yapay zekâdan şemaya uymayan bir plan ya da doğrulama cevabı geldiğinde (ör. eksik renk listesi, metin olarak "false", nesne olarak plaka) arayüz çöküp siyah ekran kalabiliyordu. Bu cevaplar artık motorda düzeltiliyor; daha önce kaydedilmiş sorular da açılırken düzeltiliyor.
  - Bir bölümde beklenmeyen bir çizim hatası olursa artık yalnızca o bölüm "Bu bölüm görüntülenemedi — Tekrar dene" gösteriyor; uygulamanın geri kalanı çalışmaya devam ediyor. Hata `data/logs/arayuz.log` dosyasına yazılıyor.
  - WebView2'nin çizim süreci çökerse (bellek ya da ekran kartı sürücüsü) sayfa kendiliğinden yeniden yükleniyor.
- **Küçük düzeltme:** Yerel soru çözümleyicide "kırmızı" kelimesi hareket kelimesi ("kır") sanılıyordu.
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

AI arama sürekli "soruya uyan sonuç bulunamadı" demiyor; hareketler türüne göre ayrılıyor.

- **Dinamik arama:**
  - Yerel analiz aday bulamazsa videolardan eşit aralıklı kareler alınıp modele doğrulatılıyor.
  - İlk turda eşleşme çıkmazsa arama genişletilip ikinci tur yapılıyor.
  - Nesne adaylarına her zaman görsel (CLIP) kare adayları da ekleniyor.
  - Soruda saat geçmiyorsa modelin uydurduğu saat aralığı yok sayılıyor.
- **Neden sonuç yok:** Sonuç çıkmadığında sebebi yazılıyor. Örneğin video henüz hazır değil, istenen saatte kayıt yok (kaydın kapsadığı saatler gösteriliyor) ya da yerel analiz o aralıkta aranan nesneyi bulamadı.
- **"Neler oldu?" soruları:** Doğrulamaya gitmeden olay listesinden cevaplanıyor. Kalabalık olaylar kişi/araç bazında ayrılıyor; her birinin saati, süresi, renkleri ve plakası yazılıyor.
- **Hareket türleri:**
  - Her hareket şu türlerden birine ayrılıyor: **nesne** (kişi/araç), **çevre** (ağaç, yaprak, gölge), **ışık** (ışık değişimi, far, bulut), **parazit** (görüntü gürültüsü) ve **belirsiz** (incelenmeli).
  - Ağaç gibi sürekli sallanan bölgeler, arka plan modelinin yuttuğu tekrarlı hareket de kare farkıyla yakalanarak ayırt ediliyor.
- **Zaman çizelgesi:**
  - Yeni olay şeridinde her olay etiketiyle gösteriliyor; örneğin "2 kişi, 1 otomobil" ya da "çevre hareketi (ağaç/gölge)".
  - Aktivite çubukları türüne göre renkleniyor.
  - Lejantta her türün toplam süresi görünüyor.
  - "Önemsiz hareketleri gizle" seçeneği eklendi.
  - Üzerine gelince o andaki kişi ve araçlar renk ve plakalarıyla listeleniyor.
- **Bilgi paneli:** Her video için hareket türlerinin süre özeti gösteriliyor.
- **Araç kopyaları:** Aynı araç hem "otomobil" hem "kamyon" olarak bulunduğunda tek tespite indiriliyor.

## 0.1.0 — 2 Kasım 2026

İlk sürüm.
