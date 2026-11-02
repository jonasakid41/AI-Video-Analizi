"""Plaka okuma: araç kırpıntısında OCR + Türk plaka biçimi doğrulaması ve düzeltmesi.

Türk plakası: il kodu (01–81) + 1–3 harf + 2–5 rakam.
  1 harf → 4–5 rakam, 2 harf → 3–4 rakam, 3 harf → 2–3 rakam.
OCR'ın sık karıştırdığı karakterler konuma göre düzeltilir (ör. rakam yerinde O → 0).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

import cv2
import numpy as np

from . import ocr

TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "J": "1", "T": "7", "Z": "2",
            "S": "5", "B": "8", "G": "6", "A": "4"}
TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A", "7": "T"}
TR_FOLD = str.maketrans({"Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U", "ı": "I"})
DIGITS_FOR_LETTERS = {1: (4, 5), 2: (3, 4), 3: (2, 3)}
FOREIGN = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9]{5,8}$")


@dataclass
class PlateRead:
    text: str          # biçimlendirilmiş: "34 ABC 123"
    raw: str
    conf: float
    valid_tr: bool
    fixes: int = 0


def clean(raw: str) -> str:
    s = raw.upper().translate(TR_FOLD)
    s = re.sub(r"[^A-Z0-9]", "", s)
    if s.startswith("TR") and len(s) > 7:
        s = s[2:]
    return s


def _fix(ch: str, want_digit: bool) -> tuple[str, int]:
    if want_digit:
        if ch.isdigit():
            return ch, 0
        return (TO_DIGIT[ch], 1) if ch in TO_DIGIT else ("", 99)
    if ch.isalpha():
        return ch, 0
    return (TO_LETTER[ch], 1) if ch in TO_LETTER else ("", 99)


def normalize_tr(raw: str) -> PlateRead | None:
    s = clean(raw)
    best: tuple[int, str] | None = None
    for nl, digit_counts in DIGITS_FOR_LETTERS.items():
        for nd in digit_counts:
            if len(s) != 2 + nl + nd:
                continue
            out, fixes = [], 0
            for i, ch in enumerate(s):
                want_digit = i < 2 or i >= 2 + nl
                c, f = _fix(ch, want_digit)
                fixes += f
                out.append(c)
            if fixes >= 99:
                continue
            txt = "".join(out)
            prov = int(txt[:2])
            if not 1 <= prov <= 81:
                continue
            formatted = f"{txt[:2]} {txt[2:2 + nl]} {txt[2 + nl:]}"
            if best is None or fixes < best[0]:
                best = (fixes, formatted)
    if best is None:
        return None
    return PlateRead(best[1], raw, 0.0, True, best[0])


def candidates_from_text(texts: list[tuple[str, float]]) -> list[PlateRead]:
    """OCR kutularından (tek tek ve yan yana birleşik) plaka adayları üretir."""
    out: list[PlateRead] = []
    joined = [(t, s) for t, s in texts]
    for i in range(len(texts) - 1):
        joined.append((texts[i][0] + texts[i + 1][0], min(texts[i][1], texts[i + 1][1])))
    for i in range(len(texts) - 2):
        joined.append((texts[i][0] + texts[i + 1][0] + texts[i + 2][0],
                       min(texts[i][1], texts[i + 1][1], texts[i + 2][1])))
    for t, score in joined:
        r = normalize_tr(t)
        if r:
            r.conf = score * (1.0 - 0.08 * r.fixes)
            out.append(r)
        else:
            c = clean(t)
            if FOREIGN.match(c):
                out.append(PlateRead(c, t, score * 0.6, False))
    return out


def read_vehicle(crop: np.ndarray) -> list[PlateRead]:
    """Araç kırpıntısından plaka adayları (en güvenilir ilk)."""
    if crop is None or crop.size == 0 or crop.shape[1] < 60:
        return []
    h = crop.shape[0]
    region = crop[int(h * 0.30):, :]
    if region.shape[1] < 480:
        f = 480 / region.shape[1]
        region = cv2.resize(region, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    boxes = ocr.read(region, min_score=0.4)
    rows: dict[int, list] = defaultdict(list)
    for b in boxes:
        rows[int((b.box[1] + b.box[3] / 2) // max(8, b.box[3]))].append(b)
    texts: list[tuple[str, float]] = []
    for _, bs in sorted(rows.items()):
        for b in sorted(bs, key=lambda b: b.box[0]):
            texts.append((b.text, b.score))
    cands = candidates_from_text(texts)
    return sorted(cands, key=lambda r: (r.valid_tr, r.conf), reverse=True)


def consensus(reads: list[PlateRead]) -> tuple[str | None, float]:
    """Bir aracın birden çok okumasından en olası plaka (güven ağırlıklı oy)."""
    if not reads:
        return None, 0.0
    votes: dict[str, float] = defaultdict(float)
    for r in reads:
        votes[r.text] += r.conf * (1.5 if r.valid_tr else 1.0)
    text, score = max(votes.items(), key=lambda kv: kv[1])
    total = sum(votes.values())
    return text, round(min(1.0, score / max(total, 1e-9)) * max(r.conf for r in reads if r.text == text), 3)


def similar(a: str, b: str) -> float:
    """Kısmi plaka araması için benzerlik (0–1)."""
    a, b = clean(a), clean(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) * 0.5 + 0.5
    # Levenshtein
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))
