# -*- mode: python ; coding: utf-8 -*-
# Analiz motoru paketi: pyinstaller aiva-engine.spec  →  dist/aiva-engine/aiva-engine.exe (onedir)
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("rapidocr", "omegaconf", "antlr4"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("reportlab")
hiddenimports += collect_submodules("uvicorn") + collect_submodules("aiva")

a = Analysis(
    ["run_engine.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "PyInstaller", "setuptools", "pip", "numpy.f2py"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aiva-engine",
    console=True,
    icon="../app/src-tauri/icons/icon.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="aiva-engine", upx=False)
