"""Soru → arama planı. Model varsa model ile, yoksa yerel kurallarla."""

from __future__ import annotations

import re
from typing import Any

from ..analyze import plates as platemod
from ..analyze.colors import COLOR_EN
from . import client, prompts

CLASS_WORDS = {
    "person": ["kişi", "kisi", "insan", "adam", "kadın", "kadin", "çocuk", "cocuk", "yaya", "biri", "birisi",
               "şahıs", "sahis", "erkek", "kız", "kiz", "genç", "yaşlı", "şüpheli", "kimse", "kim"],
    "car": ["araba", "araç", "arac", "otomobil", "taksi", "oto ", "binek"],
    "truck": ["kamyon", "kamyonet", "pikap", "tır", "panelvan", "minivan"],
    "bus": ["otobüs", "otobus", "minibüs", "minibus", "midibüs"],
    "motorcycle": ["motor", "motosiklet", "kurye", "scooter", "skuter"],
    "bicycle": ["bisiklet"],
    "backpack": ["sırt çanta", "sirt canta"],
    "handbag": ["çanta", "canta"],
    "suitcase": ["bavul", "valiz"],
    "umbrella": ["şemsiye", "semsiye"],
    "dog": ["köpek", "kopek"],
    "cat": ["kedi"],
    "knife": ["bıçak", "bicak"],
    "cell phone": ["telefon"],
}
UPPER_WORDS = ["mont", "ceket", "tişört", "tisort", "gömlek", "gomlek", "kazak", "sweat", "hırka", "yelek",
               "kapüşon", "kapusonlu", "üst", "ust", "palto", "kaban"]
LOWER_WORDS = ["pantolon", "etek", "şort", "sort", "eşofman", "esofman", "kot", "alt"]
MOTION_WORDS = ["kavga", "düş", "dus", "koş", "kos", "kaç", "kac", "bırak", "birak", "çal", "cal", "kır", "kir",
                "vur", "it", "saldır", "saldir", "atla", "tırman", "tirman", "kapı aç", "kapiyi ac"]
EN_CLASS = {"person": "a person", "car": "a car", "truck": "a truck or van", "bus": "a bus",
            "motorcycle": "a motorcycle", "bicycle": "a bicycle", "backpack": "a backpack", "handbag": "a handbag",
            "suitcase": "a suitcase", "umbrella": "an umbrella", "dog": "a dog", "cat": "a cat", "knife": "a knife",
            "cell phone": "a mobile phone"}

RE_RANGE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:['’]?(?:da|de|ta|te|dan|den|tan|ten))?\s*(?:-|–|ile|ila|ve)\s*"
                      r"(\d{1,2})(?:[:.](\d{2}))?")
RE_AFTER = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*['’]?(?:dan|den|tan|ten)\s+sonra")
RE_BEFORE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*['’]?(?:dan|den|tan|ten)\s+önce")
RE_AT = re.compile(r"saat\s+(\d{1,2})(?:[:.](\d{2}))?")


def _hm(h: str, m: str | None) -> str | None:
    hh, mm = int(h), int(m or 0)
    return f"{hh:02d}:{mm:02d}" if hh < 24 and mm < 60 else None


def _fmt_min(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def local_plan(question: str) -> dict[str, Any]:
    q = " " + question.lower() + " "
    plan: dict[str, Any] = {"intent": "ara", "time_from": None, "time_to": None, "classes": [], "colors": [],
                            "plate": None, "visual_query_en": "", "verify_question": question.strip(),
                            "needs_motion": False, "source": "yerel"}
    if (m := RE_RANGE.search(q)) and ("saat" in q or ":" in q or "." in m.group(0) or "arası" in q or "arasi" in q):
        plan["time_from"], plan["time_to"] = _hm(m.group(1), m.group(2)), _hm(m.group(3), m.group(4))
    elif m := RE_AFTER.search(q):
        plan["time_from"] = _hm(m.group(1), m.group(2))
    elif m := RE_BEFORE.search(q):
        plan["time_to"] = _hm(m.group(1), m.group(2))
    elif m := RE_AT.search(q):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h < 24 and mi < 60:
            # "saat 14" → 14:00–15:00, "saat 14:30" → 14:25–14:35
            start, end = (h * 60 + mi - 5, h * 60 + mi + 5) if m.group(2) else (h * 60, h * 60 + 60)
            plan["time_from"] = _fmt_min(max(0, start))
            plan["time_to"] = _fmt_min(min(24 * 60 - 1, end))
    for cls, words in CLASS_WORDS.items():
        if any(w in q for w in words):
            if cls == "handbag" and "backpack" in plan["classes"]:
                continue
            plan["classes"].append(cls)
    for word in re.findall(r"[a-zçğıöşü]+", q):
        for tr in COLOR_EN:
            if word.startswith(tr):
                after = q[q.find(word):q.find(word) + 30]
                if any(w in after for w in UPPER_WORDS):
                    target = "ust"
                elif any(w in after for w in LOWER_WORDS):
                    target = "alt"
                elif any(c in plan["classes"] for c in ("car", "truck", "bus", "motorcycle")):
                    target = "govde"
                else:
                    target = "genel"
                plan["colors"].append({"target": target, "color": tr})
                break
    # Plaka: tam ya da kısmi (en az 2 karakter rakam/harf karışık)
    pm = re.search(r"\b(\d{2})\s?([a-zçğıöşü]{1,3})\s?(\d{2,5})\b", q)
    if pm:
        r = platemod.normalize_tr("".join(pm.groups()))
        plan["plate"] = platemod.clean(r.text if r else "".join(pm.groups()))
    elif "plaka" in q:
        pm2 = re.search(r"plaka\w*\s+([0-9a-z]{2,8})", q)
        if pm2 and any(ch.isdigit() for ch in pm2.group(1)):
            plan["plate"] = platemod.clean(pm2.group(1))
    if plan["plate"] or "plaka" in q:
        plan["intent"] = "plaka"
        if not any(c in plan["classes"] for c in ("car", "truck", "bus", "motorcycle")):
            plan["classes"] += ["car", "truck", "bus", "motorcycle"]
    if "yüz" in q or "yuz" in q or "surat" in q:
        plan["intent"] = "yuz"
        if "person" not in plan["classes"]:
            plan["classes"].append("person")
    if re.search(r"\bkaç\b|\bkac\b|sayı|sayi", q):
        plan["intent"] = "say"
    if any(w in q for w in ("özet", "ozet", "neler oldu", "ne oldu", "olaylar")):
        plan["intent"] = "ozet"
    plan["needs_motion"] = any(re.search(rf"\b{w}", q) for w in MOTION_WORDS)
    plan["visual_query_en"] = _visual_en(plan)
    return plan


def _visual_en(plan: dict) -> str:
    cls = plan["classes"][0] if plan["classes"] else None
    base = EN_CLASS.get(cls, "a scene") if cls else "a scene"
    bits = []
    for c in plan["colors"]:
        en = COLOR_EN.get(c["color"], c["color"])
        if c["target"] == "ust":
            bits.append(f"wearing a {en} top")
        elif c["target"] == "alt":
            bits.append(f"wearing {en} trousers")
        elif c["target"] == "govde" and cls:
            base = f"a {en} {base.split(' ', 1)[1]}"
        else:
            bits.append(f"{en}")
    return (base + (" " + " and ".join(bits) if bits else "")).strip()


def plan(question: str, model: str | None, case_id: int | None, query_id: int | None) -> tuple[dict, dict]:
    """(plan, kullanım) döner. Model hatasında yerel plana düşer."""
    if model and client.configured():
        try:
            res = client.chat(model, [{"role": "system", "content": prompts.PLANNER_SYSTEM},
                                      {"role": "user", "content": question}],
                              prompts.PLAN_SCHEMA, role="planlayici", case_id=case_id, query_id=query_id,
                              max_tokens=600)
            p = res["parsed"]
            p["source"] = "model"
            p["classes"] = [c for c in p.get("classes", []) if c in prompts.CLASS_ENUM]
            if p.get("plate"):
                p["plate"] = platemod.clean(p["plate"])
            local = local_plan(question)
            # Model saat aralığını kaçırırsa yerel ayrıştırıcının bulduğunu kullan
            for k in ("time_from", "time_to"):
                p[k] = p.get(k) or local.get(k)
            if not p.get("visual_query_en"):
                p["visual_query_en"] = local["visual_query_en"]
            return p, {"cost": res["cost"], "in": res["usage"]["in"], "out": res["usage"]["out"]}
        except client.AIError as e:
            lp = local_plan(question)
            lp["warning"] = f"Planlayıcı model hatası, yerel ayrıştırma kullanıldı: {e}"
            return lp, {"cost": 0.0, "in": 0, "out": 0}
    return local_plan(question), {"cost": 0.0, "in": 0, "out": 0}
