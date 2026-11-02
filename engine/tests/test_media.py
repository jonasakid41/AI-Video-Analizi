from __future__ import annotations

from pathlib import Path

import pytest

from aiva.media import convert, encoders, frames, opener
from aiva.media.sniff import find_annexb, sniff


def test_sniff_by_content_not_extension(corpus):
    d, files = corpus
    for name, meta in files.items():
        s = sniff(d / name)
        if meta.get("expect_fail"):
            continue
        assert s.kind == meta["expect"], f"{name}: {s.kind} != {meta['expect']}"
        if meta.get("offset"):
            assert s.offset > 0, name


def test_find_annexb_skips_junk():
    junk = bytes([7, 9, 11]) * 100
    sps = b"\x00\x00\x00\x01\x67\x42\x00\x1e"
    off, codec = find_annexb(junk + sps + b"\x00" * 16)
    assert codec == "h264"
    assert off == len(junk)


@pytest.mark.parametrize("name", [
    "h264.mp4", "mpeg2.mpg", "h264.ts", "mjpeg.avi", "raw.264", "raw.h265", "flv1.flv",
    "yanlis_uzanti.dav", "uzantisiz", "tescilli_baslik.bin", "imkh_taklit.mp4", "baslikli_ham.264",
    "kesik.ts", "hevc.mkv", "vp9.webm", "wmv2.wmv",
])
def test_full_conversion(corpus, tmp_path, name):
    d, files = corpus
    if name not in files:
        pytest.skip(f"{name} bu ortamda üretilemedi")
    src = d / name
    spec, attempts = opener.choose(src, sniff(src))
    assert spec is not None, [a.to_dict() for a in attempts]

    stats = convert.remux_evidence(src, spec, tmp_path / "evidence")
    ev = Path(stats["path"])
    assert ev.exists() and stats["dropped"] == 0
    assert stats["gaps"] == [], stats["gaps"]  # uzun GOP kayıt boşluğu sanılmamalı
    ev_dec = convert.verify_decode(ev)
    expected = 42 if files[name].get("truncated") else 72
    assert abs(ev_dec["frames"] - expected) <= 1, ev_dec

    info = opener.probe(ev, opener.OpenSpec("evidence"))
    v = opener.video_stream_info(info)
    assert v["width"] == 640 and v["height"] == 360
    assert abs(v["fps"] - 12) < 0.5

    px = tmp_path / "proxy.mp4"
    convert.build_proxy(ev, px, v)
    px_dec = convert.verify_decode(px)
    assert px_dec["frames"] == ev_dec["frames"]
    assert px_dec["errors"] == 0
    # Medya zamanı korunur: delil ve proxy aynı ekseni paylaşır
    assert abs(px_dec["last_time"] - ev_dec["last_time"]) < 0.05


def test_real_timestamp_gap_detected(tmp_path):
    import av
    import numpy as np
    from fractions import Fraction
    src = tmp_path / "bosluklu.mkv"
    with av.open(str(src), "w", format="matroska") as out:
        st = out.add_stream("libx264", rate=10)
        st.width, st.height, st.pix_fmt = 320, 240, "yuv420p"
        st.codec_context.time_base = Fraction(1, 10)
        st.options = {"bf": "0"}
        for i in range(50):
            fr = av.VideoFrame.from_ndarray(np.full((240, 320, 3), i * 4, np.uint8), format="bgr24")
            fr.pts = i if i < 25 else i + 100   # 2,5. saniyeden sonra 10 sn'lik kayıt boşluğu
            fr.time_base = Fraction(1, 10)
            for p in st.encode(fr):
                out.mux(p)
        for p in st.encode(None):
            out.mux(p)
    spec, _ = opener.choose(src, sniff(src))
    stats = convert.remux_evidence(src, spec, tmp_path / "evidence")
    assert len(stats["gaps"]) == 1
    a, b = stats["gaps"][0]
    assert a == pytest.approx(2.4, abs=0.15) and b == pytest.approx(12.5, abs=0.15)


def test_broken_file_fails_with_diagnostics(corpus):
    d, _ = corpus
    src = d / "bozuk.mp4"
    spec, attempts = opener.choose(src, sniff(src))
    assert spec is None
    assert attempts and all(not a.ok for a in attempts)
    assert all(a.error for a in attempts)


def test_raw_fps_read_from_sps(corpus):
    d, _ = corpus
    spec, _ = opener.choose(d / "raw.264", sniff(d / "raw.264"))
    assert spec.raw and spec.fps == pytest.approx(12.0)


def test_encoder_chosen():
    assert encoders.choose() in encoders.ORDER + ["mpeg4"]


def test_frame_at_and_sprite(corpus, tmp_path):
    d, _ = corpus
    src = d / "h264.mp4"
    got = frames.frame_at(src, 3.0)
    assert got is not None
    t, img = got
    assert abs(t - 3.0) <= 1 / 12 + 1e-6
    assert img.shape == (360, 640, 3)
    meta = frames.make_sprite(src, 6.0, tmp_path / "sprite.jpg", count=6, cols=3)
    assert (tmp_path / "sprite.jpg").exists() and meta["count"] == 6


def test_iter_frames_sampling(corpus):
    d, _ = corpus
    times = [t for t, _ in frames.iter_frames(d / "h264.mp4", sample_fps=2, t0=1.0, t1=4.0)]
    assert times[0] >= 1.0 and times[-1] <= 4.0
    assert 6 <= len(times) <= 8
