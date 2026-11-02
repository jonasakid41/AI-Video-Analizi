"""ONNX Runtime oturumları: DirectML (her GPU) → CPU. Modeller models/ klasöründen yüklenir."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import onnxruntime as ort

from .. import paths, settings

log = logging.getLogger(__name__)
ort.set_default_logger_severity(3)

MODELS = {
    "yolox_s": ("detector/yolox_s.onnx", "Nesne tespiti (YOLOX-S)", "Apache-2.0"),
    "yolox_tiny": ("detector/yolox_tiny.onnx", "Nesne tespiti, hafif (YOLOX-Tiny)", "Apache-2.0"),
    "yunet": ("face/face_detection_yunet_2023mar.onnx", "Yüz tespiti (YuNet)", "MIT"),
    "sface": ("face/face_recognition_sface_2021dec.onnx", "Yüz tanıma (SFace)", "Apache-2.0"),
    "clip_vision": ("clip/vision_model_fp16.onnx", "Görsel arama — görüntü (CLIP)", "MIT"),
    "clip_text": ("clip/text_model_quantized.onnx", "Görsel arama — metin (CLIP)", "MIT"),
    "clip_tokenizer": ("clip/tokenizer.json", "CLIP sözcük ayırıcı", "MIT"),
    "esrgan_x2": ("upscale/real_esrgan_x2.onnx", "Büyütme x2 (Real-ESRGAN)", "BSD-3-Clause"),
    "esrgan_x4": ("upscale/real_esrgan_x4.onnx", "Büyütme x4 (Real-ESRGAN)", "BSD-3-Clause"),
}

_lock = threading.Lock()
_sessions: dict[tuple[str, bool], ort.InferenceSession] = {}


def model_path(key: str) -> Path:
    return paths.models_dir() / MODELS[key][0]


def has_model(key: str) -> bool:
    return model_path(key).exists()


def _providers(gpu: bool) -> list[str]:
    avail = ort.get_available_providers()
    device = settings.load()["analysis"].get("device", "auto")
    if gpu and device != "cpu" and "DmlExecutionProvider" in avail:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def session(key: str, gpu: bool = True) -> ort.InferenceSession:
    with _lock:
        k = (key, gpu)
        if k not in _sessions:
            p = model_path(key)
            if not p.exists():
                raise FileNotFoundError(f"Model bulunamadı: {p.name}. models/ klasörünü kontrol edin.")
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            provs = _providers(gpu)
            if provs[0] == "DmlExecutionProvider":
                opts.enable_mem_pattern = False  # DirectML gereksinimi
                opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            data = p.read_bytes()  # yol yerine bayt: Türkçe karakterli klasörlerde de çalışır
            try:
                _sessions[k] = ort.InferenceSession(data, sess_options=opts, providers=provs)
            except Exception as e:  # noqa: BLE001 — GPU açılamazsa CPU'ya düş
                log.warning("%s GPU ile açılamadı, CPU kullanılacak: %s", key, e)
                _sessions[k] = ort.InferenceSession(data, providers=["CPUExecutionProvider"])
        return _sessions[k]


def active_provider(key: str) -> str | None:
    for (k, _gpu), s in _sessions.items():
        if k == key:
            return s.get_providers()[0]
    return None


def device_info() -> dict:
    avail = ort.get_available_providers()
    return {
        "onnxruntime": ort.__version__,
        "providers": avail,
        "gpu": "DmlExecutionProvider" in avail,
        "label": "GPU (DirectML)" if "DmlExecutionProvider" in avail else "CPU",
    }


def models_status() -> list[dict]:
    out = []
    for key, (rel, label, lic) in MODELS.items():
        p = paths.models_dir() / rel
        out.append({"key": key, "label": label, "license": lic, "ok": p.exists(),
                    "size_mb": round(p.stat().st_size / 1e6, 1) if p.exists() else 0})
    return out
