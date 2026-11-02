"""Basit çok nesneli takip: IoU + hız tahmini + merkez uzaklığı (düşük örnekleme hızına dayanıklı)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .detector import Det, MOTOR_VEHICLES

COMPATIBLE = {c: MOTOR_VEHICLES for c in MOTOR_VEHICLES}


@dataclass
class Track:
    id: int
    cls: str
    t0: float
    last_t: float
    box: tuple[float, float, float, float]
    vel: tuple[float, float] = (0.0, 0.0)
    hits: int = 1
    best_conf: float = 0.0
    cls_votes: dict[str, float] = field(default_factory=dict)

    def predicted(self, t: float) -> tuple[float, float, float, float]:
        dt = t - self.last_t
        x1, y1, x2, y2 = self.box
        dx, dy = self.vel[0] * dt, self.vel[1] * dt
        return x1 + dx, y1 + dy, x2 + dx, y2 + dy

    @property
    def label(self) -> str:
        return max(self.cls_votes, key=self.cls_votes.get) if self.cls_votes else self.cls


def iou(a, b) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _center_score(a, b) -> float:
    acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    size = max(a[2] - a[0], a[3] - a[1], 1.0)
    d = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5 / size
    sa = (a[2] - a[0]) * (a[3] - a[1])
    sb = (b[2] - b[0]) * (b[3] - b[1])
    ratio = min(sa, sb) / max(sa, sb, 1.0)
    return (1.0 - d / 1.2) * ratio if d < 1.2 else 0.0


class Tracker:
    """dormant: süresi dolan izler bir süre "uykuda" tutulur; aynı yerde (IoU ≥ 0.6) yeniden
    görülen durağan nesneler (park etmiş araç gibi) yeni iz açmadan eski ize bağlanır."""

    def __init__(self, max_age: float = 3.0, iou_thr: float = 0.2, dormant_age: float = 900.0):
        self.max_age = max_age
        self.iou_thr = iou_thr
        self.dormant_age = dormant_age
        self.tracks: dict[int, Track] = {}
        self.dormant: dict[int, Track] = {}
        self.finished: list[Track] = []
        self._next = 1

    def _compatible(self, tr: Track, det: Det) -> bool:
        return det.cls == tr.cls or det.cls in COMPATIBLE.get(tr.cls, ())

    def _revive(self, t: float, dets: list[Det], used_d: set[int], out: list[tuple[Det, int]]) -> None:
        for di, d in enumerate(dets):
            if di in used_d:
                continue
            db = (d.x1, d.y1, d.x2, d.y2)
            best, best_s = None, 0.6
            for tr in self.dormant.values():
                if self._compatible(tr, d):
                    s = iou(tr.box, db)
                    if s >= best_s:
                        best, best_s = tr, s
            if best is not None:
                self.dormant.pop(best.id)
                self.tracks[best.id] = best
                best.vel = (0.0, 0.0)
                self._apply(best, t, d)
                used_d.add(di)
                out.append((d, best.id))

    def update(self, t: float, dets: list[Det]) -> list[tuple[Det, int]]:
        for tid in [k for k, tr in self.tracks.items() if t - tr.last_t > self.max_age]:
            self.dormant[tid] = self.tracks.pop(tid)
        for tid in [k for k, tr in self.dormant.items() if t - tr.last_t > self.dormant_age]:
            self.finished.append(self.dormant.pop(tid))
        pairs: list[tuple[float, int, int]] = []
        active = list(self.tracks.values())
        for di, d in enumerate(dets):
            db = (d.x1, d.y1, d.x2, d.y2)
            for tr in active:
                if not self._compatible(tr, d):
                    continue
                pb = tr.predicted(t)
                s = iou(pb, db)
                if s < self.iou_thr:
                    s = 0.5 * _center_score(pb, db)
                if s > 0.05:
                    pairs.append((s, di, tr.id))
        pairs.sort(reverse=True)
        used_d: set[int] = set()
        used_t: set[int] = set()
        out: list[tuple[Det, int]] = []
        for s, di, tid in pairs:
            if di in used_d or tid in used_t:
                continue
            used_d.add(di)
            used_t.add(tid)
            self._apply(self.tracks[tid], t, dets[di])
            out.append((dets[di], tid))
        self._revive(t, dets, used_d, out)
        for di, d in enumerate(dets):
            if di in used_d:
                continue
            tr = Track(self._next, d.cls, t, t, (d.x1, d.y1, d.x2, d.y2), best_conf=d.conf, cls_votes={d.cls: d.conf})
            self.tracks[tr.id] = tr
            self._next += 1
            out.append((d, tr.id))
        return out

    @staticmethod
    def _apply(tr: Track, t: float, d: Det) -> None:
        dt = max(1e-3, t - tr.last_t)
        ocx, ocy = (tr.box[0] + tr.box[2]) / 2, (tr.box[1] + tr.box[3]) / 2
        ncx, ncy = (d.x1 + d.x2) / 2, (d.y1 + d.y2) / 2
        vx, vy = (ncx - ocx) / dt, (ncy - ocy) / dt
        tr.vel = (0.6 * vx + 0.4 * tr.vel[0], 0.6 * vy + 0.4 * tr.vel[1]) if tr.hits > 1 else (vx, vy)
        tr.box = (d.x1, d.y1, d.x2, d.y2)
        tr.last_t = t
        tr.hits += 1
        tr.best_conf = max(tr.best_conf, d.conf)
        tr.cls_votes[d.cls] = tr.cls_votes.get(d.cls, 0.0) + d.conf

    def close(self) -> list[Track]:
        self.finished.extend(self.tracks.values())
        self.finished.extend(self.dormant.values())
        self.tracks.clear()
        self.dormant.clear()
        return self.finished
