"""Dönüştürme: kayıpsız delil kopyası (evidence.mkv) ve çalışma kopyası (proxy.mp4).

- evidence.mkv: paketler yeniden kodlanmadan kopyalanır; zaman ekseni 0'dan başlar.
  Ham akışlarda zaman damgası fps'ten üretilir. Zaman sıçramaları "kayıt boşluğu" olarak raporlanır.
- proxy.mp4: tarayıcıda (WebView2) oynatılabilir H.264. Kaynak uygunsa yalnızca yeniden paketlenir,
  değilse donanım kodlayıcıyla (NVENC vb.) kodlanır. Zaman damgaları korunur (t_m aynı kalır).
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Callable

import av

from . import encoders
from .frames import decoding
from .opener import OpenSpec, open_container

log = logging.getLogger(__name__)
Progress = Callable[[float, str | None], None]

GAP_MIN_SECONDS = 2.0
BROWSER_AUDIO = {"aac", "mp3"}


def _noop(_v: float, _m: str | None = None) -> None:
    pass


# Kayıpsız kopya için kap sırası: MKV çoğu codec'i taşır; taşıyamazsa FFmpeg'in NUT kabı
EVIDENCE_CONTAINERS = [("matroska", ".mkv"), ("nut", ".nut")]


class UnsupportedInContainer(ValueError):
    pass


def remux_evidence(src: Path, spec: OpenSpec, dst_base: Path, progress: Progress = _noop) -> dict:
    """dst_base uzantısız hedef yoldur (ör. .../evidence). Oluşan dosya stats["path"] içindedir."""
    last_err: Exception | None = None
    for fmt, ext in EVIDENCE_CONTAINERS:
        dst = dst_base.with_suffix(ext)
        try:
            stats = _remux_into(src, spec, dst, fmt, progress)
            stats["path"] = str(dst)
            stats["container"] = fmt
            return stats
        except UnsupportedInContainer as e:
            last_err = e
            dst.unlink(missing_ok=True)
    raise ValueError(f"Kayıpsız kopya oluşturulamadı: {last_err}")


def _raw_presentation_ranks(src: Path, spec: OpenSpec) -> list[int | None] | None:
    """Ham akışta B-frame varsa paketlerin gösterim sırasını çözücüden öğrenir.

    Her pakete çözme sırası numarası pts olarak verilir; çözücü kareleri gösterim sırasında
    bu etiketlerle döndürür. Sıralama zaten doğruysa None döner.
    """
    order: list[int] = []
    n = 0
    with open_container(src, spec) as ic:
        vin = ic.streams.video[0]
        vin.thread_type = "SLICE"
        for pkt in ic.demux(vin):
            if pkt.size:
                pkt.pts = n
                pkt.dts = None
                n += 1
            try:
                for fr in pkt.decode():
                    if fr.pts is not None:
                        order.append(int(fr.pts))
            except av.error.FFmpegError:
                pass
    if order == sorted(order):
        return None
    rank: dict[int, int] = {j: k for k, j in enumerate(order)}
    return [rank.get(j) for j in range(n)]


def _remux_into(src: Path, spec: OpenSpec, dst: Path, fmt: str, progress: Progress) -> dict:
    size = max(1, src.stat().st_size)
    stats = {"packets": 0, "dropped": 0, "gaps": [], "video_codec": None, "audio": False}
    ranks = _raw_presentation_ranks(src, spec) if spec.raw else None
    delay = max((j - r for j, r in enumerate(ranks) if r is not None), default=0) if ranks else 0
    with open_container(src, spec) as ic:
        vin = ic.streams.video[0]
        ins = [vin] + list(ic.streams.audio[:1])
        with av.open(str(dst), "w", format=fmt) as out:
            omap = {}
            for s in ins:
                try:
                    omap[s.index] = out.add_stream_from_template(s)
                except (ValueError, av.error.FFmpegError) as e:
                    if s is vin:
                        raise UnsupportedInContainer(str(e)) from e
            stats["audio"] = len(omap) > 1
            stats["video_codec"] = vin.codec_context.name
            stats["b_frames_reordered"] = bool(ranks)
            fps = spec.fps or float(vin.average_rate or vin.guessed_rate or 25)
            frame_dur = 1.0 / fps
            raw_counter = 0
            # Ham akışın kendi zaman ekseni yok; 0'dan üretilir, kaydırma gerekmez
            shift: float | None = 0.0 if spec.raw else None
            last_dts: dict[int, int] = {}
            last_vt: float | None = None
            for pkt in ic.demux(*ins):
                if pkt.size == 0:
                    continue
                st = pkt.stream
                if st.index not in omap:
                    continue
                tb = pkt.time_base or st.time_base
                if spec.raw and st is vin:
                    j = raw_counter
                    raw_counter += 1
                    r = ranks[j] if ranks and j < len(ranks) else j
                    if r is None:
                        stats["dropped"] += 1
                        continue
                    tick = frame_dur / tb
                    pkt.pts = int(round((r + delay) * tick))
                    pkt.dts = int(round(j * tick))
                if pkt.pts is None and pkt.dts is None:
                    stats["dropped"] += 1
                    continue
                if pkt.pts is None:
                    pkt.pts = pkt.dts
                # dts boşsa (MKV'de B-frame'li akışlar) muxer hesaplar; doldurulmaz
                if shift is None:
                    if st is not vin:
                        continue  # ilk video paketinden önceki ses atlanır
                    shift = float(pkt.pts * tb)
                off = int(round(shift / tb))
                if off:
                    pkt.pts -= off
                    if pkt.dts is not None:
                        pkt.dts -= off
                if st is not vin and pkt.pts < 0:
                    continue
                if pkt.dts is not None:
                    prev = last_dts.get(st.index)
                    if prev is not None and pkt.dts <= prev:
                        stats["dropped"] += 1
                        continue
                    last_dts[st.index] = pkt.dts
                if st is vin:
                    # Kayıt boşluğu: ardışık video paketleri arasında beklenmedik zaman sıçraması
                    vt = float((pkt.dts if pkt.dts is not None else pkt.pts) * tb)
                    if last_vt is not None and vt - last_vt > max(GAP_MIN_SECONDS, 10 * frame_dur):
                        stats["gaps"].append([round(last_vt, 3), round(vt, 3)])
                    last_vt = vt if last_vt is None else max(last_vt, vt)
                    if pkt.is_keyframe:
                        stats.setdefault("_keys", []).append(float(pkt.pts * tb))
                pkt.stream = omap[st.index]
                try:
                    out.mux(pkt)
                    stats["packets"] += 1
                except (ValueError, av.error.FFmpegError):
                    stats["dropped"] += 1
                if stats["packets"] % 500 == 0 and pkt.pos and pkt.pos > 0:
                    progress(min(0.99, pkt.pos / size), None)
    keys = stats.pop("_keys", [])
    stats["keyframe_interval"] = round((keys[-1] - keys[0]) / (len(keys) - 1), 3) if len(keys) > 1 else None
    if stats["packets"] == 0:
        raise ValueError("Hiç video paketi kopyalanamadı")
    return stats


def _even(x: float) -> int:
    v = int(round(x))
    return v - (v % 2)


def proxy_size(w: int, h: int, max_h: int = 1080) -> tuple[int, int]:
    if h > max_h:
        w, h = w * max_h / h, max_h
    return max(2, _even(w)), max(2, _even(h))


def can_remux_proxy(vinfo: dict) -> bool:
    return (vinfo.get("codec") == "h264"
            and vinfo.get("pix_fmt") in ("yuv420p", "yuvj420p")
            and (vinfo.get("height") or 9999) <= 1080
            and not vinfo.get("has_b_frames"))


def _remux_proxy(src: Path, dst: Path, progress: Progress) -> dict:
    with av.open(str(src)) as ic, av.open(str(dst), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        vin = ic.streams.video[0]
        ins = [vin]
        omap = {vin.index: out.add_stream_from_template(vin)}
        a = ic.streams.audio[0] if ic.streams.audio else None
        if a is not None and a.codec_context.name in BROWSER_AUDIO:
            omap[a.index] = out.add_stream_from_template(a)
            ins.append(a)
        dur = float(ic.duration / av.time_base) if ic.duration else None
        n = 0
        for pkt in ic.demux(*ins):
            if pkt.size == 0 or pkt.dts is None:
                continue
            t = float(pkt.dts * pkt.time_base)
            pkt.stream = omap[pkt.stream.index]
            out.mux(pkt)
            n += 1
            if dur and n % 300 == 0:
                progress(min(0.99, t / dur), None)
    return {"mode": "yeniden_paketleme", "encoder": None}


def _transcode_proxy(src: Path, dst: Path, vinfo: dict, progress: Progress, max_h: int) -> dict:
    enc = encoders.choose()
    pix = encoders.pix_fmt_for(enc)
    w, h = proxy_size(vinfo["width"], vinfo["height"], max_h)
    fps = float(vinfo.get("fps") or 25)
    with decoding(src) as (ic, vin):
        dur = float(ic.duration / av.time_base) if ic.duration else None
        with av.open(str(dst), "w", format="mp4", options={"movflags": "+faststart"}) as out:
            ost = out.add_stream(enc, rate=Fraction(fps).limit_denominator(1001))
            ost.width, ost.height, ost.pix_fmt = w, h, pix
            ost.codec_context.time_base = vin.time_base
            ost.codec_context.gop_size = max(1, int(round(fps)))
            ost.codec_context.max_b_frames = 0
            if enc == "h264_nvenc":
                ost.codec_context.bit_rate = 0
            ost.options = encoders.options_for(enc)
            last_pts = None
            n = 0
            for frame in ic.decode(vin):
                if frame.pts is None or (last_pts is not None and frame.pts <= last_pts):
                    continue
                last_pts = frame.pts
                f2 = frame.reformat(width=w, height=h, format=pix, interpolation="BILINEAR")
                f2.pts = frame.pts
                f2.time_base = vin.time_base
                for pkt in ost.encode(f2):
                    out.mux(pkt)
                n += 1
                if dur and n % 100 == 0:
                    progress(min(0.99, float(frame.time or 0) / dur), None)
            for pkt in ost.encode(None):
                out.mux(pkt)
    return {"mode": "kodlama", "encoder": enc, "encoder_label": encoders.LABELS.get(enc, enc),
            "size": [w, h]}


def build_proxy(src: Path, dst: Path, vinfo: dict, progress: Progress = _noop, max_h: int = 1080) -> dict:
    tmp = dst.with_suffix(".tmp.mp4")
    try:
        if can_remux_proxy(vinfo):
            try:
                info = _remux_proxy(src, tmp, progress)
            except (ValueError, av.error.FFmpegError) as e:
                log.warning("Proxy yeniden paketleme başarısız, kodlanacak: %s", e)
                info = _transcode_proxy(src, tmp, vinfo, progress, max_h)
        else:
            info = _transcode_proxy(src, tmp, vinfo, progress, max_h)
        tmp.replace(dst)
        return info
    finally:
        if tmp.exists():
            tmp.unlink()


def verify_decode(path: Path, max_seconds: float | None = None) -> dict:
    """Dosyayı baştan sona (ya da max_seconds kadar) çözer; kare sayısı ve hataları döner."""
    frames = 0
    errors = 0
    last_t = 0.0
    with decoding(path) as (c, vs):
        for pkt in c.demux(vs):
            try:
                for fr in pkt.decode():
                    frames += 1
                    if fr.time is not None:
                        last_t = float(fr.time)
            except av.error.FFmpegError:
                errors += 1
            if max_seconds and last_t > max_seconds:
                break
    return {"frames": frames, "errors": errors, "last_time": last_t}
