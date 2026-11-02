"""İş kuyruğu: dönüştürme, analiz, sorgu gibi uzun işler arka planda çalışır.

GPU kullanan işler `gpu_lock` ile sıraya girer (dizüstü VRAM'i sınırlı).
"""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import db, events
from .util import dumps, loads, now_iso

gpu_lock = threading.Lock()


class Cancelled(Exception):
    pass


class JobContext:
    def __init__(self, job_id: int):
        self.job_id = job_id
        self.cancel_event = threading.Event()
        self._last_push = 0.0

    def progress(self, value: float, message: str | None = None) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()
        now = time.monotonic()
        if now - self._last_push < 0.25 and value < 1.0:
            return
        self._last_push = now
        data: dict[str, Any] = {"progress": round(max(0.0, min(1.0, value)), 4)}
        if message is not None:
            data["message"] = message
        db.update("jobs", self.job_id, data)
        _push(self.job_id)

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()


JobFn = Callable[[JobContext, dict], Any]

_registry: dict[str, JobFn] = {}
_contexts: dict[int, JobContext] = {}
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def register(kind: str) -> Callable[[JobFn], JobFn]:
    def deco(fn: JobFn) -> JobFn:
        _registry[kind] = fn
        return fn
    return deco


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="aiva-job")
        return _executor


def recover_interrupted() -> None:
    db.execute(
        "UPDATE jobs SET status='yarida_kaldi', message='Uygulama kapandığı için yarıda kaldı' "
        "WHERE status IN ('beklemede','calisiyor')"
    )


def submit(kind: str, params: dict, case_id: int | None = None, evidence_id: int | None = None) -> int:
    if kind not in _registry:
        raise KeyError(f"Bilinmeyen iş türü: {kind}")
    job_id = db.insert("jobs", {
        "case_id": case_id, "evidence_id": evidence_id, "kind": kind,
        "status": "beklemede", "progress": 0, "message": "Sırada",
        "params": dumps(params), "created_at": now_iso(),
    })
    ctx = JobContext(job_id)
    _contexts[job_id] = ctx
    _push(job_id)
    _pool().submit(_run, kind, ctx, params)
    return job_id


def _run(kind: str, ctx: JobContext, params: dict) -> None:
    if ctx.cancel_event.is_set():  # sıradayken iptal edildi
        _contexts.pop(ctx.job_id, None)
        _push(ctx.job_id)
        db.close_thread_connection()
        return
    db.update("jobs", ctx.job_id, {"status": "calisiyor", "started_at": now_iso(), "message": "Başladı"})
    _push(ctx.job_id)
    try:
        result = _registry[kind](ctx, params)
        db.update("jobs", ctx.job_id, {
            "status": "tamamlandi", "progress": 1, "message": "Tamamlandı",
            "result": dumps(result) if result is not None else None, "finished_at": now_iso(),
        })
    except Cancelled:
        db.update("jobs", ctx.job_id, {"status": "iptal", "message": "İptal edildi", "finished_at": now_iso()})
    except Exception as e:  # noqa: BLE001 — iş hatası kullanıcıya gösterilir
        db.update("jobs", ctx.job_id, {
            "status": "hata", "message": str(e) or e.__class__.__name__,
            "error": traceback.format_exc(), "finished_at": now_iso(),
        })
    finally:
        _contexts.pop(ctx.job_id, None)
        _push(ctx.job_id)
        db.close_thread_connection()


def cancel(job_id: int) -> bool:
    ctx = _contexts.get(job_id)
    if ctx is None:
        return False
    ctx.cancel_event.set()
    # Henüz başlamamış iş hemen "iptal" olur; çalışan iş bir sonraki kontrol noktasında durur
    db.execute("UPDATE jobs SET status='iptal', message='İptal edildi', finished_at=? WHERE id=? AND status='beklemede'",
               (now_iso(), job_id))
    return True


def cancel_and_wait(job_ids: list[int], timeout: float = 30.0) -> bool:
    """İşleri iptal eder ve gerçekten durmalarını bekler (dosya silmeden önce gerekli)."""
    for j in job_ids:
        cancel(j)
    end = time.monotonic() + timeout
    for j in job_ids:
        while time.monotonic() < end:
            row = db.row("SELECT status FROM jobs WHERE id = ?", (j,))
            if not row or row["status"] not in ("beklemede", "calisiyor") or j not in _contexts:
                break
            time.sleep(0.1)
    return all(j not in _contexts for j in job_ids)


def get(job_id: int) -> dict | None:
    j = db.row("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _public(j) if j else None


def list_jobs(case_id: int | None = None, active_only: bool = False, limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM jobs WHERE 1=1"
    args: list[Any] = []
    if case_id is not None:
        sql += " AND case_id = ?"
        args.append(case_id)
    if active_only:
        sql += " AND status IN ('beklemede','calisiyor')"
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [_public(j) for j in db.rows(sql, args)]


def wait(job_id: int, timeout: float = 600) -> dict:
    """Testler ve CLI için: iş bitene kadar bekler."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        j = get(job_id)
        if j and j["status"] not in ("beklemede", "calisiyor"):
            return j
        time.sleep(0.1)
    raise TimeoutError(f"İş {job_id} zaman aşımına uğradı")


def _public(j: dict) -> dict:
    j = dict(j)
    j["params"] = loads(j.get("params"), {})
    j["result"] = loads(j.get("result"))
    if j.get("status") != "hata":
        j.pop("error", None)
    return j


def _push(job_id: int) -> None:
    j = get(job_id)
    if j:
        events.publish("job", job=j)
