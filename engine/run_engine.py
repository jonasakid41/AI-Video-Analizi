"""PyInstaller giriş noktası (dağıtımda engine/aiva-engine.exe)."""

import multiprocessing
import sys

if __name__ == "__main__":
    # Yalıtılmış medya işlemleri (aiva.worker) aynı exe'yi alt süreç olarak başlatır
    multiprocessing.freeze_support()
    from aiva.__main__ import main
    sys.exit(main())
