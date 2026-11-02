"""Üç zaman ekseni:

    medya zamanı (t_m, sn)  --parçalar-->  kamera saati  --düzeltmeler-->  gerçek saat

- Kamera saati parçalı tanımlanır: her parça [t_from, sonraki t_from) aralığında
  kamera = t_m + offset. Kayıt boşlukları/saat sıçramaları yeni parça başlatır.
- Düzeltme referansları (kamera saati, gerçek saat) çiftleridir:
  0 çift = düzeltme yok, 1 çift = sabit fark, 2+ çift = parçalı doğrusal (kayma/drift).
Tüm saatler kameranın yerel duvar saatidir (saat dilimsiz); `tz` yalnızca gösterim içindir.
"""

from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

EPOCH = datetime(1970, 1, 1)


def to_sec(dt: datetime) -> float:
    return (dt.replace(tzinfo=None) - EPOCH).total_seconds()


def from_sec(s: float) -> datetime:
    return EPOCH + timedelta(seconds=s)


def parse_dt(s: str | datetime) -> datetime:
    if isinstance(s, datetime):
        return s.replace(tzinfo=None)
    return datetime.fromisoformat(s).replace(tzinfo=None)


@dataclass
class Piece:
    t_from: float
    offset: float        # kamera_sn - t_m


@dataclass
class TimeMapping:
    pieces: list[Piece] = field(default_factory=list)
    corrections: list[tuple[str, str]] = field(default_factory=list)   # (kamera ISO, gerçek ISO)
    tz: str = "Europe/Istanbul"
    source: str = "yok"          # osd | dosya_adi | metadata | elle | yok
    gaps: list[dict] = field(default_factory=list)   # [{"t": t_m, "jump": sn}]

    # --- serileştirme ---------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["pieces"] = [asdict(p) for p in self.pieces]
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "TimeMapping":
        if not d:
            return cls()
        return cls(
            pieces=[Piece(**p) for p in d.get("pieces", [])],
            corrections=[tuple(c) for c in d.get("corrections", [])],  # type: ignore[misc]
            tz=d.get("tz", "Europe/Istanbul"),
            source=d.get("source", "yok"),
            gaps=d.get("gaps", []),
        )

    @classmethod
    def from_start(cls, start: datetime, source: str = "elle") -> "TimeMapping":
        return cls(pieces=[Piece(0.0, to_sec(start))], source=source)

    # --- kamera saati ---------------------------------------------------------
    @property
    def has_camera_time(self) -> bool:
        return bool(self.pieces)

    def _piece_index(self, t_m: float) -> int:
        starts = [p.t_from for p in self.pieces]
        return max(0, bisect.bisect_right(starts, t_m) - 1)

    def camera_sec(self, t_m: float) -> float | None:
        if not self.pieces:
            return None
        p = self.pieces[self._piece_index(t_m)]
        return t_m + p.offset

    def to_camera(self, t_m: float) -> datetime | None:
        s = self.camera_sec(t_m)
        return from_sec(s) if s is not None else None

    # --- düzeltme ---------------------------------------------------------------
    def _corr_points(self) -> list[tuple[float, float]]:
        pts = sorted((to_sec(parse_dt(c)), to_sec(parse_dt(r))) for c, r in self.corrections)
        return pts

    def validate(self) -> None:
        """Düzeltme referansları kamera saatiyle birlikte gerçek saatte de ileri gitmeli (ters çevrilebilirlik)."""
        pts = self._corr_points()
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x1 - x0 < 1.0:
                raise ValueError("İki referans aynı kamera saatine düşüyor; birini kaldırın")
            if y1 <= y0:
                raise ValueError("Referanslar çelişkili: daha sonraki kamera saati daha erken bir gerçek saate "
                                 "eşlenmiş. Saat sıfırlanması varsa ekran saati taramasını kullanın.")

    def correct_sec(self, cam_s: float) -> float:
        pts = self._corr_points()
        if not pts:
            return cam_s
        if len(pts) == 1:
            return cam_s + (pts[0][1] - pts[0][0])
        xs = [p[0] for p in pts]
        i = bisect.bisect_right(xs, cam_s) - 1
        i = min(max(i, 0), len(pts) - 2)
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 1.0
        return y0 + (cam_s - x0) * slope

    def uncorrect_sec(self, real_s: float) -> float:
        pts = self._corr_points()
        if not pts:
            return real_s
        if len(pts) == 1:
            return real_s - (pts[0][1] - pts[0][0])
        ys = [p[1] for p in pts]
        i = bisect.bisect_right(ys, real_s) - 1
        i = min(max(i, 0), len(pts) - 2)
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        slope = (y1 - y0) / (x1 - x0) if x1 != x0 else 1.0
        if slope <= 0:  # geçersiz (validate'den geçmemiş eski) veride sıfıra bölme olmasın
            slope = 1.0
        return x0 + (real_s - y0) / slope

    # --- gerçek saat ------------------------------------------------------------
    def real_sec(self, t_m: float) -> float | None:
        c = self.camera_sec(t_m)
        return self.correct_sec(c) if c is not None else None

    def to_real(self, t_m: float) -> datetime | None:
        s = self.real_sec(t_m)
        return from_sec(s) if s is not None else None

    def to_media(self, real: datetime | str, duration: float | None = None) -> list[float]:
        """Gerçek saate karşılık gelen medya zamanları (saat sıfırlanması yüzünden birden fazla olabilir)."""
        if not self.pieces:
            return []
        cam = self.uncorrect_sec(to_sec(parse_dt(real)))
        out = []
        for i, p in enumerate(self.pieces):
            t = cam - p.offset
            end = self.pieces[i + 1].t_from if i + 1 < len(self.pieces) else (duration if duration is not None else float("inf"))
            if p.t_from - 1e-6 <= t < end:
                out.append(t)
        return out

    def media_range(self, real_from: datetime | str, real_to: datetime | str,
                    duration: float) -> list[tuple[float, float]]:
        """Gerçek saat aralığına düşen medya aralıkları."""
        if not self.pieces:
            return [(0.0, duration)]
        a = self.uncorrect_sec(to_sec(parse_dt(real_from)))
        b = self.uncorrect_sec(to_sec(parse_dt(real_to)))
        out = []
        for i, p in enumerate(self.pieces):
            end = self.pieces[i + 1].t_from if i + 1 < len(self.pieces) else duration
            lo = max(p.t_from, a - p.offset)
            hi = min(end, b - p.offset)
            if hi > lo:
                out.append((lo, hi))
        return out

    # --- özet --------------------------------------------------------------------
    def summary(self) -> dict:
        corr = self._corr_points()
        delta = None
        drift_per_day = None
        if len(corr) == 1:
            delta = corr[0][1] - corr[0][0]
        elif len(corr) >= 2:
            delta = corr[0][1] - corr[0][0]
            (x0, y0), (x1, y1) = corr[0], corr[-1]
            if x1 != x0:
                drift_per_day = ((y1 - x1) - (y0 - x0)) / (x1 - x0) * 86400
        return {
            "kamera_saati_var": self.has_camera_time,
            "kaynak": self.source,
            "duzeltme_farki_sn": delta,
            "gunluk_kayma_sn": drift_per_day,
            "parca_sayisi": len(self.pieces),
            "bosluklar": self.gaps,
        }
