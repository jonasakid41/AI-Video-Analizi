"""Nesne tespiti: YOLOX (Apache-2.0), COCO sınıfları. Ön/son işleme YOLOX ONNX demosuyla aynıdır."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import runtime

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

# Analizde tutulan sınıflar ve Türkçe adları
CLASSES_TR = {
    "person": "kişi", "bicycle": "bisiklet", "car": "otomobil", "motorcycle": "motosiklet", "bus": "otobüs",
    "truck": "kamyon/kamyonet", "backpack": "sırt çantası", "handbag": "el çantası", "suitcase": "bavul",
    "umbrella": "şemsiye", "knife": "bıçak", "cell phone": "cep telefonu", "baseball bat": "sopa",
    "dog": "köpek", "cat": "kedi", "bottle": "şişe", "laptop": "dizüstü bilgisayar",
}
VEHICLES = {"car", "motorcycle", "bus", "truck", "bicycle"}
MOTOR_VEHICLES = {"car", "motorcycle", "bus", "truck"}


@dataclass
class Det:
    cls: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    def crop(self, img: np.ndarray, pad: float = 0.0) -> np.ndarray:
        H, W = img.shape[:2]
        px, py = self.w * pad, self.h * pad
        x0, y0 = int(max(0, self.x1 - px)), int(max(0, self.y1 - py))
        x1, y1 = int(min(W, self.x2 + px)), int(min(H, self.y2 + py))
        return img[y0:y1, x0:x1]


class Detector:
    def __init__(self, name: str = "yolox_s"):
        self.sess = runtime.session(name)
        shp = self.sess.get_inputs()[0].shape
        self.size = int(shp[2]) if isinstance(shp[2], int) else 640
        self.input_name = self.sess.get_inputs()[0].name
        self._grids, self._strides = self._make_grids(self.size)
        self.keep_ids = np.array([i for i, c in enumerate(COCO) if c in CLASSES_TR])

    @staticmethod
    def _make_grids(size: int) -> tuple[np.ndarray, np.ndarray]:
        grids, strides = [], []
        for stride in (8, 16, 32):
            hs = ws = size // stride
            xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
            grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
            grids.append(grid)
            strides.append(np.full((1, grid.shape[1], 1), stride))
        return np.concatenate(grids, 1), np.concatenate(strides, 1)

    def _preprocess(self, img: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = img.shape[:2]
        r = min(self.size / h, self.size / w)
        resized = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
        padded = np.full((self.size, self.size, 3), 114, np.uint8)
        padded[: resized.shape[0], : resized.shape[1]] = resized
        blob = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        return blob, r

    def detect(self, img: np.ndarray, min_conf: float = 0.35, nms: float = 0.45) -> list[Det]:
        blob, r = self._preprocess(img)
        out = self.sess.run(None, {self.input_name: blob})[0]
        out[..., :2] = (out[..., :2] + self._grids) * self._strides
        out[..., 2:4] = np.exp(out[..., 2:4]) * self._strides
        pred = out[0]
        obj = pred[:, 4:5]
        cls_scores = pred[:, 5:][:, self.keep_ids] * obj
        cls_idx = cls_scores.argmax(1)
        conf = cls_scores[np.arange(len(cls_idx)), cls_idx]
        mask = conf >= min_conf
        if not mask.any():
            return []
        boxes = pred[mask, :4]
        conf = conf[mask]
        cls_ids = self.keep_ids[cls_idx[mask]]
        xywh = np.stack([(boxes[:, 0] - boxes[:, 2] / 2) / r, (boxes[:, 1] - boxes[:, 3] / 2) / r,
                         boxes[:, 2] / r, boxes[:, 3] / r], 1)
        keep = cv2.dnn.NMSBoxesBatched(xywh.tolist(), conf.tolist(), cls_ids.tolist(), min_conf, nms)
        H, W = img.shape[:2]
        dets = []
        for i in np.array(keep).reshape(-1):
            x, y, bw, bh = xywh[i]
            dets.append(Det(COCO[int(cls_ids[i])], float(conf[i]),
                            float(max(0, x)), float(max(0, y)), float(min(W, x + bw)), float(min(H, y + bh))))
        return merge_vehicle_duplicates(dets)


def _iou(a: Det, b: Det) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def merge_vehicle_duplicates(dets: list[Det], thr: float = 0.65) -> list[Det]:
    """Aynı araç bazen hem "otomobil" hem "kamyon" olarak bulunur (sınıf bazlı NMS ikisini de tutar).
    Araç sınıfları arasında büyük ölçüde çakışan kutulardan güveni yüksek olan kalır."""
    out: list[Det] = []
    for d in sorted(dets, key=lambda d: -d.conf):
        if d.cls in MOTOR_VEHICLES and any(o.cls in MOTOR_VEHICLES and _iou(o, d) >= thr for o in out):
            continue
        out.append(d)
    return out
