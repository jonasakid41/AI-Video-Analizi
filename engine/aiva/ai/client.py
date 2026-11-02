"""OpenRouter (ya da OpenAI uyumlu yerel sunucu) sohbet çağrıları.

Her çağrı yerel `ai_calls` tablosuna yazılır (görüntüler yerine hash ve boyut saklanır).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any

import httpx

from .. import db, settings
from ..util import dumps, now_iso
from . import catalog


class AIError(RuntimeError):
    pass


ERRORS = {
    400: "İstek model tarafından reddedildi",
    401: "API anahtarı geçersiz. Ayarlar'dan anahtarınızı kontrol edin.",
    402: "OpenRouter bakiyeniz yetersiz. Ücretsiz profile geçebilir ya da bakiye yükleyebilirsiniz.",
    403: "Bu model için erişim izni yok (içerik denetimi ya da bölge kısıtı olabilir).",
    404: ("Seçilen model için uygun sağlayıcı bulunamadı. Gizlilik ayarlarınız (eğitimde kullanılmasın / "
          "sıfır saklama) bu modelin sağlayıcılarını dışarıda bırakıyor olabilir."),
    408: "Model zamanında yanıt vermedi.",
    413: "Gönderilen görüntüler/video çok büyük. Aday sayısını azaltın.",
    429: "Hız sınırına takıldı (ücretsiz modellerde sık görülür). Biraz bekleyip tekrar deneyin.",
    502: "Model sağlayıcısı geçici olarak yanıt vermiyor.",
    503: "Uygun sağlayıcı şu an yok. Biraz sonra tekrar deneyin ya da başka model seçin.",
}


def _redact(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            parts = []
            for p in c:
                if p.get("type") in ("image_url", "video_url"):
                    url = p[p["type"]]["url"]
                    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
                    parts.append({"type": p["type"], "sha256_16": digest, "bytes": len(url) * 3 // 4})
                else:
                    parts.append(p)
            out.append({**m, "content": parts})
        else:
            out.append(m)
    return out


def image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


def video_part(mp4: bytes, processing: str | None = None) -> dict:
    part: dict[str, Any] = {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + base64.b64encode(mp4).decode()}}
    if processing:
        part["processing"] = processing
    return part


def parse_json(text: str) -> Any:
    if not text:
        raise ValueError("Boş yanıt")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def configured(model: str | None = None) -> bool:
    """Model çağrılabilir mi? CLI modelleri (cli:<araç>:…) için araç kurulu olmalı, diğerleri için anahtar."""
    if model and model.startswith("cli:"):
        from . import cli
        return cli.available(cli.parse_id(model)[0])
    s = settings.load()
    return bool(settings.get_api_key(s)) or "openrouter.ai" not in s["ai"]["base_url"]


def _cli_chat(model: str, messages: list[dict], schema: dict | None, role: str, case_id: int | None,
              query_id: int | None) -> dict:
    from . import cli
    timeout = max(240.0, float(settings.load()["ai"].get("timeout_s", 120)))
    row = {"case_id": case_id, "query_id": query_id, "role": role, "model": model, "cost": 0.0,
           "request": dumps({"messages": _redact(messages), "schema": bool(schema)}), "created_at": now_iso()}
    try:
        out = cli.chat(model, messages, schema, timeout)
    except AIError as e:
        db.insert("ai_calls", {**row, "response": str(e), "ok": 0})
        raise
    db.insert("ai_calls", {**row, "response": out["content"], "tokens_in": out["usage"]["in"],
                           "tokens_out": out["usage"]["out"], "ok": 1})
    return out


def chat(model: str, messages: list[dict], schema: dict | None = None, *, role: str = "", case_id: int | None = None,
         query_id: int | None = None, max_tokens: int = 1500, temperature: float = 0.1,
         transport: httpx.BaseTransport | None = None) -> dict:
    if model.startswith("cli:"):
        return _cli_chat(model, messages, schema, role, case_id, query_id)
    s = settings.load()
    ai = s["ai"]
    base = ai["base_url"].rstrip("/")
    key = settings.get_api_key(s)
    is_or = "openrouter.ai" in base
    if is_or and not key:
        raise AIError("OpenRouter API anahtarı girilmemiş. Ayarlar'dan anahtar ekleyin.")
    info = catalog.get(model) if is_or else None
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if schema:
        if info is None or info.get("structured"):
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": schema.get("title", "cevap"), "strict": True, "schema": schema}}
        else:
            body["messages"] = messages + [{"role": "system", "content":
                                            "Yanıtı YALNIZCA şu JSON şemasına uyan tek bir JSON nesnesi olarak ver:\n"
                                            + json.dumps(schema, ensure_ascii=False)}]
    if is_or:
        prov: dict[str, Any] = {}
        if ai.get("data_collection_deny", True):
            prov["data_collection"] = "deny"
        if ai.get("zdr"):
            prov["zdr"] = True
        if prov:
            body["provider"] = prov
        body["usage"] = {"include": True}
    headers = {"Content-Type": "application/json", "X-Title": "AI Video Analizi"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    started = time.monotonic()
    last_err = ""
    data: dict = {}
    with httpx.Client(timeout=float(ai.get("timeout_s", 120)), transport=transport) as cli:
        for attempt in range(3):
            try:
                r = cli.post(f"{base}/chat/completions", headers=headers, json=body)
            except httpx.HTTPError as e:
                last_err = f"Bağlantı hatası: {e.__class__.__name__}"
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                data = r.json()
                if "error" in data and not data.get("choices"):
                    last_err = str(data["error"].get("message", data["error"]))
                    break
                break
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")
            except ValueError:
                pass
            last_err = ERRORS.get(r.status_code, f"Model hatası ({r.status_code})") + (f" — {detail}" if detail else "")
            if r.status_code in (429, 502, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            break
    ok = bool(data.get("choices"))
    content = (data["choices"][0]["message"].get("content") or "") if ok else ""
    usage = data.get("usage") or {}
    tin, tout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    cost = usage.get("cost")
    if cost is None and info:
        cost = tin * info["price_prompt"] + tout * info["price_completion"]
    cost = float(cost or 0.0)
    db.insert("ai_calls", {
        "case_id": case_id, "query_id": query_id, "role": role, "model": model,
        "request": dumps({"messages": _redact(body["messages"]), "schema": bool(schema)}),
        "response": content if ok else last_err, "tokens_in": tin, "tokens_out": tout, "cost": cost,
        "ok": int(ok), "created_at": now_iso(),
    })
    if not ok:
        raise AIError(last_err or "Model yanıt vermedi")
    out = {"content": content, "usage": {"in": tin, "out": tout}, "cost": cost, "model": data.get("model", model),
           "seconds": round(time.monotonic() - started, 2)}
    if schema:
        try:
            out["parsed"] = parse_json(content)
        except ValueError as e:
            raise AIError(f"Model geçerli JSON döndürmedi: {content[:200]}") from e
    return out
