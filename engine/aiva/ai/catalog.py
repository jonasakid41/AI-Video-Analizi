"""OpenRouter canlı model kataloğu (anahtar gerektirmez). data/cache/models.json'da günlük önbelleklenir."""

from __future__ import annotations

import json
import math
import threading
import time
from typing import Any

import httpx

from .. import paths, settings

TTL = 24 * 3600
_lock = threading.Lock()
_mem: dict[str, Any] = {}


def _cache_file():
    return paths.cache_dir() / "models.json"


def _is_openrouter(base_url: str) -> bool:
    return "openrouter.ai" in base_url


def normalize(m: dict) -> dict:
    arch = m.get("architecture") or {}
    ins = arch.get("input_modalities") or ["text", "image"]
    pr = m.get("pricing") or {}

    def f(k: str) -> float:
        try:
            return max(0.0, float(pr.get(k) or 0))
        except (TypeError, ValueError):
            return 0.0

    prompt, completion = f("prompt"), f("completion")
    params = m.get("supported_parameters") or []
    return {
        "id": m["id"],
        "name": m.get("name") or m["id"],
        "description": (m.get("description") or "")[:300],
        "context": m.get("context_length"),
        "input": ins,
        "image": "image" in ins,
        "video": "video" in ins,
        "structured": "structured_outputs" in params or "response_format" in params,
        "free": m["id"].endswith(":free") or (prompt == 0 and completion == 0 and pr != {}),
        "price_in_m": round(prompt * 1e6, 4),
        "price_out_m": round(completion * 1e6, 4),
        "price_prompt": prompt,
        "price_completion": completion,
        "created": m.get("created"),
    }


def fetch(refresh: bool = False) -> dict:
    s = settings.load()
    base = s["ai"]["base_url"].rstrip("/")
    with _lock:
        if not refresh and _mem.get("base") == base and time.time() - _mem.get("fetched", 0) < TTL:
            return _mem["data"]
        cf = _cache_file()
        if not refresh and cf.exists():
            try:
                cached = json.loads(cf.read_text(encoding="utf-8"))
                if cached.get("base") == base and time.time() - cached.get("fetched", 0) < TTL:
                    _mem.update(cached)
                    return cached["data"]
            except ValueError:
                pass
    headers = {}
    key = settings.get_api_key(s)
    if key and not _is_openrouter(base):
        headers["Authorization"] = f"Bearer {key}"
    try:
        r = httpx.get(f"{base}/models", headers=headers, timeout=30)
        r.raise_for_status()
        raw = r.json().get("data", [])
    except (httpx.HTTPError, ValueError) as e:
        cf = _cache_file()
        if cf.exists():
            cached = json.loads(cf.read_text(encoding="utf-8"))
            data = cached["data"]
            data["warning"] = f"Model listesi güncellenemedi, önbellek kullanılıyor ({e.__class__.__name__})"
            return data
        raise RuntimeError(f"Model listesi alınamadı: {e}") from e
    models = [normalize(m) for m in raw if m.get("id")]
    models.sort(key=lambda m: (not m["video"], not m["image"], m["price_in_m"]))
    data = {
        "models": models,
        "total": len(models),
        "image_count": sum(m["image"] for m in models),
        "video_count": sum(m["video"] for m in models),
        "free_vision": sum(m["image"] and m["free"] for m in models),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    blob = {"base": base, "fetched": time.time(), "data": data}
    with _lock:
        _mem.update(blob)
        _cache_file().write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
    return data


def get(model_id: str) -> dict | None:
    try:
        data = fetch()
    except RuntimeError:
        return None
    return next((m for m in data["models"] if m["id"] == model_id), None)


def image_tokens(w: int, h: int) -> int:
    """Görsel başına kaba token tahmini (sağlayıcıya göre değişir; üst sınıra yakın tutulur)."""
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def estimate(model_id: str, text_tokens: int, images: list[tuple[int, int]], out_tokens: int) -> float:
    m = get(model_id)
    if not m:
        return 0.0
    tin = text_tokens + sum(image_tokens(w, h) for w, h in images)
    return round(tin * m["price_prompt"] + out_tokens * m["price_completion"], 5)
