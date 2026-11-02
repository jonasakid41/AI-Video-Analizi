"""Gece, kızılötesi (IR) ve siyah-beyaz görüntü ipuçları.

Birçok kamera gece siyah-beyaz (IR) moda geçer. Bu karelerde renk bilgisi yoktur: renk adları
yanıltıcı olur ("gri mont"), renk filtresi doğru kişiyi eleyebilir. Karanlık ya da düşük kontrastlı
karelerde ise dedektör kişileri kaçırabilir; tespitten önce yerel kontrast artırılır.
"""

from __future__ import annotations

import cv2
import numpy as np


def frame_stats(img_bgr: np.ndarray) -> tuple[bool, bool, bool]:
    """(renksiz, karanlık, düşük kontrast). Küçük bir kopya üzerinde hızlı ölçüm."""
    small = cv2.resize(img_bgr, (64, 36), interpolation=cv2.INTER_AREA)
    ycc = cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    y, cr, cb = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    chroma = float((np.abs(cr - 128) + np.abs(cb - 128)).mean())
    # Saf gri ya da tek renk tonlu (morumsu/yeşilimsi IR) görüntü: renk farkı yok ya da her yerde aynı
    gray = chroma < 3.0 or (float(cr.std()) < 1.5 and float(cb.std()) < 1.5)
    return gray, float(y.mean()) < 70, float(y.std()) < 28


def enhance(img_bgr: np.ndarray, clip: float = 2.5) -> np.ndarray:
    """Tespit için yerel kontrast (CLAHE, yalnızca parlaklık kanalı)."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(lab[..., 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
