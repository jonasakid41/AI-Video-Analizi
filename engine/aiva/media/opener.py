"""Strateji zinciri: bir dosyayı açmanın yollarını sırayla dener, ilk çalışanı seçer.

Başarı ölçütü: en az bir video akışı var ve ilk kareler hatasız çözülebiliyor.
Seçilen strateji (OpenSpec) kaydedilir; sonraki tüm adımlar dosyayı aynı yolla açar.
"""

from __future__ import annotations

import io
import logging
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import av

from .sniff import SniffResult, find_annexb

log = logging.getLogger(__name__)
av.logging.set_level(av.logging.FATAL)

TOLERANT = {"err_detect": "ignore_err", "fflags": "+genpts+discardcorrupt"}


@dataclass
class OpenSpec:
    name: str                          # kullanıcıya gösterilen strateji adı
    format: str | None = None
    offset: int = 0
    options: dict[str, str] = field(default_factory=dict)
    raw: bool = False                  # ham elementer akış (zaman damgası üretilecek)
    fps: float | None = None           # ham akışlarda varsayılan fps

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OpenSpec":
        return cls(**d)


class OffsetReader(io.RawIOBase):
    """Dosyayı belirtilen ofsetten başlıyormuş gibi gösterir (tescilli başlık atlama)."""

    def __init__(self, path: Path, offset: int):
        self._f = open(path, "rb")
        self._off = offset
        self._f.seek(offset)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        return self._f.readinto(b)

    def seek(self, pos: int, whence: int = 0) -> int:
        if whence == 0:
            self._f.seek(self._off + pos)
        else:
            self._f.seek(pos, whence)
        return self._f.tell() - self._off

    def tell(self) -> int:
        return self._f.tell() - self._off

    def close(self) -> None:
        self._f.close()
        super().close()


def open_container(path: Path, spec: OpenSpec) -> av.container.InputContainer:
    opts = dict(spec.options)
    if spec.raw and spec.fps:
        opts.setdefault("framerate", _fps_str(spec.fps))
    src: Any = OffsetReader(path, spec.offset) if spec.offset else str(path)
    return av.open(src, mode="r", format=spec.format, options=opts, timeout=None)


def _fps_str(fps: float) -> str:
    return str(Fraction(fps).limit_denominator(1001))


@dataclass
class Attempt:
    spec: OpenSpec
    ok: bool
    frames: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {"strateji": self.spec.name, "basarili": self.ok, "cozulen_kare": self.frames, "hata": self.error}


def candidate_specs(path: Path, s: SniffResult) -> list[OpenSpec]:
    specs: list[OpenSpec] = []
    raw = s.kind in ("h264", "hevc")
    if not raw and s.offset == 0:
        specs.append(OpenSpec("Doğrudan açma"))
    if s.format_hint:
        specs.append(OpenSpec(f"Demuxer zorlama ({s.format_hint})", format=s.format_hint,
                              offset=s.offset, options=dict(TOLERANT), raw=raw, fps=25.0 if raw else None))
    if s.kind == "mp4" and "MPEG-PS" in " ".join(s.notes):
        specs.append(OpenSpec("MP4 içinde MPEG-PS (Hikvision)", format="mpeg", options=dict(TOLERANT)))
    if not raw:
        specs.append(OpenSpec("Hata toleranslı açma", options=dict(TOLERANT)))
    # Son çare: ilk birkaç MB içinde ham H.264/H.265 başlangıcı ara
    with path.open("rb") as f:
        scan = f.read(4 * 1024 * 1024)
    ab = find_annexb(scan)
    if ab is not None:
        off, codec = ab
        specs.append(OpenSpec(f"Başlık atlama + ham {codec.upper()} ({off} bayt)", format=codec, offset=off,
                              options=dict(TOLERANT), raw=True, fps=25.0))
    # Tekrarları ayıkla
    seen: set[tuple] = set()
    uniq = []
    for sp in specs:
        key = (sp.format, sp.offset, tuple(sorted(sp.options.items())), sp.raw)
        if key not in seen:
            seen.add(key)
            uniq.append(sp)
    return uniq


def try_spec(path: Path, spec: OpenSpec, min_frames: int = 3, max_frames: int = 30) -> Attempt:
    try:
        with open_container(path, spec) as c:
            if not c.streams.video:
                return Attempt(spec, False, error="Video akışı bulunamadı")
            vs = c.streams.video[0]
            # Kare iş parçacıklı çözücü erken kapatılınca kilitlenebiliyor; doğrulamada kapalı
            vs.thread_type = "SLICE"
            frames = 0
            errors = 0
            for packet in c.demux(vs):
                try:
                    for _ in packet.decode():
                        frames += 1
                except av.error.FFmpegError:
                    errors += 1
                    if errors > 50:
                        break
                if frames >= max_frames:
                    break
            if frames >= min_frames:
                if spec.raw:
                    spec.fps = _guess_raw_fps(vs) or spec.fps
                return Attempt(spec, True, frames)
            return Attempt(spec, False, frames, f"Yalnızca {frames} kare çözülebildi")
    except (av.error.FFmpegError, OSError, ValueError) as e:
        return Attempt(spec, False, error=str(e))


def _guess_raw_fps(vs) -> float | None:
    # SPS/VUI zamanlama bilgisi varsa çözücü bunu codec_context.framerate'e yazar
    for rate in (vs.codec_context.framerate, vs.average_rate, vs.guessed_rate):
        if rate and 1 <= float(rate) <= 120:
            return float(rate)
    return None


def choose(path: Path, s: SniffResult) -> tuple[OpenSpec | None, list[Attempt]]:
    attempts: list[Attempt] = []
    for spec in candidate_specs(path, s):
        a = try_spec(path, spec)
        attempts.append(a)
        if a.ok:
            return spec, attempts
    return None, attempts


def probe(path: Path, spec: OpenSpec) -> dict[str, Any]:
    """Medya bilgisi (ffprobe benzeri)."""
    with open_container(path, spec) as c:
        info: dict[str, Any] = {
            "format": c.format.name,
            "format_long": c.format.long_name,
            "duration": (c.duration / av.time_base) if c.duration else None,
            "bit_rate": c.bit_rate,
            "metadata": dict(c.metadata),
            "streams": [],
        }
        for st in c.streams:
            d: dict[str, Any] = {
                "index": st.index, "type": st.type,
                "codec": st.codec_context.name if st.codec_context else None,
                "time_base": str(st.time_base) if st.time_base else None,
                "duration": float(st.duration * st.time_base) if st.duration and st.time_base else None,
                "frames": st.frames or None,
                "metadata": dict(st.metadata),
            }
            if st.type == "video":
                cc = st.codec_context
                rate = st.average_rate or st.guessed_rate or st.base_rate
                d.update({
                    "width": cc.width, "height": cc.height, "pix_fmt": cc.pix_fmt,
                    "fps": spec.fps if spec.raw and spec.fps else (float(rate) if rate else None),
                    "profile": cc.profile, "has_b_frames": cc.has_b_frames,
                })
            elif st.type == "audio":
                cc = st.codec_context
                d.update({"sample_rate": cc.sample_rate, "channels": cc.channels})
            info["streams"].append(d)
    return info


def video_stream_info(info: dict) -> dict:
    for s in info.get("streams", []):
        if s["type"] == "video":
            return s
    return {}
