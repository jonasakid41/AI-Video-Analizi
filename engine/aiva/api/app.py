"""FastAPI uygulaması. Yalnızca 127.0.0.1 üzerinde, oturum token'ı ile çalışır."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__, db, events, jobs
from . import deps

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="AI Video Analizi Motoru", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(https?://tauri\.localhost|tauri://localhost|http://(localhost|127\.0\.0\.1):\d+)$",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
    )

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if request.url.path.startswith("/api"):
            try:
                deps.check_request(request)
            except HTTPException as e:
                return JSONResponse({"detail": e.detail}, status_code=e.status_code)
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def key_error(_request: Request, exc: KeyError):
        msg = exc.args[0] if exc.args else "Kayıt bulunamadı"
        return JSONResponse({"detail": str(msg)}, status_code=404)

    @app.exception_handler(FileNotFoundError)
    async def fnf_error(_request: Request, exc: FileNotFoundError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(ValueError)
    async def value_error(_request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    from . import routes_ai, routes_analysis, routes_core, routes_media
    app.include_router(routes_core.router)
    app.include_router(routes_media.router)
    app.include_router(routes_analysis.router)
    app.include_router(routes_ai.router)

    @app.websocket("/api/events")
    async def ws_events(ws: WebSocket):
        if not deps.check_ws(ws):
            await ws.close(code=4401)
            return
        await ws.accept()
        q = events.subscribe(asyncio.get_running_loop())
        try:
            await ws.send_text(json.dumps({"type": "hello", "version": __version__}))
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                    await ws.send_text(json.dumps(msg, ensure_ascii=False, default=str))
                except asyncio.TimeoutError:
                    await ws.send_text('{"type":"ping"}')
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            events.unsubscribe(q)

    return app


def startup(db_path: Path | None = None) -> None:
    db.init(db_path)
    jobs.recover_interrupted()
    # İş türlerini kaydet
    from .. import analysis, enhance, evaluate, evidence, export, query, report, timeservice  # noqa: F401
