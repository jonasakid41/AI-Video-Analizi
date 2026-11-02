"""Temel uçlar: sağlık, ayarlar, vakalar, videolar, saat, işler, geçmiş."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import __version__, cases, evidence, history, jobs, paths, settings, timeservice, update
from ..analyze import runtime
from ..media import encoders
from ..util import now_iso
from . import deps

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@router.get("/power")
def power() -> dict:
    """Dizüstü bilgisayar pilde mi? (Windows GetSystemPowerStatus)"""
    import ctypes
    import sys

    if sys.platform != "win32":
        return {"on_battery": False, "percent": None}

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    s = SPS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
        return {"on_battery": False, "percent": None}
    has_battery = s.BatteryFlag != 128 and s.BatteryFlag != 255
    return {"on_battery": has_battery and s.ACLineStatus == 0,
            "percent": s.BatteryLifePercent if s.BatteryLifePercent <= 100 else None}


@router.get("/system")
def system() -> dict:
    return {
        "version": __version__,
        "data_dir": str(paths.data_dir()),
        "models_dir": str(paths.models_dir()),
        "frozen": paths.is_frozen(),
        "encoders": encoders.available(),
        "encoder": encoders.choose(),
        "inference": runtime.device_info(),
        "models": runtime.models_status(),
    }


class ClientLogIn(BaseModel):
    where: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=4000)
    stack: str = Field(default="", max_length=20000)


@router.post("/log")
def client_log(body: ClientLogIn) -> dict:
    """Arayüz hataları (çizim hatası, yakalanmamış istisna) data/logs/arayuz.log dosyasına yazılır."""
    p = paths.logs_dir() / "arayuz.log"
    if p.exists() and p.stat().st_size > 1_000_000:
        p.replace(p.with_name("arayuz.log.1"))
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {__version__} {body.where}: {body.message}\n{body.stack.strip()}\n\n")
    return {"ok": True}


# --- güncelleme --------------------------------------------------------------------

class UpdateIn(BaseModel):
    version: str = Field(min_length=1, max_length=40)


@router.get("/update")
def update_status() -> dict:
    return update.status()


@router.post("/update/check")
def update_check() -> dict:
    update.check()
    return update.status()


@router.post("/update/download")
def update_download(body: UpdateIn) -> dict:
    return {"job_id": update.start_download(body.version)}


@router.delete("/update/staged")
def update_discard() -> dict:
    update.discard()
    return update.status()


@router.post("/update/ack")
def update_ack() -> dict:
    update.ack_result()
    return update.status()


# --- ayarlar -----------------------------------------------------------------------

@router.get("/settings")
def get_settings() -> dict:
    return settings.public()


@router.put("/settings")
def put_settings(patch: dict[str, Any]) -> dict:
    return settings.public(settings.update(patch))


class ApiKeyIn(BaseModel):
    key: str = Field(min_length=8)


@router.put("/settings/api-key")
def put_api_key(body: ApiKeyIn) -> dict:
    settings.set_api_key(body.key)
    return settings.public()


@router.delete("/settings/api-key")
def delete_api_key() -> dict:
    settings.set_api_key(None)
    return settings.public()


# --- vakalar -----------------------------------------------------------------------

class CaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class CasePatch(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("/cases")
def list_cases() -> list[dict]:
    return cases.list_all()


@router.post("/cases")
def create_case(body: CaseIn) -> dict:
    return cases.create(body.name, body.description)


@router.get("/cases/{case_id}")
def get_case(case_id: int) -> dict:
    c = cases.get(case_id)
    if not c:
        raise deps.not_found("Vaka")
    return c


@router.patch("/cases/{case_id}")
def patch_case(case_id: int, body: CasePatch) -> dict:
    c = cases.update(case_id, body.name, body.description)
    if not c:
        raise deps.not_found("Vaka")
    return c


@router.delete("/cases/{case_id}")
def delete_case(case_id: int) -> dict:
    cases.delete(case_id)
    return {"ok": True}


@router.get("/cases/{case_id}/history")
def case_history(case_id: int) -> list[dict]:
    return history.list_for_case(case_id)


# --- videolar ------------------------------------------------------------------------

class EvidenceIn(BaseModel):
    paths: list[str] = Field(min_length=1)
    camera: str = ""


class EvidencePatch(BaseModel):
    camera: str | None = None


@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id: int) -> list[dict]:
    return evidence.list_for_case(case_id)


@router.post("/cases/{case_id}/evidence")
def add_evidence(case_id: int, body: EvidenceIn) -> dict:
    ids = evidence.add(case_id, body.paths, body.camera)
    return {"ids": ids}


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: int) -> dict:
    return evidence.public(evidence.require(evidence_id))


@router.patch("/evidence/{evidence_id}")
def patch_evidence(evidence_id: int, body: EvidencePatch) -> dict:
    return evidence.update(evidence_id, body.camera)


@router.delete("/evidence/{evidence_id}")
def delete_evidence(evidence_id: int) -> dict:
    evidence.delete(evidence_id)
    return {"ok": True}


@router.post("/evidence/{evidence_id}/reingest")
def reingest(evidence_id: int) -> dict:
    ev = evidence.require(evidence_id)
    return {"job_id": jobs.submit("ingest", {"evidence_id": evidence_id}, ev["case_id"], evidence_id)}


@router.get("/evidence/{evidence_id}/diagnostics")
def diagnostics(evidence_id: int) -> dict:
    ev = evidence.require(evidence_id)
    p = evidence.folder(ev) / "teshis.txt"
    return {"path": str(p) if p.exists() else None, "text": p.read_text(encoding="utf-8") if p.exists() else ""}


# --- saat ----------------------------------------------------------------------------

class TimeIn(BaseModel):
    camera_start: str | None = None
    corrections: list[list[str]] | None = None
    references: list[dict] | None = None
    tz: str | None = None
    reason: str = ""
    apply_to_camera: bool = False


class OsdIn(BaseModel):
    region: list[float] | None = None
    every: float = 10.0


@router.get("/evidence/{evidence_id}/time")
def get_time(evidence_id: int) -> dict:
    evidence.require(evidence_id)
    m = evidence.get_mapping(evidence_id)
    return {"mapping": m.to_dict(), "summary": m.summary(), "versions": evidence.mapping_versions(evidence_id),
            "readings": timeservice.readings(evidence_id)}


@router.put("/evidence/{evidence_id}/time")
def put_time(evidence_id: int, body: TimeIn) -> dict:
    timeservice.set_manual(evidence_id, body.camera_start, body.corrections, body.references, body.tz,
                           body.reason, body.apply_to_camera)
    return get_time(evidence_id)


@router.post("/evidence/{evidence_id}/time/osd")
def osd_scan(evidence_id: int, body: OsdIn) -> dict:
    ev = evidence.require(evidence_id)
    return {"job_id": jobs.submit("osd_scan", {"evidence_id": evidence_id, "region": body.region,
                                               "every": body.every}, ev["case_id"], evidence_id)}


@router.get("/evidence/{evidence_id}/time/at")
def time_at(evidence_id: int, t: float) -> dict:
    return timeservice.describe(evidence.get_mapping(evidence_id), t)


# --- işler ---------------------------------------------------------------------------

@router.get("/jobs")
def list_jobs(case_id: int | None = None, active: bool = False) -> list[dict]:
    return jobs.list_jobs(case_id, active_only=active)


@router.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict:
    j = jobs.get(job_id)
    if not j:
        raise deps.not_found("İş")
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    return {"ok": jobs.cancel(job_id)}
