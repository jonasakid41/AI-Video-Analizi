"""Uygulama klasörleri.

Dağıtım (taşınabilir) düzeni:
    AIVideoAnalizi/
      AIVideoAnalizi.exe
      engine/aiva-engine.exe      <- sys.executable
      models/
      data/                       <- tüm kullanıcı verisi

Geliştirme düzeninde kök, depo köküdür. AIVA_DATA_DIR / AIVA_MODELS_DIR ile ezilebilir.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    env = os.environ.get("AIVA_DATA_DIR")
    p = Path(env) if env else app_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    env = os.environ.get("AIVA_MODELS_DIR")
    return Path(env) if env else app_root() / "models"


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def cases_dir() -> Path:
    return _sub("cases")


def cache_dir() -> Path:
    return _sub("cache")


def tmp_dir() -> Path:
    return _sub("tmp")


def logs_dir() -> Path:
    return _sub("logs")


def case_dir(case_id: int) -> Path:
    p = cases_dir() / str(case_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def evidence_dir(case_id: int, evidence_id: int) -> Path:
    p = case_dir(case_id) / "evidence" / str(evidence_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir(case_id: int) -> Path:
    p = case_dir(case_id) / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_inside_data(path: Path) -> bool:
    try:
        path.resolve().relative_to(data_dir().resolve())
        return True
    except ValueError:
        return False
