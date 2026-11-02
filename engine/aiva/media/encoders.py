"""H.264 kodlayıcı seçimi: donanım (NVENC / QSV / AMF) varsa onu, yoksa yazılımı kullanır."""

from __future__ import annotations

import threading
from fractions import Fraction

import av
import numpy as np

ORDER = ["h264_nvenc", "h264_qsv", "h264_amf", "libx264", "h264_mf"]

LABELS = {
    "h264_nvenc": "NVIDIA NVENC (donanım)",
    "h264_qsv": "Intel Quick Sync (donanım)",
    "h264_amf": "AMD AMF (donanım)",
    "libx264": "x264 (yazılım)",
    "h264_mf": "Windows Media Foundation",
}

_lock = threading.Lock()
_cache: dict[str, bool] = {}
_chosen: str | None = None


def pix_fmt_for(name: str) -> str:
    return "nv12" if name in ("h264_qsv", "h264_mf") else "yuv420p"


def options_for(name: str) -> dict[str, str]:
    # Yüksek çözünürlüklü kaynak 1080p'ye indirilirken ince ayrıntı (plaka, yüz) bloklaşmasın diye kalite
    # bir kademe yüksek; NVENC'de uzamsal uyarlamalı niceleme düz alanlardaki bloklanmayı azaltır
    return {
        "h264_nvenc": {"preset": "p5", "rc": "vbr", "cq": "22", "spatial-aq": "1"},
        "h264_qsv": {"preset": "faster", "global_quality": "22"},
        "h264_amf": {"quality": "balanced", "rc": "cqp", "qp_i": "20", "qp_p": "22"},
        "libx264": {"preset": "veryfast", "crf": "21"},
        "h264_mf": {"rate_control": "quality", "quality": "75"},
    }.get(name, {})


def works(name: str) -> bool:
    with _lock:
        if name in _cache:
            return _cache[name]
    ok = False
    if name in av.codecs_available:
        try:
            ctx = av.CodecContext.create(name, "w")
            ctx.width, ctx.height = 256, 144
            ctx.pix_fmt = pix_fmt_for(name)
            ctx.time_base = Fraction(1, 25)
            ctx.framerate = Fraction(25)
            ctx.options = options_for(name)
            ctx.open()
            frame = av.VideoFrame.from_ndarray(np.zeros((144, 256, 3), np.uint8), format="bgr24")
            frame = frame.reformat(format=ctx.pix_fmt)
            frame.pts = 0
            ctx.encode(frame)
            ctx.encode(None)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
    with _lock:
        _cache[name] = ok
    return ok


def choose() -> str:
    global _chosen
    if _chosen is None:
        _chosen = next((n for n in ORDER if works(n)), "mpeg4")
    return _chosen


def available() -> list[dict]:
    return [{"name": n, "label": LABELS[n], "ok": works(n)} for n in ORDER]
