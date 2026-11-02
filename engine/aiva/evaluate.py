"""Model karşılaştırma: aynı soru ve aynı yerel adaylar birden çok modele doğrulatılır.

Kullanıcı sonuçları "doğru / yanlış" diye işaretlediyse her model için isabet (precision),
duyarlılık (recall) ve doğruluk hesaplanır; işaret yoksa yalnızca eşleşme sayıları, maliyet ve süre
karşılaştırılır. Sonuçlar yerelde saklanır; model seçimini veriye dayandırmak içindir.
"""

from __future__ import annotations

import time
from dataclasses import fields

from . import db, events, history, jobs, query, settings
from .ai import verify as verifymod
from .ai.search import Candidate
from .util import dumps, loads, now_iso

MAX_CANDIDATES = 24
MAX_MODELS = 5
_CAND_FIELDS = {f.name for f in fields(Candidate)}


def labels(query_id: int) -> dict[str, bool]:
    r = db.row("SELECT labels FROM queries WHERE id = ?", (query_id,))
    if r is None:
        raise KeyError("Sorgu bulunamadı")
    return loads(r["labels"], {}) or {}


def set_labels(query_id: int, changes: dict[str, bool | None]) -> dict[str, bool]:
    cur = labels(query_id)
    for k, v in changes.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = bool(v)
    db.execute("UPDATE queries SET labels = ? WHERE id = ?", (dumps(cur), query_id))
    return cur


def _candidates(q: dict, lab: dict[str, bool]) -> list[Candidate]:
    items = q.get("results") or []
    # İşaretlenmiş sonuçlar önce: ölçüm onlarla yapılır
    items = sorted(items, key=lambda i: (i["id"] not in lab, -i.get("score", 0)))
    if lab:
        items = [i for i in items if i["id"] in lab] or items
    return [Candidate(**{k: v for k, v in i.items() if k in _CAND_FIELDS}) for i in items[:MAX_CANDIDATES]]


def estimate(query_id: int, models: list[str]) -> dict:
    q = query.get(query_id)
    cands = _candidates(q, labels(query_id))
    s = settings.load()["ai"]
    per = {m: verifymod.estimate(m, cands, s["send_context_frame"], int(s["batch_size"])) for m in models}
    return {"candidates": len(cands), "per_model": per, "total": round(sum(per.values()), 5)}


def start(query_id: int, models: list[str]) -> dict:
    models = [m.strip() for m in dict.fromkeys(models) if m and m.strip()]
    if not 1 <= len(models) <= MAX_MODELS:
        raise ValueError(f"1 ile {MAX_MODELS} arasında model seçin")
    q = query.get(query_id)
    if q["status"] != "tamamlandi" or not q.get("results"):
        raise ValueError("Karşılaştırma için sonuçları olan tamamlanmış bir soru gerekir")
    eid = db.insert("evaluations", {"case_id": q["case_id"], "query_id": query_id, "models": dumps(models),
                                    "status": "beklemede", "created_at": now_iso()})
    jid = jobs.submit("evaluate", {"evaluation_id": eid}, case_id=q["case_id"])
    return {"evaluation_id": eid, "job_id": jid}


def get(eval_id: int) -> dict:
    r = db.row("SELECT * FROM evaluations WHERE id = ?", (eval_id,))
    if not r:
        raise KeyError("Karşılaştırma bulunamadı")
    r["models"] = loads(r["models"], [])
    r["results"] = loads(r["results"], [])
    return r


def for_query(query_id: int) -> list[dict]:
    return [get(r["id"]) for r in db.rows("SELECT id FROM evaluations WHERE query_id = ? ORDER BY id DESC", (query_id,))]


def summary(case_id: int) -> list[dict]:
    """Vakadaki tüm karşılaştırmalardan model başına ortalama."""
    agg: dict[str, dict] = {}
    for r in db.rows("SELECT results FROM evaluations WHERE case_id = ? AND status = 'tamamlandi'", (case_id,)):
        for m in loads(r["results"], []):
            a = agg.setdefault(m["model"], {"model": m["model"], "runs": 0, "cost": 0.0, "seconds": 0.0, "p": [], "r": []})
            a["runs"] += 1
            a["cost"] += m["cost"]
            a["seconds"] += m["seconds"]
            if m.get("precision") is not None:
                a["p"].append(m["precision"])
            if m.get("recall") is not None:
                a["r"].append(m["recall"])
    out = []
    for a in agg.values():
        out.append({"model": a["model"], "runs": a["runs"], "cost": round(a["cost"], 5), "seconds": round(a["seconds"], 1),
                    "precision": round(sum(a["p"]) / len(a["p"]), 3) if a["p"] else None,
                    "recall": round(sum(a["r"]) / len(a["r"]), 3) if a["r"] else None})
    return sorted(out, key=lambda x: (-(x["precision"] or 0) - (x["recall"] or 0), x["cost"]))


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


@jobs.register("evaluate")
def evaluate_job(ctx: jobs.JobContext, params: dict) -> dict:
    ev = get(params["evaluation_id"])
    q = query.get(ev["query_id"])
    lab = labels(ev["query_id"])
    cands = _candidates(q, lab)
    question = (q.get("plan") or {}).get("verify_question") or q["question"]
    s = settings.load()["ai"]
    db.update("evaluations", ev["id"], {"status": "calisiyor"})
    results = []
    try:
        for i, model in enumerate(ev["models"]):
            ctx.progress(i / len(ev["models"]), f"{model} değerlendiriliyor ({len(cands)} aday)")
            t0 = time.monotonic()
            verdicts, usage = verifymod.verify(
                cands, question, model, case_id=q["case_id"], query_id=q["id"], batch=int(s["batch_size"]),
                with_context=bool(s["send_context_frame"]),
                progress=lambda v, i=i: ctx.progress((i + v) / len(ev["models"]), f"{model} değerlendiriliyor"))
            secs = round(time.monotonic() - t0, 2)
            matched = {k for k, v in verdicts.items() if v["match"]}
            row = {"model": model, "candidates": len(cands), "answered": len(verdicts), "matched": len(matched),
                   "cost": round(usage["cost"], 6), "seconds": secs, "errors": usage["errors"][:2],
                   "verdicts": {k: {"match": v["match"], "confidence": v["confidence"]} for k, v in verdicts.items()}}
            if lab:
                ids = {c.id for c in cands}
                pos = {k for k, v in lab.items() if v and k in ids}
                neg = {k for k, v in lab.items() if not v and k in ids}
                tp, fp = len(matched & pos), len(matched & neg)
                fn, tn = len(pos - matched), len(neg - matched)
                row.update({"labeled": len(pos) + len(neg), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
                            "accuracy": _ratio(tp + tn, tp + tn + fp + fn)})
            results.append(row)
            db.update("evaluations", ev["id"], {"results": dumps(results)})
        db.update("evaluations", ev["id"], {"status": "tamamlandi", "finished_at": now_iso()})
    except jobs.Cancelled:
        db.update("evaluations", ev["id"], {"status": "iptal", "finished_at": now_iso()})
        raise
    except Exception as e:
        db.update("evaluations", ev["id"], {"status": "hata", "error": str(e), "finished_at": now_iso()})
        raise
    history.log("model_karsilastirma", q["case_id"], soru=q["question"], modeller=ev["models"],
                isaretli=len(lab), maliyet_usd=round(sum(r["cost"] for r in results), 4))
    events.publish("evaluation", evaluation_id=ev["id"], query_id=q["id"], case_id=q["case_id"])
    return {"evaluation_id": ev["id"], "models": len(results)}
