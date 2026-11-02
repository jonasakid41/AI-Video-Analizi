"""Hareketin türünü ayırt etme: kişi/araç, ağaç/gölge, ışık, parazit, tanımlanamayan."""

from __future__ import annotations

import numpy as np
import pytest

import synth
from aiva.analyze import motion
from conftest import REPO, needs_models

VTEST = REPO / "testdata" / "real" / "vtest.avi"
GH, GW = motion.GRID_H, motion.GRID_W


def sample(t, cells, brightness=100.0, blobs=1, largest=0.02):
    g = np.zeros((GH, GW), bool)
    for (y0, y1, x0, x1) in cells:
        g[y0:y1, x0:x1] = True
    return motion.Sample(t, float(g.mean()) + 0.01, np.packbits(g.reshape(-1)), brightness, blobs, largest)


def test_classify_kinds():
    tree = (2, 8, 2, 8)  # hep aynı yerde
    samples = [sample(i, [tree]) for i in range(6)]
    samples.append(sample(6.0, [(10, 20, 20, 26)]))                  # kutunun içinde → nesne
    samples.append(sample(7.0, [(10, 14, 30, 34)]))                  # yeni yerde, kutu yok → belirsiz
    samples.append(sample(8.0, [(0, GH, 0, GW)], brightness=160))    # her yer + parlaklık sıçraması → ışık
    samples.append(sample(9.0, [(y, y + 1, x, x + 1) for y in range(0, GH, 4) for x in range(0, GW, 4)],
                          brightness=160, blobs=60, largest=0.0005))  # dağınık noktalar → parazit
    boxes = motion.BoxIndex([(6.0, 20 / GW, 10 / GH, 6 / GW, 10 / GH)])
    kinds = motion.classify(samples, boxes, threshold=0.001)
    assert kinds[:6] == ["cevre"] * 6
    assert kinds[6:] == ["nesne", "belirsiz", "isik", "parazit"]
    evs = motion.events(samples, kinds, max_gap=1.5)
    assert evs[0] == ("cevre", 0, 5)
    assert [e[0] for e in evs[1:]] == ["nesne", "belirsiz", "isik", "parazit"]


@needs_models
def test_tree_motion_is_marked_ignorable(api_client, tmp_path):
    api, wait_all = api_client
    p = synth.build_tree_video(tmp_path / "agac.mp4")
    c = api.post("/api/cases", json={"name": "Ağaç"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(p)]}).json()["ids"][0]
    jobs = wait_all(api, c["id"])
    assert all(j["status"] == "tamamlandi" for j in jobs), [(j["kind"], j["message"]) for j in jobs]
    act = api.get(f"/api/evidence/{eid}/activity").json()
    kinds = {e["kind"] for e in act["events"]}
    assert "cevre" in kinds, act["events"]
    assert any(e["ignorable"] and e["kind"] == "cevre" for e in act["events"])
    # Dedektörün tanımadığı hareketli şekil "incelenmeli" olarak ayrı kalmalı
    assert any(e["kind"] == "belirsiz" and 7 <= e["t0"] <= 14 for e in act["events"]), act["events"]
    summ = api.get(f"/api/evidence/{eid}").json()["analysis_info"]["analiz"]["hareket_ozeti"]
    assert summ.get("cevre", 0) > 5
    assert any(k for k in act["kinds"] if k)


@needs_models
@pytest.mark.skipif(not VTEST.exists(), reason="testdata/real/vtest.avi yok")
def test_pedestrian_events_labelled_with_people(api_client):
    api, wait_all = api_client
    c = api.post("/api/cases", json={"name": "Yaya olayları"}).json()
    eid = api.post(f"/api/cases/{c['id']}/evidence", json={"paths": [str(VTEST)]}).json()["ids"][0]
    wait_all(api, c["id"], timeout=900)
    evs = api.get(f"/api/evidence/{eid}/activity").json()["events"]
    obj = [e for e in evs if e["kind"] == "nesne"]
    assert obj and any("kişi" in e["label"] for e in obj), evs[:5]
    # "Neler oldu?" sorusu olay listesinden yanıtlanır
    q = api.post(f"/api/cases/{c['id']}/queries", json={"question": "Bu videoda neler oldu?", "mode": "hizli"}).json()
    wait_all(api, c["id"])
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert res["status"] == "tamamlandi"
    assert res["answer"].startswith("Önemli olaylar") and "kişi" in res["answer"]


@needs_models
def test_dynamic_search_widens_and_explains(api_client, tmp_path, monkeypatch):
    api, wait_all = api_client
    from aiva import db, settings
    from aiva.ai import client as aiclient
    p = synth.build_tree_video(tmp_path / "CH05_20261028143000.mp4")
    c = api.post("/api/cases", json={"name": "Dinamik"}).json()
    cid = c["id"]
    api.post(f"/api/cases/{cid}/evidence", json={"paths": [str(p)]})
    wait_all(api, cid)
    settings.set_api_key("sk-or-v1-sahte-anahtar-0000")
    calls = {"verify": 0, "seen": []}

    def fake_chat(model, messages, schema=None, **kw):
        role = kw.get("role")
        if role == "planlayici":  # model soruda olmayan bir saat uyduruyor
            parsed = {"intent": "ara", "time_from": "03:00", "time_to": "04:00", "classes": [], "colors": [],
                      "plate": None, "visual_query_en": "a yellow box", "verify_question": "Sarı bir kutu var mı?",
                      "needs_motion": False}
            return {"content": "", "parsed": parsed, "usage": {"in": 1, "out": 1}, "cost": 0.0, "model": model}
        if role == "dogrulayici":
            calls["verify"] += 1
            ids = [x["text"].split()[1] for x in messages[1]["content"] if x["type"] == "text" and x["text"].startswith("Aday ")]
            calls["seen"].append(ids)
            hit = calls["verify"] > 1  # ilk turda hiçbir şey eşleşmez
            return {"content": "", "parsed": {"results": [{"id": i, "match": hit, "confidence": 0.8, "explanation": "x",
                                                           "plate": None} for i in ids]},
                    "usage": {"in": 1, "out": 1}, "cost": 0.0001, "model": model}
        return {"content": "Özet", "usage": {"in": 1, "out": 1}, "cost": 0.0, "model": model}

    monkeypatch.setattr(aiclient, "chat", fake_chat)
    settings.update({"ai": {"batch_size": 64}})
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "Sarı bir kutu geçti mi?", "mode": "dogrula"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert res["status"] == "tamamlandi", res
    assert res["plan"]["time_from"] is None  # soruda saat yok: uydurulan aralık yok sayıldı
    assert calls["verify"] == 2 and not set(calls["seen"][0]) & set(calls["seen"][1])
    assert any("genişletildi" in n for n in res["options"]["notes"])
    assert any(r.get("verdict", {}).get("match") for r in res["results"])

    # Hazır olmayan video ve kayıt olmayan saat aralığı cevapta açıklanır
    db.insert("evidence", {"case_id": cid, "original_name": "bozuk.dav", "status": "hata", "created_at": ""})
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "saat 03:00 ile 04:00 arası kim geçti?", "mode": "hizli"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert "bulunamadı" in res["answer"]
    assert "istenen saat aralığında kayıt yok" in res["answer"] or "hazır değil" in res["answer"], res["answer"]
    assert any("hazır değil" in n for n in res["options"]["notes"])
