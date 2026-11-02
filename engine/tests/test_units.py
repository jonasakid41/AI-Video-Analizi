from __future__ import annotations

from datetime import datetime

import httpx
import numpy as np
import pytest

from aiva.ai import planner
from aiva.ai.search import media_windows
from aiva.analyze import colors, plates
from aiva.analyze.detector import Det
from aiva.analyze.tracker import Tracker
from aiva.timecorr.mapping import TimeMapping


@pytest.mark.parametrize("raw,expected", [
    ("34 ABC 123", "34 ABC 123"),
    ("34abc123", "34 ABC 123"),
    ("TR 06 A 1234", "06 A 1234"),
    ("O6 AB 5O1", "06 AB 501"),
    ("35-KL-4521", "35 KL 4521"),
    ("82 ABC 123", None),       # il kodu 81'den büyük
    ("34 ABCD 12", "34 ABC 012"),  # OCR'ın 0 yerine okuduğu D düzeltilir (güven düşer)
    ("34 ABCDE 1", None),       # geçerli biçime getirilemez
    ("ABC123", None),
])
def test_tr_plate_normalize(raw, expected):
    r = plates.normalize_tr(raw)
    assert (r.text if r else None) == expected


def test_plate_candidates_join_split_boxes_and_consensus():
    cands = plates.candidates_from_text([("34", 0.9), ("ABC 123", 0.95)])
    assert cands[0].text == "34 ABC 123" or any(c.text == "34 ABC 123" for c in cands)
    reads = [plates.PlateRead("34 ABC 123", "", 0.9, True), plates.PlateRead("34 ABC 128", "", 0.5, True),
             plates.PlateRead("34 ABC 123", "", 0.8, True)]
    text, conf = plates.consensus(reads)
    assert text == "34 ABC 123" and conf > 0.4
    assert plates.similar("34ABC", "34 ABC 123") > 0.7
    assert plates.similar("06XY99", "34 ABC 123") < 0.4


@pytest.mark.parametrize("q,checks", [
    ("14:00-15:00 arası kırmızı montlu biri geçti mi?",
     {"time_from": "14:00", "time_to": "15:00", "classes": ["person"], "color": ("ust", "kırmızı")}),
    ("saat 9 ile 10 arasında beyaz araba", {"time_from": "09:00", "time_to": "10:00", "color": ("govde", "beyaz")}),
    ("16.30'dan sonra gelen kamyonet", {"time_from": "16:30", "classes": ["truck"]}),
    ("saat 14:30 civarı", {"time_from": "14:25", "time_to": "14:35"}),
    ("34 ABC 123 plakalı araç", {"plate": "34ABC123", "intent": "plaka"}),
    ("girişte kavga eden kişiler", {"needs_motion": True}),
    ("kaç kişi geçti", {"intent": "say"}),
])
def test_local_planner(q, checks):
    p = planner.local_plan(q)
    for k, v in checks.items():
        if k == "color":
            assert {"target": v[0], "color": v[1]} in p["colors"], p["colors"]
        elif k == "classes":
            assert all(c in p["classes"] for c in v), p["classes"]
        else:
            assert p[k] == v, (k, p[k])
    assert p["visual_query_en"]


def test_visual_query_english():
    p = planner.local_plan("kırmızı montlu adam")
    assert p["visual_query_en"] == "a person wearing a red top"
    p = planner.local_plan("beyaz araba")
    assert "white" in p["visual_query_en"] and "car" in p["visual_query_en"]


def test_colors_dominant():
    red = np.zeros((40, 40, 3), np.uint8)
    red[:] = (30, 30, 220)
    assert colors.dominant(red)[0][0] == "kırmızı"
    navy = np.zeros((40, 40, 3), np.uint8)
    navy[:] = (80, 20, 10)
    assert colors.dominant(navy)[0][0] in ("lacivert", "mavi")
    white = np.full((40, 40, 3), 235, np.uint8)
    assert colors.dominant(white)[0][0] == "beyaz"


def test_tracker_keeps_identity_and_revives_static_objects():
    tr = Tracker(max_age=1.5)
    ids = []
    for i in range(6):  # sağa yürüyen kişi, 2 fps
        x = 100 + i * 30
        out = tr.update(i * 0.5, [Det("person", 0.9, x, 100, x + 40, 200)])
        ids.append(out[0][1])
    assert len(set(ids)) == 1
    parked = tr.update(10.0, [Det("car", 0.8, 500, 300, 700, 400)])[0][1]
    again = tr.update(20.0, [Det("car", 0.8, 502, 301, 701, 401)])[0][1]  # 10 sn sonra aynı yerde
    assert parked == again
    assert len(tr.close()) == 2


def test_media_windows_uses_real_time():
    m = TimeMapping.from_start(datetime(2026, 10, 28, 13, 50, 0))
    w, warn = media_windows(m, 3600, "14:00", "14:10")
    assert warn is None and w == [(pytest.approx(600), pytest.approx(1200))]
    w, warn = media_windows(TimeMapping(), 100, "14:00", None)
    assert w == [(0.0, 100)] and warn


def test_db_migrates_v1_to_latest(tmp_path):
    import sqlite3
    from aiva import db
    p = tmp_path / "eski.sqlite"
    c = sqlite3.connect(p)
    c.executescript(db.SCHEMA_V1)
    c.execute("PRAGMA user_version = 1")
    c.execute("INSERT INTO cases (name, created_at, updated_at) VALUES ('eski', '', '')")
    c.commit()
    c.close()
    db.init(p)
    assert db.conn().execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)
    cols = {r["name"] for r in db.rows("PRAGMA table_info(queries)")}
    assert "labels" in cols
    assert db.row("SELECT name FROM cases")["name"] == "eski"
    db.close_thread_connection()


def test_vault_roundtrip():
    from aiva import vault
    enc = vault.protect("sk-or-v1-abc")
    assert "abc" not in enc and vault.unprotect(enc) == "sk-or-v1-abc"
    assert vault.unprotect("dpapi:bozukveri") is None
    assert vault.mask("sk-or-v1-1234567890") .startswith("sk-or-")


def test_catalog_normalize():
    from aiva.ai.catalog import estimate, image_tokens, normalize
    m = normalize({"id": "x/y:free", "architecture": {"input_modalities": ["text", "image", "video"]},
                   "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["structured_outputs"]})
    assert m["video"] and m["image"] and m["free"] and m["structured"]
    assert image_tokens(512, 512) == 255
    assert estimate("yok/boyle-model", 100, [], 10) == 0.0


def test_client_error_mapping(data_dir, monkeypatch):
    from aiva import settings
    from aiva.ai import catalog, client
    settings.set_api_key("sk-or-v1-test-0000")
    monkeypatch.setattr(catalog, "get", lambda _m: {"structured": True, "price_prompt": 1e-6, "price_completion": 2e-6})
    monkeypatch.setattr(client.time, "sleep", lambda _s: None)
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(req.content)
        seen.update(body)
        if body["model"] == "kotu/anahtar":
            return httpx.Response(401, json={"error": {"message": "No auth"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    t = httpx.MockTransport(handler)
    res = client.chat("iyi/model", [{"role": "user", "content": "x"}], {"title": "t", "type": "object"}, transport=t)
    assert res["parsed"] == {"ok": True} and res["cost"] == pytest.approx(10e-6 + 10e-6)
    assert seen["provider"]["data_collection"] == "deny" and seen["response_format"]["type"] == "json_schema"
    with pytest.raises(client.AIError, match="API anahtarı geçersiz"):
        client.chat("kotu/anahtar", [{"role": "user", "content": "x"}], transport=t)
    from aiva import db
    calls = db.rows("SELECT ok FROM ai_calls ORDER BY id")
    assert [c["ok"] for c in calls] == [1, 0]


def test_vehicle_duplicates_merged_across_classes():
    from aiva.analyze.detector import Det, merge_vehicle_duplicates
    dets = [Det("car", 0.57, 466, 74, 691, 174), Det("truck", 0.61, 462, 76, 694, 171),
            Det("person", 0.9, 470, 80, 520, 170), Det("car", 0.8, 10, 10, 100, 60)]
    out = merge_vehicle_duplicates(dets)
    assert [d.cls for d in out] == ["person", "car", "truck"] or sorted(d.cls for d in out) == ["car", "person", "truck"]
    assert len(out) == 3 and not any(d.cls == "car" and d.x1 == 466 for d in out)  # düşük güvenli kopya atıldı
