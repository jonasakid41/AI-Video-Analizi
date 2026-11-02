from __future__ import annotations

import hashlib
import io
import json
import zipfile

import httpx
import pytest

PKG = {
    "AIVideoAnalizi/AIVideoAnalizi.exe": b"MZ yeni kabuk",
    "AIVideoAnalizi/engine/aiva-engine.exe": b"MZ yeni motor",
    "AIVideoAnalizi/models/model.onnx": b"x" * 5000,
}


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    from aiva import update
    monkeypatch.setattr(update, "_last", None)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _github(zdata: bytes, *, tag: str = "v9.0.0", digest: str | None = "ok", body_sha: bool = False):
    """Sahte GitHub: son sürüm bilgisi + yönlendirmeli paket indirme."""
    from aiva import update
    sha = hashlib.sha256(zdata).hexdigest()
    name = f"AIVideoAnalizi-{tag.lstrip('v')}-win64.zip"
    dl = f"{update.DOWNLOAD_PREFIX}{tag}/{name}"
    asset = {"name": name, "size": len(zdata), "browser_download_url": dl}
    if digest:
        asset["digest"] = "sha256:" + (sha if digest == "ok" else "0" * 64)
    body = f"Notlar\n\n**ZIP SHA-256:** `{sha}`" if body_sha else "Notlar"

    def handler(req: httpx.Request) -> httpx.Response:
        if str(req.url) == update.LATEST_URL:
            return httpx.Response(200, json={"tag_name": tag, "name": f"AI Video Analizi {tag}", "body": body,
                                             "html_url": "https://github.com/x", "assets": [asset]})
        if str(req.url) == dl:
            return httpx.Response(302, headers={"location": "https://release-assets.githubusercontent.com/p"})
        if req.url.host == "release-assets.githubusercontent.com":
            return httpx.Response(200, content=zdata)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_check_reports_newer_version_and_hash(data_dir, monkeypatch):
    from aiva import settings, update
    monkeypatch.setattr(update, "transport", _github(_zip(PKG)))
    info = update.check()
    assert info["newer"] and info["latest"] == "9.0.0"
    assert len(info["asset"]["sha256"]) == 64
    assert settings.load()["update"]["last_check"]
    # Asset özeti yoksa sürüm notlarındaki SHA-256 kullanılır
    monkeypatch.setattr(update, "transport", _github(_zip(PKG), digest=None, body_sha=True))
    assert update.check()["asset"]["sha256"] == hashlib.sha256(_zip(PKG)).hexdigest()
    monkeypatch.setattr(update, "transport", _github(_zip(PKG), tag="v0.0.1"))
    assert not update.check()["newer"]
    assert update.parse_version("v0.10.0") > update.parse_version("0.9.9")


def test_download_job_verifies_and_stages(data_dir, monkeypatch):
    from aiva import jobs, update
    monkeypatch.setattr(update, "transport", _github(_zip(PKG)))
    j = jobs.wait(jobs.submit("guncelleme", {"version": "9.0.0"}))
    assert j["status"] == "tamamlandi", j
    st = update.staged()
    assert st and st["version"] == "9.0.0"
    from pathlib import Path
    app = Path(st["dir"])
    assert (app / "engine" / "aiva-engine.exe").read_bytes() == b"MZ yeni motor"
    assert not list(update.updates_dir().glob("*.zip")) and not list(update.updates_dir().glob("*.part"))
    update.discard()
    assert update.staged() is None and not app.exists()


def test_download_rejects_wrong_hash(data_dir, monkeypatch):
    from aiva import jobs, update
    monkeypatch.setattr(update, "transport", _github(_zip(PKG), digest="bad"))
    j = jobs.wait(jobs.submit("guncelleme", {"version": "9.0.0"}))
    assert j["status"] == "hata" and "SHA-256" in j["message"]
    assert update.staged() is None and not list(update.updates_dir().iterdir())


def test_download_rejects_missing_hash_and_bad_paths(data_dir, monkeypatch, tmp_path):
    from aiva import jobs, update
    monkeypatch.setattr(update, "transport", _github(_zip(PKG), digest=None))
    j = jobs.wait(jobs.submit("guncelleme", {"version": "9.0.0"}))
    assert j["status"] == "hata" and "SHA-256" in j["message"]
    evil = dict(PKG) | {"AIVideoAnalizi/../../kotu.txt": b"x"}
    monkeypatch.setattr(update, "transport", _github(_zip(evil)))
    j = jobs.wait(jobs.submit("guncelleme", {"version": "9.0.0"}))
    assert j["status"] == "hata" and "geçersiz dosya yolu" in j["message"]
    assert not (data_dir / "kotu.txt").exists() and not (data_dir.parent / "kotu.txt").exists()
    assert update.staged() is None


def test_update_api_and_cleanup(api_client, monkeypatch):
    client, _ = api_client
    from aiva import update
    monkeypatch.setattr(update, "transport", _github(_zip(PKG)))
    s = client.post("/api/update/check").json()
    assert s["latest"]["newer"] and not s["can_apply"] and "Geliştirme" in s["reason"]
    r = client.post("/api/update/download", json={"version": "9.0.0"})
    assert r.status_code == 400 and "Geliştirme" in r.json()["detail"]
    # Güncelleyicinin bıraktığı sonuç arayüze bir kez gösterilir, sonra silinir
    d = update.updates_dir()
    (d / "sonuc.json").write_text(json.dumps({"ok": True, "version": "9.0.0"}), encoding="utf-8")
    (d / "staging").mkdir()
    (d / "guncelleyici.exe").write_bytes(b"MZ")
    update.cleanup()
    assert not (d / "staging").exists() and not (d / "guncelleyici.exe").exists()
    assert client.get("/api/update").json()["result"]["ok"]
    assert client.post("/api/update/ack").json()["result"] is None
    r = client.post("/api/log", json={"where": "panel: sor", "message": "x is undefined", "stack": "at AskPanel"})
    assert r.json()["ok"]
    from aiva import paths
    assert "panel: sor: x is undefined" in (paths.logs_dir() / "arayuz.log").read_text(encoding="utf-8")


def test_plan_sanitize_handles_off_schema_model_output():
    from aiva.ai import planner
    p = planner.sanitize({"intent": "bilinmiyor", "classes": None,
                          "colors": ["kırmızı", {"target": "ust", "color": "kırmızı"}, {"target": "x", "color": "mavi"},
                                     {"target": "alt", "color": "fosforlu"}],
                          "plate": {"metin": "34"}, "time_from": "14.00", "time_to": "yarın",
                          "needs_motion": "evet", "visual_query_en": 5},
                         "saat 14'ten sonra kırmızı montlu biri")
    assert p["intent"] == "ara" and p["classes"] == ["person"]
    assert p["colors"] == [{"target": "ust", "color": "kırmızı"}, {"target": "genel", "color": "mavi"}]
    assert p["plate"] is None and p["time_from"] == "14:00" and p["time_to"] is None
    assert p["needs_motion"] is False and p["visual_query_en"] == "5"
    empty = planner.sanitize(None, "beyaz araba")
    assert empty["classes"] == ["car"] and empty["colors"] and empty["verify_question"] == "beyaz araba"


def test_verdict_normalize():
    from aiva.ai import verify
    v = verify.verdict({"match": "false", "confidence": "%80", "plate": {"x": 1}, "explanation": ["a"]})
    assert v == {"match": False, "confidence": 0.8, "explanation": "", "plate": None}
    assert verify.verdict({"match": True, "confidence": 0.5, "plate": "34 ABC 123", "explanation": "uygun"})["plate"] == "34 ABC 123"
    assert [r["id"] for r in verify._rows([{"id": "1"}, "x", None])] == ["1"]
    assert verify._rows({"results": "yok"}) == []


def test_query_get_sanitizes_old_rows(data_dir):
    from aiva import cases, db, query
    from aiva.util import dumps, now_iso
    c = cases.create("eski kayıt")
    qid = db.insert("queries", {
        "case_id": c["id"], "question": "beyaz araba", "options": "{}", "status": "tamamlandi", "created_at": now_iso(),
        "plan": dumps({"intent": "ara", "classes": ["car"], "visual_query_en": "a white car"}),
        "results": dumps([{"id": "1", "evidence_id": 1, "t": 2.0, "verdict": {"match": True, "plate": {"a": 1}}}, "bozuk"]),
    })
    q = query.get(qid)
    assert q["plan"]["colors"] == [{"target": "govde", "color": "beyaz"}]
    assert len(q["results"]) == 1 and q["results"][0]["verdict"]["plate"] is None


@pytest.mark.parametrize("v,expected", [("0.1.2", (0, 1, 2)), ("v1.0", (1, 0)), ("", (0,))])
def test_parse_version(v, expected):
    from aiva import update
    assert update.parse_version(v) == expected
