export function fmtBytes(n: number | null | undefined): string {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

export function fmtUsd(v: number | null | undefined): string {
  if (!v) return "$0";
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `%${Math.round(v * 100)}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

export const JOB_LABELS: Record<string, string> = {
  ingest: "Dönüştürme",
  analyze: "Analiz",
  osd_scan: "Ekran saati okuma",
  query: "Soru",
  enhance: "İyileştirme",
  export_clip: "Kesit dışa aktarma",
  report: "Rapor",
  evaluate: "Model karşılaştırma",
};

export const STATUS_LABELS: Record<string, string> = {
  beklemede: "Sırada",
  calisiyor: "Çalışıyor",
  tamamlandi: "Tamamlandı",
  hata: "Hata",
  iptal: "İptal edildi",
  yarida_kaldi: "Yarıda kaldı",
};

export const TIME_SOURCE: Record<string, string> = {
  osd: "Ekran saati (OCR)",
  dosya_adi: "Dosya adı",
  metadata: "Dosya bilgisi",
  elle: "Elle girildi",
  yok: "Bilinmiyor",
};

export const ACTION_LABELS: Record<string, string> = {
  vaka_olusturuldu: "Vaka oluşturuldu",
  video_eklendi: "Video eklendi",
  donusturuldu: "Dönüştürüldü",
  donusturme_basarisiz: "Dönüştürme başarısız",
  analiz_tamamlandi: "Analiz tamamlandı",
  saat_eslemesi_guncellendi: "Saat eşlemesi güncellendi",
  soru_soruldu: "Soru soruldu",
  bulgu_eklendi: "Bulgu eklendi",
  bulgu_guncellendi: "Bulgu güncellendi",
  bulgu_silindi: "Bulgu silindi",
  iyilestirme: "İyileştirme",
  kare_disa_aktarildi: "Kare dışa aktarıldı",
  kesit_disa_aktarildi: "Kesit dışa aktarıldı",
  rapor_olusturuldu: "Rapor oluşturuldu",
  yuz_aramasi: "Yüz araması",
  plaka_aramasi: "Plaka araması",
  alan_eklendi: "Alan eklendi",
  video_silindi: "Video silindi",
  model_karsilastirma: "Model karşılaştırma",
};

export const CLASS_TR: Record<string, string> = {
  person: "kişi", car: "otomobil", truck: "kamyon/kamyonet", bus: "otobüs", motorcycle: "motosiklet",
  bicycle: "bisiklet", backpack: "sırt çantası", handbag: "çanta", suitcase: "bavul", umbrella: "şemsiye",
  knife: "bıçak", "cell phone": "telefon", dog: "köpek", cat: "kedi", bottle: "şişe", laptop: "dizüstü",
  "baseball bat": "sopa",
};

export const TARGET_TR: Record<string, string> = { ust: "üst", alt: "alt", govde: "gövde", genel: "" };

export function clsColor(cls: string | null | undefined): string {
  switch (cls) {
    case "person":
      return "#38bdf8";
    case "car":
    case "truck":
    case "bus":
    case "motorcycle":
      return "#f59e0b";
    case "bicycle":
      return "#a3e635";
    default:
      return "#e879f9";
  }
}
