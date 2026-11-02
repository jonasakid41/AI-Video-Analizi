from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, WebSocket

TOKEN = os.environ.get("AIVA_TOKEN") or secrets.token_urlsafe(24)
OPEN_PATHS = {"/api/health"}


def set_token(token: str) -> None:
    global TOKEN
    TOKEN = token


def token_ok(value: str | None) -> bool:
    return bool(value) and secrets.compare_digest(value, TOKEN)  # type: ignore[arg-type]


def check_request(request: Request) -> None:
    if request.url.path in OPEN_PATHS or request.method == "OPTIONS":
        return
    if not (token_ok(request.headers.get("x-aiva-token")) or token_ok(request.query_params.get("k"))):
        raise HTTPException(401, "Yetkisiz erişim")


def check_ws(ws: WebSocket) -> bool:
    return token_ok(ws.query_params.get("k"))


def not_found(what: str = "Kayıt") -> HTTPException:
    return HTTPException(404, f"{what} bulunamadı")
