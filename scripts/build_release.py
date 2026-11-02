"""Taşınabilir dağıtım paketi üretir: dist/AIVideoAnalizi/ ve dist/AIVideoAnalizi-<sürüm>-win64.zip

Adımlar:
  1. Analiz motoru (PyInstaller, onedir)          → engine/dist/aiva-engine/
  2. Arayüz (Vite) + masaüstü kabuğu (Tauri, release) → app/src-tauri/target/release/ai-video-analizi.exe
  3. Klasör düzeni: AIVideoAnalizi.exe, engine/, models/, lisanslar, BENIOKU.txt
  4. ZIP

Kullanım:  engine/.venv/Scripts/python.exe scripts/build_release.py [--skip-engine] [--skip-app] [--no-zip]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
APP = ROOT / "app"
DIST = ROOT / "dist"
NAME = "AIVideoAnalizi"
sys.path.insert(0, str(ENGINE))
from aiva import __version__  # noqa: E402

MODEL_FILES = [
    "detector/yolox_s.onnx", "detector/yolox_tiny.onnx",
    "face/face_detection_yunet_2023mar.onnx", "face/face_recognition_sface_2021dec.onnx",
    "clip/vision_model_fp16.onnx", "clip/text_model_quantized.onnx", "clip/tokenizer.json",
    "upscale/real_esrgan_x2.onnx", "upscale/real_esrgan_x4.onnx",
]


def run(cmd: list[str], cwd: Path) -> None:
    print("»", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=(sys.platform == "win32" and cmd[0] in ("npm", "npx")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-engine", action="store_true")
    ap.add_argument("--skip-app", action="store_true")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()

    missing = [m for m in MODEL_FILES if not (ROOT / "models" / m).exists()]
    if missing:
        print("Eksik modeller; önce: python scripts/download_models.py", missing)
        return 1

    if not args.skip_engine:
        run([str(ENGINE / ".venv" / "Scripts" / "python.exe"), "-m", "PyInstaller", "aiva-engine.spec", "--noconfirm"], ENGINE)
    if not args.skip_app:
        run(["npx", "tauri", "build", "--no-bundle"], APP)

    out = DIST / NAME
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy2(APP / "src-tauri" / "target" / "release" / "ai-video-analizi.exe", out / f"{NAME}.exe")
    shutil.copytree(ENGINE / "dist" / "aiva-engine", out / "engine")
    for m in MODEL_FILES:
        dst = out / "models" / m
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "models" / m, dst)
    shutil.copy2(ROOT / "LICENSE", out / "LICENSE.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.txt", out / "THIRD_PARTY_NOTICES.txt")
    shutil.copy2(ROOT / "docs" / "BENIOKU.txt", out / "BENIOKU.txt")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Klasör hazır: {out}  ({size / 1e9:.2f} GB)")

    if not args.no_zip:
        zpath = DIST / f"{NAME}-{__version__}-win64.zip"
        zpath.unlink(missing_ok=True)
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(out.rglob("*")):
                if p.is_file():
                    z.write(p, Path(NAME) / p.relative_to(out))
        print(f"ZIP hazır: {zpath}  ({zpath.stat().st_size / 1e9:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
