"""Yalıtılmış medya işlemleri: çökme, takılma ve iptal motoru etkilememeli."""

from __future__ import annotations

import threading
import time

import pytest

from aiva import jobs, worker


def test_crash_in_child_does_not_kill_engine():
    with pytest.raises(worker.WorkerCrashed, match="çıkış kodu 3"):
        worker.run("aiva.media.convert:_test_crash", {})


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
