"""CLIP (ViT-B/32) ile metin→görüntü arama vektörleri. Görüntü kodlayıcı GPU'da, metin kodlayıcı CPU'da."""

from __future__ import annotations

import threading

import cv2
import numpy as np

from . import runtime

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32)
CTX = 77
EOT = 49407

_lock = threading.Lock()
_tok = None


def _tokenizer():
    global _tok
    if _tok is None:
        from tokenizers import Tokenizer
        _tok = Tokenizer.from_file(str(runtime.model_path("clip_tokenizer")))
    return _tok


def _prep(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    s = 224 / min(h, w)
    r = cv2.resize(img, (max(224, round(w * s)), max(224, round(h * s))), interpolation=cv2.INTER_CUBIC)
    y0 = (r.shape[0] - 224) // 2
    x0 = (r.shape[1] - 224) // 2
    r = r[y0:y0 + 224, x0:x0 + 224, ::-1].astype(np.float32) / 255.0
    return ((r - MEAN) / STD).transpose(2, 0, 1)


def _norm(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def embed_images(imgs: list[np.ndarray], batch: int = 16) -> np.ndarray:
    if not imgs:
        return np.zeros((0, 512), np.float32)
    sess = runtime.session("clip_vision")
    outs = []
    for i in range(0, len(imgs), batch):
        x = np.stack([_prep(im) for im in imgs[i:i + batch]]).astype(np.float32)
        with _lock:
            outs.append(sess.run(None, {"pixel_values": x})[0])
    return _norm(np.concatenate(outs).astype(np.float32))


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 512), np.float32)
    tok = _tokenizer()
    ids = np.full((len(texts), CTX), EOT, np.int64)
    for i, t in enumerate(texts):
        enc = tok.encode(t).ids[:CTX]
        if enc and enc[-1] != EOT:
            enc[-1] = EOT
        ids[i, :len(enc)] = enc
    sess = runtime.session("clip_text", gpu=False)
    with _lock:
        out = sess.run(None, {"input_ids": ids})[0]
    return _norm(out.astype(np.float32))


def available() -> bool:
    return all(runtime.has_model(k) for k in ("clip_vision", "clip_text", "clip_tokenizer"))
