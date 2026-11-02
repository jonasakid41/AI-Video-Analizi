"""Metinden tarih/saat çıkarma: ekran saati (OCR) ve dosya adları."""

from __future__ import annotations

import re
from datetime import date, datetime, time

DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "i": "1",
                           "Z": "2", "z": "2", "S": "5", "s": "5", "B": "8", "G": "6", "g": "9", "q": "9"})

_TSEP = r"[:.;]"
# Tarih bileşenleri arasında aynı ayırıcı (-, /, .) zorunlu; ayırıcısız yalnızca 8 hane (YYYYAAGG)
RE_YMD = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:([-/.])(\d{1,2})\2(\d{1,2})|(\d{2})(\d{2}))(?!\d)")
RE_DMY = re.compile(r"(?<!\d)(\d{1,2})([-/.])(\d{1,2})\2((?:19|20)\d{2})(?!\d)")
RE_TIME = re.compile(rf"(?<!\d)(\d{{1,2}}){_TSEP}(\d{{2}}){_TSEP}(\d{{2}})(?!\d)(?:\s*([AaPp])\.?[Mm]\.?)?")


def _normalize(text: str) -> str:
    # Rakam bağlamında harf karışıklıklarını düzelt (OCR)
    out = []
    for i, ch in enumerate(text):
        if ord(ch) in DIGIT_FIX and _digit_context(text, i):
            out.append(ch.translate(DIGIT_FIX))
        else:
            out.append(ch)
    return "".join(out)


def _digit_context(text: str, i: int) -> bool:
    left = text[i - 1] if i > 0 else ""
    right = text[i + 1] if i + 1 < len(text) else ""
    return left.isdigit() or right.isdigit()


def _mk_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_date(text: str) -> date | None:
    t = _normalize(text)
    for m in RE_YMD.finditer(t):
        mo, da = (m.group(3), m.group(4)) if m.group(2) else (m.group(5), m.group(6))
        d = _mk_date(int(m.group(1)), int(mo), int(da))
        if d:
            return d
    m = RE_DMY.search(t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(3)), int(m.group(4))
        # Türkiye biçimi GG-AA-YYYY; ay 12'den büyükse ABD biçimi (AA-GG-YYYY)
        return _mk_date(y, b, a) or _mk_date(y, a, b)
    return None


def find_time(text: str) -> time | None:
    t = _normalize(text)
    for m in RE_TIME.finditer(t):
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ampm = (m.group(4) or "").lower()
        if ampm == "p" and h < 12:
            h += 12
        elif ampm == "a" and h == 12:
            h = 0
        if h < 24 and mi < 60 and s < 60:
            return time(h, mi, s)
    return None


def parse_osd(text: str, default_date: date | None = None) -> datetime | None:
    tm = find_time(text)
    if tm is None:
        return None
    d = find_date(text) or default_date
    if d is None:
        return None
    return datetime.combine(d, tm)


RE_FILENAME = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"[-_.T ]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)"
)


def parse_filename(name: str) -> datetime | None:
    """CH01_20261028143000.dav, 2026-10-28_14-30-00.mp4, NVR_ch2_main_20261028143000_20261028150000 ..."""
    m = RE_FILENAME.search(name)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None
