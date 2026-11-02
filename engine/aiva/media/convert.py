"""Dönüştürme: kayıpsız delil kopyası (evidence.mkv) ve çalışma kopyası (proxy.mp4).

- evidence.mkv: paketler yeniden kodlanmadan kopyalanır; zaman ekseni 0'dan başlar.
  Ham akışlarda zaman damgası fps'ten üretilir. Zaman sıçramaları "kayıt boşluğu" olarak raporlanır.
- proxy.mp4: tarayıcıda (WebView2) oynatılabilir H.264. Kaynak uygunsa yalnızca yeniden paketlenir,
  değilse donanım kodlayıcıyla (NVENC vb.) kodlanır. Zaman damgaları korunur (t_m aynı kalır).
"""

from __future__ import annotations

import logging
import time
from fractions import Fraction
from pathlib import Path
from typing import Callable

import av
from av.codec.codec import UnknownCodecError

from . import encoders
from .frames import decoding
from .opener import OpenSpec, open_container

log = logging.getLogger(__name__)
Progress = Callable[[float, str | None], None]

GAP_MIN_SECONDS = 2.0
BROWSER_AUDIO = {"aac", "mp3"}


def _noop(_v: float, _m: str | None = None) -> None:
    pass


# Kayıpsız kopya planları: önce ses + video (MKV çoğu kodeği taşır; taşıyamazsa FFmpeg'in NUT kabı),
# olmazsa yalnızca video. G.711 gibi sesleri MKV taşıyamaz; parametreleri bozuk bir ses akışı
# (ör. örnekleme hızı 0) kabın başlığını yazdırmaz ve önceden hiçbir paket kopyalanamıyordu.
EVIDENCE_PLANS = [("matroska", ".mkv", True), ("nut", ".nut", True), ("matroska", ".mkv", False),
                  ("nut", ".nut", False)]
# Bu kadar geri giden zaman damgası kamera saatinin geri alınması / sayacın sıfırlanması sayılır
CLOCK_RESET_SECONDS = 2.0
WRAP_33 = 1 << 33  # MPEG 90 kHz zaman damgası aralığı


class UnsupportedInContainer(ValueError):
    pass


def copy_stream(out: av.container.OutputContainer, s: av.stream.Stream) -> av.stream.Stream:
    """Akışı yeniden kodlamadan kopyalamak için çıkış akışı. PyAV şablondaki çözücünün adını kodlayıcı
    olarak arar; adlar farklıysa (ör. AV1 → "libdav1d") UnknownCodecError (ValueError) verir ve
    yüksek çözünürlüklü AV1 videolar "dönüştürülemedi" oluyordu. O durumda kodek bilgisi doğrudan kopyalanır."""
    try:
        return out.add_stream_from_template(s)
    except UnknownCodecError:
        return out.add_stream_from_template(s, opaque=True)


def remux_evidence(src: Path, spec: OpenSpec, dst_base: Path, progress: Progress = _noop) -> dict:
    """dst_base uzantısız hedef yoldur (ör. .../evidence). Oluşan dosya stats["path"] içindedir."""
    last_err: Exception | None = None
    for fmt, ext, audio in EVIDENCE_PLANS:
        dst = dst_base.with_suffix(ext)
        try:
            stats = _remux_into(src, spec, dst, fmt, progress, audio)
            stats["path"] = str(dst)
            stats["container"] = fmt
            return stats
        except UnsupportedInContainer as e:
            log.info("Kayıpsız kopya planı geçildi (%s, ses=%s): %s", fmt, audio, e)
            last_err = e
            dst.unlink(missing_ok=True)
    raise ValueError(f"Kayıpsız kopya oluşturulamadı: {last_err}")


PROBE_PACKETS = 600


def _scan_order(src: Path, spec: OpenSpec, limit: int | None, progress: Progress) -> tuple[list[int], int]:
    size = max(1, src.stat().st_size)
    order: list[int] = []
    n = 0
    last = time.monotonic()
    with open_container(src, spec) as ic:
        vin = ic.streams.video[0]
        vin.thread_type = "SLICE"  # erken çıkışta kilitlenmesin diye kare iş parçacığı yok
        for pkt in ic.demux(vin):
            if pkt.size:
                if limit is not None and n >= limit:
                    break
                pkt.pts = n
                pkt.dts = None
                n += 1
            try:
                for fr in pkt.decode():
                    if fr.pts is not None:
                        order.append(int(fr.pts))
            except av.error.FFmpegError:
                pass
            if limit is None and time.monotonic() - last > 0.3:
                last = time.monotonic()
                progress(min(0.99, (pkt.pos or 0) / size), "Kare sırası çözülüyor (B-frame)")
    return order, n


def _raw_presentation_ranks(src: Path, spec: OpenSpec, progress: Progress = _noop) -> list[int | None] | None:
    """Ham akışta B-frame varsa paketlerin gösterim sırasını çözücüden öğrenir.

    Her pakete çözme sırası numarası pts olarak verilir; çözücü kareleri gösterim sırasında
    bu etiketlerle döndürür. Önce yalnızca ilk PROBE_PACKETS paket çözülür: sıralama bozulmuyorsa
    (CCTV akışlarının çoğu B-frame kullanmaz) dosyanın tamamı çözülmez. Sıralama doğruysa None döner.
    """
    order, n = _scan_order(src, spec, PROBE_PACKETS, progress)
    if order == sorted(order):
        return None
    order, n = _scan_order(src, spec, None, progress)
    if order == sorted(order):
        return None
    rank: dict[int, int] = {j: k for k, j in enumerate(order)}
    return [rank.get(j) for j in range(n)]


def _remux_into(src: Path, spec: OpenSpec, dst: Path, fmt: str, progress: Progress, with_audio: bool = True) -> dict:
    """Paketleri yeniden kodlamadan kopyalar. Video paketleri zaman damgası yüzünden atılmaz: atılan tek bir
    P karesi sonraki kareleri bir sonraki anahtar kareye kadar bozar (kayıtta "ufak bozulmalar").
    Eksik damga bir önceki kareden tahmin edilir, eşit ya da az geri giden damga bir tık ileri alınır,
    büyük geri sıçramada (kamera saati geri alındı / sayaç sıfırlandı) zaman çizgisi kesintisiz sürdürülür."""
    size = max(1, src.stat().st_size)
    stats = {"packets": 0, "video_packets": 0, "dropped": 0, "gaps": [], "video_codec": None, "audio": False,
             "audio_codec": None, "fixed_timestamps": 0, "clock_jumps": []}
    ranks = None
    if spec.raw:
        ranks = _raw_presentation_ranks(src, spec, lambda v, m=None: progress(0.5 * v, m))
        base, span = (0.5, 0.5) if ranks else (0.0, 1.0)
    else:
        base, span = 0.0, 1.0
    last_beat = time.monotonic()
    delay = max((j - r for j, r in enumerate(ranks) if r is not None), default=0) if ranks else 0
    with open_container(src, spec) as ic:
        vin = ic.streams.video[0]
        auds = [a for a in ic.streams.audio[:1] if with_audio and (a.codec_context.sample_rate or 0) > 0]
        ins = [vin] + auds
        with av.open(str(dst), "w", format=fmt) as out:
            omap = {}
            for s in ins:
                try:
                    omap[s.index] = copy_stream(out, s)
                except (ValueError, av.error.FFmpegError) as e:
                    raise UnsupportedInContainer(f"{s.type} ({s.codec_context.name}): {e}") from e
            try:
                out.start_encoding()  # başlık burada yazılır; olmazsa her paket hata verirdi
            except (ValueError, av.error.FFmpegError) as e:
                raise UnsupportedInContainer(f"kap başlığı yazılamadı: {e}") from e
            stats["audio"] = len(omap) > 1
            stats["audio_codec"] = auds[0].codec_context.name if auds else None
            stats["video_codec"] = vin.codec_context.name
            stats["b_frames_reordered"] = bool(ranks)
            fps = spec.fps or float(vin.average_rate or vin.guessed_rate or 25)
            frame_dur = 1.0 / fps
            raw_counter = 0
            # Ham akışın kendi zaman ekseni yok; 0'dan üretilir, kaydırma gerekmez
            shift: float | None = 0.0 if spec.raw else None
            adjust = 0.0  # sn: geri sıçramalardan sonra zaman çizgisini sürdürmek için eklenen
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
                step = max(1, int(round(frame_dur / tb)))
                if pkt.pts is None and pkt.dts is None:
                    if st is not vin or vin.index not in last_dts:
                        stats["dropped"] += 1  # ses ya da ilk paket: tahmin için dayanak yok
                        continue
                    # Damgasız video paketi: bir önceki karenin ardına konur (atılırsa görüntü bozulur)
                    pkt.dts = pkt.pts = last_dts[vin.index] + step
                    stats["fixed_timestamps"] += 1
                else:
                    if pkt.pts is None:
                        pkt.pts = pkt.dts
                    # dts boşsa (MKV'de B-frame'li akışlar) muxer hesaplar; doldurulmaz
                    if shift is None:
                        if st is not vin:
                            continue  # ilk video paketinden önceki ses atlanır
                        shift = float(pkt.pts * tb)
                    off = int(round((shift - adjust) / tb))
                    if off:
                        pkt.pts -= off
                        if pkt.dts is not None:
                            pkt.dts -= off
                    if st is not vin and pkt.pts < 0:
                        continue
                    prev = last_dts.get(st.index)
                    if (pkt.dts is not None and prev is not None and tb == Fraction(1, 90000)
                            and pkt.dts - prev > WRAP_33 // 2):
                        # MPEG-PS/TS damgaları 33 bittir: geri giden saat sayacı taşırıp ~26 saatlik sahte
                        # bir "boşluk" gibi görünür; gerçekte geri sıçramadır (zaman çizgisini video yönetir)
                        pkt.pts -= WRAP_33
                        pkt.dts -= WRAP_33
                        if st is vin:
                            adjust -= float(WRAP_33 * tb)
                    if pkt.dts is not None and prev is not None and pkt.dts <= prev:
                        if st is not vin:
                            stats["dropped"] += 1  # geri giden ses paketi atlanır (görüntüyü etkilemez)
                            continue
                        back = float((prev - pkt.dts) * tb)
                        if back >= CLOCK_RESET_SECONDS:
                            # Kamera saati geri alındı ya da sayaç sıfırlandı: zaman çizgisi kesintisiz sürer
                            fix = prev - pkt.dts + step
                            adjust += float(fix * tb)
                            stats["clock_jumps"].append([round(float(prev * tb), 3), round(-back, 3)])
                        else:
                            fix = prev - pkt.dts + 1  # eşit / az geri damga: bir tık ileri
                            stats["fixed_timestamps"] += 1
                        pkt.pts += fix
                        pkt.dts += fix
                if pkt.dts is not None:
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
                    stats["video_packets"] += st is vin
                except (ValueError, av.error.FFmpegError):
                    stats["dropped"] += 1
                if time.monotonic() - last_beat > 0.3:  # zamana bağlı: takılma bekçisi ilerlemeyi görür
                    last_beat = time.monotonic()
                    progress(base + span * min(0.99, (pkt.pos or 0) / size), None)
    keys = stats.pop("_keys", [])
    stats["keyframe_interval"] = round((keys[-1] - keys[0]) / (len(keys) - 1), 3) if len(keys) > 1 else None
    if stats["video_packets"] == 0:
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
        omap = {vin.index: copy_stream(out, vin)}
        a = ic.streams.audio[0] if ic.streams.audio else None
        if a is not None and a.codec_context.name in BROWSER_AUDIO:
            omap[a.index] = copy_stream(out, a)
            ins.append(a)
        dur = float(ic.duration / av.time_base) if ic.duration else None
        beat = time.monotonic()
        for pkt in ic.demux(*ins):
            if pkt.size == 0 or pkt.dts is None:
                continue
            t = float(pkt.dts * pkt.time_base)
            pkt.stream = omap[pkt.stream.index]
            out.mux(pkt)
            if time.monotonic() - beat > 0.3:
                beat = time.monotonic()
                progress(min(0.99, t / dur) if dur else 0.0, None)
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
            beat = time.monotonic()
            for frame in ic.decode(vin):
                if time.monotonic() - beat > 0.3:
                    beat = time.monotonic()
                    progress(min(0.99, float(frame.time or 0) / dur) if dur else 0.0, None)
                if frame.pts is None or (last_pts is not None and frame.pts <= last_pts):
                    continue
                last_pts = frame.pts
                f2 = frame.reformat(width=w, height=h, format=pix, interpolation="BILINEAR")
                f2.pts = frame.pts
                f2.time_base = vin.time_base
                for pkt in ost.encode(f2):
                    out.mux(pkt)
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


# --- yalıtılmış süreçte çalıştırılan görevler (aiva.worker) ------------------------------

def remux_task(src: str, spec: dict, dst_base: str, progress: Progress) -> dict:
    return remux_evidence(Path(src), OpenSpec.from_dict(spec), Path(dst_base), progress)


def proxy_task(src: str, dst: str, vinfo: dict, progress: Progress) -> dict:
    return build_proxy(Path(src), Path(dst), vinfo, progress)


def _test_crash(progress: Progress) -> None:
    """Yalnızca testler için: kodun içinde çöken bir işlemi taklit eder."""
    import os
    progress(0.1, None)
    os._exit(3)


def _test_value_error(progress: Progress) -> None:
    """Yalnızca testler için: istisnayla biten bir işlem (ör. kodek desteklenmiyor)."""
    progress(0.1, None)
    raise UnknownCodecError("libornek")


def _test_hang(progress: Progress) -> None:
    """Yalnızca testler için: ilerleme bildirmeden takılan bir işlemi taklit eder."""
    progress(0.1, None)
    time.sleep(3600)
