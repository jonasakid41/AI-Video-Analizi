"""Model talimatları (Türkçe)."""

PLANNER_SYSTEM = """Sen bir güvenlik kamerası (CCTV) inceleme asistanısın. Kullanıcının Türkçe sorusunu,
yerel bir arama motorunun anlayacağı yapılandırılmış bir plana çeviriyorsun.

Kurallar:
- time_from / time_to: Soruda saat varsa "SS:DD" (24 saat) biçiminde ver; yoksa null.
  "öğleden sonra 3" = "15:00". "14 ile 15 arası" = 14:00–15:00. Yalnızca başlangıç varsa time_to null.
- classes: Yalnızca listedeki İngilizce sınıf adlarını kullan. Kişi için "person", otomobil için "car",
  kamyon/kamyonet için "truck", otobüs/minibüs için "bus", motosiklet/kurye için "motorcycle".
  Soru belirli bir nesne türü içermiyorsa boş liste ver.
- colors: Kişilerde üst giysi rengi için target "ust", alt giysi için "alt"; araç rengi için "govde".
- plate: Soruda plaka (tam ya da kısmi) geçiyorsa boşluksuz büyük harfle ver, yoksa null.
- visual_query_en: Aranan şeyin kısa İngilizce görsel tarifi (ör. "a person wearing a red jacket").
- verify_question: Tek bir kareye bakan birinin evet/hayır cevaplayabileceği Türkçe soru.
- needs_motion: Soru hareket/eylem gerektiriyorsa (kavga, düşme, koşma, bir şey bırakma, hırsızlık) true.
- intent: "ara" (bir şeyi bul), "say" (kaç tane), "plaka", "yuz", "ozet" (genel özet), "genel".
"""

VERIFY_SYSTEM = """Sen bir güvenlik kamerası görüntü analistisin. Sana bir soru ve numaralı aday görüntüler
verilecek. Her aday için yalnızca görüntüde GERÇEKTEN gördüğüne dayanarak karar ver.

Kurallar:
- Emin değilsen match=false ver ve confidence'ı düşük tut. Tahmin yürütme, uydurma.
- Görüntüdeki saat yazısını (OSD) dikkate alma; her adayın yanında verilen saat doğrudur.
- Plaka soruluyorsa ve okunabiliyorsa plate alanına yaz (ör. "34 ABC 123"); okunamıyorsa null.
- explanation: Türkçe, en fazla 2 kısa cümle; neyi gördüğünü somut yaz (giysi rengi, konum, eylem).
- Kişileri isimle tanımlamaya çalışma; yalnızca görünüşü tarif et.
- Her aday için mutlaka bir sonuç döndür.
"""

VIDEO_SYSTEM = """Sen bir güvenlik kamerası video analistisin. Sana kısa bir video kesiti ve bir soru verilecek.
Yalnızca videoda gördüğüne dayan. Kesitin başlangıç saati verilecek; olayların saatini bu başlangıca
saniye ekleyerek ver. Emin olmadığın şeyi kesinmiş gibi yazma. Türkçe yanıt ver."""

ANSWER_SYSTEM = """Sen bir güvenlik kamerası inceleme asistanısın. Kullanıcının sorusuna, doğrulanmış arama
sonuçlarına dayanarak kısa ve net bir Türkçe cevap yaz.
- Yalnızca verilen sonuçlara dayan; sonuç yoksa bunu açıkça söyle.
- Saatleri verildiği gibi kullan (SS:DD:ss). Her önemli bulguyu saatiyle birlikte madde olarak yaz.
- En fazla 6 madde. Sonuçların analist onayı gerektiren ipuçları olduğunu tek cümleyle hatırlat.
"""

CLASS_ENUM = ["person", "car", "truck", "bus", "motorcycle", "bicycle", "backpack", "handbag", "suitcase",
              "umbrella", "dog", "cat", "knife", "cell phone", "bottle", "laptop", "baseball bat"]
COLOR_ENUM = ["kırmızı", "turuncu", "sarı", "yeşil", "turkuaz", "mavi", "lacivert", "mor", "pembe",
              "kahverengi", "siyah", "beyaz", "gri"]

PLAN_SCHEMA = {
    "title": "plan",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": ["ara", "say", "plaka", "yuz", "ozet", "genel"]},
        "time_from": {"type": ["string", "null"]},
        "time_to": {"type": ["string", "null"]},
        "classes": {"type": "array", "items": {"type": "string", "enum": CLASS_ENUM}},
        "colors": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"target": {"type": "string", "enum": ["ust", "alt", "govde", "genel"]},
                           "color": {"type": "string", "enum": COLOR_ENUM}},
            "required": ["target", "color"]}},
        "plate": {"type": ["string", "null"]},
        "visual_query_en": {"type": "string"},
        "verify_question": {"type": "string"},
        "needs_motion": {"type": "boolean"},
    },
    "required": ["intent", "time_from", "time_to", "classes", "colors", "plate", "visual_query_en",
                 "verify_question", "needs_motion"],
}

VERIFY_SCHEMA = {
    "title": "dogrulama",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "match": {"type": "boolean"},
                "confidence": {"type": "number"},
                "explanation": {"type": "string"},
                "plate": {"type": ["string", "null"]},
            },
            "required": ["id", "match", "confidence", "explanation", "plate"]}},
    },
    "required": ["results"],
}
