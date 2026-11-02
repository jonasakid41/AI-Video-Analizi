"""Gizli değerlerin (API anahtarı) Windows DPAPI ile şifrelenmesi.

Şifreli değer yalnızca aynı Windows kullanıcısı tarafından çözülebilir. Klasör başka bir
bilgisayara kopyalanırsa anahtarın yeniden girilmesi gerekir.
"""

from __future__ import annotations

import base64
import sys

PREFIX_DPAPI = "dpapi:"
PREFIX_PLAIN = "b64:"   # yalnızca Windows dışı geliştirme ortamı için


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(blob_in), "AI Video Analizi", None, None, None, flags,
                                      ctypes.byref(blob_out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, flags,
                                        ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI işlemi başarısız")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(secret: str) -> str:
    raw = secret.encode("utf-8")
    if sys.platform == "win32":
        return PREFIX_DPAPI + base64.b64encode(_dpapi(raw, True)).decode("ascii")
    return PREFIX_PLAIN + base64.b64encode(raw).decode("ascii")


def unprotect(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if value.startswith(PREFIX_DPAPI):
            return _dpapi(base64.b64decode(value[len(PREFIX_DPAPI):]), False).decode("utf-8")
        if value.startswith(PREFIX_PLAIN):
            return base64.b64decode(value[len(PREFIX_PLAIN):]).decode("utf-8")
    except (OSError, ValueError):
        return None  # başka kullanıcı / bilgisayar: anahtar yeniden girilmeli
    return None


def mask(secret: str | None) -> str:
    if not secret:
        return ""
    return secret[:6] + "…" + secret[-4:] if len(secret) > 12 else "…"
