"""PyInstaller giriş noktası (dağıtımda engine/aiva-engine.exe)."""

import sys

from aiva.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
