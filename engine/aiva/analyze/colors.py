"""Baskın renk adları (Türkçe). Kişilerde üst/alt beden, araçlarda gövde."""

from __future__ import annotations

import cv2
import numpy as np

# HSV (OpenCV: H 0–179) aralıkları
HUES = [
    ("kırmızı", [(0, 8), (170, 179)]),
    ("turuncu", [(9, 20)]),
    ("sarı", [(21, 33)]),
    ("yeşil", [(34, 85)]),
    ("turkuaz", [(86, 99)]),
    ("mavi", [(100, 128)]),
    ("mor", [(129, 150)]),
    ("pembe", [(151, 169)]),
]

COLOR_EN = {
    "kırmızı": "red", "turuncu": "orange", "sarı": "yellow", "yeşil": "green", "turkuaz": "cyan",
    "mavi": "blue", "mor": "purple", "pembe": "pink", "siyah": "black", "beyaz": "white", "gri": "gray",
    "kahverengi": "brown", "lacivert": "navy",
}


def dominant(crop: np.ndarray, top: int = 2) -> list[tuple[str, float]]:
    if crop is None or crop.size == 0:
        return []
    small = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    n = len(h)
    counts: dict[str, int] = {}
    black = v < 50
    white = (v > 190) & (s < 40)
    gray = (~black) & (~white) & (s < 45)
    counts["siyah"] = int(black.sum())
    counts["beyaz"] = int(white.sum())
    counts["gri"] = int(gray.sum())
    chroma = ~(black | white | gray)
    for name, ranges in HUES:
        m = np.zeros(n, bool)
        for lo, hi in ranges:
            m |= (h >= lo) & (h <= hi)
        m &= chroma
        if name == "turuncu":
            brown = m & (v < 150)
            counts["kahverengi"] = counts.get("kahverengi", 0) + int(brown.sum())
            m &= ~brown
        if name == "mavi":
            navy = m & (v < 90)
            counts["lacivert"] = int(navy.sum())
            m &= ~navy
        counts[name] = counts.get(name, 0) + int(m.sum())
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [(k, round(c / n, 3)) for k, c in ranked[:top] if c / n >= 0.12]


def describe_person(crop: np.ndarray) -> dict:
    h = crop.shape[0]
    upper = crop[int(h * 0.18):int(h * 0.50)]
    lower = crop[int(h * 0.55):int(h * 0.90)]
    w = crop.shape[1]
    upper = upper[:, int(w * 0.2):int(w * 0.8)]
    lower = lower[:, int(w * 0.2):int(w * 0.8)]
    return {"ust": dominant(upper), "alt": dominant(lower)}


def describe_vehicle(crop: np.ndarray) -> dict:
    h, w = crop.shape[:2]
    body = crop[int(h * 0.25):int(h * 0.75), int(w * 0.15):int(w * 0.85)]
    return {"govde": dominant(body)}
