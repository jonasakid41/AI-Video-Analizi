"""Bilgisayardaki yapay zekâ CLI araçları (Claude Code, Codex, Gemini) — sahte süreçlerle."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aiva.ai import cli, client

IMG = client.image_part(b"\xff\xd8jpegveri")
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
MSGS = [{"role": "system", "content": "Sistem talimatı"},
        {"role": "user", "content": [{"type": "text", "text": "Aday 1"}, IMG, {"type": "text", "text": "Aday 2"}, IMG]}]


def _fake(monkeypatch, tool: str, exe: str, respond):
    """find() sahte bir exe döner; _run çağrısını yakalayıp respond(args, stdin, cwd) ile yanıtlar."""
    seen: dict = {}
    monkeypatch.setattr(cli, "find", lambda t: Path(exe) if t == tool else None)

    def run(args, stdin, cwd, timeout):
        seen.update(args=args, stdin=stdin, files=sorted(p.name for p in Path(cwd).iterdir()))
        out, rc = respond(args, stdin, Path(cwd))
        return subprocess.CompletedProcess(args, rc, out, "")

    monkeypatch.setattr(cli, "_run", run)
    return seen


def test_claude_native_uses_inline_images_and_schema(data_dir, monkeypatch):
    def respond(args, stdin, cwd):
        res = {"type": "result", "is_error": False, "result": '{"ok": true}', "structured_output": {"ok": True},
               "usage": {"input_tokens": 100, "output_tokens": 5}}
        return "\n".join([json.dumps({"type": "system"}), json.dumps(res)]), 0

    seen = _fake(monkeypatch, "claude", r"C:\x\claude.exe", respond)
    out = client.chat("cli:claude:haiku", MSGS, SCHEMA, role="dogrulayici")
    assert out["parsed"] == {"ok": True} and out["cost"] == 0.0 and out["usage"]["in"] == 100
    a = seen["args"]
    assert a[a.index("--model") + 1] == "haiku" and a[a.index("--tools") + 1] == ""
    assert json.loads(a[a.index("--json-schema") + 1]) == SCHEMA
    assert a[a.index("--system-prompt") + 1] == "Sistem talimatı" and "--no-session-persistence" in a
    content = json.loads(seen["stdin"])["message"]["content"]
    assert [c["type"] for c in content] == ["text", "image", "text", "image"]
    from aiva import db
    row = db.row("SELECT model, ok, cost FROM ai_calls ORDER BY id DESC LIMIT 1")
    assert row["model"] == "cli:claude:haiku" and row["ok"] == 1 and row["cost"] == 0


def test_claude_cmd_shim_puts_schema_in_message(data_dir, monkeypatch):
    def respond(args, stdin, cwd):
        return json.dumps({"type": "result", "is_error": False, "result": '```json\n{"ok": false}\n```'}), 0

    seen = _fake(monkeypatch, "claude", r"C:\npm\claude.cmd", respond)
    out = client.chat("cli:claude:", MSGS, SCHEMA)
    assert out["parsed"] == {"ok": False}
    assert "--json-schema" not in seen["args"] and "--system-prompt" not in seen["args"] and "--model" not in seen["args"]
    texts = [c["text"] for c in json.loads(seen["stdin"])["message"]["content"] if c["type"] == "text"]
    assert texts[0] == "Sistem talimatı" and "JSON şemasına" in texts[-1]


@pytest.mark.parametrize("text,needle", [
    ("Claude AI usage limit reached|1762000000", "kullanım sınırına"),
    ("Invalid API key · Please run /login", "oturumu açık değil"),
])
def test_claude_errors_explained(data_dir, monkeypatch, text, needle):
    _fake(monkeypatch, "claude", r"C:\x\claude.exe",
          lambda *a: (json.dumps({"type": "result", "is_error": True, "result": text}), 1))
    with pytest.raises(client.AIError, match=needle):
        client.chat("cli:claude:sonnet", MSGS)
    from aiva import db
    assert db.row("SELECT ok FROM ai_calls ORDER BY id DESC LIMIT 1")["ok"] == 0


def test_codex_gets_image_files_and_schema_file(data_dir, monkeypatch):
    def respond(args, stdin, cwd):
        assert json.loads((cwd / "sema.json").read_text(encoding="utf-8")) == SCHEMA
        (cwd / "cevap.txt").write_text('{"ok": true}', encoding="utf-8")
        return "", 0

    seen = _fake(monkeypatch, "codex", r"C:\x\codex.exe", respond)
    out = client.chat("cli:codex:", MSGS, SCHEMA)
    assert out["parsed"] == {"ok": True}
    assert "--image=goruntu_1.jpg,goruntu_2.jpg" in seen["args"] and seen["args"][1] == "exec"
    assert "[Ekli görüntü 2]" in seen["stdin"] and seen["files"] == ["goruntu_1.jpg", "goruntu_2.jpg", "sema.json"]


def test_gemini_references_images_with_at(data_dir, monkeypatch):
    seen = _fake(monkeypatch, "gemini", r"C:\npm\gemini.cmd",
                 lambda *a: (json.dumps({"response": '{"ok": true}', "stats": {}}), 0))
    out = client.chat("cli:gemini:", MSGS, SCHEMA)
    assert out["parsed"] == {"ok": True}
    assert "@goruntu_1.jpg" in seen["stdin"] and "@goruntu_2.jpg" in seen["stdin"]
    assert "JSON şemasına" in seen["stdin"]
    assert not list((Path(data_dir) / "tmp" / "cli").iterdir())  # geçici görüntüler silindi


def test_cli_models_in_catalog_and_settings(api_client, monkeypatch):
    api, _ = api_client
    from aiva.ai import catalog
    monkeypatch.setattr(cli, "find", lambda t: Path(r"C:\x\claude.exe") if t == "claude" else None)
    monkeypatch.setattr(cli, "version", lambda t: "2.1.0 (Claude Code)")

    def offline(refresh=False):
        raise RuntimeError("Model listesi alınamadı: çevrimdışı")

    monkeypatch.setattr(catalog, "_remote", offline)
    data = api.get("/api/models").json()  # çevrimdışıyken de CLI modelleri seçilebilir
    ids = [m["id"] for m in data["models"]]
    assert "cli:claude:sonnet" in ids and data["warning"] and data["cli_count"] == 3
    assert catalog.get("cli:claude:sonnet")["free"] and catalog.estimate("cli:claude:sonnet", 1000, [(512, 512)], 100) == 0
    s = api.get("/api/settings").json()
    assert not s["ai_ready"]  # anahtar yok, OpenRouter modeli seçili
    s = api.post("/api/ai/cli/use", json={"tool": "claude"}).json()
    assert s["ai"]["roles"]["verifier"] == "cli:claude:sonnet" and s["ai_ready"] and s["ai_source"] == "cli"
    assert client.configured("cli:claude:sonnet") and not client.configured("cli:codex:")
    st = api.get("/api/ai/cli").json()
    assert [t["tool"] for t in st if t["found"]] == ["claude"] and st[0]["version"].startswith("2.1")
    assert api.post("/api/ai/cli/use", json={"tool": "codex"}).status_code == 400
    # Anahtar olmadan da doğrulamalı mod kullanılabilir (CLI seçiliyse yerel moda düşülmez)
    from aiva import query
    monkeypatch.setattr(query.jobs, "submit", lambda *a, **k: 0)  # gerçek CLI çağrılmasın
    cid = api.post("/api/cases", json={"name": "CLI"}).json()["id"]
    q = query.create(cid, "beyaz araba var mı", {"mode": "dogrula"})
    assert q["mode"] == "dogrula"
