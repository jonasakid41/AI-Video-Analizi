"""Ekran saati (OSD) taraması: kareleri OCR ile okuyup medya→kamera eşlemesi kurar.

1. Video boyunca belirli aralıklarla kare alınır, saat bölgesi okunur.
2. Her okuma için fark = kamera_sn - t_m hesaplanır; ardışık benzer farklar bir parça olur.
3. Tek seferlik aykırı okumalar (OCR hatası) atılır.
4. Parça sınırları (saat sıçraması / kayıt boşluğu) ikili aramayla daraltılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import numpy as np

from ..analyze import ocr
from ..media import frames
from .mapping import Piece, TimeMapping, to_sec
from .parse import parse_osd

TOLERANCE = 2.5   # sn: aynı parça sayılacak fark sapması


@dataclass
class Reading:
    t: float
    camera: datetime
    text: str

    @property
    def offset(self) -> float:
        return to_sec(self.camera) - self.t


def crop_region(img: np.ndarray, region: list[float] | None) -> list[np.ndarray]:
    """Bölge verilmişse onu (normalize x,y,w,h), verilmemişse üst ve alt şeritleri döner."""
    h, w = img.shape[:2]
    if region:
        x, y, rw, rh = region
        x0, y0 = int(x * w), int(y * h)
        x1, y1 = int((x + rw) * w), int((y + rh) * h)
        return [img[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]]
    band = max(32, int(h * 0.16))
    return [img[:band], img[h - band:]]


def read_at(path: Path, t: float, region: list[float] | None, default_date: date | None) -> Reading | None:
    got = frames.frame_at(path, t)
    if got is None:
        return None
    ft, img = got
    for part in crop_region(img, region):
        if part.size == 0:
            continue
        if part.shape[0] < 48:
            part = np.ascontiguousarray(np.kron(part, np.ones((2, 2, 1), np.uint8)))
        text = ocr.read_text(part)
        dt = parse_osd(text, default_date)
        if dt:
            return Reading(ft, dt, text)
    return None


def group_pieces(readings: list[Reading], tol: float = TOLERANCE) -> list[list[Reading]]:
    groups: list[list[Reading]] = []
    for r in sorted(readings, key=lambda r: r.t):
        if groups and abs(r.offset - float(np.median([x.offset for x in groups[-1]]))) <= tol:
            groups[-1].append(r)
        else:
            groups.append([r])
    # Tek okumalı grup: komşularından farklıysa OCR hatasıdır, atılır
    cleaned: list[list[Reading]] = []
    for g in groups:
        if len(g) == 1 and len(groups) > 1:
            continue
        if cleaned and abs(np.median([x.offset for x in cleaned[-1]]) - np.median([x.offset for x in g])) <= tol:
            cleaned[-1].extend(g)
        else:
            cleaned.append(g)
    return cleaned or groups


def scan(path: Path, duration: float, region: list[float] | None = None, every: float = 10.0,
         default_date: date | None = None, refine_steps: int = 6,
         progress: Callable[[float], None] | None = None) -> tuple[TimeMapping | None, list[Reading]]:
    times = list(np.arange(0.0, max(duration - 0.5, 0.0), every)) + [max(0.0, duration - 0.5)]
    times = sorted(set(round(t, 3) for t in times))
    readings: list[Reading] = []
    known_date = default_date
    for i, t in enumerate(times):
        r = read_at(path, t, region, known_date)
        if r:
            readings.append(r)
            known_date = known_date or r.camera.date()
        if progress:
            progress((i + 1) / (len(times) + refine_steps * 2))
    if not readings:
        return None, []
    groups = group_pieces(readings)
    pieces: list[Piece] = []
    gaps: list[dict] = []
    for gi, g in enumerate(groups):
        offset = float(np.median([x.offset for x in g]))
        t_from = 0.0 if gi == 0 else g[0].t
        if gi > 0:
            prev = groups[gi - 1]
            prev_off = float(np.median([x.offset for x in prev]))
            lo, hi = prev[-1].t, g[0].t
            for _ in range(refine_steps):  # sıçramanın yerini daralt
                if hi - lo < 0.5:
                    break
                mid = (lo + hi) / 2
                r = read_at(path, mid, region, known_date)
                if r is None:
                    break
                if abs(r.offset - offset) <= TOLERANCE:
                    hi = r.t
                elif abs(r.offset - prev_off) <= TOLERANCE:
                    lo = r.t
                else:
                    break
            t_from = hi
            gaps.append({"t": round(hi, 3), "jump": round(offset - prev_off, 3)})
        pieces.append(Piece(round(t_from, 3), offset))
    mapping = TimeMapping(pieces=pieces, source="osd", gaps=gaps)
    return mapping, readings
