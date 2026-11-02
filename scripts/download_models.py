"""Yerel analiz modellerini models/ klasörüne indirir.

Kullanım:  python scripts/download_models.py
Modeller git'e eklenmez; dağıtım paketine bu betikle indirilen dosyalar konur.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

HF = "https://huggingface.co"
GH_YOLOX = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"

# (hedef yol, kaynak URL, lisans)
FILES: list[tuple[str, str, str]] = [
    ("detector/yolox_s.onnx", f"{GH_YOLOX}/yolox_s.onnx", "Apache-2.0"),
    ("detector/yolox_tiny.onnx", f"{GH_YOLOX}/yolox_tiny.onnx", "Apache-2.0"),
    ("face/face_detection_yunet_2023mar.onnx",
     f"{HF}/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx", "MIT"),
    ("face/face_recognition_sface_2021dec.onnx",
     f"{HF}/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx", "Apache-2.0"),
    ("clip/vision_model_fp16.onnx",
     f"{HF}/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_fp16.onnx", "MIT"),
    ("clip/text_model_quantized.onnx",
     f"{HF}/Xenova/clip-vit-base-patch32/resolve/main/onnx/text_model_quantized.onnx", "MIT"),
    ("clip/tokenizer.json",
     f"{HF}/Xenova/clip-vit-base-patch32/resolve/main/tokenizer.json", "MIT"),
    ("upscale/real_esrgan_x2.onnx",
     f"{HF}/SceneWorks/real-esrgan-onnx/resolve/main/real_esrgan_x2.onnx", "BSD-3-Clause"),
    ("upscale/real_esrgan_x4.onnx",
     f"{HF}/SceneWorks/real-esrgan-onnx/resolve/main/real_esrgan_x4.onnx", "BSD-3-Clause"),
    ("upscale/README.md", f"{HF}/SceneWorks/real-esrgan-onnx/resolve/main/README.md", "BSD-3-Clause"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    for rel, url, lic in FILES:
        dest = MODELS / rel
        if dest.exists() and dest.stat().st_size > 0:
            print(f"var      {rel}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        print(f"indir    {rel}  ({lic})", flush=True)
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
        print(f"         {dest.stat().st_size / 1e6:.1f} MB  sha256={sha256(dest)[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
