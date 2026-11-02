# Sürüm geçmişi

## 0.1.6 — 2 Kasım 2026

Yapay zekâ artık videonun tamamına bakıyor; CLI'da model seçilebiliyor ve varsayılan en güçlü model.

- **Neden gerekliydi:** Önceden yapay zekâ yalnızca yerel analizin seçtiği adayları görüyordu: en fazla 40 kişi/araç kırpıntısı, birkaç benzer kare ve bulunamazsa 16–24 düzenli kare. Yerel dedektörün tanımadığı bir nesne (çanta, yerdeki eşya, belirli bir giysi, bir olay) modele hiç gösterilmiyordu. Videoyu doğrudan Claude'a vermek bu yüzden daha iyi sonuç veriyordu.
- **Yüklemeden sonra yapay zekâ ön incelemesi:**
  - Analizden sonra model videonun tamamını kare ızgaralarıyla izliyor; hareketli bölümler daha sık örnekleniyor.
  - Model her kare için zaman damgalı Türkçe notlar yazıyor: kişiler, giysiler, araçlar, eylemler, dikkat çeken olaylar.
  - Notlar Bilgi sekmesinde listeleniyor; tıklanınca o ana gidiliyor.
  - CLI aboneliğinde otomatik başlıyor (ücretsiz); OpenRouter'da elle başlatılıyor (maliyet çıkarır).
- **Sorularda yapay zekâ taraması:**
  - Doğrulamalı ve Derin modda model önce ön inceleme notlarında arıyor. Not yoksa ya da yetersizse videonun tamamını kare ızgaralarıyla tarıyor.
  - Bulduğu anlar tam çözünürlükte yeniden doğrulanıyor; yerel adaylar da eklenmeye devam ediyor.
  - Soru bir nesne türü içermiyorsa doğrulama ilgisiz kişi kırpıntılarıyla dolmuyor.
  - Yapay zekânın bulduğu anlar sonuç kartında işaretleniyor.
- **CLI model seçimi:**
  - Ayarlar'da her CLI aracı için model seçilebiliyor. Claude Code'da varsayılan Opus (en güçlü), tüm görevler için.
  - Codex ve Gemini için model adı elle yazılabiliyor.
- **Doğrulama:**
  - Modele kullanıcının özgün sorusu her zaman gidiyor.
  - Aday grupları aynı anda 3 çağrıyla doğrulanıyor.
  - CLI'da tam kareler 1536 px'e kadar gönderiliyor.
  - Bir grubun hatası diğer adayların doğrulanmasını durdurmuyor.
- **Ayarlar:** Ayarlar > Yapay zekâ > "Yapay zekâ ile inceleme" bölümünde tarama açık/kapalı, ön incelemenin ne zaman yapılacağı, tarama ayrıntısı (görüntü başına 4/9/16 kare) ve soru başına en fazla taranacak kare sayısı ayarlanabiliyor.
- **Gerçek deneme (Claude Code, Opus):** Yaya videosunda yerel dedektörün tanımadığı "çimendeki beyaz nesne" hem ön inceleme notlarıyla hem yalnızca taramayla bulundu (soru başına ~50 sn).
## 0.1.5 — 2 Kasım 2026

Hikvision dışa aktarımlarının (IMKH başlıklı MPEG-PS, H.265 + G.711) dönüştürülememesi ve kayıtta görülen ufak bozulmalar düzeltildi.

- **"Hiç video paketi kopyalanamadı" hatası:**
  - Hikvision dosyalarında başlık atlanınca ses G.711 yerine MP2 sanılıyordu. Örnekleme hızı 0 çıktığı için kayıpsız kopyanın kabı hiç yazılamıyor ve dosya dönüştürülemiyordu.
  - Bu dosyalar artık IMKH başlığıyla açılıyor; FFmpeg sesi doğru tanıyor.
  - Kayıpsız kopya önce ses + video için MKV'yi, sonra NUT'u, en son yalnızca videoyu deniyor. Kap başlığı önceden yazılıyor; bir ses sorunu artık videoyu engellemiyor.
  - G.711 ses kayıpsız kopyada korunuyor.
- **Ufak bozulmalar:**
  - Kopyalamada zaman damgası eşit, eksik ya da geri giden video kareleri atılıyordu. Atılan tek bir kare, sonraki kareleri bir sonraki anahtar kareye kadar bozuyordu.
  - Artık hiçbir video karesi zaman damgası yüzünden atılmıyor. Eksik damga tahmin ediliyor, eşit ya da az geri giden damga bir tık ileri alınıyor.
- **Kamera saati geri atlarsa:**
  - Saat ayarı ya da sayaç sıfırlanması yüzünden zaman damgası geri giderse zaman çizgisi kesintisiz sürdürülüyor ve olay Bilgi sekmesinde gösteriliyor.
  - MPEG-PS'in 33 bitlik sayacının taşması artık 25 saatlik sahte bir "kayıt boşluğu" oluşturmuyor.
- **Çalışma kopyası kalitesi:** Yüksek çözünürlükten 1080p'ye indirilen görüntüde bloklanmayı azaltmak için kodlayıcı kalitesi bir kademe yükseltildi.
## 0.1.4 — 2 Kasım 2026

Yüksek çözünürlüklü bazı videoların "ValueError" ile dönüştürülememesi düzeltildi.

- **AV1 videolar:** Kayıpsız kopya adımında AV1 kodlu videolar (YouTube'dan indirilen ve yeni kameralardan gelen 4K kayıtlarda sık) "ValueError: Kayıpsız kopya oluşturulamadı: libdav1d" hatası veriyordu. Video kodlayıcının adı bulunamadığında kodek bilgisi artık doğrudan kopyalanıyor.
- **Denenen biçimler:** 4K/8K H.264 ve HEVC, 10 bit HEVC, DCI 4K, 5K ultra geniş, dikey 4K, 60 fps B-frame, 4:2:2, ProRes, VP9, MJPEG, AV1 ve 4,3 GB'lık bir dosya dönüştürüldü; 8K, dikey 4K, AV1 ve 10 bit HEVC videolar analiz edildi.
- **Daha anlaşılır hata ve teşhis:**
  - Dönüştürme ayrı süreçte hata verirse kullanıcı "ValueError" yerine anlaşılır bir mesaj görüyor.
  - Hatanın türü ve tam ayrıntısı teşhis paketine (Bilgi sekmesi) ve motor günlüğüne yazılıyor.
## 0.1.3 — 2 Kasım 2026

Abonelikle yapay zekâ kullanımı, uzaktaki kişilerin bulunması ve gece/siyah-beyaz kayıtlar.

- **Bilgisayardaki AI araçları (abonelik):**
  - OpenRouter yerine bilgisayarda kurulu Claude Code, OpenAI Codex CLI ya da Gemini CLI kullanılabilir. Ücret alınmaz; aboneliğin kullanım sınırları geçerlidir.
  - Ayarlar > Yapay zekâ'da kurulu araçlar sürümleriyle listelenir. "Test et" ile çalıştığı denenir, "Kullan" ile tüm görevler o araca geçer.
  - Modeller "abonelik" rozetiyle görev seçicide görünür; model karşılaştırmada da kullanılabilir.
  - Video analizi için video yerine kısa aralıklı kareler gönderilir.
  - Kullanım sınırı ya da açık olmayan oturum gibi hatalar anlaşılır bir mesajla gösterilir.
  - Codex ve Gemini desteği deneyseldir.
- **"Kayıtta kişi var ama bulunamadı" düzeltmeleri:**
  - Geniş açılı yüksek çözünürlüklü kameralarda hareket 640 px'te ölçülüyor. Küçük ama süren hareket de bölümü "aktif" sayıyor; önceden bu bölümler 10 sn'de bir kareyle taranıyor ve kişi kaçıyordu.
  - Hiçbir tespitin açıklamadığı hareket bölgesi kırpılıp büyütülerek yeniden taranıyor. Testte uzaktaki kişilerde bulunan iz 1'den 19'a çıktı.
  - Kişiler için tespit eşiği düşürüldü. Tek karelik yanlış tespitleri takip filtresi eliyor.
  - Dedektörün tanımadığı hareket anları, hareket bölgesi yakından gösterilerek yapay zekâya doğrulatılıyor.
  - Kutusuz kareler modele daha yüksek çözünürlükte gönderiliyor.
  - Doğrulama talimatı uzak, küçük ve karanlık figürleri kaçırmayacak şekilde düzenlendi.
- **Gece / siyah-beyaz (IR) kayıtlar:**
  - Siyah-beyaz kareler otomatik tanınıyor. Renk yerine ton (koyu/açık) kaydediliyor ve "siyah-beyaz kayıt" olarak işaretleniyor.
  - Renkli sorularda (ör. "kırmızı montlu") kişiler renge göre elenmiyor. Modele rengin doğrulanamayacağı söyleniyor; cevapta da açıkça belirtiliyor.
  - Görsel arama siyah-beyaz kayıtta renk sözcükleri olmadan yapılıyor.
  - Karanlık ya da düşük kontrastlı karelerde kişi, yüz ve plaka kontrast artırılarak aranıyor.
  - İyileştir sekmesine "Gece / IR", "Plaka / yazı" ve "Genel" hazır ayarları eklendi; siyah-beyaz kayıtta gece ayarı öneriliyor.
  - Siyah-beyaz karede gürültü azaltma tek kanalda yapılıyor; daha hızlı ve renk lekesiz.
  - Bilgi sekmesinde "Görüntü" satırı var: renkli ya da siyah-beyaz, düşük ışık oranı, yakınlaştırmayla gelen ek tespitler.
- **Cevaplar:** Yapay zekâ cevabı düz metin olarak yazılıyor ve arama notlarını (ör. siyah-beyaz kayıt) dikkate alıyor.
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
