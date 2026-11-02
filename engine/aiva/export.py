"""Dışa aktarma: kare (PNG + JSON), kesit (kayıpsız orijinal + saatli çalışma kopyası)."""

from __future__ import annotations

import hashlib
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from . import evidence, history, jobs, paths
from .media import encoders, frames
from .util import dumps, imwrite


def _rel(p: Path) -> str:
    return p.resolve().relative_to(paths.data_dir().resolve()).as_posix()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frame(evidence_id: int, t: float) -> dict:
    ev = evidence.require(evidence_id)
    src = evidence.evidence_file(ev)
    got = frames.frame_at(src, t) if src else None
    if got is None:
        raise ValueError("Kare alınamadı")
    ft, img = got
    m = evidence.get_mapping(evidence_id)
    out_dir = paths.exports_dir(ev["case_id"]) / "kareler"
    base = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_v{evidence_id}_{int(ft * 1000)}"
    png = base.with_suffix(".png")
    imwrite(png, img)
    cam, real = m.to_camera(ft), m.to_real(ft)
    meta = {"video": ev["original_name"], "video_sha256": ev["sha256"], "medya_zamani_sn": round(ft, 4),
            "kamera_saati": cam.isoformat() if cam else None, "gercek_saat": real.isoformat() if real else None,
            "cozunurluk": [int(img.shape[1]), int(img.shape[0])], "png_sha256": _sha(png)}
    base.with_suffix(".json").write_text(dumps(meta), encoding="utf-8")
    history.log("kare_disa_aktarildi", ev["case_id"], evidence_id, t=round(ft, 3))
    return {"image": _rel(png), "meta": _rel(base.with_suffix(".json")), "t": ft}


def _overlay(img: np.ndarray, lines: list[str]) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(img)
    W, _H = pil.size
    size = max(14, W // 45)
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(pil, "RGBA")
    y = 6
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=font)
        d.rectangle([4, y - 2, bb[2] + 14, y + bb[3] + 4], fill=(0, 0, 0, 160))
        d.text((9, y), ln, font=font, fill=(255, 255, 255, 255))
        y += bb[3] + 8
    return np.array(pil)


@jobs.register("export_clip")
def export_clip_job(ctx: jobs.JobContext, params: dict) -> dict:
    eid = params["evidence_id"]
    t0, t1 = float(params["t0"]), float(params["t1"])
    if t1 <= t0:
        raise ValueError("Bitiş, başlangıçtan sonra olmalı")
    ev = evidence.require(eid)
    src = evidence.evidence_file(ev)
    if src is None:
        raise ValueError("Video henüz dönüştürülmedi")
    m = evidence.get_mapping(eid)
    out_dir = paths.exports_dir(ev["case_id"]) / "kesitler"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_v{eid}_{int(t0)}-{int(t1)}"

    # 1) Kayıpsız orijinal kesit (anahtar kareden başlar)
    orig = base.with_name(base.name + "_orijinal.mkv")
    with av.open(str(src)) as ic, av.open(str(orig), "w", format="matroska") as out:
        vin = ic.streams.video[0]
        ins = [vin] + list(ic.streams.audio[:1])
        omap = {s.index: out.add_stream_from_template(s) for s in ins}
        ic.seek(int(t0 / vin.time_base), stream=vin, backward=True, any_frame=False)
        started = False
        for pkt in ic.demux(*ins):
            if pkt.size == 0 or pkt.pts is None:
                continue
            tt = float(pkt.pts * pkt.time_base)
            if pkt.stream is vin:
                if not started and not pkt.is_keyframe:
                    continue
                started = True
                if tt > t1:
                    break
            elif not started:
                continue
            pkt.stream = omap[pkt.stream.index]
            try:
                out.mux(pkt)
            except (ValueError, av.error.FFmpegError):
                pass
    ctx.progress(0.3, "Saatli kopya hazırlanıyor")

    # 2) Düzeltilmiş saat yazılı çalışma kopyası
    burned = base.with_name(base.name + "_saatli.mp4")
    enc = encoders.choose()
    with frames.decoding(src) as (ic, vs):
        fps = float(vs.average_rate or 25)
        ic.seek(int(t0 / vs.time_base), stream=vs, backward=True, any_frame=False)
        with av.open(str(burned), "w", format="mp4", options={"movflags": "+faststart"}) as out:
            os_ = out.add_stream(enc, rate=Fraction(fps).limit_denominator(1001))
            os_.width = (ev["width"] or 640) // 2 * 2
            os_.height = (ev["height"] or 360) // 2 * 2
            os_.pix_fmt = encoders.pix_fmt_for(enc)
            os_.options = encoders.options_for(enc)
            n = 0
            for fr in ic.decode(vs):
                ft = float(fr.time or 0)
                if ft < t0:
                    continue
                if ft > t1:
                    break
                real, cam = m.to_real(ft), m.to_camera(ft)
                lines = [f"Gerçek saat: {real:%d.%m.%Y %H:%M:%S}" if real else f"Video zamanı: {ft:.2f} sn"]
                if cam and real and abs((real - cam).total_seconds()) >= 1:
                    lines.append(f"Kamera saati: {cam:%d.%m.%Y %H:%M:%S}")
                lines.append(f"{ev['camera'] or ev['original_name']}")
                img = _overlay(fr.to_ndarray(format="rgb24"), lines)
                f2 = av.VideoFrame.from_ndarray(img, format="rgb24").reformat(width=os_.width, height=os_.height,
                                                                               format=os_.pix_fmt)
                f2.pts = n
                n += 1
                for p in os_.encode(f2):
                    out.mux(p)
                ctx.progress(0.3 + 0.65 * min(1.0, (ft - t0) / (t1 - t0)), "Saatli kopya hazırlanıyor")
            for p in os_.encode(None):
                out.mux(p)
    meta = {"video": ev["original_name"], "video_sha256": ev["sha256"], "baslangic_sn": t0, "bitis_sn": t1,
            "gercek_baslangic": (m.to_real(t0).isoformat() if m.to_real(t0) else None),
            "orijinal_kesit": {"dosya": orig.name, "sha256": _sha(orig), "not": "Yeniden kodlanmadı; anahtar kareden başlar"},
            "saatli_kopya": {"dosya": burned.name, "sha256": _sha(burned), "not": "Çalışma kopyası; saat yazısı eklenmiştir"}}
    base.with_suffix(".json").write_text(dumps(meta), encoding="utf-8")
    history.log("kesit_disa_aktarildi", ev["case_id"], eid, t0=t0, t1=t1)
    return {"original": _rel(orig), "burned": _rel(burned), "meta": _rel(base.with_suffix(".json")),
            "folder": str(out_dir)}
