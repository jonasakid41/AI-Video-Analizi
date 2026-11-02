from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_default)


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"JSON'a çevrilemiyor: {type(o)}")


def sha256_file(path: Path, progress=None) -> str:
    h = hashlib.sha256()
    total = path.stat().st_size or 1
    done = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done / total)
    return h.hexdigest()


def vec_to_blob(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def blob_to_vec(b: bytes | None) -> np.ndarray | None:
    if not b:
        return None
    return np.frombuffer(b, dtype=np.float32)


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


def parent_watchdog(pid: int) -> None:
    """Ebeveyn süreç kapanınca bu süreci de kapatır (Windows)."""
    import os
    import threading

    if os.name != "nt":
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not h:
        return

    def watch():
        k32.WaitForSingleObject(h, 0xFFFFFFFF)
        os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watchdog").start()


def remove_tree(path: Path, attempts: int = 5) -> None:
    """Klasörü siler; salt-okunur dosyaları (orijinal kopyalar) ve kısa süreli kilitleri (Windows) aşar."""
    import os
    import shutil
    import stat
    import time

    def force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    for i in range(attempts):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=force)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.4 * (i + 1))


def imwrite(path: Path, img: np.ndarray, quality: int = 88) -> None:
    """cv2.imwrite Windows'ta Türkçe karakterli yollarda başarısız olur; bu yüzden imencode + write."""
    import cv2
    ext = path.suffix.lower() or ".jpg"
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise ValueError(f"Görüntü kodlanamadı: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.tobytes())


def imread(path: Path) -> np.ndarray | None:
    import cv2
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def fmt_media_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
