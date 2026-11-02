"""AI uçları: model kataloğu, sorular, bulgular; iyileştirme, dışa aktarma, rapor."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import enhance, evaluate, evidence, export, jobs, query
from ..ai import catalog

router = APIRouter(prefix="/api")


@router.get("/models")
def models(refresh: bool = False) -> dict:
    try:
        return catalog.fetch(refresh)
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e


# --- sorular -------------------------------------------------------------------------

class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: str = "dogrula"
    evidence_ids: list[int] | None = None
    roi_id: int | None = None
    max_candidates: int | None = None
    budget_usd: float | None = None


@router.post("/cases/{case_id}/queries/estimate")
def query_estimate(case_id: int, body: QueryIn) -> dict:
    return query.estimate(case_id, body.question, body.model_dump(exclude_none=True))


@router.post("/cases/{case_id}/queries")
def query_create(case_id: int, body: QueryIn) -> dict:
    if body.mode not in query.MODES:
        raise HTTPException(400, "Geçersiz mod")
    opts = body.model_dump(exclude_none=True)
    opts.pop("question", None)
    return query.create(case_id, body.question, opts)


@router.get("/cases/{case_id}/queries")
def query_list(case_id: int) -> list[dict]:
    return query.list_for_case(case_id)


@router.get("/queries/{query_id}")
def query_get(query_id: int) -> dict:
    return query.get(query_id)


@router.delete("/queries/{query_id}")
def query_delete(query_id: int) -> dict:
    query.delete(query_id)
    return {"ok": True}


# --- model karşılaştırma ---------------------------------------------------------------

class LabelsIn(BaseModel):
    labels: dict[str, bool | None]


@router.put("/queries/{query_id}/labels")
def query_labels(query_id: int, body: LabelsIn) -> dict:
    return {"labels": evaluate.set_labels(query_id, body.labels)}


class EvaluateIn(BaseModel):
    models: list[str] = Field(min_length=1, max_length=evaluate.MAX_MODELS)
    dry_run: bool = False


@router.post("/queries/{query_id}/evaluate")
def query_evaluate(query_id: int, body: EvaluateIn) -> dict:
    if body.dry_run:
        return evaluate.estimate(query_id, body.models)
    return evaluate.start(query_id, body.models)


@router.get("/queries/{query_id}/evaluations")
def query_evaluations(query_id: int) -> list[dict]:
    return evaluate.for_query(query_id)


@router.get("/cases/{case_id}/evaluations/summary")
def evaluations_summary(case_id: int) -> list[dict]:
    return evaluate.summary(case_id)


# --- bulgular -------------------------------------------------------------------------

class FindingIn(BaseModel):
    evidence_id: int | None = None
    t: float | None = None
    title: str = Field(min_length=1, max_length=300)
    note: str = ""
    source: str = "elle"
    confidence: float | None = None
    box: list[float] | None = None
    data: dict | None = None


class FindingPatch(BaseModel):
    status: str | None = None
    note: str | None = None
    title: str | None = None


@router.get("/cases/{case_id}/findings")
def findings(case_id: int) -> list[dict]:
    return query.findings_for(case_id)


@router.post("/cases/{case_id}/findings")
def finding_create(case_id: int, body: FindingIn) -> dict:
    return query.finding_create(case_id, body.evidence_id, body.t, body.title, body.note, body.source,
                                body.confidence, body.box, body.data)


@router.patch("/findings/{finding_id}")
def finding_patch(finding_id: int, body: FindingPatch) -> dict:
    return query.finding_update(finding_id, body.status, body.note, body.title)


@router.delete("/findings/{finding_id}")
def finding_delete(finding_id: int) -> dict:
    query.finding_delete(finding_id)
    return {"ok": True}


# --- iyileştirme / dışa aktarma / rapor -------------------------------------------------

class EnhanceIn(BaseModel):
    t: float
    box: list[float] | None = None
    ops: list[dict] = Field(default_factory=list)


@router.get("/enhance/ops")
def enhance_ops() -> dict:
    return {"ops": enhance.OPS, "ai_warning": enhance.AI_WATERMARK}


@router.post("/evidence/{evidence_id}/enhance")
def enhance_run(evidence_id: int, body: EnhanceIn) -> dict:
    ev = evidence.require(evidence_id)
    return {"job_id": jobs.submit("enhance", {"evidence_id": evidence_id, "t": body.t, "box": body.box,
                                              "ops": body.ops}, ev["case_id"], evidence_id)}


class FrameIn(BaseModel):
    t: float


@router.post("/evidence/{evidence_id}/export-frame")
def export_frame(evidence_id: int, body: FrameIn) -> dict:
    return export.frame(evidence_id, body.t)


class ClipIn(BaseModel):
    t0: float
    t1: float


@router.post("/evidence/{evidence_id}/export-clip")
def export_clip(evidence_id: int, body: ClipIn) -> dict:
    ev = evidence.require(evidence_id)
    if body.t1 - body.t0 > 1800:
        raise HTTPException(400, "Kesit en fazla 30 dakika olabilir")
    return {"job_id": jobs.submit("export_clip", {"evidence_id": evidence_id, "t0": body.t0, "t1": body.t1},
                                  ev["case_id"], evidence_id)}


class ReportIn(BaseModel):
    include_candidates: bool = False


@router.post("/cases/{case_id}/report")
def report(case_id: int, body: ReportIn) -> dict:
    return {"job_id": jobs.submit("report", {"case_id": case_id, "include_candidates": body.include_candidates},
                                  case_id)}
