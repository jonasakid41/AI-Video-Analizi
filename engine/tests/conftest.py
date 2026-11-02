from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synth  # noqa: E402

REPO = ENGINE.parent
MODELS = REPO / "models"


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> tuple[Path, dict]:
    d = tmp_path_factory.mktemp("corpus")
    files = synth.build_corpus(d)
    return d, files


@pytest.fixture(scope="session")
def osd_video(tmp_path_factory) -> tuple[Path, synth.Scene]:
    d = tmp_path_factory.mktemp("osd")
    p = d / "osd.mp4"
    sc = synth.build_osd_video(p)
    return p, sc


@pytest.fixture()
def data_dir(tmp_path, monkeypatch) -> Path:
    """Her test için temiz bir data/ klasörü ve veritabanı."""
    d = tmp_path / "data"
    monkeypatch.setenv("AIVA_DATA_DIR", str(d))
    monkeypatch.setenv("AIVA_MODELS_DIR", str(MODELS))
    from aiva import db
    db.init(d / "aiva.sqlite")
    yield d
    db.close_thread_connection()


def models_available(*rel: str) -> bool:
    return all((MODELS / r).exists() for r in rel)


needs_models = pytest.mark.skipif(
    not models_available("detector/yolox_s.onnx", "face/face_detection_yunet_2023mar.onnx"),
    reason="models/ indirilmemiş (scripts/download_models.py)",
)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
