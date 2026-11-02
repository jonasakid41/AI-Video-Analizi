"""Uçtan uca: API üzerinden vaka → video ekleme → dönüştürme → analiz → saat → soru → bulgu → rapor."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import synth
from conftest import REPO, needs_models

VTEST = REPO / "testdata" / "real" / "vtest.avi"
DOG = REPO / "testdata" / "real" / "dog.jpg"


@pytest.fixture()
def api(data_dir):
    from aiva import settings
    from aiva.api import deps
    from aiva.api.app import create_app, startup
    startup(data_dir / "aiva.sqlite")
    settings.update({"analysis": {"sample_fps": 2.0}})
    client = TestClient(create_app())
    client.headers["x-aiva-token"] = deps.TOKEN
    return client


def wait_all(api, case_id, timeout=600):
    from aiva import jobs
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        active = api.get("/api/jobs", params={"case_id": case_id, "active": True}).json()
        if not active:
            return api.get("/api/jobs", params={"case_id": case_id}).json()
        time.sleep(0.2)
    raise TimeoutError("İşler bitmedi")


def test_auth_required(api):
    c = TestClient(api.app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/cases").status_code == 401
    assert c.get("/api/cases", params={"k": "yanlis"}).status_code == 401


def test_settings_and_api_key_encrypted(api, data_dir):
    s = api.put("/api/settings", json={"ai": {"profile": "ucretsiz"}}).json()
    assert s["ai"]["roles"]["verifier"].endswith(":free")
    s = api.put("/api/settings/api-key", json={"key": "sk-or-v1-test-anahtar-123456"}).json()
    assert s["api_key_set"] and "test-anahtar" not in s["api_key_masked"]
    raw = (data_dir / "settings.json").read_text(encoding="utf-8")
    assert "test-anahtar" not in raw and "dpapi:" in raw
    assert api.delete("/api/settings/api-key").json()["api_key_set"] is False


def test_case_crud(api):
    c = api.post("/api/cases", json={"name": "Deneme vakası", "description": "açıklama"}).json()
    assert c["name"] == "Deneme vakası"
    assert api.patch(f"/api/cases/{c['id']}", json={"name": "Yeni ad"}).json()["name"] == "Yeni ad"
    assert len(api.get("/api/cases").json()) == 1
    assert api.delete(f"/api/cases/{c['id']}").json()["ok"]
    assert api.get(f"/api/cases/{c['id']}").status_code == 404


def test_broken_file_gets_diagnostics(api, corpus):
    d, _ = corpus
    c = api.post("/api/cases", json={"name": "Bozuk"}).json()
    ids = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(d / "bozuk.mp4")]}).json()["ids"]
    jobs = wait_all(api, c["id"])
    assert jobs[0]["status"] == "hata"
    ev = api.get(f"/api/evidence/{ids[0]}").json()
    assert ev["status"] == "hata"
    diag = api.get(f"/api/evidence/{ids[0]}/diagnostics").json()
    assert "Teşhis paketi" in diag["text"] and "hex" in diag["text"]


@needs_models
@pytest.mark.skipif(not DOG.exists(), reason="testdata/real/dog.jpg yok")
def test_full_flow_synthetic(api, osd_video, tmp_path, monkeypatch):
    path, scene = osd_video
    # Dosya adındaki tarih kamera başlangıcı olarak okunur (OSD taramasıyla düzeltilecek)
    named = tmp_path / "CH01_20261028143000.mp4"
    shutil.copy(path, named)
    vehicle = synth.build_vehicle_video(tmp_path / "CH02_20261028150000.mp4", DOG)
    c = api.post("/api/cases", json={"name": "Otopark"}).json()
    cid = c["id"]
    eid, eid2 = api.post(f"/api/cases/{cid}/evidence", json={"paths": [str(named), str(vehicle)]}).json()["ids"]
    jobs = wait_all(api, cid)
    assert all(j["status"] == "tamamlandi" for j in jobs), [(j["kind"], j["message"]) for j in jobs]
    ev = api.get(f"/api/evidence/{eid}").json()
    assert ev["status"] == "hazir" and ev["analyzed"] and ev["camera"] == "Kamera 1"
    assert ev["time"]["kaynak"] == "dosya_adi"
    assert len(ev["sha256"]) == 64

    # Proxy Range isteğini destekler (tarayıcıda ileri/geri sarma)
    r = api.get(f"/api/evidence/{eid}/proxy", headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206 and len(r.content) == 1024
    assert api.get(f"/api/evidence/{eid}/frame", params={"t": 5, "w": 320}).headers["content-type"] == "image/jpeg"
    act = api.get(f"/api/evidence/{eid}/activity").json()
    assert max(act["activity"]) > 0

    # Plaka okuma (gerçek kamyon fotoğrafı üzerine işlenmiş plaka)
    plates = api.get(f"/api/evidence/{eid2}/plates").json()
    assert any(p["plate"] == "34 ABC 123" for p in plates), plates
    hits = api.get(f"/api/cases/{cid}/plate-search", params={"q": "34ABC"}).json()
    assert hits and hits[0]["plate"] == "34 ABC 123"

    # Ekran saati taraması: +222 sn kayma ve 10. sn'deki 600 sn sıçrama
    jid = api.post(f"/api/evidence/{eid}/time/osd", json={"every": 4}).json()["job_id"]
    wait_all(api, cid)
    assert api.get(f"/api/jobs/{jid}").json()["status"] == "tamamlandi"
    t = api.get(f"/api/evidence/{eid}/time").json()
    assert t["summary"]["parca_sayisi"] == 2 and t["summary"]["kaynak"] == "osd"
    cam5 = api.get(f"/api/evidence/{eid}/time/at", params={"t": 5}).json()["camera"]
    assert cam5.startswith("2026-10-28T14:33:4")  # 14:30:00 + 5 + 222
    # Gerçek saat referansı: 5. saniyede gerçek saat 14:30:05 idi → kamera 3:42 ileri
    t = api.put(f"/api/evidence/{eid}/time", json={"references": [{"t_media": 5, "real": "2026-10-28T14:30:05"}],
                                                    "reason": "DVR ekranı fotoğrafı"}).json()
    assert t["summary"]["duzeltme_farki_sn"] == pytest.approx(-222, abs=1.5)
    real15 = api.get(f"/api/evidence/{eid}/time/at", params={"t": 15}).json()["real"]
    assert real15.startswith("2026-10-28T14:40:1")  # 14:30 + 15 + 600 sn kayıt boşluğu

    # Alan (ROI): yol bölgesi; aracın izi bu alandan geçer
    roi = api.post(f"/api/evidence/{eid}/rois", json={"name": "Yol", "kind": "alan",
                                                     "points": [[0, 0.6], [1, 0.6], [1, 1], [0, 1]]}).json()
    assert isinstance(api.get(f"/api/rois/{roi['id']}/events").json(), list)

    # Yerel (hızlı) soru: saat filtresi gerçek saate göre çalışır
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "34 ABC 123 plakalı araç ne zaman geçti?",
                                                     "mode": "hizli"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert res["status"] == "tamamlandi", res
    assert res["plan"]["plate"] == "34ABC123"
    assert res["results"] and res["results"][0]["plate"] == "34 ABC 123"
    assert res["answer"]

    # Model doğrulamalı soru (OpenRouter sahte yanıtla)
    from aiva import settings
    from aiva.ai import client as aiclient
    settings.set_api_key("sk-or-v1-sahte-anahtar-0000")
    calls = []

    def fake_chat(model, messages, schema=None, **kw):
        calls.append((kw.get("role"), model))
        if kw.get("role") == "planlayici":
            parsed = {"intent": "ara", "time_from": None, "time_to": None, "classes": ["car", "truck"], "colors": [],
                      "plate": None, "visual_query_en": "a white car", "verify_question": "Beyaz bir araç var mı?",
                      "needs_motion": False}
            return {"content": "", "parsed": parsed, "usage": {"in": 100, "out": 50}, "cost": 0.0001, "model": model}
        if kw.get("role") == "dogrulayici":
            ids = [p["text"].split()[1] for p in messages[1]["content"] if p["type"] == "text" and p["text"].startswith("Aday ")]
            parsed = {"results": [{"id": i, "match": True, "confidence": 0.9, "explanation": "Beyaz araç görünüyor.",
                                   "plate": "34 ABC 123"} for i in ids]}
            return {"content": "", "parsed": parsed, "usage": {"in": 900, "out": 80}, "cost": 0.002, "model": model}
        return {"content": "Beyaz araç 14:40 civarında görüldü.", "usage": {"in": 50, "out": 20}, "cost": 0.0001,
                "model": model}

    monkeypatch.setattr(aiclient, "chat", fake_chat)
    est = api.post(f"/api/cases/{cid}/queries/estimate", json={"question": "beyaz araç", "mode": "dogrula"}).json()
    assert est["candidates"] >= 1
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "Beyaz bir araç geçti mi?", "mode": "dogrula"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert res["status"] == "tamamlandi", res
    assert any(r.get("verdict", {}).get("match") for r in res["results"])
    assert {"planlayici", "dogrulayici"} <= {c[0] for c in calls}
    assert res["cost"] > 0

    # Model karşılaştırma: bir sonucu doğru, birini yanlış işaretle; iki modeli yarıştır
    ids = [r["id"] for r in res["results"]]
    lab = {ids[0]: True}
    if len(ids) > 1:
        lab[ids[1]] = False
    assert api.put(f"/api/queries/{q['query_id']}/labels", json={"labels": lab}).json()["labels"] == lab
    est = api.post(f"/api/queries/{q['query_id']}/evaluate", json={"models": ["a/model", "b/model"], "dry_run": True}).json()
    assert est["candidates"] == len(lab)
    ev_ = api.post(f"/api/queries/{q['query_id']}/evaluate", json={"models": ["a/model", "b/model"]}).json()
    wait_all(api, cid)
    evals = api.get(f"/api/queries/{q['query_id']}/evaluations").json()
    assert evals[0]["id"] == ev_["evaluation_id"] and evals[0]["status"] == "tamamlandi"
    rows = evals[0]["results"]
    assert [r["model"] for r in rows] == ["a/model", "b/model"]
    assert rows[0]["tp"] == 1 and rows[0]["recall"] == 1.0  # sahte model hepsine "eşleşti" der
    assert rows[0]["precision"] == (1.0 if len(lab) == 1 else 0.5)
    summ = api.get(f"/api/cases/{cid}/evaluations/summary").json()
    assert {s["model"] for s in summ} == {"a/model", "b/model"}

    # Bulgu → doğrula → rapor
    top = res["results"][0]
    f = api.post(f"/api/cases/{cid}/findings", json={"evidence_id": top["evidence_id"], "t": top["t"], "title": "Beyaz araç",
                                                     "source": "ai", "confidence": 0.9, "box": top["box"]}).json()
    assert f["image"] and f["real_t"]
    assert api.patch(f"/api/findings/{f['id']}", json={"status": "dogrulandi"}).json()["status"] == "dogrulandi"

    # İyileştirme: klasik + AI büyütme
    box = top["box"]
    jid = api.post(f"/api/evidence/{top['evidence_id']}/enhance", json={"t": top["t"], "box": box, "ops": [
        {"op": "clahe"}, {"op": "keskinlestir"}, {"op": "ai_buyut", "params": {"kat": 2}}]}).json()["job_id"]
    wait_all(api, cid)
    j = api.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "tamamlandi", j
    assert j["result"]["ai"] is True
    assert api.get("/api/files", params={"path": j["result"]["image"]}).status_code == 200

    # Derin mod için modele gönderilen kısa video kesiti geçerli bir MP4 olmalı
    import io

    import av
    from aiva.ai import verify as verifymod
    mp4 = verifymod.make_clip(eid2, 1.0, 5.0)
    with av.open(io.BytesIO(mp4)) as c:
        n = sum(1 for _ in c.decode(video=0))
    assert len(mp4) > 1000 and n >= 20  # ~4 sn × 8 fps
    assert "on_battery" in api.get("/api/power").json()

    # Dışa aktarma ve rapor
    fr = api.post(f"/api/evidence/{eid}/export-frame", json={"t": 12}).json()
    assert fr["image"].endswith(".png")
    jid = api.post(f"/api/evidence/{eid}/export-clip", json={"t0": 9, "t1": 13}).json()["job_id"]
    jid2 = api.post(f"/api/cases/{cid}/report", json={}).json()["job_id"]
    wait_all(api, cid)
    assert api.get(f"/api/jobs/{jid}").json()["status"] == "tamamlandi"
    rep = api.get(f"/api/jobs/{jid2}").json()
    assert rep["status"] == "tamamlandi", rep
    assert Path(rep["result"]["path"]).stat().st_size > 5000
    hist = api.get(f"/api/cases/{cid}/history").json()
    actions = {h["action"] for h in hist}
    assert {"video_eklendi", "donusturuldu", "analiz_tamamlandi", "saat_eslemesi_guncellendi",
            "soru_soruldu", "rapor_olusturuldu"} <= actions


def _wait_running(api, case_id, kind, timeout=120):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for j in api.get("/api/jobs", params={"case_id": case_id}).json():
            if j["kind"] == kind and j["status"] == "calisiyor":
                return j
        time.sleep(0.05)
    raise TimeoutError(kind)


@needs_models
@pytest.mark.skipif(not VTEST.exists(), reason="testdata/real/vtest.avi yok")
def test_cancelled_analysis_leaves_no_partial_results(api):
    c = api.post("/api/cases", json={"name": "İptal"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(VTEST)]}).json()["ids"][0]
    j = _wait_running(api, c["id"], "analyze")
    assert api.post(f"/api/jobs/{j['id']}/cancel").json()["ok"]
    wait_all(api, c["id"])
    assert api.get(f"/api/jobs/{j['id']}").json()["status"] == "iptal"
    ev = api.get(f"/api/evidence/{eid}").json()
    assert ev["analyzed"] == 0 and "analiz" not in ev["analysis_info"]
    assert api.get(f"/api/evidence/{eid}/tracks").json() == []
    assert api.get(f"/api/evidence/{eid}/detections/range", params={"t0": 0, "t1": 80}).json() == []


@needs_models
@pytest.mark.skipif(not VTEST.exists(), reason="testdata/real/vtest.avi yok")
def test_delete_video_while_job_running(api, data_dir):
    c = api.post("/api/cases", json={"name": "Silme"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(VTEST)]}).json()["ids"][0]
    _wait_running(api, c["id"], "analyze")
    r = api.delete(f"/api/evidence/{eid}")
    assert r.status_code == 200, r.text
    assert not (data_dir / "cases" / str(c["id"]) / "evidence" / str(eid)).exists()
    assert api.get(f"/api/evidence/{eid}").status_code == 404
    wait_all(api, c["id"])
    assert api.delete(f"/api/cases/{c['id']}").status_code == 200
    assert not (data_dir / "cases" / str(c["id"])).exists()


@needs_models
@pytest.mark.skipif(not VTEST.exists(), reason="testdata/real/vtest.avi yok")
def test_real_pedestrian_video(api):
    c = api.post("/api/cases", json={"name": "Yayalar"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(VTEST)]}).json()["ids"][0]
    jobs = wait_all(api, c["id"], timeout=900)
    assert all(j["status"] == "tamamlandi" for j in jobs), [(j["kind"], j["message"]) for j in jobs]
    ev = api.get(f"/api/evidence/{eid}").json()
    stats = ev["analysis_info"]["analiz"]
    assert stats["izler"].get("kişi", 0) >= 5, stats
    tracks = api.get(f"/api/evidence/{eid}/tracks", params={"cls": "person"}).json()
    assert tracks and tracks[0]["thumb"]
    dets = api.get(f"/api/evidence/{eid}/detections", params={"t": 20}).json()
    assert dets and all(0 <= v <= 1.0001 for d in dets for v in d["box"][:2])
    people = api.get(f"/api/cases/{c['id']}/people").json()
    assert isinstance(people, list)
