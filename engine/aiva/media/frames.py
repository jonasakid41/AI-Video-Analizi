"""Kare erişimi: güvenli çözme, belirli ana gitme, örnekleme, önizleme şeritleri."""

from __future__ import annotations

import math
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import av
import cv2
import numpy as np

from ..util import imwrite
from .opener import OpenSpec, open_container


@contextmanager
def decoding(path: Path, spec: OpenSpec | None = None, threads: bool = True, keyframes_only: bool = False):
    """Video çözme bağlamı. Çıkışta çözücü boşaltılır (kare iş parçacıklı çözücü
    boşaltılmadan kapatılırsa kilitlenebiliyor)."""
    c = open_container(path, spec) if spec else av.open(str(path))
    if not c.streams.video:
        c.close()
        raise ValueError("Video akışı yok")
    vs = c.streams.video[0]
    vs.thread_type = "AUTO" if threads else "SLICE"
    if keyframes_only:
        vs.codec_context.skip_frame = "NONKEY"
    try:
        yield c, vs
    finally:
        try:
            for _ in vs.codec_context.decode(None):
                pass
        except Exception:  # noqa: BLE001
            pass
        c.close()


def frame_time(frame: av.VideoFrame) -> float | None:
    return float(frame.time) if frame.time is not None else None


def frame_at(path: Path, t: float, tolerance: float | None = None) -> tuple[float, np.ndarray] | None:
    """t saniyesindeki (ya da hemen sonraki) kareyi BGR olarak döner."""
    with decoding(path, threads=False) as (c, vs):
        fps = float(vs.average_rate or vs.guessed_rate or 25)
        half = tolerance if tolerance is not None else 0.5 / fps
        target = max(0.0, t)
        c.seek(int(target / vs.time_base), stream=vs, backward=True, any_frame=False)
        prev: tuple[float, av.VideoFrame] | None = None
        for frame in c.decode(vs):
            ft = frame_time(frame)
            if ft is None:
                continue
            if ft + half >= target:
                if prev and abs(prev[0] - target) <= abs(ft - target):
                    return prev[0], prev[1].to_ndarray(format="bgr24")
                return ft, frame.to_ndarray(format="bgr24")
            prev = (ft, frame)
        return (prev[0], prev[1].to_ndarray(format="bgr24")) if prev else None


def iter_frames(path: Path, sample_fps: float, t0: float | None = None, t1: float | None = None,
                keyframes_only: bool = False, cancel=None) -> Iterator[tuple[float, av.VideoFrame]]:
    """[t0, t1] aralığında yaklaşık sample_fps hızında kare üretir."""
    step = 1.0 / sample_fps if sample_fps > 0 else 0.0
    with decoding(path, keyframes_only=keyframes_only) as (c, vs):
        if t0 and t0 > 0:
            c.seek(int(t0 / vs.time_base), stream=vs, backward=True, any_frame=False)
        next_t = t0 or 0.0
        for frame in c.decode(vs):
            ft = frame_time(frame)
            if ft is None:
                continue
            if t0 is not None and ft < t0:
                continue
            if t1 is not None and ft > t1:
                break
            if ft + 1e-6 >= next_t:
                if cancel:
                    cancel()
                yield ft, frame
                next_t = ft + step if step else ft


def keyframe_interval(path: Path, max_packets: int = 2000) -> float | None:
    """Ortalama anahtar kare aralığı (sn)."""
    with av.open(str(path)) as c:
        vs = c.streams.video[0]
        keys: list[float] = []
        for i, pkt in enumerate(c.demux(vs)):
            if i >= max_packets:
                break
            if pkt.is_keyframe and pkt.pts is not None:
                keys.append(float(pkt.pts * pkt.time_base))
        if len(keys) < 2:
            return None
        return (keys[-1] - keys[0]) / (len(keys) - 1)


def resize_to_width(img: np.ndarray, width: int) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img
    nh = int(round(h * width / w))
    return cv2.resize(img, (width, nh), interpolation=cv2.INTER_AREA)


def make_sprite(path: Path, duration: float, dest: Path, count: int = 60, tile_w: int = 160,
                cols: int = 10) -> dict:
    """Zaman çizelgesi önizleme şeridi (JPEG ızgara) üretir."""
    count = max(1, min(count, int(math.ceil(duration)) or 1))
    times = [duration * (i + 0.5) / count for i in range(count)]
    tiles: list[np.ndarray] = []
    tile_h = None
    with decoding(path, threads=False) as (c, vs):
        for t in times:
            c.seek(int(t / vs.time_base), stream=vs, backward=True, any_frame=False)
            img = None
            for frame in c.decode(vs):
                img = frame.to_ndarray(format="bgr24")
                break
            if img is None:
                img = np.zeros((90, tile_w, 3), np.uint8) if tile_h is None else np.zeros((tile_h, tile_w, 3), np.uint8)
            img = cv2.resize(img, (tile_w, int(round(img.shape[0] * tile_w / img.shape[1]))), interpolation=cv2.INTER_AREA)
            if tile_h is None:
                tile_h = img.shape[0]
            img = cv2.resize(img, (tile_w, tile_h))
            tiles.append(img)
    rows = int(math.ceil(len(tiles) / cols))
    sheet = np.zeros((rows * tile_h, cols * tile_w, 3), np.uint8)  # type: ignore[operator]
    for i, tile in enumerate(tiles):
        r, col = divmod(i, cols)
        sheet[r * tile_h:(r + 1) * tile_h, col * tile_w:(col + 1) * tile_w] = tile  # type: ignore[operator]
    imwrite(dest, sheet, 80)
    return {"times": times, "tile_w": tile_w, "tile_h": tile_h, "cols": cols, "count": len(tiles)}


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG kodlanamadı")
    return buf.tobytes()
