"""Ayarlar: data/settings.json. API anahtarı DPAPI ile şifreli saklanır."""

from __future__ import annotations

import copy
import json
import threading
from typing import Any

from . import paths, vault

PROFILES: dict[str, dict[str, str]] = {
    # 2 Kasım 2026 OpenRouter kataloğundan; kullanıcı her rolü değiştirebilir
    "ucretsiz": {
        "planner": "nvidia/nemotron-3.5-super-vl:free",
        "verifier": "nvidia/nemotron-3.5-super-vl:free",
        "video": "nvidia/nemotron-3.5-super-vl:free",
    },
    "ekonomik": {
        "planner": "qwen/qwen3.8-flash",
        "verifier": "qwen/qwen3.8-flash",
        "video": "qwen/qwen3.8-flash",
    },
    "dengeli": {
        "planner": "google/gemini-3.5-flash-lite",
        "verifier": "google/gemini-3.8-flash",
        "video": "google/gemini-3.8-flash",
    },
    "en_iyi": {
        "planner": "google/gemini-3.8-flash",
        "verifier": "google/gemini-4-argon",
        "video": "google/gemini-4-argon",
    },
}

PROFILE_LABELS = {
    "ucretsiz": "Ücretsiz",
    "ekonomik": "Ekonomik",
    "dengeli": "Dengeli",
    "en_iyi": "En yüksek doğruluk",
}

DEFAULTS: dict[str, Any] = {
    "notice_accepted": False,
    "ai": {
        "base_url": "https://openrouter.ai/api/v1",
        "profile": "dengeli",
        "roles": dict(PROFILES["dengeli"]),
        "data_collection_deny": True,
        "zdr": False,
        "max_candidates": 40,
        "batch_size": 8,
        "budget_per_query_usd": 0.50,
        "send_context_frame": True,
        "timeout_s": 120,
        "cli_paths": {},  # araç → exe yolu (boşsa PATH ve bilinen kurulum yerleri taranır)
    },
    "analysis": {
        "auto_analyze": True,
        "sample_fps": 2.0,
        "scan_fps": 1.0,
        "detector": "yolox_s",
        "min_conf": 0.35,
        "faces": True,
        "plates": True,
        "clip": True,
        "motion_threshold": 0.004,
        "device": "auto",
    },
    "time": {"tz": "Europe/Istanbul"},
    # Açılışta GitHub'a bağlanmak kullanıcının tercihidir (varsayılan kapalı; dışarıya izinsiz istek gitmez)
    "update": {"check_on_start": False, "last_check": None},
    "secrets": {},
}

_lock = threading.Lock()


def _path():
    return paths.data_dir() / "settings.json"


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict[str, Any]:
    with _lock:
        p = _path()
        data: dict = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                data = {}
        return _merge(DEFAULTS, data)


def save(s: dict[str, Any]) -> None:
    with _lock:
        p = _path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)


def update(patch: dict[str, Any]) -> dict[str, Any]:
    patch = {k: v for k, v in patch.items() if k != "secrets"}
    s = _merge(load(), patch)
    ai = s["ai"]
    if "profile" in (patch.get("ai") or {}) and "roles" not in patch["ai"] and ai["profile"] in PROFILES:
        ai["roles"] = dict(PROFILES[ai["profile"]])
    save(s)
    return s


def public(s: dict[str, Any] | None = None) -> dict[str, Any]:
    """Arayüze gönderilecek hali: gizli değerler maskelenir."""
    s = copy.deepcopy(s or load())
    key = get_api_key(s)
    s.pop("secrets", None)
    s["api_key_set"] = bool(key)
    s["api_key_masked"] = vault.mask(key)
    from .ai import client
    verifier = s["ai"]["roles"].get("verifier") or ""
    s["ai_source"] = "cli" if verifier.startswith("cli:") else "api"
    s["ai_ready"] = client.configured(verifier) if verifier.startswith("cli:") else bool(key) or (
        "openrouter.ai" not in s["ai"]["base_url"])
    s["profiles"] = {k: {"label": PROFILE_LABELS[k], "roles": v} for k, v in PROFILES.items()}
    return s


def get_api_key(s: dict[str, Any] | None = None) -> str | None:
    s = s or load()
    return vault.unprotect(s.get("secrets", {}).get("openrouter"))


def set_api_key(key: str | None) -> None:
    s = load()
    if key:
        s.setdefault("secrets", {})["openrouter"] = vault.protect(key.strip())
    else:
        s.setdefault("secrets", {}).pop("openrouter", None)
    save(s)
