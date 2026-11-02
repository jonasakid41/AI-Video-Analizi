"""Yalıtılmış medya işlemleri: çökme, takılma ve iptal motoru etkilememeli."""

from __future__ import annotations

import threading
import time

import pytest

from aiva import jobs, worker


def test_crash_in_child_does_not_kill_engine():
    with pytest.raises(worker.WorkerCrashed, match="çıkış kodu 3"):
        worker.run("aiva.media.convert:_test_crash", {})


def test_child_exception_keeps_type_and_traceback():
    # Önceden kullanıcı yalnızca "ValueError: …" görüyordu; tür ve traceback teşhis paketine gider
    with pytest.raises(worker.WorkerError) as ei:
        worker.run("aiva.media.convert:_test_value_error", {})
    e = ei.value
    assert str(e) == "libornek" and e.kind == "UnknownCodecError"
    assert "_test_value_error" in e.trace and "Traceback" in e.trace


def test_av1_video_is_converted(tmp_path):
    """AV1'de çözücünün adı (libdav1d) kodlayıcı olarak bulunamıyordu: kayıpsız kopya ValueError veriyordu."""
    import av
    from fractions import Fraction

    import numpy as np
    from aiva.media import convert, opener
    from aiva.media.sniff import sniff
    if "libsvtav1" not in av.codecs_available:
        pytest.skip("AV1 kodlayıcı yok")
    src = tmp_path / "av1.mkv"
    with av.open(str(src), "w", format="matroska") as out:
        st = out.add_stream("libsvtav1", rate=Fraction(10))
        st.width, st.height, st.pix_fmt, st.options = 640, 360, "yuv420p", {"preset": "12"}
        for i in range(10):
            img = np.full((360, 640, 3), (i * 20) % 255, np.uint8)
            for pkt in st.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    spec, _ = opener.choose(src, sniff(src))
    stats = convert.remux_evidence(src, spec, tmp_path / "evidence")
    assert stats["packets"] >= 9 and stats["video_codec"] == "libdav1d"
    ev = opener.probe(tmp_path / "evidence.mkv", opener.OpenSpec("evidence"))
    info = convert.build_proxy(tmp_path / "evidence.mkv", tmp_path / "proxy.mp4", opener.video_stream_info(ev))
    assert info["mode"] == "kodlama" and (tmp_path / "proxy.mp4").stat().st_size > 0


def test_hang_is_detected_by_idle_timeout():
    t = time.monotonic()
    with pytest.raises(worker.WorkerStalled):
        worker.run("aiva.media.convert:_test_hang", {}, idle_timeout=2.0)
    assert time.monotonic() - t < 30


def test_cancel_kills_child_immediately():
    ctx = jobs.JobContext(-1)
    threading.Timer(2.5, ctx.cancel_event.set).start()
    t = time.monotonic()
    with pytest.raises(jobs.Cancelled):
        worker.run("aiva.media.convert:_test_hang", {}, ctx, idle_timeout=600)
    assert time.monotonic() - t < 15


def test_real_remux_runs_isolated(corpus, tmp_path):
    from aiva.media import opener
    from aiva.media.sniff import sniff
    d, _ = corpus
    src = d / "raw.h265"
    spec, _ = opener.choose(src, sniff(src))
    seen = []
    stats = worker.run("aiva.media.convert:remux_task",
                       {"src": str(src), "spec": spec.to_dict(), "dst_base": str(tmp_path / "evidence")},
                       on_progress=lambda v, m=None: seen.append(v))
    assert stats["packets"] > 0 and stats["b_frames_reordered"]
    assert (tmp_path / "evidence.mkv").exists()


def test_interrupted_ingest_recovered_on_startup(data_dir):
    from aiva import cases, db, evidence
    c = cases.create("Kurtarma")
    eid = db.insert("evidence", {"case_id": c["id"], "original_name": "x.mp4", "status": "donusturuluyor",
                                 "status_detail": "Kayıpsız kopya oluşturuluyor", "created_at": ""})
    evidence.recover()
    ev = evidence.require(eid)
    assert ev["status"] == "hata" and "yarıda kaldı" in ev["status_detail"]
