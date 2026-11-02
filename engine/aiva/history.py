"""İşlem geçmişi: hangi işlem ne zaman, hangi parametrelerle yapıldı. Kullanıcı kimliği tutulmaz."""

from __future__ import annotations

from typing import Any

from . import db
from .util import dumps, loads, now_iso


def log(action: str, case_id: int | None = None, evidence_id: int | None = None, **detail: Any) -> None:
    db.insert("history", {
        "case_id": case_id,
        "evidence_id": evidence_id,
        "action": action,
        "detail": dumps(detail) if detail else None,
        "created_at": now_iso(),
    })


def list_for_case(case_id: int, limit: int = 500) -> list[dict]:
    out = db.rows("SELECT * FROM history WHERE case_id = ? ORDER BY id DESC LIMIT ?", (case_id, limit))
    for r in out:
        r["detail"] = loads(r["detail"], {})
    return out
