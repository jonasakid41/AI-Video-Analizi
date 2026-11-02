"""Medya uçları: proxy video (Range), küçük resim, önizleme şeridi, tam kare, dosyalar."""

from __future__ import annotations

import os
from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .. import evidence, paths
from ..media import frames

router = APIRouter(prefix="/api")

NO_CACHE = {"Cache-Control": "no-store"}


@router.get("/evidence/{evidence_id}/proxy")
def proxy(evidence_id: int):
    ev = evidence.require(evidence_id)
    p = evidence.proxy_file(ev)
    if not p.exists():
        raise HTTPException(404, "Çalışma kopyası henüz hazır değil")
    return FileResponse(p, media_type="video/mp4")


@router.get("/evidence/{evidence_id}/thumb")
def thumb(evidence_id: int):
    ev = evidence.require(evidence_id)
    p = evidence.folder(ev) / "thumb.jpg"
    if not p.exists():
        raise HTTPException(404, "Küçük resim yok")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/evidence/{evidence_id}/sprite")
def sprite(evidence_id: int):
    ev = evidence.require(evidence_id)
    p = evidence.folder(ev) / "sprite.jpg"
    if not p.exists():
        raise HTTPException(404, "Önizleme şeridi yok")
    return FileResponse(p, media_type="image/jpeg")


@router.get("/evidence/{evidence_id}/frame")
def frame(evidence_id: int, t: float, w: int = 0, q: int = 88, crop: str | None = None):
    """Kayıpsız kopyadan t anındaki kare. crop = "x,y,w,h" (0–1 normalize)."""
    ev = evidence.require(evidence_id)
    src = evidence.evidence_file(ev)
    if src is None:
        raise HTTPException(404, "Video henüz dönüştürülmedi")
    got = frames.frame_at(src, t)
    if got is None:
        raise HTTPException(404, "Kare bulunamadı")
    ft, img = got
    if crop:
        x, y, cw, ch = (float(v) for v in crop.split(","))
        H, W = img.shape[:2]
        x0, y0 = max(0, int(x * W)), max(0, int(y * H))
        x1, y1 = min(W, int((x + cw) * W)), min(H, int((y + ch) * H))
        if x1 > x0 and y1 > y0:
            img = img[y0:y1, x0:x1]
    if w and w > 0:
        img = frames.resize_to_width(img, w)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, max(30, min(q, 98))])
    if not ok:
        raise HTTPException(500, "Kare kodlanamadı")
    return Response(buf.tobytes(), media_type="image/jpeg", headers={**NO_CACHE, "X-Frame-Time": f"{ft:.4f}"})


@router.get("/files")
def files(path: str):
    """Yalnızca data/ klasörü içindeki dosyalar (kırpıntılar, dışa aktarımlar)."""
    p = Path(path)
    if not p.is_absolute():
        p = paths.data_dir() / p
    if not paths.is_inside_data(p) or not p.is_file():
        raise HTTPException(404, "Dosya bulunamadı")
    return FileResponse(p)


@router.post("/open-folder")
def open_folder(path: str):
    """Windows Gezgini'nde klasörü açar (yalnızca data/ içinde)."""
    p = Path(path)
    if not p.is_absolute():
        p = paths.data_dir() / p
    if not paths.is_inside_data(p):
        raise HTTPException(400, "Yalnızca veri klasörü açılabilir")
    target = p if p.is_dir() else p.parent
    while not target.exists() and paths.is_inside_data(target.parent):
        target = target.parent
    if os.name == "nt":
        os.startfile(str(target))  # noqa: S606 — yerel, kullanıcının kendi klasörü
    return {"ok": True}
