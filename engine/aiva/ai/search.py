"""Yerel aday bulma: plan → (zaman, sınıf, alan, renk, plaka filtreleri) + CLIP benzerliği ile sıralama."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta

import numpy as np

from .. import db, evidence, results
from ..analyze import clip
from ..analyze import plates as platemod
from ..analyze.detector import CLASSES_TR
from ..timecorr.mapping import TimeMapping
from ..util import blob_to_vec, loads


@dataclass
class Candidate:
    id: str
    kind: str                     # iz | kare
    evidence_id: int
    t: float
    box: list[float] | None       # 0–1 normalize (x, y, w, h)
    score: float
    track_id: int | None = None
    t0: float | None = None
    t1: float | None = None
    cls: str | None = None
    cls_tr: str | None = None
    thumb: str | None = None
    real_t: str | None = None
    camera: str = ""
    video: str = ""
    color_text: str = ""
    plate: str | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_hm(s: str | None) -> time | None:
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s).time()
        h, m = s.split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, IndexError):
        return None


def media_windows(m: TimeMapping, duration: float, t_from: str | None, t_to: str | None) -> tuple[list[tuple[float, float]], str | None]:
    """Plan saat aralığını bu videonun medya aralıklarına çevirir. (aralıklar, uyarı)"""
    a, b = _parse_hm(t_from), _parse_hm(t_to)
    if a is None and b is None:
        return [(0.0, duration)], None
    if not m.has_camera_time:
        return [(0.0, duration)], "Bu videonun saati bilinmediği için saat filtresi uygulanamadı"
    start, end = m.to_real(0), m.to_real(duration)
    if start is None or end is None:
        return [(0.0, duration)], None
    out: list[tuple[float, float]] = []
    day = start.date()
    while day <= end.date():
        lo = datetime.combine(day, a or time(0, 0))
        hi = datetime.combine(day, b or time(23, 59, 59))
        if hi <= lo:
            hi += timedelta(days=1)
        out += m.media_range(lo, hi, duration)
        day += timedelta(days=1)
    return out, None


def _overlaps(t0: float, t1: float, windows: list[tuple[float, float]]) -> bool:
    return any(t1 >= a and t0 <= b for a, b in windows)


def _best_point(path: list) -> tuple[float, list[float]] | None:
    if not path:
        return None
    p = max(path, key=lambda p: p[3] * p[4])
    return p[0], p[1:5]


def _color_score(cols: dict, wanted: list[dict]) -> tuple[float, list[str]]:
    if not wanted:
        return 0.0, []
    score, why = 0.0, []
    for w in wanted:
        keys = [w["target"]] if w["target"] != "genel" else ["ust", "alt", "govde", "genel"]
        for k in keys:
            names = [c for c, _ in cols.get(k, [])]
            if w["color"] in names:
                score += 1.0 if names and names[0] == w["color"] else 0.6
                why.append(f"{w['color']} renk")
                break
    return score / len(wanted), why


def find(case_id: int, plan: dict, evidence_ids: list[int] | None = None, roi_id: int | None = None,
         limit: int = 40) -> tuple[list[Candidate], list[str]]:
    notes: list[str] = []
    evs = db.rows("SELECT * FROM evidence WHERE case_id = ? AND status = 'hazir'", (case_id,))
    if evidence_ids:
        evs = [e for e in evs if e["id"] in evidence_ids]
    if not evs:
        return [], ["Vakada analiz edilebilir video yok"]
    roi = results.roi_get(roi_id) if roi_id else None
    if roi:
        evs = [e for e in evs if e["id"] == roi["evidence_id"]]
    qvec = None
    if plan.get("visual_query_en") and clip.available():
        qvec = clip.embed_texts([plan["visual_query_en"]])[0]
    classes = set(plan.get("classes") or [])
    cands: list[Candidate] = []
    for ev in evs:
        m = evidence.get_mapping(ev["id"])
        windows, warn = media_windows(m, ev["duration"] or 0.0, plan.get("time_from"), plan.get("time_to"))
        if warn:
            notes.append(f"{ev['original_name']}: {warn}")
        if not windows:
            continue
        name = ev["original_name"]
        if not ev["analyzed"]:
            notes.append(f"{name}: henüz analiz edilmedi; düzenli aralıklı kareler kullanıldı")
            cands += _uniform_frames(ev, m, windows, limit)
            continue
        trs = db.rows("SELECT * FROM tracks WHERE evidence_id = ?", (ev["id"],))
        if roi:
            inside = {d["id"]: d for d in results.roi_events(roi, trs)}
            trs = [t for t in trs if t["id"] in inside]
        for tr in trs:
            if classes and tr["cls"] not in classes:
                continue
            if not _overlaps(tr["t0"], tr["t1"], windows):
                continue
            cols = loads(tr["colors"], {})
            reasons = [CLASSES_TR.get(tr["cls"], tr["cls"])]
            score = 0.2 + 0.2 * tr["best_conf"]
            cs, why = _color_score(cols, plan.get("colors") or [])
            score += 0.8 * cs
            reasons += why
            if plan.get("plate"):
                reads = [tr["plate"] or ""] + [r["text"] for r in db.rows("SELECT text FROM plates WHERE track_id = ?", (tr["id"],))]
                ps = max(platemod.similar(plan["plate"], r) for r in reads if r) if any(reads) else 0.0
                if ps < 0.55:
                    continue
                score += 1.5 * ps
                reasons.append(f"plaka benzerliği %{int(ps * 100)}")
            vec = blob_to_vec(tr["embedding"])
            if qvec is not None and vec is not None:
                sim = float(np.dot(qvec, vec))
                score += 3.0 * max(0.0, sim - 0.18)
            bp = _best_point(loads(tr["path"], []))
            if bp is None:
                continue
            t_best, box = bp
            # Saat aralığı izin bir kısmını kapsıyorsa en iyi kareyi aralık içinden seç
            if not any(a <= t_best <= b for a, b in windows):
                inside_pts = [p for p in loads(tr["path"], []) if any(a <= p[0] <= b for a, b in windows)]
                if inside_pts:
                    t_best, box = _best_point(inside_pts)  # type: ignore[misc]
            r = m.to_real(t_best)
            cands.append(Candidate(
                id=f"i{tr['id']}", kind="iz", evidence_id=ev["id"], t=t_best, box=box, score=round(score, 4),
                track_id=tr["id"], t0=tr["t0"], t1=tr["t1"], cls=tr["cls"], cls_tr=CLASSES_TR.get(tr["cls"], tr["cls"]),
                thumb=tr["thumb"], real_t=r.isoformat(timespec="seconds") if r else None, camera=ev["camera"],
                video=name, color_text=results.color_text(tr["cls"], cols), plate=tr["plate"], reasons=reasons))
        if not classes and qvec is not None:
            cands += _frame_candidates(ev, m, windows, qvec, limit)
    cands.sort(key=lambda c: -c.score)
    return cands[:limit], notes


def _frame_candidates(ev: dict, m: TimeMapping, windows, qvec: np.ndarray, limit: int) -> list[Candidate]:
    rows = db.rows("SELECT t, embedding FROM frame_embeddings WHERE evidence_id = ?", (ev["id"],))
    rows = [r for r in rows if any(a <= r["t"] <= b for a, b in windows)]
    if not rows:
        return []
    mat = np.stack([blob_to_vec(r["embedding"]) for r in rows])
    sims = mat @ qvec
    order = np.argsort(-sims)[: max(5, limit // 2)]
    out = []
    for i in order:
        t = rows[int(i)]["t"]
        r = m.to_real(t)
        out.append(Candidate(id=f"k{ev['id']}_{int(t * 1000)}", kind="kare", evidence_id=ev["id"], t=t, box=None,
                             score=round(float(sims[i]) * 2, 4), real_t=r.isoformat(timespec="seconds") if r else None,
                             camera=ev["camera"], video=ev["original_name"], reasons=["görsel benzerlik"]))
    return out


def _uniform_frames(ev: dict, m: TimeMapping, windows, limit: int) -> list[Candidate]:
    total = sum(b - a for a, b in windows) or 1.0
    n = max(4, min(limit, int(total / 10)))
    out = []
    for a, b in windows:
        k = max(1, int(round(n * (b - a) / total)))
        for i in range(k):
            t = a + (b - a) * (i + 0.5) / k
            r = m.to_real(t)
            out.append(Candidate(id=f"k{ev['id']}_{int(t * 1000)}", kind="kare", evidence_id=ev["id"], t=t, box=None,
                                 score=0.1, real_t=r.isoformat(timespec="seconds") if r else None,
                                 camera=ev["camera"], video=ev["original_name"], reasons=["düzenli örnek"]))
    return out
