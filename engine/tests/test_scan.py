"""Yapay zekâ taraması ve ön incelemesi: model videonun tamamını kare ızgaralarıyla görür.

Sahte model ızgara görüntülerini gerçekten açar ve kutunun göründüğü kareleri renginden bulur
(gerçek bir modelin videoya bakmasının taklidi). Sentetik videodaki kutu yerel dedektörün tanıdığı
bir sınıf değildir: yalnızca yerel adaylara bakan eski akış bu anı modele hiç göstermiyordu.
"""

from __future__ import annotations

import base64
import re

import cv2
import numpy as np
import pytest

import synth
from conftest import needs_models

BOX_T = (8.0, 13.0)  # build_tree_video: kutu bu aralıkta görünür


def _sheets(messages):
    """(ilk kare numarası, son kare numarası, BGR görüntü) listesi."""
    out, label = [], None
    for part in messages[1]["content"]:
        if part["type"] == "text" and part["text"].startswith("Izgara: kare"):
            a, b = map(int, re.findall(r"\d+", part["text"])[:2])
            label = (a, b)
        elif part["type"] == "image_url" and label:
            raw = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
            out.append((*label, cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)))
            label = None
    return out


def _tiles_with_box(messages, grid=3):
    hits = []
    for a, b, img in _sheets(messages):
        tw = img.shape[1] // grid
        th = tw * 360 // 640
        for k, n in enumerate(range(a, b + 1)):
            r, c = divmod(k, grid)
            tile = img[r * th + th // 6:(r + 1) * th, c * tw:(c + 1) * tw].astype(int)  # numara etiketi hariç
            box = (tile[..., 0] > 150) & (tile[..., 1] > 150) & (tile[..., 2] < 110)
            if box.mean() > 0.003:
                hits.append(n)
    return hits


def _fake(calls):
    def chat(model, messages, schema=None, **kw):
        role = kw.get("role")
        calls.setdefault(role, 0)
        calls[role] += 1
        parsed = None
        if role == "planlayici":
            parsed = {"intent": "ara", "time_from": None, "time_to": None, "classes": [], "colors": [], "plate": None,
                      "visual_query_en": "a box", "verify_question": "Kutu var mı?", "needs_motion": False}
        elif role == "tarama":
            parsed = {"hits": [{"tile": n, "confidence": 0.8, "note": "kutu görünüyor"} for n in _tiles_with_box(messages)]}
        elif role == "inceleme":
            seen = set(_tiles_with_box(messages))
            tiles = [n for a, b, _img in _sheets(messages) for n in range(a, b + 1)]
            parsed = {"tiles": [{"tile": n, "text": "sarı-mavi bir kutu sağa kayıyor" if n in seen else "değişiklik yok",
                                 "notable": n in seen, "people": 0, "vehicles": 0} for n in tiles]}
        elif role == "not_secimi":
            ids = re.findall(r"^(n\d+) \|.*kutu", messages[1]["content"], re.M)
            parsed = {"hits": [{"id": i, "confidence": 0.9, "note": "kutu"} for i in ids]}
        elif role == "dogrulayici":
            res = []
            for part in messages[1]["content"]:
                if part["type"] == "text" and part["text"].startswith("Aday "):
                    cid = part["text"].split()[1]
                    t = float(re.search(r"video içi (\d+(?:\.\d+)?)", part["text"]).group(1))
                    res.append({"id": cid, "match": BOX_T[0] - 0.5 <= t <= BOX_T[1] + 0.5, "confidence": 0.85,
                                "explanation": "kutu", "plate": None})
            parsed = {"results": res}
        return {"content": "Özet", "parsed": parsed, "usage": {"in": 1, "out": 1}, "cost": 0.0, "model": model}
    return chat


@pytest.fixture()
def tree_case(api_client, tmp_path, monkeypatch):
    api, wait_all = api_client
    from aiva import settings
    from aiva.ai import client as aiclient
    p = synth.build_tree_video(tmp_path / "bahce.mp4")
    cid = api.post("/api/cases", json={"name": "Tarama"}).json()["id"]
    eid = api.post(f"/api/cases/{cid}/evidence", json={"paths": [str(p)]}).json()["ids"][0]
    wait_all(api, cid)
    settings.set_api_key("sk-or-v1-sahte-anahtar-0000")
    calls: dict = {}
    monkeypatch.setattr(aiclient, "chat", _fake(calls))
    return api, wait_all, cid, eid, calls


def test_sample_times_denser_in_motion(data_dir):
    from aiva import cases, db
    from aiva.ai import scan
    c = cases.create("örnekleme")
    eid = db.insert("evidence", {"case_id": c["id"], "original_name": "x.mp4", "status": "hazir", "duration": 100.0,
                                 "created_at": ""})
    db.insert("segments", {"evidence_id": eid, "kind": "aktif", "t0": 40.0, "t1": 60.0, "info": None})
    times = scan.sample_times(db.row("SELECT * FROM evidence WHERE id = ?", (eid,)), [(0.0, 100.0)], 500)
    inside = [t for t in times if 40 <= t <= 60]
    assert len(inside) >= 9 and len(times) - len(inside) <= 10  # hareketli bölüm 2 sn, durağan 10 sn arayla
    assert len(scan.sample_times(db.row("SELECT * FROM evidence WHERE id = ?", (eid,)), [(0.0, 100.0)], 5)) == 5


@needs_models
def test_scan_finds_what_local_analysis_missed(tree_case):
    api, wait_all, cid, eid, calls = tree_case
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "Sarı bir kutu geçti mi?", "mode": "dogrula"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert res["status"] == "tamamlandi", res.get("error")
    assert calls.get("tarama", 0) >= 1 and "not_secimi" not in calls  # not yok: kare taraması
    ai = [r for r in res["results"] if r["id"].startswith("a")]
    assert ai and all(BOX_T[0] - 1 <= r["t"] <= BOX_T[1] + 1 for r in ai), [(r["id"], r["t"]) for r in ai]
    assert any(r.get("verdict", {}).get("match") for r in ai)
    assert any("Yapay zekâ" in n and "taradı" in n for n in res["options"]["notes"])


@needs_models
def test_review_notes_are_used_by_questions(tree_case):
    api, wait_all, cid, eid, calls = tree_case
    assert api.get(f"/api/evidence/{eid}/ai-notes").json() == []
    api.post(f"/api/evidence/{eid}/ai-review")
    wait_all(api, cid)
    notes = api.get(f"/api/evidence/{eid}/ai-notes").json()
    notable = [n for n in notes if n["notable"]]
    assert notes and notable and all(BOX_T[0] - 1 <= n["t"] <= BOX_T[1] + 1 for n in notable)
    calls.clear()
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "Kutu ne zaman geçti?", "mode": "dogrula"}).json()
    wait_all(api, cid)
    res = api.get(f"/api/queries/{q['query_id']}").json()
    assert calls.get("not_secimi") == 1 and "tarama" not in calls  # notlar yetti: yeniden tarama yok
    # Notun işaret ettiği an doğrulanmış olmalı (yerel adayla çakışıyorsa onun gerekçelerine eklenir)
    by_ai = [r for r in res["results"] if any(x.startswith("yapay zekâ notu") for x in r["reasons"])]
    assert by_ai and any(r.get("verdict", {}).get("match") for r in by_ai), \
        [(r["id"], round(r["t"], 1), r["reasons"][:1]) for r in res["results"]][:12]
    # "Neler oldu?" cevabı ön inceleme notlarını da içerir
    q = api.post(f"/api/cases/{cid}/queries", json={"question": "Neler oldu?", "mode": "hizli"}).json()
    wait_all(api, cid)
    ans = api.get(f"/api/queries/{q['query_id']}").json()["answer"]
    assert "Yapay zekâ ön inceleme notları" in ans and "kutu" in ans


def test_ai_flags_moments_local_analysis_missed(data_dir):
    from aiva import cases, db, results
    from aiva.ai import scan
    from aiva.util import now_iso
    c = cases.create("karşılaştırma")
    eid = db.insert("evidence", {"case_id": c["id"], "original_name": "x.mp4", "status": "hazir", "duration": 60.0,
                                 "created_at": ""})
    db.insert("detections", {"evidence_id": eid, "track_id": 1, "t": 5.0, "cls": "person", "conf": 0.9,
                             "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.3})
    for t, people, vehicles in ((5.0, 3, 0), (20.0, 1, 1), (40.0, 0, 0)):
        db.insert("ai_notes", {"evidence_id": eid, "t": t, "text": f"{people} kişi", "notable": 1, "people": people,
                               "vehicles": vehicles, "model": "x", "created_at": now_iso()})
    assert scan.flag_misses(eid) == 2
    assert scan.flag_misses(eid) == 2  # yeniden hesaplanır, birikmez
    evs = [e for e in results.events(eid) if e["kind"] == "yz"]
    assert [round(e["t_peak"]) for e in evs] == [5, 20]
    assert "2 kişi" in evs[0]["label"] and "1 kişi, 1 araç" in evs[1]["label"] and not evs[0]["ignorable"]
