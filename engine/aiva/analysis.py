"""Video analizi işi (tamamen yerel, buluta veri gitmez).

A) Hareket taraması: anahtar kareler (ya da 1 fps) üzerinde arka plan çıkarımı → aktivite eğrisi.
B) Tespit: aktif bölümlerde sample_fps, durağan bölümlerde seyrek örnekleme (park etmiş araçlar için).
   Nesne tespiti + takip; kişilerde yüz, araçlarda plaka; kare ve iz vektörleri (CLIP).
C) Özet: iz başına baskın renkler, plaka uzlaşısı, en iyi kırpıntı; yüz kümeleri.
Tüm konumlar kare boyutuna göre 0–1 normalize, tüm dosya yolları data/ klasörüne göredir.
"""

from __future__ import annotations

import bisect
import shutil
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import db, events, evidence, history, jobs, paths, settings
from .analyze import clip, colors, faces, lowlight, motion, plates, runtime
from .analyze.detector import CLASSES_TR, MOTOR_VEHICLES, Det, Detector, _iou
from .analyze.tracker import Tracker
from .media import frames
from .results import color_text
from .util import dumps, imwrite, loads, vec_to_blob

FRAME_EMB_EVERY = 2.0
SPARSE_FPS = 0.1
PERSON_CONF = 0.28   # kişiler için tespit eşiği (genel eşikten düşük; tek karelik izler sonradan elenir)
ZOOM_MAX = 2         # kare başına en fazla bu kadar hareket bölgesi büyütülerek yeniden taranır
ENHANCE_LOW = True   # karanlık/düşük kontrastlı karelerde tespit öncesi CLAHE


@dataclass
class TrackData:
    best_score: float = 0.0
    best_crop: np.ndarray | None = None
    best_t: float = 0.0
    path: list = field(default_factory=list)
    face_tries: int = 0
    last_face_t: float = -1e9
    plate_tries: int = 0
    last_plate_t: float = -1e9
    plate_reads: list = field(default_factory=list)
    faces: int = 0
    gray: bool = False    # en iyi kırpıntının alındığı kare siyah-beyaz mı


def rel(p: Path) -> str:
    return p.resolve().relative_to(paths.data_dir().resolve()).as_posix()


def _clear(eid: int, crops: Path) -> None:
    for table in ("activity", "detections", "tracks", "faces", "plates", "frame_embeddings"):
        db.execute(f"DELETE FROM {table} WHERE evidence_id = ?", (eid,))
    db.execute("DELETE FROM segments WHERE evidence_id = ? AND kind IN ('aktif','seyrek','olay')", (eid,))
    if crops.exists():
        shutil.rmtree(crops, ignore_errors=True)


def recover() -> None:
    """Açılışta: yarıda kalan analizlerin (analiz edildi bayrağı kapalı ama satırları olan) kalıntılarını siler."""
    for ev in db.rows("""SELECT DISTINCT e.id, e.case_id FROM evidence e
                         JOIN detections d ON d.evidence_id = e.id WHERE e.analyzed = 0"""):
        _clear(ev["id"], paths.evidence_dir(ev["case_id"], ev["id"]) / "crops")


def _object_label(tracks: list[dict]) -> tuple[str, str]:
    """Olaydaki izlerden kısa etiket ("2 kişi, 1 otomobil") ve ayrıntı (renk, plaka)."""
    counts: dict[str, int] = defaultdict(int)
    details: list[str] = []
    for tr in tracks:
        counts[CLASSES_TR.get(tr["cls"], tr["cls"])] += 1
        bits = [CLASSES_TR.get(tr["cls"], tr["cls"])]
        ct = color_text(tr["cls"], loads(tr["colors"], {}))
        if ct:
            bits.append(ct)
        if tr["plate"]:
            bits.append(f"plaka {tr['plate']}")
        details.append(" · ".join(bits))
    label = ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])[:3]) or "nesne"
    return label, "; ".join(details[:6])


def _motion_events(eid: int, msamples: list, threshold: float, scan_fps: float, use_keys: bool,
                   keyframe_interval: float | None) -> dict:
    """Hareket örneklerini türlerine ayırır, olayları kaydeder ve tür başına süre özetini döner."""
    rows = db.rows("SELECT t, x, y, w, h FROM detections WHERE evidence_id = ?", (eid,))
    boxes = motion.BoxIndex([(r["t"], r["x"], r["y"], r["w"], r["h"]) for r in rows])
    kinds = motion.classify(msamples, boxes, threshold)
    with db.tx() as c:
        c.executemany("INSERT INTO activity (evidence_id, t, score, kind) VALUES (?, ?, ?, ?)",
                      [(eid, round(s.t, 3), round(s.visible, 5), k) for s, k in zip(msamples, kinds)])
    step = (keyframe_interval or 1.0) if use_keys else 1.0 / max(scan_fps, 0.1)
    evs = motion.events(msamples, kinds, max_gap=max(2.5, 2.5 * step))
    tracks = db.rows("SELECT id, cls, t0, t1, colors, plate FROM tracks WHERE evidence_id = ?", (eid,))
    summary: dict[str, float] = defaultdict(float)
    out = []
    for kind, a, b in evs:
        a, b = max(0.0, a - step / 2), b + step / 2
        summary[kind] += b - a
        info = {"tur": kind, "etiket": motion.KINDS[kind], "ayrinti": "", "onemsiz": kind in motion.IGNORABLE}
        if kind in ("nesne", "belirsiz"):
            t_peak, box = _event_box(msamples, kinds, kind, a, b)
            if box:
                info["t_tepe"], info["kutu"] = t_peak, box
        if kind == "nesne":
            inside = [tr for tr in tracks if tr["t1"] >= a and tr["t0"] <= b]
            if inside:
                info["etiket"], info["ayrinti"] = _object_label(inside)
                info["izler"] = [tr["id"] for tr in inside][:80]
        out.append((eid, "olay", round(a, 3), round(b, 3), dumps(info)))
    with db.tx() as c:
        c.executemany("INSERT INTO segments (evidence_id, kind, t0, t1, info) VALUES (?, ?, ?, ?, ?)", out)
    return {k: round(v, 1) for k, v in summary.items()}


def _zoom_detect(detector: Detector, img: np.ndarray, sample: motion.Sample | None, dets: list[Det],
                 conf: float) -> list[Det]:
    """Hareket var ama onu açıklayan tespit yok: hareket bölgesi kırpılıp büyütülerek yeniden aranır.
    Dedektör kareyi 640 px'e küçülttüğü için geniş açılı kameralarda uzaktaki kişiler kayboluyordu."""
    if sample is None or not sample.boxes:
        return []
    H, W = img.shape[:2]
    extra: list[Det] = []
    for bx, by, bw, bh in sample.boxes[:ZOOM_MAX]:
        cx, cy = (bx + bw / 2) * W, (by + bh / 2) * H
        if any(d.x1 - 0.3 * d.w <= cx <= d.x2 + 0.3 * d.w and d.y1 - 0.3 * d.h <= cy <= d.y2 + 0.3 * d.h
               for d in dets + extra):
            continue
        cw, ch = min(W, max(W * 0.3, bw * W * 5)), min(H, max(H * 0.3, bh * H * 5))
        if cw > W * 0.7:
            continue  # bölge zaten büyük: tam kare taraması yeterli
        x0 = int(max(0.0, min(W - cw, cx - cw / 2)))
        y0 = int(max(0.0, min(H - ch, cy - ch / 2)))
        for d in detector.detect(img[y0:y0 + int(ch), x0:x0 + int(cw)], conf, person_conf=PERSON_CONF):
            d2 = Det(d.cls, d.conf, d.x1 + x0, d.y1 + y0, d.x2 + x0, d.y2 + y0)
            if all(_iou(d2, o) < 0.4 for o in dets + extra):
                extra.append(d2)
    return extra


def _event_box(samples: list[motion.Sample], kinds: list[str | None], kind: str, a: float, b: float):
    """Olayın en belirgin anı ve hareket kutusu (doğrulamada o bölge yakından gösterilir)."""
    inside = [s for s, k in zip(samples, kinds) if k == kind and a <= s.t <= b and s.boxes]
    if not inside:
        return None, None
    peak = max(inside, key=lambda s: s.mlargest)
    return round(peak.t, 3), [round(v, 4) for v in peak.boxes[0]]


def _plan(segs: list[tuple[float, float]], duration: float, fps: float) -> list[tuple[float, float, float, str]]:
    """Aktif bölümler tam hızda, aradakiler seyrek örneklenir."""
    plan = []
    cur = 0.0
    for a, b in segs:
        if a - cur > 1.0:
            plan.append((cur, a, SPARSE_FPS, "seyrek"))
        plan.append((a, b, fps, "aktif"))
        cur = b
    if duration - cur > 1.0:
        plan.append((cur, duration, SPARSE_FPS, "seyrek"))
    return plan


def _save_jpg(img: np.ndarray, p: Path, q: int = 88) -> str:
    imwrite(p, img, q)
    return rel(p)


@jobs.register("analyze")
def analyze_job(ctx: jobs.JobContext, params: dict) -> dict:
    """Analiz başlarken önceki sonuçlar geçersiz sayılır; iptal ya da hata olursa yarım kalan satırlar
    temizlenir ve video "analiz edilmedi" durumuna döner (yarım sonuç gösterilmez)."""
    eid = params["evidence_id"]
    ev = evidence.require(eid)
    info = loads(ev.get("analysis_info"), {})
    info.pop("analiz", None)
    db.update("evidence", eid, {"analyzed": 0, "analysis_info": dumps(info)})
    events.publish("evidence", evidence=evidence.public(evidence.require(eid)))
    try:
        return _analyze(ctx, params)
    except BaseException:
        _clear(eid, evidence.folder(ev) / "crops")
        events.publish("analysis", evidence_id=eid)
        events.publish("evidence", evidence=evidence.public(evidence.require(eid)))
        raise


def _analyze(ctx: jobs.JobContext, params: dict) -> dict:
    eid = params["evidence_id"]
    ev = evidence.require(eid)
    path = evidence.evidence_file(ev)
    if path is None:
        raise RuntimeError("Video henüz dönüştürülmedi")
    cfg = {**settings.load()["analysis"], **(params.get("options") or {})}
    duration = float(ev["duration"] or 0.0)
    W, H = float(ev["width"] or 1), float(ev["height"] or 1)
    crops = evidence.folder(ev) / "crops"
    _clear(eid, crops)
    t_all = time.monotonic()
    timings: dict[str, float] = {}

    # --- A) hareket taraması ---------------------------------------------------------
    info = loads(ev.get("analysis_info"), {})
    ki = (info.get("donusturme") or {}).get("keyframe_interval") or frames.keyframe_interval(path)
    use_keys = ki is not None and ki <= 2.5
    mwidth = motion.meter_width(W)
    meter = motion.MotionMeter(width=mwidth)
    msamples: list[motion.Sample] = []
    scan_fps = float(cfg["scan_fps"])
    n_gray = n_low = 0
    for t, frame in frames.iter_frames(path, scan_fps, keyframes_only=use_keys, cancel=ctx.check):
        small = frame.reformat(width=mwidth, height=max(2, int(mwidth * H / W) // 2 * 2), format="bgr24").to_ndarray()
        msamples.append(meter.measure(small, t))
        g, low, _flat = lowlight.frame_stats(small)
        n_gray += g
        n_low += low
        if duration:
            ctx.progress(0.02 + 0.18 * min(1.0, t / duration), "Hareket taraması")
    picture = {"renksiz_oran": round(n_gray / max(1, len(msamples)), 3),
               "dusuk_isik_oran": round(n_low / max(1, len(msamples)), 3)}
    segs = motion.active_segments(motion.segment_signal(msamples, float(cfg["motion_threshold"])),
                                  float(cfg["motion_threshold"]), duration=duration or None)
    ms_ts = [s.t for s in msamples]

    def sample_near(t: float) -> motion.Sample | None:
        i = bisect.bisect_left(ms_ts, t)
        near = [msamples[j] for j in (i - 1, i) if 0 <= j < len(msamples) and abs(msamples[j].t - t) <= 0.75]
        return min(near, key=lambda s: abs(s.t - t)) if near else None
    plan = _plan(segs, duration, float(cfg["sample_fps"]))
    with db.tx() as c:
        c.executemany("INSERT INTO segments (evidence_id, kind, t0, t1, info) VALUES (?, ?, ?, ?, ?)",
                      [(eid, kind, a, b, None) for a, b, _f, kind in plan])
    timings["hareket"] = round(time.monotonic() - t_all, 2)

    # --- B) tespit, takip, yüz, plaka -------------------------------------------------
    t_b = time.monotonic()
    det_name = cfg["detector"] if runtime.has_model(cfg["detector"]) else "yolox_s"
    detector = Detector(det_name)
    use_faces = bool(cfg["faces"]) and runtime.has_model("yunet") and runtime.has_model("sface")
    use_plates = bool(cfg["plates"])
    use_clip = bool(cfg["clip"]) and clip.available()
    tracker = Tracker()
    tdata: dict[int, TrackData] = defaultdict(TrackData)
    det_rows: list[tuple] = []
    face_rows: list[tuple] = []
    plate_rows: list[tuple] = []
    emb_imgs: list[np.ndarray] = []
    emb_ts: list[float] = []
    last_emb = -1e9
    planned = sum((b - a) * f for a, b, f, _k in plan) or 1.0
    done = 0.0
    n_frames = 0
    n_zoom = 0
    n_enhanced = 0

    def flush_embeddings() -> None:
        if not emb_imgs:
            return
        with jobs.gpu_lock:
            vecs = clip.embed_images(emb_imgs)
        with db.tx() as c:
            c.executemany("INSERT INTO frame_embeddings (evidence_id, t, embedding) VALUES (?, ?, ?)",
                          [(eid, round(t, 3), vec_to_blob(v)) for t, v in zip(emb_ts, vecs)])
        emb_imgs.clear()
        emb_ts.clear()

    def flush_dets() -> None:
        if det_rows:
            with db.tx() as c:
                c.executemany("INSERT INTO detections (evidence_id, track_id, t, cls, conf, x, y, w, h) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", det_rows)
            det_rows.clear()

    for a, b, fps, kind in plan:
        prev_t = a
        for t, frame in frames.iter_frames(path, fps, t0=a, t1=b, cancel=ctx.check):
            img = frame.to_ndarray(format="bgr24")
            n_frames += 1
            gray, dark, flat = lowlight.frame_stats(img)
            low = ENHANCE_LOW and (dark or flat)
            # Karanlık/düşük kontrastlı karede tespit, yüz ve plaka kontrastı artırılmış kopyada aranır;
            # renkler ve kayıtlı kırpıntılar özgün kareden alınır
            det_img = lowlight.enhance(img) if low else img
            n_enhanced += low
            conf = float(cfg["min_conf"])
            with jobs.gpu_lock:
                dets = detector.detect(det_img, conf, person_conf=min(conf, PERSON_CONF))
                if kind == "aktif":
                    extra = _zoom_detect(detector, det_img, sample_near(t), dets, conf)
                    n_zoom += len(extra)
                    dets += extra
            for d, tid in tracker.update(t, dets):
                td = tdata[tid]
                nx, ny, nw, nh = d.x1 / W, d.y1 / H, d.w / W, d.h / H
                det_rows.append((eid, -tid, round(t, 3), d.cls, round(d.conf, 4), nx, ny, nw, nh))
                td.path.append([round(t, 3), round(nx, 4), round(ny, 4), round(nw, 4), round(nh, 4)])
                edge = 0.7 if (d.x1 < 2 or d.y1 < 2 or d.x2 > W - 2 or d.y2 > H - 2) else 1.0
                score = d.w * d.h * d.conf * edge
                if score > td.best_score:
                    td.best_score, td.best_t, td.gray = score, t, gray
                    td.best_crop = d.crop(img, 0.06).copy()
                if use_faces and d.cls == "person" and td.face_tries < 12 and t - td.last_face_t >= 0.9:
                    td.face_tries += 1
                    td.last_face_t = t
                    for f, vec, fcrop in faces.faces_in_person(det_img, (d.x1, d.y1, d.x2, d.y2)):
                        thumb = _save_jpg(fcrop, crops / "faces" / f"{uuid.uuid4().hex[:12]}.jpg", 92)
                        face_rows.append((eid, -tid, round(t, 3), f.x / W, f.y / H, f.w / W, f.h / H,
                                          round(f.score, 4), round(f.quality, 4), thumb, vec_to_blob(vec)))
                        td.faces += 1
                if (use_plates and d.cls in MOTOR_VEHICLES and d.w >= 100 and td.plate_tries < 10
                        and t - td.last_plate_t >= 0.45):
                    td.plate_tries += 1
                    td.last_plate_t = t
                    vcrop = d.crop(det_img, 0.02)
                    reads = plates.read_vehicle(vcrop)
                    if reads:
                        r = reads[0]
                        thumb = _save_jpg(vcrop, crops / "plates" / f"{uuid.uuid4().hex[:12]}.jpg", 92)
                        plate_rows.append((eid, -tid, round(t, 3), r.text, r.raw, round(r.conf, 4),
                                           int(r.valid_tr), thumb))
                        td.plate_reads.append(r)
            if use_clip and t - last_emb >= FRAME_EMB_EVERY:
                emb_imgs.append(frames.resize_to_width(img, 448))
                emb_ts.append(t)
                last_emb = t
                if len(emb_imgs) >= 16:
                    flush_embeddings()
            if len(det_rows) >= 500:
                flush_dets()
            done += (t - prev_t) * fps
            prev_t = t
            ctx.progress(0.20 + 0.70 * min(1.0, done / planned),
                         "Nesne, yüz ve plaka analizi" if kind == "aktif" else "Durağan bölümler taranıyor")
        done += (b - prev_t) * fps
    flush_dets()
    flush_embeddings()
    timings["tespit"] = round(time.monotonic() - t_b, 2)

    # --- C) iz özetleri -----------------------------------------------------------------
    ctx.progress(0.92, "Sonuçlar özetleniyor")
    t_c = time.monotonic()
    finished = tracker.close()
    kept, dropped = [], []
    for tr in finished:
        (kept if (tr.hits >= 2 or tr.best_conf >= 0.5) else dropped).append(tr)
    if face_rows:
        with db.tx() as c:
            c.executemany("INSERT INTO faces (evidence_id, track_id, t, x, y, w, h, score, quality, thumb, embedding) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", face_rows)
    if plate_rows:
        with db.tx() as c:
            c.executemany("INSERT INTO plates (evidence_id, track_id, t, text, raw, conf, valid_tr, thumb) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", plate_rows)
    track_crops: list[np.ndarray] = []
    track_db_ids: list[int] = []
    counts: dict[str, int] = defaultdict(int)
    for tr in kept:
        td = tdata[tr.id]
        cls = tr.label
        counts[cls] += 1
        crop = td.best_crop
        cols: dict = {}
        thumb = None
        if crop is not None and crop.size:
            if td.gray:
                cols = colors.describe_gray(crop, cls)
            else:
                cols = colors.describe_person(crop) if cls == "person" else (
                    colors.describe_vehicle(crop) if cls in MOTOR_VEHICLES else {"genel": colors.dominant(crop)})
            thumb = _save_jpg(crop, crops / "tracks" / f"{uuid.uuid4().hex[:12]}.jpg", 90)
        plate, pconf = plates.consensus(td.plate_reads)
        tid_db = db.insert("tracks", {
            "evidence_id": eid, "cls": cls, "t0": round(tr.t0, 3), "t1": round(tr.last_t, 3), "n": tr.hits,
            "best_conf": round(tr.best_conf, 4), "thumb": thumb, "colors": dumps(cols),
            "plate": plate, "plate_conf": pconf if plate else None, "face_count": td.faces,
            "embedding": None, "path": dumps(td.path), "rois": None,
        })
        with db.tx() as c:
            for table in ("detections", "faces", "plates"):
                c.execute(f"UPDATE {table} SET track_id = ? WHERE evidence_id = ? AND track_id = ?", (tid_db, eid, -tr.id))
        if crop is not None and crop.size and use_clip:
            track_crops.append(crop)
            track_db_ids.append(tid_db)
    with db.tx() as c:
        for tr in dropped:
            for table in ("detections", "faces", "plates"):
                c.execute(f"DELETE FROM {table} WHERE evidence_id = ? AND track_id = ?", (eid, -tr.id))
    if track_crops:
        with jobs.gpu_lock:
            vecs = clip.embed_images(track_crops)
        with db.tx() as c:
            c.executemany("UPDATE tracks SET embedding = ? WHERE id = ?",
                          [(vec_to_blob(v), i) for v, i in zip(vecs, track_db_ids)])

    # Yüz kümeleri (aynı kişi)
    frows = db.rows("SELECT id, quality, embedding FROM faces WHERE evidence_id = ?", (eid,))
    if frows:
        vecs = [np.frombuffer(r["embedding"], np.float32) for r in frows]
        labels = faces.cluster(vecs, [r["quality"] for r in frows])
        with db.tx() as c:
            c.executemany("UPDATE faces SET cluster = ? WHERE id = ?", [(lab, r["id"]) for lab, r in zip(labels, frows)])
    # Hareketin türü (kişi/araç mı, ağaç/gölge/ışık/parazit mi) ve olay listesi
    motion_summary = _motion_events(eid, msamples, float(cfg["motion_threshold"]), scan_fps, use_keys, ki)
    timings["ozet"] = round(time.monotonic() - t_c, 2)
    timings["toplam"] = round(time.monotonic() - t_all, 2)

    plates_found = db.rows("SELECT DISTINCT plate FROM tracks WHERE evidence_id = ? AND plate IS NOT NULL", (eid,))
    stats = {
        "sure_sn": timings,
        "aygit": runtime.active_provider(det_name) or "CPU",
        "dedektor": det_name,
        "anahtar_kare_taramasi": use_keys,
        "analiz_edilen_kare": n_frames,
        "aktif_bolum": len(segs),
        "aktif_sure_sn": round(sum(b - a for a, b in segs), 1),
        "izler": {CLASSES_TR.get(k, k): v for k, v in sorted(counts.items(), key=lambda kv: -kv[1])},
        "iz_sayisi": len(kept),
        "yuz_sayisi": len(frows),
        "kisi_kumesi": len(db.rows("SELECT DISTINCT cluster FROM faces WHERE evidence_id = ?", (eid,))),
        "plakalar": [p["plate"] for p in plates_found],
        "hareket_ozeti": motion_summary,
        "goruntu": {**picture, "iyilestirilen_kare": n_enhanced, "yakinlastirma_tespiti": n_zoom},
        "yuz_tanima": use_faces, "plaka_okuma": use_plates, "gorsel_arama": use_clip,
    }
    info["analiz"] = stats
    db.update("evidence", eid, {"analyzed": 1, "analysis_info": dumps(info)})
    history.log("analiz_tamamlandi", ev["case_id"], eid, **{k: v for k, v in stats.items() if k != "plakalar"},
                plaka_sayisi=len(stats["plakalar"]))
    events.publish("analysis", evidence_id=eid)
    events.publish("evidence", evidence=evidence.public(evidence.require(eid)))
    from .ai import scan as scanmod
    if scanmod.auto_review_enabled():
        # Yapay zekâ videonun tamamını izleyip not çıkarır; sorular önce bu notlarda aranır
        jobs.submit("ai_review", {"evidence_id": eid}, case_id=ev["case_id"], evidence_id=eid)
    return stats
