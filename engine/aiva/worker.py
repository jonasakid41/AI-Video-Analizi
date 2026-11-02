"""Riskli medya işlemlerini ayrı bir süreçte çalıştırır.

Bozuk ya da alışılmadık dosyalarda FFmpeg kitaplıkları çökebilir ya da sonsuz döngüye girebilir.
Aynı süreçte olsa bu motoru düşürür ya da iptal edilemez. Burada:
  - çocuk süreç çökerse  → WorkerCrashed (motor ayakta kalır)
  - belirli süre ilerleme gelmezse → WorkerStalled (süreç öldürülür)
  - kullanıcı iptal ederse → süreç hemen öldürülür, jobs.Cancelled
Çocuk süreç, ebeveyn (motor) kapanırsa kendini de kapatır.
"""

from __future__ import annotations

import importlib
import multiprocessing as mp
import os
import queue
import time
import traceback
from typing import Any

from . import jobs


class WorkerCrashed(RuntimeError):
    pass


class WorkerStalled(RuntimeError):
    pass


def _child(target: str, kwargs: dict, q, parent_pid: int) -> None:
    from .util import parent_watchdog
    parent_watchdog(parent_pid)
    mod_name, fn_name = target.split(":")
    fn = getattr(importlib.import_module(mod_name), fn_name)
    last = [0.0]

    def progress(v: float, msg: str | None = None) -> None:
        now = time.monotonic()
        if now - last[0] >= 0.3 or v >= 1.0:
            last[0] = now
            q.put(("p", float(v), msg))

    try:
        q.put(("ok", fn(**kwargs, progress=progress)))
    except BaseException as e:  # noqa: BLE001 — hata ebeveyne iletilir
        q.put(("err", f"{e.__class__.__name__}: {e}", traceback.format_exc()))


def run(target: str, kwargs: dict, ctx: jobs.JobContext | None = None, *, on_progress=None,
        idle_timeout: float = 180.0) -> Any:
    """target = "paket.modül:fonksiyon"; fonksiyon progress=callable(v, msg) parametresi almalı.

    idle_timeout saniye boyunca ilerleme gelmezse işlem takılmış sayılır.
    """
    ctx_ = mp.get_context("spawn")
    q = ctx_.Queue()
    p = ctx_.Process(target=_child, args=(target, kwargs, q, os.getpid()), daemon=True, name="aiva-worker")
    p.start()
    last_beat = time.monotonic()
    try:
        while True:
            if ctx is not None and ctx.cancel_event.is_set():
                raise jobs.Cancelled()
            try:
                msg = q.get(timeout=0.2)
            except queue.Empty:
                if not p.is_alive():
                    # Süreç bitti ama sonuç bırakmadı: kodun içinde çöktü
                    try:
                        msg = q.get(timeout=1.0)
                    except queue.Empty:
                        raise WorkerCrashed(f"İşlem beklenmedik şekilde sonlandı (çıkış kodu {p.exitcode})") from None
                elif time.monotonic() - last_beat > idle_timeout:
                    raise WorkerStalled(f"İşlem {int(idle_timeout)} saniyedir ilerlemiyor") from None
                else:
                    continue
            kind = msg[0]
            if kind == "p":
                last_beat = time.monotonic()
                if on_progress:
                    on_progress(msg[1], msg[2])
            elif kind == "ok":
                return msg[1]
            else:
                raise RuntimeError(msg[1])
    finally:
        if p.is_alive():
            p.terminate()
            p.join(3)
            if p.is_alive():
                p.kill()
        p.join(1)
        q.close()
