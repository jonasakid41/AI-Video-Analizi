"""Bilgisayarda kurulu yapay zekâ CLI araçları: Claude Code, OpenAI Codex CLI, Gemini CLI.

Kullanıcı aracında kendi aboneliğiyle oturum açmışsa uygulama soruları ona sorar; ücret OpenRouter'dan
düşmez, aboneliğin kullanım sınırları geçerlidir. Model kimliği `cli:<araç>:<model>` biçimindedir
(model boşsa aracın varsayılanı). İstemci bu önekle gelen çağrıları buraya yönlendirir.

Görüntüler Claude Code'a satır içi (stream-json), Codex ve Gemini'ye geçici dosya olarak verilir.
Araç dosyalara, kabuğa ya da ağa erişemesin diye araçları kapalı ya da salt okunur çalıştırılır.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .. import paths, settings
from ..util import remove_tree

CREATE_NO_WINDOW = 0x0800_0000

TOOLS: dict[str, dict[str, Any]] = {
    "claude": {"label": "Claude Code", "exe": "claude", "login": "claude", "experimental": False,
               "models": [("sonnet", "Sonnet"), ("haiku", "Haiku (hızlı)"), ("opus", "Opus (en güçlü)")],
               "roles": {"planner": "haiku", "verifier": "sonnet", "video": "sonnet"}},
    "codex": {"label": "OpenAI Codex CLI", "exe": "codex", "login": "codex login", "experimental": True,
              "models": [("", "varsayılan model")], "roles": {"planner": "", "verifier": "", "video": ""}},
    "gemini": {"label": "Gemini CLI", "exe": "gemini", "login": "gemini", "experimental": True,
               "models": [("", "varsayılan model")], "roles": {"planner": "", "verifier": "", "video": ""}},
}

_versions: dict[str, tuple[float, str | None]] = {}


def _error(msg: str) -> Exception:
    from .client import AIError
    return AIError(msg)


def parse_id(model_id: str) -> tuple[str, str]:
    _, tool, *rest = model_id.split(":", 2) + [""]
    return tool, (rest[0] if rest else "")


def model_id(tool: str, model: str = "") -> str:
    return f"cli:{tool}:{model}"


def _candidates(tool: str) -> list[Path]:
    exe = TOOLS[tool]["exe"]
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    return [home / ".local" / "bin" / f"{exe}.exe", appdata / "npm" / f"{exe}.cmd",
            local / "Microsoft" / "WinGet" / "Links" / f"{exe}.exe", home / ".cargo" / "bin" / f"{exe}.exe"]


def find(tool: str) -> Path | None:
    custom = (settings.load()["ai"].get("cli_paths") or {}).get(tool)
    if custom and Path(custom).is_file():
        return Path(custom)
    found = shutil.which(TOOLS[tool]["exe"])
    if found:
        return Path(found)
    return next((p for p in _candidates(tool) if p.is_file()), None)


def available(tool: str) -> bool:
    return tool in TOOLS and find(tool) is not None


def version(tool: str) -> str | None:
    exe = find(tool)
    if exe is None:
        return None
    cached = _versions.get(str(exe))
    if cached and time.time() - cached[0] < 600:
        return cached[1]
    try:
        p = subprocess.run([str(exe), "--version"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
        v = (p.stdout or p.stderr).strip().splitlines()[0][:80] if (p.stdout or p.stderr).strip() else None
    except (OSError, subprocess.TimeoutExpired):
        v = None
    _versions[str(exe)] = (time.time(), v)
    return v


def status() -> list[dict]:
    out = []
    for tool, t in TOOLS.items():
        exe = find(tool)
        out.append({"tool": tool, "label": t["label"], "path": str(exe) if exe else None, "found": exe is not None,
                    "version": version(tool) if exe else None, "experimental": t["experimental"],
                    "login": t["login"], "models": [{"id": model_id(tool, m), "name": n} for m, n in t["models"]]})
    return out


def info(mid: str) -> dict:
    """Katalog girdisi biçiminde sahte model bilgisi (fiyat 0, video yok: kareler kullanılır)."""
    tool, model = parse_id(mid)
    t = TOOLS.get(tool, {"label": tool, "models": []})
    name = dict(t["models"]).get(model) or model or "varsayılan model"
    return {"id": mid, "name": f"{t['label']} (abonelik) · {name}", "description": "Bilgisayarınızdaki CLI aracı; "
            "aboneliğinizle çalışır, OpenRouter ücreti yoktur.", "context": None, "input": ["text", "image"],
            "image": True, "video": False, "structured": True, "free": True, "cli": True, "price_in_m": 0,
            "price_out_m": 0, "price_prompt": 0.0, "price_completion": 0.0, "created": None}


def model_entries() -> list[dict]:
    return [info(model_id(tool, m)) for tool, t in TOOLS.items() if available(tool) for m, _n in t["models"]]


# --- mesaj dönüştürme -----------------------------------------------------------------

def _split(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI biçimli mesajları (sistem metni, sıralı parçalar) olarak ayırır.
    Parça: {"text": str} ya da {"jpeg": bytes}. Video parçaları desteklenmez (atlanır)."""
    system: list[str] = []
    parts: list[dict] = []
    for m in messages:
        c = m.get("content")
        items = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
        for p in items:
            if p.get("type") == "text":
                if m.get("role") == "system":
                    system.append(p["text"])
                else:
                    parts.append({"text": p["text"]})
            elif p.get("type") == "image_url":
                url = p["image_url"]["url"]
                parts.append({"jpeg": base64.b64decode(url.split(",", 1)[1])})
    return "\n\n".join(system), parts


def _schema_note(schema: dict | None) -> str:
    if not schema:
        return ""
    return ("\n\nYanıtı YALNIZCA şu JSON şemasına uyan tek bir JSON nesnesi olarak ver, başka metin yazma:\n"
            + json.dumps(schema, ensure_ascii=False))


def _run(args: list[str], stdin: str, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=cwd, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as e:
        raise _error(f"CLI aracı {timeout:.0f} sn içinde yanıt vermedi") from e
    except OSError as e:
        raise _error(f"CLI aracı çalıştırılamadı: {e}") from e


LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "quota", "too many requests", "resource_exhausted")
LOGIN_WORDS = ("login", "log in", "authenticate", "authentication", "invalid api key", "not logged", "auth method",
               "unauthorized", "credentials")


def _explain(tool: str, text: str) -> Exception:
    t = TOOLS[tool]
    low = text.lower()
    if any(w in low for w in LIMIT_WORDS):
        return _error(f"{t['label']} aboneliğinin kullanım sınırına ulaşıldı. Sınır sıfırlanınca tekrar deneyin "
                      "ya da Ayarlar'dan OpenRouter modeline geçin.")
    if any(w in low for w in LOGIN_WORDS):
        return _error(f"{t['label']} oturumu açık değil. Bir terminalde '{t['login']}' komutunu çalıştırıp "
                      "aboneliğinizle giriş yapın.")
    tail = " ".join(text.strip().split())[-300:]
    return _error(f"{t['label']} hata verdi: {tail or 'yanıt yok'}")


def _claude(exe: Path, model: str, system: str, parts: list[dict], schema: dict | None, cwd: Path,
            timeout: float) -> tuple[str, Any, dict]:
    # npm kurulumundaki .cmd kabuğu (cmd.exe) satır sonu/tırnak içeren argümanları bozar: o durumda
    # sistem metni ve şema mesajın içine yazılır
    native = exe.suffix.lower() == ".exe"
    content: list[dict] = []
    if not native and system:
        content.append({"type": "text", "text": system})
    for p in parts:
        if "text" in p:
            content.append({"type": "text", "text": p["text"]})
        else:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(p["jpeg"]).decode()}})
    if not native and schema:
        content.append({"type": "text", "text": _schema_note(schema)})
    args = [str(exe), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--tools", "", "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "project,local"]
    if model:
        args += ["--model", model]
    if native and system:
        args += ["--system-prompt", system]
    if native and schema:
        args += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    msg = {"type": "user", "message": {"role": "user", "content": content}}
    p = _run(args, json.dumps(msg, ensure_ascii=False) + "\n", cwd, timeout)
    result = None
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            result = ev
    if result is None or result.get("is_error"):
        raise _explain("claude", (result or {}).get("result") or p.stderr or p.stdout)
    usage = result.get("usage") or {}
    tokens = {"in": sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                        "cache_creation_input_tokens")),
              "out": int(usage.get("output_tokens") or 0)}
    return str(result.get("result") or ""), result.get("structured_output"), tokens


def _write_images(parts: list[dict], cwd: Path) -> list[str]:
    names = []
    for p in parts:
        if "jpeg" in p:
            name = f"goruntu_{len(names) + 1}.jpg"
            (cwd / name).write_bytes(p["jpeg"])
            names.append(name)
    return names


def _prompt(system: str, parts: list[dict], schema: dict | None, image_ref) -> str:
    """Metin istem: görüntülerin yeri "[Görüntü n]" ile belirtilir (image_ref ile araca özgü gösterim)."""
    out = [system] if system else []
    n = 0
    for p in parts:
        if "text" in p:
            out.append(p["text"])
        else:
            n += 1
            out.append(image_ref(n))
    return "\n\n".join(out) + _schema_note(schema)


def _codex(exe: Path, model: str, system: str, parts: list[dict], schema: dict | None, cwd: Path,
           timeout: float) -> tuple[str, Any, dict]:
    imgs = _write_images(parts, cwd)
    args = [str(exe), "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
            "--output-last-message", "cevap.txt"]
    if model:
        args += ["--model", model]
    if schema:
        (cwd / "sema.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        args += ["--output-schema", "sema.json"]
    if imgs:
        args.append("--image=" + ",".join(imgs))
    prompt = _prompt(system, parts, None, lambda n: f"[Ekli görüntü {n}]")
    p = _run(args, prompt, cwd, timeout)
    out = cwd / "cevap.txt"
    text = out.read_text(encoding="utf-8", errors="replace").strip() if out.exists() else ""
    if p.returncode != 0 or not text:
        raise _explain("codex", p.stderr + "\n" + p.stdout)
    return text, None, {"in": 0, "out": 0}


def _gemini(exe: Path, model: str, system: str, parts: list[dict], schema: dict | None, cwd: Path,
            timeout: float) -> tuple[str, Any, dict]:
    _write_images(parts, cwd)
    args = [str(exe), "--output-format", "json"]
    if model:
        args += ["--model", model]
    prompt = _prompt(system, parts, schema, lambda n: f"@goruntu_{n}.jpg")
    p = _run(args, prompt, cwd, timeout)
    text, tokens = p.stdout.strip(), {"in": 0, "out": 0}
    try:
        data = json.loads(text)
        if data.get("error"):
            raise _explain("gemini", json.dumps(data["error"], ensure_ascii=False))
        text = str(data.get("response") or "")
    except ValueError:
        pass
    if p.returncode != 0 or not text:
        raise _explain("gemini", p.stderr + "\n" + p.stdout)
    return text, None, tokens


ADAPTERS = {"claude": _claude, "codex": _codex, "gemini": _gemini}


def chat(mid: str, messages: list[dict], schema: dict | None, timeout: float) -> dict:
    """client.chat ile aynı biçimde sonuç döner (maliyet 0)."""
    from .client import parse_json
    tool, model = parse_id(mid)
    if tool not in TOOLS:
        raise _error(f"Bilinmeyen CLI aracı: {tool}")
    exe = find(tool)
    if exe is None:
        raise _error(f"{TOOLS[tool]['label']} bu bilgisayarda bulunamadı. Kurup giriş yaptıktan sonra "
                     "Ayarlar > Yapay zekâ'dan yeniden tarayın.")
    system, parts = _split(messages)
    cwd = paths.tmp_dir() / "cli" / uuid.uuid4().hex[:12]
    cwd.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        text, structured, tokens = ADAPTERS[tool](exe, model, system, parts, schema, cwd, timeout)
    finally:
        remove_tree(cwd)
    out: dict[str, Any] = {"content": text, "usage": tokens, "cost": 0.0, "model": mid,
                           "seconds": round(time.monotonic() - started, 2)}
    if schema:
        if structured is not None:
            out["parsed"] = structured
        else:
            try:
                out["parsed"] = parse_json(text)
            except ValueError as e:
                raise _error(f"{TOOLS[tool]['label']} geçerli JSON döndürmedi: {text[:200]}") from e
    return out


def test(tool: str, model: str = "") -> dict:
    """Ayarlar'daki "Test et": küçük bir soru sorar (aboneliğinizden çok az kullanım düşer)."""
    from .client import AIError
    started = time.monotonic()
    try:
        r = chat(model_id(tool, model), [{"role": "user", "content": "Yalnızca TAMAM yaz."}], None, timeout=120)
        return {"ok": True, "seconds": round(time.monotonic() - started, 1), "text": r["content"][:200]}
    except AIError as e:
        return {"ok": False, "seconds": round(time.monotonic() - started, 1), "error": str(e)}
