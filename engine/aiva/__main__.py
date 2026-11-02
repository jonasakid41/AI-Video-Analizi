"""Motoru başlatır: `python -m aiva` ya da dağıtımda `engine/aiva-engine.exe`.

Hazır olduğunda stdout'a tek satır yazar:  AIVA_READY {"port": 51234, "token": "...", "data_dir": "..."}
Arayüz (Tauri) bu satırı okuyup bağlanır. AIVA_PARENT_PID verilirse ebeveyn kapanınca motor da kapanır.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
from logging.handlers import RotatingFileHandler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aiva-engine")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AIVA_PORT", "0")))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from . import paths
    log_file = paths.logs_dir() / "motor.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # uvicorn bağlantı satırları URL'deki oturum token'ını içerir; günlüğe yazılmaz
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    import uvicorn

    from .api import deps
    from .api.app import create_app, startup

    if os.environ.get("AIVA_TOKEN"):
        deps.set_token(os.environ["AIVA_TOKEN"])
    startup()
    if (ppid := os.environ.get("AIVA_PARENT_PID")) and ppid.isdigit():
        from .util import parent_watchdog
        parent_watchdog(int(ppid))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((args.host, args.port))
    port = sock.getsockname()[1]
    app = create_app()
    config = uvicorn.Config(app, log_config=None, access_log=False, ws="websockets-sansio" if _has_ws_sansio() else "auto",
                            timeout_keep_alive=30)
    server = uvicorn.Server(config)

    def ready():
        while not server.started:
            time.sleep(0.05)
        print("AIVA_READY " + json.dumps({"port": port, "token": deps.TOKEN, "data_dir": str(paths.data_dir())}),
              flush=True)

    threading.Thread(target=ready, daemon=True).start()
    server.run(sockets=[sock])
    return 0


def _has_ws_sansio() -> bool:
    try:
        import uvicorn.protocols.websockets.websockets_sansio_impl  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
