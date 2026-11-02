"""Hareket/aktivite ölçümü: arka plan çıkarımı (MOG2) ile ön plan piksel oranı."""

from __future__ import annotations

import cv2
import numpy as np


class MotionMeter:
    def __init__(self, width: int = 320, warmup: int = 3):
        self.width = width
        self.warmup = warmup
        self.n = 0
        self.bg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=True)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def score(self, img_bgr: np.ndarray) -> float:
        h, w = img_bgr.shape[:2]
        small = cv2.resize(img_bgr, (self.width, max(1, int(h * self.width / w))), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        fg = self.bg.apply(gray)
        self.n += 1
        if self.n <= self.warmup:
            return 0.0
        mask = (fg > 200).astype(np.uint8)  # gölgeler (127) hariç
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        return float(mask.mean())


def active_segments(samples: list[tuple[float, float]], threshold: float, pad: float = 1.5,
                    min_gap: float = 3.0, duration: float | None = None) -> list[tuple[float, float]]:
    """Eşiği aşan anları birleştirip [t0, t1] aralıkları üretir."""
    hits = [t for t, s in samples if s >= threshold]
    if not hits:
        return []
    segs: list[list[float]] = []
    for t in hits:
        a, b = t - pad, t + pad
        if segs and a <= segs[-1][1] + min_gap:
            segs[-1][1] = max(segs[-1][1], b)
        else:
            segs.append([a, b])
    end = duration if duration is not None else float("inf")
    return [(max(0.0, a), min(end, b)) for a, b in segs]
