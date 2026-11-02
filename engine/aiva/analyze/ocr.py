"""RapidOCR (PP-OCR, ONNX) sarmalayıcı. Tek örnek, iş parçacığı güvenli."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

_lock = threading.Lock()
_engine = None


@dataclass
class TextBox:
    text: str
    score: float
    box: tuple[int, int, int, int]   # x, y, w, h (piksel)


def _get():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        _engine = RapidOCR(params={"Global.log_level": "error"})
    return _engine


def read(img: np.ndarray, min_score: float = 0.5) -> list[TextBox]:
    with _lock:
        res = _get()(img)
    if res is None or res.txts is None:
        return []
    out = []
    for txt, score, box in zip(res.txts, res.scores, res.boxes):
        if score < min_score:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(min(xs)), int(min(ys))
        out.append(TextBox(str(txt), float(score), (x, y, int(max(xs)) - x, int(max(ys)) - y)))
    return out


def read_text(img: np.ndarray, min_score: float = 0.5) -> str:
    return " ".join(b.text for b in read(img, min_score))
