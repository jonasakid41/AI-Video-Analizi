"""Uzaktaki küçük kişiler, siyah-beyaz (gece/IR) ve karanlık kayıtlar."""

from __future__ import annotations

import numpy as np
import pytest

import synth
from aiva.analyze import lowlight, motion
from conftest import REPO, needs_models

VTEST = REPO / "testdata" / "real" / "vtest.avi"
needs_vtest = pytest.mark.skipif(not VTEST.exists(), reason="testdata/real/vtest.avi yok")


def test_lowlight_stats():
    rng = np.random.default_rng(1)
    color = rng.integers(0, 255, (72, 128, 3), dtype=np.uint8)
    gray = np.repeat(rng.integers(40, 200, (72, 128, 1), dtype=np.uint8), 3, axis=2)
    tinted = gray.astype(np.float32)
    tinted[..., 2] *= 1.08   # morumsu IR: her yerde aynı ton
    tinted = np.clip(tinted, 0, 255).astype(np.uint8)
    dark = (gray * 0.25).astype(np.uint8)
    assert lowlight.frame_stats(color)[0] is False
    assert lowlight.frame_stats(gray)[0] and lowlight.frame_stats(tinted)[0]
    g, is_dark, _flat = lowlight.frame_stats(dark)
    assert g and is_dark
    assert lowlight.enhance(dark).std() > dark.std()


def _s(t, px):
    return motion.Sample(t, 0.0, np.packbits(np.zeros(motion.GRID_W * motion.GRID_H, bool)), 100.0, 1, 0.0,
                         mlargest_px=px, boxes=((0.5, 0.5, 0.01, 0.02),))


def test_small_persistent_motion_activates_segment():
    # Uzaktaki kişi: toplam hareket eşiğin çok altında ama leke ardışık örneklerde sürüyor
    walk = [_s(t, 20) for t in range(3, 8)]
    blip = [_s(20, 20)]   # tek örneklik leke (gürültü) aktif sayılmaz
    samples = [_s(t, 0) for t in range(3)] + walk + [_s(t, 0) for t in range(8, 20)] + blip
    segs = motion.active_segments(motion.segment_signal(samples, 0.004), 0.004)
    assert len(segs) == 1 and segs[0][0] <= 3 and segs[0][1] >= 7
    assert motion.meter_width(1920) == 640 and motion.meter_width(640) == 320


@needs_models
@needs_vtest
def test_far_away_people_found_by_zoom(api_client, tmp_path):
    api, wait_all = api_client
    p = synth.build_from_real(tmp_path / "genis_aci.mp4", VTEST, seconds=20, scale=0.45, canvas=(1920, 1080))
    c = api.post("/api/cases", json={"name": "Uzak kişiler"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(p)]}).json()["ids"][0]
    jobs = wait_all(api, c["id"], timeout=900)
    assert all(j["status"] == "tamamlandi" for j in jobs), [(j["kind"], j["message"]) for j in jobs]
    st = api.get(f"/api/evidence/{eid}").json()["analysis_info"]["analiz"]
    tracks = api.get(f"/api/evidence/{eid}/tracks").json()
    people = [t for t in tracks if t["cls"] == "person" and t["n"] >= 3]
    # Eski kurallarla (320 px hareket taraması, yakınlaştırma yok) bu videoda yalnızca 1 kısa iz çıkıyordu
    assert len(people) >= 5, (len(people), st["goruntu"], st["aktif_sure_sn"])
    assert st["goruntu"]["yakinlastirma_tespiti"] > 0 and st["aktif_sure_sn"] > 10


@needs_models
@needs_vtest
def test_gray_night_video_colors_not_used_as_filter(api_client, tmp_path):
    api, wait_all = api_client
    from aiva import db
    from aiva.ai import planner, search, verify
    p = synth.build_from_real(tmp_path / "gece_ir.mp4", VTEST, seconds=15, gray=True, dark=0.35)
    c = api.post("/api/cases", json={"name": "Gece"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(p)]}).json()["ids"][0]
    wait_all(api, c["id"], timeout=900)
    st = api.get(f"/api/evidence/{eid}").json()["analysis_info"]["analiz"]
    assert st["goruntu"]["renksiz_oran"] > 0.9 and st["goruntu"]["dusuk_isik_oran"] > 0.9
    assert st["goruntu"]["iyilestirilen_kare"] > 0
    tracks = api.get(f"/api/evidence/{eid}/tracks").json()
    people = [t for t in tracks if t["cls"] == "person"]
    assert people and all("siyah-beyaz" in t["color_text"] for t in people), [t["color_text"] for t in people[:3]]
    assert not any("kırmızı" in t["color_text"] or "gri" in t["color_text"] for t in people)
    # "Kırmızı montlu" sorusu siyah-beyaz kayıtta kişileri elemez; modele kaydın renksiz olduğu söylenir
    plan = planner.local_plan("kırmızı montlu biri geçti mi?")
    cands, notes = search.find(c["id"], plan)
    assert any("siyah-beyaz" in n for n in notes), notes
    tracks_c = [x for x in cands if x.kind == "iz"]
    assert tracks_c and all(x.gray for x in tracks_c)
    assert "siyah-beyaz" in verify.label(tracks_c[0])
    assert db.row("SELECT COUNT(*) AS n FROM tracks WHERE evidence_id = ?", (eid,))["n"] == len(tracks)


@needs_models
def test_unrecognized_motion_becomes_candidate(api_client, tmp_path):
    api, wait_all = api_client
    from aiva.ai import planner, search
    p = synth.build_tree_video(tmp_path / "bahce.mp4")
    c = api.post("/api/cases", json={"name": "Bahçe"}).json()
    api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(p)]})
    wait_all(api, c["id"])
    cands, notes = search.find(c["id"], planner.local_plan("bahçede biri var mı?"))
    hidden = [x for x in cands if x.id.startswith("h")]
    assert hidden and hidden[0].box and 7 <= hidden[0].t <= 14, [(x.id, x.t) for x in cands]
    assert hidden[0].box[2] >= 0.14  # hareket kutusu doğrulamada çevresiyle görünecek kadar geniş
    assert any("tespit edemedi" in n for n in notes) or any(x.kind == "iz" for x in cands)
