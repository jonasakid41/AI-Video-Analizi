"""Vaka işlemleri."""

from __future__ import annotations

from . import db, history, jobs, paths
from .util import now_iso, remove_tree


def create(name: str, description: str = "") -> dict:
    ts = now_iso()
    cid = db.insert("cases", {"name": name.strip() or "Adsız vaka", "description": description,
                              "created_at": ts, "updated_at": ts})
    paths.case_dir(cid)
    history.log("vaka_olusturuldu", cid, name=name)
    return get(cid)  # type: ignore[return-value]


def get(case_id: int) -> dict | None:
    c = db.row("SELECT * FROM cases WHERE id = ?", (case_id,))
    if not c:
        return None
    c["evidence_count"] = db.row("SELECT COUNT(*) n FROM evidence WHERE case_id = ?", (case_id,))["n"]  # type: ignore[index]
    c["finding_count"] = db.row("SELECT COUNT(*) n FROM findings WHERE case_id = ?", (case_id,))["n"]  # type: ignore[index]
    return c


def list_all() -> list[dict]:
    out = db.rows("""
        SELECT c.*, (SELECT COUNT(*) FROM evidence e WHERE e.case_id = c.id) AS evidence_count,
               (SELECT COUNT(*) FROM findings f WHERE f.case_id = c.id) AS finding_count
        FROM cases c ORDER BY c.updated_at DESC
    """)
    return out


def update(case_id: int, name: str | None = None, description: str | None = None) -> dict | None:
    data = {}
    if name is not None:
        data["name"] = name.strip() or "Adsız vaka"
    if description is not None:
        data["description"] = description
    if data:
        data["updated_at"] = now_iso()
        db.update("cases", case_id, data)
    return get(case_id)


def touch(case_id: int) -> None:
    db.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now_iso(), case_id))


def delete(case_id: int) -> None:
    active = [j["id"] for j in jobs.list_jobs(case_id, active_only=True)]
    if active and not jobs.cancel_and_wait(active):
        raise ValueError("Vakadaki işlemler durdurulamadı; birkaç saniye sonra tekrar deneyin")
    try:
        remove_tree(paths.cases_dir() / str(case_id))
    except PermissionError as e:
        raise ValueError("Vaka dosyaları başka bir program tarafından kullanılıyor; kapatıp tekrar deneyin") from e
    db.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    db.execute("DELETE FROM history WHERE case_id = ?", (case_id,))
    db.execute("DELETE FROM jobs WHERE case_id = ?", (case_id,))
    db.execute("DELETE FROM ai_calls WHERE case_id = ?", (case_id,))
