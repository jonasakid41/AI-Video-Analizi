"""Analiz sonuçlarına erişim: izler, tespitler, yüzler/kişiler, plakalar, alanlar (ROI)."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import db, evidence
from .analyze import faces as facemod
from .analyze import plates as platemod
from .analyze.detector import CLASSES_TR
from .timecorr.mapping import TimeMapping
from .util import blob_to_vec, dumps, loads, now_iso


def _iso(m: TimeMapping, t: float) -> str | None:
    r = m.to_real(t)
    return r.isoformat(timespec="seconds") if r else None


def color_text(cls: str, cols: dict) -> str:
    def names(lst):
        return "/".join(c for c, _ in lst[:2]) if lst else ""
    suffix = " (siyah-beyaz kayıt)" if cols.get("renksiz") else ""
    if cls == "person":
        parts = []
        if names(cols.get("ust", [])):
            parts.append(f"üst: {names(cols['ust'])}")
        if names(cols.get("alt", [])):
            parts.append(f"alt: {names(cols['alt'])}")
        return ", ".join(parts) + suffix if parts else suffix.strip(" ()")
    if cols.get("govde"):
        return names(cols["govde"]) + suffix
    return names(cols.get("genel", [])) + suffix


def track_public(r: dict, m: TimeMapping | None = None) -> dict:
    m = m or evidence.get_mapping(r["evidence_id"])
    cols = loads(r.get("colors"), {})
    return {
        "id": r["id"], "evidence_id": r["evidence_id"], "cls": r["cls"], "cls_tr": CLASSES_TR.get(r["cls"], r["cls"]),
        "t0": r["t0"], "t1": r["t1"], "real_t0": _iso(m, r["t0"]), "real_t1": _iso(m, r["t1"]),
        "n": r["n"], "conf": r["best_conf"], "thumb": r["thumb"], "colors": cols,
        "color_text": color_text(r["cls"], cols), "plate": r["plate"], "plate_conf": r["plate_conf"],
        "face_count": r["face_count"],
    }


def tracks(evidence_id: int, cls: str | None = None, t0: float | None = None, t1: float | None = None,
           limit: int = 2000) -> list[dict]:
    sql = "SELECT * FROM tracks WHERE evidence_id = ?"
    args: list = [evidence_id]
    if cls:
        sql += " AND cls IN (%s)" % ",".join("?" * len(cls.split(",")))
        args += cls.split(",")
    if t0 is not None:
        sql += " AND t1 >= ?"
        args.append(t0)
    if t1 is not None:
        sql += " AND t0 <= ?"
        args.append(t1)
    sql += " ORDER BY t0 LIMIT ?"
    args.append(limit)
    m = evidence.get_mapping(evidence_id)
    return [track_public(r, m) for r in db.rows(sql, args)]


def track(track_id: int) -> dict:
    r = db.row("SELECT * FROM tracks WHERE id = ?", (track_id,))
    if not r:
        raise KeyError("İz bulunamadı")
    out = track_public(r)
    out["path"] = loads(r["path"], [])
    out["faces"] = db.rows("SELECT id, t, score, quality, thumb, cluster FROM faces WHERE track_id = ? ORDER BY quality DESC",
                           (track_id,))
    out["plates"] = db.rows("SELECT id, t, text, raw, conf, valid_tr, thumb FROM plates WHERE track_id = ? ORDER BY conf DESC",
                            (track_id,))
    return out


def detections_near(evidence_id: int, t: float, window: float = 0.6) -> list[dict]:
    rows = db.rows("""SELECT d.*, tr.cls AS tcls, tr.plate FROM detections d LEFT JOIN tracks tr ON tr.id = d.track_id
                      WHERE d.evidence_id = ? AND d.t BETWEEN ? AND ? ORDER BY ABS(d.t - ?)""",
                   (evidence_id, t - window, t + window, t))
    seen: set = set()
    out = []
    for r in rows:
        key = r["track_id"] or ("d", r["id"])
        if key in seen:
            continue
        seen.add(key)
        cls = r["tcls"] or r["cls"]
        out.append({"track_id": r["track_id"], "t": r["t"], "cls": cls, "cls_tr": CLASSES_TR.get(cls, cls),
                    "conf": r["conf"], "box": [r["x"], r["y"], r["w"], r["h"]], "plate": r["plate"]})
    return out


def detections_range(evidence_id: int, t0: float, t1: float) -> list[dict]:
    return db.rows("SELECT track_id, t, cls, conf, x, y, w, h FROM detections WHERE evidence_id = ? AND t BETWEEN ? AND ? "
                   "ORDER BY t", (evidence_id, t0, t1))


def events(evidence_id: int, m: TimeMapping | None = None) -> list[dict]:
    """Hareket olayları: tür (nesne/cevre/isik/parazit/belirsiz), etiket, ayrıntı, saatler."""
    m = m or evidence.get_mapping(evidence_id)
    out = []
    for r in db.rows("SELECT t0, t1, info FROM segments WHERE evidence_id = ? AND kind = 'olay' ORDER BY t0", (evidence_id,)):
        info = loads(r["info"], {})
        out.append({"t0": r["t0"], "t1": r["t1"], "real_t0": _iso(m, r["t0"]), "real_t1": _iso(m, r["t1"]),
                    "kind": info.get("tur"), "label": info.get("etiket", ""), "detail": info.get("ayrinti", ""),
                    "ignorable": bool(info.get("onemsiz")), "tracks": info.get("izler", []),
                    "box": info.get("kutu"), "t_peak": info.get("t_tepe")})
    return out


def activity(evidence_id: int, buckets: int = 600) -> dict:
    rows = db.rows("SELECT t, score, kind FROM activity WHERE evidence_id = ? ORDER BY t", (evidence_id,))
    segs = db.rows("SELECT kind, t0, t1 FROM segments WHERE evidence_id = ? AND kind != 'olay' ORDER BY t0", (evidence_id,))
    ev = evidence.require(evidence_id)
    dur = ev["duration"] or (rows[-1]["t"] if rows else 1.0)
    bins = np.zeros(buckets, np.float32)
    kinds: list[str | None] = [None] * buckets
    for r in rows:
        i = min(buckets - 1, int(r["t"] / max(dur, 1e-6) * buckets))
        if r["score"] >= bins[i]:
            bins[i] = r["score"]
            kinds[i] = r["kind"]
    det_bins = {"person": np.zeros(buckets, np.int32), "vehicle": np.zeros(buckets, np.int32)}
    for r in db.rows("SELECT cls, t0, t1 FROM tracks WHERE evidence_id = ?", (evidence_id,)):
        key = "person" if r["cls"] == "person" else ("vehicle" if r["cls"] in ("car", "truck", "bus", "motorcycle") else None)
        if key:
            a = min(buckets - 1, int(r["t0"] / max(dur, 1e-6) * buckets))
            b = min(buckets - 1, int(r["t1"] / max(dur, 1e-6) * buckets))
            det_bins[key][a:b + 1] += 1
    return {"duration": dur, "buckets": buckets, "activity": [round(float(x), 5) for x in bins], "kinds": kinds,
            "person": det_bins["person"].tolist(), "vehicle": det_bins["vehicle"].tolist(), "segments": segs,
            "events": events(evidence_id)}


# --- yüzler / kişiler ----------------------------------------------------------------

def face_public(r: dict, m: TimeMapping | None = None) -> dict:
    m = m or evidence.get_mapping(r["evidence_id"])
    return {"id": r["id"], "evidence_id": r["evidence_id"], "track_id": r["track_id"], "t": r["t"],
            "real_t": _iso(m, r["t"]), "score": r["score"], "quality": r["quality"], "thumb": r["thumb"],
            "cluster": r.get("cluster"), "box": [r["x"], r["y"], r["w"], r["h"]]}


def faces_for(evidence_id: int) -> list[dict]:
    m = evidence.get_mapping(evidence_id)
    return [face_public(r, m) for r in db.rows("SELECT * FROM faces WHERE evidence_id = ? ORDER BY t", (evidence_id,))]


def people(case_id: int, threshold: float = 0.42) -> list[dict]:
    """Vaka genelinde aynı kişi olabilecek yüz grupları (videolar arası)."""
    rows = db.rows("""SELECT f.* FROM faces f JOIN evidence e ON e.id = f.evidence_id WHERE e.case_id = ?""", (case_id,))
    if not rows:
        return []
    vecs = [blob_to_vec(r["embedding"]) for r in rows]
    labels = facemod.cluster(vecs, [r["quality"] for r in rows], threshold)  # type: ignore[arg-type]
    groups: dict[int, list[dict]] = defaultdict(list)
    for lab, r in zip(labels, rows):
        groups[lab].append(r)
    maps: dict[int, TimeMapping] = {}
    out = []
    for lab, items in groups.items():
        items.sort(key=lambda r: -r["quality"])
        best = items[0]
        apps: dict[int, list[float]] = defaultdict(list)
        for r in items:
            apps[r["evidence_id"]].append(r["t"])
        appearances = []
        for eid, ts in apps.items():
            m = maps.setdefault(eid, evidence.get_mapping(eid))
            appearances.append({"evidence_id": eid, "t0": min(ts), "t1": max(ts), "count": len(ts),
                                "real_t0": _iso(m, min(ts)), "real_t1": _iso(m, max(ts))})
        mp = lambda r: maps.setdefault(r["evidence_id"], evidence.get_mapping(r["evidence_id"]))  # noqa: E731
        out.append({"person": lab, "face_count": len(items), "best": face_public(best, mp(best)),
                    "faces": [face_public(r, mp(r)) for r in items[:12]], "appearances": appearances})
    out.sort(key=lambda p: -p["face_count"])
    return out


def face_search(case_id: int, vector: np.ndarray, threshold: float = facemod.MATCH_THRESHOLD,
                limit: int = 200) -> list[dict]:
    rows = db.rows("""SELECT f.* FROM faces f JOIN evidence e ON e.id = f.evidence_id WHERE e.case_id = ?""", (case_id,))
    scored = []
    for r in rows:
        v = blob_to_vec(r["embedding"])
        if v is None:
            continue
        s = facemod.similarity(vector, v)
        if s >= threshold:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    best_per_track: dict = {}
    for s, r in scored:
        key = r["track_id"] or ("f", r["id"])
        if key not in best_per_track:
            best_per_track[key] = (s, r)
    out = []
    for s, r in list(best_per_track.values())[:limit]:
        d = face_public(r)
        d["similarity"] = round(s, 3)
        d["strength"] = "güçlü" if s >= facemod.STRONG_THRESHOLD else "olası"
        out.append(d)
    return out


def face_vector(face_id: int) -> np.ndarray:
    r = db.row("SELECT embedding FROM faces WHERE id = ?", (face_id,))
    if not r:
        raise KeyError("Yüz bulunamadı")
    return blob_to_vec(r["embedding"])  # type: ignore[return-value]


# --- plakalar --------------------------------------------------------------------------

def plates_for(evidence_id: int) -> list[dict]:
    m = evidence.get_mapping(evidence_id)
    out = []
    for r in db.rows("SELECT * FROM tracks WHERE evidence_id = ? AND plate IS NOT NULL ORDER BY t0", (evidence_id,)):
        d = track_public(r, m)
        d["reads"] = db.rows("SELECT id, t, text, raw, conf, valid_tr, thumb FROM plates WHERE track_id = ? ORDER BY conf DESC LIMIT 6",
                             (r["id"],))
        out.append(d)
    return out


def plate_search(case_id: int, q: str, min_sim: float = 0.6) -> list[dict]:
    rows = db.rows("""SELECT tr.* FROM tracks tr JOIN evidence e ON e.id = tr.evidence_id
                      WHERE e.case_id = ? AND tr.plate IS NOT NULL""", (case_id,))
    reads: dict[int, list[str]] = defaultdict(list)
    for p in db.rows("""SELECT p.track_id, p.text FROM plates p JOIN evidence e ON e.id = p.evidence_id
                        WHERE e.case_id = ?""", (case_id,)):
        reads[p["track_id"]].append(p["text"])
    maps: dict[int, TimeMapping] = {}
    out = []
    for r in rows:
        s = max([platemod.similar(q, r["plate"])] + [platemod.similar(q, t) for t in reads.get(r["id"], [])])
        if s >= min_sim:
            d = track_public(r, maps.setdefault(r["evidence_id"], evidence.get_mapping(r["evidence_id"])))
            d["similarity"] = round(s, 3)
            out.append(d)
    out.sort(key=lambda d: -d["similarity"])
    return out


# --- alanlar (ROI) ----------------------------------------------------------------------

def rois(evidence_id: int) -> list[dict]:
    out = db.rows("SELECT * FROM rois WHERE evidence_id = ? ORDER BY id", (evidence_id,))
    for r in out:
        r["points"] = loads(r["points"], [])
    return out


def roi_create(evidence_id: int, name: str, kind: str, points: list[list[float]]) -> dict:
    if kind not in ("alan", "cizgi"):
        raise ValueError("Alan türü 'alan' ya da 'cizgi' olmalı")
    if (kind == "alan" and len(points) < 3) or (kind == "cizgi" and len(points) != 2):
        raise ValueError("Alan için en az 3, çizgi için 2 nokta gerekir")
    rid = db.insert("rois", {"evidence_id": evidence_id, "name": name or "Alan", "kind": kind,
                             "points": dumps(points), "created_at": now_iso()})
    return next(r for r in rois(evidence_id) if r["id"] == rid)


def roi_delete(roi_id: int) -> None:
    db.execute("DELETE FROM rois WHERE id = ?", (roi_id,))


def roi_get(roi_id: int) -> dict:
    r = db.row("SELECT * FROM rois WHERE id = ?", (roi_id,))
    if not r:
        raise KeyError("Alan bulunamadı")
    r["points"] = loads(r["points"], [])
    return r


def point_in_polygon(x: float, y: float, poly: list[list[float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _side(p, a, b) -> float:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _segments_cross(p1, p2, a, b) -> bool:
    d1, d2 = _side(p1, a, b), _side(p2, a, b)
    d3, d4 = _side(a, p1, p2), _side(b, p1, p2)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def anchor(box: list[float]) -> tuple[float, float]:
    """Zemindeki nokta: kutunun alt orta noktası (kişi ayakları / araç tekerleri)."""
    x, y, w, h = box
    return x + w / 2, y + h


def roi_events(roi: dict, track_rows: list[dict] | None = None) -> list[dict]:
    eid = roi["evidence_id"]
    rows = track_rows if track_rows is not None else db.rows("SELECT * FROM tracks WHERE evidence_id = ?", (eid,))
    m = evidence.get_mapping(eid)
    out = []
    for r in rows:
        path = loads(r.get("path"), [])
        if not path:
            continue
        if roi["kind"] == "alan":
            inside = [p[0] for p in path if point_in_polygon(*anchor(p[1:]), roi["points"])]
            if inside:
                d = track_public(r, m)
                d.update({"enter_t": min(inside), "exit_t": max(inside), "inside_s": round(max(inside) - min(inside), 2),
                          "real_enter": _iso(m, min(inside)), "event": "alanda"})
                out.append(d)
        else:
            a, b = roi["points"]
            for p, q in zip(path, path[1:]):
                pa, qa = anchor(p[1:]), anchor(q[1:])
                if _segments_cross(pa, qa, a, b):
                    direction = "A→B" if _side(qa, a, b) > 0 else "B→A"
                    d = track_public(r, m)
                    d.update({"enter_t": q[0], "exit_t": q[0], "real_enter": _iso(m, q[0]), "event": "cizgi_gecti",
                              "direction": direction})
                    out.append(d)
                    break
    out.sort(key=lambda d: d["enter_t"])
    return out
