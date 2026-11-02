"""Hareket/aktivite ölçümü ve hareketin türü.

Arka plan çıkarımıyla (MOG2) ön plan maskesi çıkarılır. Hareketin ne olduğu şu ipuçlarıyla ayrılır:
  nesne     — hareket tespit edilen bir kişi/araç kutusunun içinde
  cevre     — nesne yokken hep aynı bölgede tekrarlayan hareket (ağaç, bitki, bayrak, gölge)
  isik      — parlaklık birden değişti ya da görüntünün büyük kısmı aynı anda değişti
  parazit   — çok sayıda küçük, dağınık nokta (yağmur, kar, görüntü gürültüsü)
  belirsiz  — hiçbirine uymayan hareket (ör. dedektörün kaçırdığı uzak/karanlık bir kişi): incelenmeli
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

import cv2
import numpy as np

GRID_W, GRID_H = 48, 27

KINDS = {
    "nesne": "kişi/araç hareketi",
    "cevre": "ağaç/bitki/gölge (tekrarlayan)",
    "isik": "ışık değişimi",
    "parazit": "yağmur/kar/parazit",
    "belirsiz": "tanımlanamayan hareket",
}
IGNORABLE = {"cevre", "isik", "parazit"}


@dataclass
class Sample:
    t: float
    score: float            # arka plan modeline göre yeni hareket (MOG2; tekrarlayan hareketi bastırır)
    mask: np.ndarray        # GRID_H×GRID_W bool (np.packbits ile saklanır): MOG2 ∪ kare farkı
    brightness: float
    blobs: int
    largest: float          # en büyük lekenin görüntüye oranı
    diff: float = 0.0       # ardışık örnekler arası fark (tekrarlayan hareketi de görür: ağaç, bayrak…)
    mlargest: float = 0.0   # MOG2 maskesindeki en büyük lekenin oranı (tekrarlayan hareket bastırılmış)
    boxes: tuple = ()       # MOG2 lekelerinin kutuları, büyükten küçüğe en fazla 4 (0–1 x, y, w, h)
    mlargest_px: int = 0    # aynı lekenin ölçüm çözünürlüğündeki piksel alanı

    def grid(self) -> np.ndarray:
        return np.unpackbits(self.mask)[: GRID_W * GRID_H].reshape(GRID_H, GRID_W).astype(bool)

    @property
    def visible(self) -> float:
        """Zaman çizelgesinde gösterilen hareket miktarı."""
        return max(self.score, self.diff)


class MotionMeter:
    def __init__(self, width: int = 320, warmup: int = 3):
        self.width = width
        self.warmup = warmup
        self.n = 0
        self.prev: np.ndarray | None = None
        self.bg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=True)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def measure(self, img_bgr: np.ndarray, t: float = 0.0) -> Sample:
        h, w = img_bgr.shape[:2]
        small = cv2.resize(img_bgr, (self.width, max(1, int(h * self.width / w))), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        fg = self.bg.apply(gray)
        prev, self.prev = self.prev, gray
        self.n += 1
        brightness = float(gray.mean())
        if self.n <= self.warmup or prev is None or prev.shape != gray.shape:
            return Sample(t, 0.0, np.packbits(np.zeros(GRID_W * GRID_H, bool)), brightness, 0, 0.0)
        mask = (fg > 200).astype(np.uint8)  # gölgeler (127) hariç
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        dmask = (cv2.absdiff(gray, prev) > 14).astype(np.uint8)
        dmask = cv2.morphologyEx(dmask, cv2.MORPH_OPEN, self.kernel)
        both = mask | dmask
        n, _lab, stats, _c = cv2.connectedComponentsWithStats(both)
        areas = stats[1:, cv2.CC_STAT_AREA] if n > 1 else np.zeros(0)
        grid = cv2.resize(both.astype(np.float32), (GRID_W, GRID_H), interpolation=cv2.INTER_AREA) > 0.12
        nm, _l, ms, _c = cv2.connectedComponentsWithStats(mask)
        mh, mw = mask.shape
        blobs = sorted((r for r in ms[1:] if r[cv2.CC_STAT_AREA] >= 6), key=lambda r: -r[cv2.CC_STAT_AREA])[:4] if nm > 1 else []
        return Sample(t, float(mask.mean()), np.packbits(grid.reshape(-1)), brightness,
                      int((areas >= 2).sum()), float(areas.max() / both.size) if areas.size else 0.0,
                      float(dmask.mean()),
                      float(blobs[0][cv2.CC_STAT_AREA] / mask.size) if blobs else 0.0,
                      tuple((r[0] / mw, r[1] / mh, r[2] / mw, r[3] / mh) for r in blobs),
                      int(blobs[0][cv2.CC_STAT_AREA]) if blobs else 0)

    def score(self, img_bgr: np.ndarray) -> float:
        return self.measure(img_bgr).score


# Uzaktaki bir kişi ölçüm karesinde birkaç piksellik leke olur: toplam hareket eşiğin altında kalsa da
# ardışık örneklerde süren derli toplu bir leke "aktif" sayılır (yoksa o bölüm seyrek taranıp kişi kaçıyordu).
# Eşik piksel cinsindendir; yüksek çözünürlüklü videolar daha geniş ölçüm karesiyle taranır (meter_width).
MIN_BLOB_PX = 12


def meter_width(video_width: float) -> int:
    """Geniş açılı yüksek çözünürlüklü kamerada uzaktaki kişiler 320 px'te tamamen kaybolur."""
    return 640 if video_width >= 1280 else 320


def compact(samples: list[Sample]) -> list[bool]:
    big = [s.mlargest_px >= MIN_BLOB_PX for s in samples]
    return [b and ((i > 0 and big[i - 1]) or (i + 1 < len(big) and big[i + 1])) for i, b in enumerate(big)]


def segment_signal(samples: list[Sample], threshold: float) -> list[tuple[float, float]]:
    """active_segments için (t, değer): küçük ama süren hareket eşik değerine yükseltilir."""
    return [(s.t, max(s.score, threshold) if c else s.score) for s, c in zip(samples, compact(samples))]


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


class BoxIndex:
    """Belirli bir ana yakın tespit kutuları (0–1 normalize x, y, w, h)."""

    def __init__(self, rows: list[tuple[float, float, float, float, float]]):
        rows = sorted(rows)
        self.ts = [r[0] for r in rows]
        self.boxes = [r[1:] for r in rows]

    def near(self, t: float, window: float = 0.8) -> list[tuple[float, float, float, float]]:
        i = bisect.bisect_left(self.ts, t - window)
        j = bisect.bisect_right(self.ts, t + window)
        return self.boxes[i:j]


def _box_mask(boxes, pad: float = 0.1) -> np.ndarray:
    m = np.zeros((GRID_H, GRID_W), bool)
    for x, y, w, h in boxes:
        x0, y0 = int((x - w * pad) * GRID_W), int((y - h * pad) * GRID_H)
        x1, y1 = int(np.ceil((x + w * (1 + pad)) * GRID_W)), int(np.ceil((y + h * (1 + pad)) * GRID_H))
        m[max(0, y0):min(GRID_H, y1), max(0, x0):min(GRID_W, x1)] = True
    return m


def classify(samples: list[Sample], boxes: BoxIndex, threshold: float) -> list[str | None]:
    grids = [s.grid() for s in samples]
    active = [s.visible >= threshold or c for s, c in zip(samples, compact(samples))]
    overlap = [0.0] * len(samples)
    for i, s in enumerate(samples):
        if not active[i]:
            continue
        fg = grids[i].sum()
        if fg:
            near = boxes.near(s.t)
            overlap[i] = float((grids[i] & _box_mask(near)).sum() / fg) if near else 0.0
    env = [grids[i] for i in range(len(samples)) if active[i] and overlap[i] < 0.3]
    persistent = (np.mean(env, axis=0) > 0.3) if len(env) >= 3 else np.zeros((GRID_H, GRID_W), bool)
    kinds: list[str | None] = []
    prev_b: float | None = None
    for i, s in enumerate(samples):
        jump = abs(s.brightness - prev_b) if prev_b is not None else 0.0
        prev_b = s.brightness
        if not active[i]:
            kinds.append(None)
            continue
        g = grids[i]
        frac = float(g.mean())
        fg = max(int(g.sum()), 1)
        if overlap[i] >= 0.3:
            kinds.append("nesne")
        elif jump > 12 or frac > 0.45:
            kinds.append("isik")
        elif persistent.any() and (g & persistent).sum() / fg > 0.6:
            kinds.append("cevre")
        elif s.blobs >= 12 and s.largest < 0.01:
            kinds.append("parazit")
        else:
            kinds.append("belirsiz")
    return kinds


def events(samples: list[Sample], kinds: list[str | None], max_gap: float) -> list[tuple[str, float, float]]:
    """Ardışık aynı türdeki anları olaylara birleştirir: (tür, t0, t1)."""
    out: list[list] = []
    for s, k in zip(samples, kinds):
        if k is None:
            continue
        if out and out[-1][0] == k and s.t - out[-1][2] <= max_gap:
            out[-1][2] = s.t
        else:
            out.append([k, s.t, s.t])
    return [(k, a, b) for k, a, b in out]
