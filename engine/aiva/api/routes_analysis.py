"""Analiz uçları: analiz başlatma, aktivite, izler, tespitler, yüzler/kişiler, plakalar, alanlar."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import evidence, history, jobs, results
from ..analyze import faces as facemod
from ..util import imread

router = APIRouter(prefix="/api")


class AnalyzeIn(BaseModel):
    options: dict = Field(default_factory=dict)


@router.post("/evidence/{evidence_id}/analyze")
def analyze(evidence_id: int, body: AnalyzeIn) -> dict:
    ev = evidence.require(evidence_id)
    if ev["status"] != "hazir":
        raise HTTPException(400, "Video henüz hazır değil")
    return {"job_id": jobs.submit("analyze", {"evidence_id": evidence_id, "options": body.options},
                                  ev["case_id"], evidence_id)}


@router.get("/evidence/{evidence_id}/activity")
def activity(evidence_id: int, buckets: int = 600) -> dict:
    return results.activity(evidence_id, max(50, min(buckets, 4000)))


@router.get("/evidence/{evidence_id}/tracks")
def tracks(evidence_id: int, cls: str | None = None, t0: float | None = None, t1: float | None = None) -> list[dict]:
    return results.tracks(evidence_id, cls, t0, t1)


@router.get("/tracks/{track_id}")
def track(track_id: int) -> dict:
    return results.track(track_id)


@router.get("/evidence/{evidence_id}/detections")
def detections(evidence_id: int, t: float, window: float = 0.6) -> list[dict]:
    return results.detections_near(evidence_id, t, window)


@router.get("/evidence/{evidence_id}/detections/range")
def detections_range(evidence_id: int, t0: float, t1: float) -> list[dict]:
    if t1 - t0 > 600:
        raise HTTPException(400, "En fazla 10 dakikalık aralık istenebilir")
    return results.detections_range(evidence_id, t0, t1)


@router.get("/evidence/{evidence_id}/faces")
def faces(evidence_id: int) -> list[dict]:
    return results.faces_for(evidence_id)


@router.get("/evidence/{evidence_id}/plates")
def plates(evidence_id: int) -> list[dict]:
    return results.plates_for(evidence_id)


@router.get("/cases/{case_id}/people")
def people(case_id: int) -> list[dict]:
    return results.people(case_id)


class FaceSearchIn(BaseModel):
    face_id: int | None = None
    image_path: str | None = None
    threshold: float = facemod.MATCH_THRESHOLD


@router.post("/cases/{case_id}/face-search")
def face_search(case_id: int, body: FaceSearchIn) -> dict:
    if body.face_id:
        vec = results.face_vector(body.face_id)
        source = {"face_id": body.face_id}
    elif body.image_path:
        img = imread(Path(body.image_path))
        if img is None:
            raise HTTPException(400, "Fotoğraf açılamadı")
        found = facemod.detect_and_embed(img)
        if not found:
            raise HTTPException(400, "Fotoğrafta yüz bulunamadı")
        f, vec = max(found, key=lambda fv: fv[0].w * fv[0].h)
        source = {"image": Path(body.image_path).name}
    else:
        raise HTTPException(400, "Yüz ya da fotoğraf seçilmeli")
    matches = results.face_search(case_id, vec, body.threshold)
    history.log("yuz_aramasi", case_id, **source, esik=body.threshold, sonuc=len(matches))
    return {"matches": matches, "threshold": body.threshold,
            "note": "Yüz benzerliği bir soruşturma ipucudur; kimlik tespiti için tek başına yeterli değildir."}


@router.get("/cases/{case_id}/plate-search")
def plate_search(case_id: int, q: str, min_sim: float = 0.6) -> list[dict]:
    if len(q.strip()) < 2:
        raise HTTPException(400, "En az 2 karakter girin")
    out = results.plate_search(case_id, q, min_sim)
    history.log("plaka_aramasi", case_id, sorgu=q, sonuc=len(out))
    return out


class RoiIn(BaseModel):
    name: str = "Alan"
    kind: str = "alan"
    points: list[list[float]]


@router.get("/evidence/{evidence_id}/rois")
def rois(evidence_id: int) -> list[dict]:
    return results.rois(evidence_id)


@router.post("/evidence/{evidence_id}/rois")
def roi_create(evidence_id: int, body: RoiIn) -> dict:
    ev = evidence.require(evidence_id)
    r = results.roi_create(evidence_id, body.name, body.kind, body.points)
    history.log("alan_eklendi", ev["case_id"], evidence_id, ad=body.name, tur=body.kind)
    return r


@router.delete("/rois/{roi_id}")
def roi_delete(roi_id: int) -> dict:
    results.roi_delete(roi_id)
    return {"ok": True}


@router.get("/rois/{roi_id}/events")
def roi_events(roi_id: int) -> list[dict]:
    return results.roi_events(results.roi_get(roi_id))
