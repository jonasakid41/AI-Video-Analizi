"""Yüz tespiti (YuNet, MIT) ve yüz tanıma vektörü (SFace, Apache-2.0) — OpenCV ile.

Benzerlik kosinüs ile ölçülür. SFace için önerilen eşik 0.363'tür; bu uygulamada
"aynı kişi olabilir" için 0.36, "güçlü eşleşme" için 0.50 kullanılır.
Sonuçlar soruşturma ipucudur; kesin kimlik tespiti değildir.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from . import runtime

MATCH_THRESHOLD = 0.36
STRONG_THRESHOLD = 0.50
MIN_FACE_PX = 20

_lock = threading.Lock()
_engine: "FaceEngine | None" = None


@dataclass
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float
    row: np.ndarray   # YuNet çıktısı (15 değer), hizalama için

    @property
    def quality(self) -> float:
        return float(self.score * min(1.0, self.w / 80.0))


class FaceEngine:
    def __init__(self):
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        # Modeller bellekten yüklenir: OpenCV, Türkçe karakterli Windows yollarını açamıyor
        empty = np.array([], np.uint8)
        det_buf = np.fromfile(str(runtime.model_path("yunet")), np.uint8)
        rec_buf = np.fromfile(str(runtime.model_path("sface")), np.uint8)
        self.det = cv2.FaceDetectorYN.create("onnx", det_buf, empty, (320, 320), 0.75, 0.3, 50)
        self.rec = cv2.FaceRecognizerSF.create("onnx", rec_buf, empty)

    def detect(self, img: np.ndarray) -> list[Face]:
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(img)
        out = []
        if faces is None:
            return out
        for row in faces:
            x, y, fw, fh = (float(v) for v in row[:4])
            if fw < MIN_FACE_PX or fh < MIN_FACE_PX:
                continue
            out.append(Face(max(0.0, x), max(0.0, y), fw, fh, float(row[14]), row.copy()))
        return out

    def embed(self, img: np.ndarray, face: Face) -> np.ndarray:
        aligned = self.rec.alignCrop(img, face.row)
        feat = self.rec.feature(aligned).reshape(-1).astype(np.float32)
        return feat / max(float(np.linalg.norm(feat)), 1e-9)


def engine() -> FaceEngine:
    global _engine
    with _lock:
        if _engine is None:
            _engine = FaceEngine()
        return _engine


def detect_and_embed(img: np.ndarray) -> list[tuple[Face, np.ndarray]]:
    eng = engine()
    with _lock:
        faces = eng.detect(img)
        return [(f, eng.embed(img, f)) for f in faces]


def faces_in_person(img: np.ndarray, box: tuple[float, float, float, float]) -> list[tuple[Face, np.ndarray, np.ndarray]]:
    """Kişi kutusunun üst kısmında yüz arar. (yüz [tam kare koordinatı], vektör, kırpıntı) döner."""
    x1, y1, x2, y2 = box
    H, W = img.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    if bh < 60:
        return []
    rx0, ry0 = int(max(0, x1 - bw * 0.15)), int(max(0, y1 - bh * 0.05))
    rx1, ry1 = int(min(W, x2 + bw * 0.15)), int(min(H, y1 + bh * 0.45))
    region = img[ry0:ry1, rx0:rx1]
    if region.size == 0:
        return []
    scale = 1.0
    if region.shape[1] < 160:
        scale = 160 / region.shape[1]
        region = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    out = []
    for f, vec in detect_and_embed(region):
        fx, fy = rx0 + f.x / scale, ry0 + f.y / scale
        fw, fh = f.w / scale, f.h / scale
        full = Face(fx, fy, fw, fh, f.score, f.row)
        crop = img[int(max(0, fy - fh * 0.25)):int(min(H, fy + fh * 1.25)),
                   int(max(0, fx - fw * 0.25)):int(min(W, fx + fw * 1.25))]
        out.append((full, vec, crop))
    return out


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def cluster(vectors: list[np.ndarray], qualities: list[float], threshold: float = 0.42) -> list[int]:
    """Açgözlü kümeleme: kaliteli yüzden başlayarak benzerleri aynı kişiye atar."""
    order = sorted(range(len(vectors)), key=lambda i: -qualities[i])
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    labels = [-1] * len(vectors)
    for i in order:
        v = vectors[i]
        best, best_s = -1, threshold
        for ci, c in enumerate(centroids):
            s = float(np.dot(v, c / max(np.linalg.norm(c), 1e-9)))
            if s >= best_s:
                best, best_s = ci, s
        if best < 0:
            centroids.append(v.copy())
            counts.append(1)
            labels[i] = len(centroids) - 1
        else:
            centroids[best] = centroids[best] + v
            counts[best] += 1
            labels[i] = best
    return labels
