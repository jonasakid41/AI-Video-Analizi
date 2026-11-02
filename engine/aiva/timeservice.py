"""Saat düzeltme servisi: ekran saati taraması (iş) ve elle düzeltme."""

from __future__ import annotations


from . import db, evidence, jobs
from .timecorr import osd
from .timecorr.mapping import Piece, TimeMapping, parse_dt, to_sec
from .timecorr.parse import parse_filename


@jobs.register("osd_scan")
def osd_scan_job(ctx: jobs.JobContext, params: dict) -> dict:
    eid = params["evidence_id"]
    ev = evidence.require(eid)
    path = evidence.evidence_file(ev)
    if path is None:
        raise RuntimeError("Video henüz dönüştürülmedi")
    current = evidence.get_mapping(eid)
    default_date = None
    if current.has_camera_time:
        default_date = current.to_camera(0).date()  # type: ignore[union-attr]
    elif (fn := parse_filename(ev["original_name"])):
        default_date = fn.date()
    mapping, readings = osd.scan(path, ev["duration"] or 0.0, params.get("region"), float(params.get("every", 10.0)),
                                 default_date, progress=lambda v: ctx.progress(v, "Ekran saati okunuyor"))
    db.execute("DELETE FROM ocr_readings WHERE evidence_id = ?", (eid,))
    for r in readings:
        db.insert("ocr_readings", {"evidence_id": eid, "t": r.t, "text": r.text, "parsed": r.camera.isoformat()})
    if mapping is None:
        raise RuntimeError("Ekran saati okunamadı. Saat yazısının bulunduğu bölgeyi seçip tekrar deneyin.")
    mapping.corrections = current.corrections
    mapping.tz = current.tz
    # Yüklemede bulunan kayıt boşlukları (dosya zaman damgaları) korunur, saat sıçramalarıyla birleştirilir
    known = {round(g["t"], 1) for g in mapping.gaps}
    mapping.gaps = sorted(mapping.gaps + [g for g in current.gaps if round(g["t"], 1) not in known], key=lambda g: g["t"])
    evidence.save_mapping(eid, mapping, f"Ekran saati taraması ({len(readings)} okuma)")
    return {"okuma": len(readings), "parca": len(mapping.pieces), "bosluk": mapping.gaps}


def set_manual(evidence_id: int, camera_start: str | None = None, corrections: list[list[str]] | None = None,
               references: list[dict] | None = None, tz: str | None = None, reason: str = "",
               apply_to_camera: bool = False) -> dict:
    """Elle saat ayarı.

    camera_start: videonun ilk karesindeki kamera saati (ekrandaki saat)
    corrections:  [[kamera_saati, gerçek_saat], ...]
    references:   [{"t_media": sn, "real": gerçek_saat}] — "videonun şu anında gerçek saat şuydu"
    """
    m = evidence.get_mapping(evidence_id)
    if camera_start:
        start = to_sec(parse_dt(camera_start))
        if m.pieces:
            shift = start - m.pieces[0].offset
            m.pieces = [Piece(p.t_from, p.offset + shift) for p in m.pieces]
        else:
            m.pieces = [Piece(0.0, start)]
        m.source = "elle"
    if corrections is not None:
        m.corrections = [(parse_dt(c).isoformat(), parse_dt(r).isoformat()) for c, r in corrections]
    for ref in references or []:
        t = float(ref["t_media"])
        real = parse_dt(ref["real"])
        if not m.has_camera_time:
            # Kamera saati bilinmiyorsa gerçek saati kamera saati kabul et
            m.pieces = [Piece(0.0, to_sec(real) - t)]
            m.source = "elle"
        else:
            cam = m.to_camera(t)
            m.corrections = [c for c in m.corrections if abs(to_sec(parse_dt(c[0])) - to_sec(cam)) > 1.0]  # type: ignore[arg-type]
            m.corrections.append((cam.isoformat(), real.isoformat()))  # type: ignore[union-attr]
    if tz:
        m.tz = tz
    m.validate()
    out = evidence.save_mapping(evidence_id, m, reason or "Elle düzeltme")
    if apply_to_camera:
        ev = evidence.require(evidence_id)
        if ev["camera"]:
            for other in db.rows("SELECT id FROM evidence WHERE case_id = ? AND camera = ? AND id != ?",
                                 (ev["case_id"], ev["camera"], evidence_id)):
                om = evidence.get_mapping(other["id"])
                om.corrections = list(m.corrections)
                om.tz = m.tz
                evidence.save_mapping(other["id"], om, f"{ev['original_name']} videosundan kopyalandı")
    return out


def readings(evidence_id: int) -> list[dict]:
    return db.rows("SELECT t, text, parsed FROM ocr_readings WHERE evidence_id = ? ORDER BY t", (evidence_id,))


def real_iso(m: TimeMapping, t: float) -> str | None:
    r = m.to_real(t)
    return r.isoformat(timespec="seconds") if r else None


def describe(m: TimeMapping, t: float) -> dict:
    cam = m.to_camera(t)
    real = m.to_real(t)
    return {"t": t, "camera": cam.isoformat(timespec="seconds") if cam else None,
            "real": real.isoformat(timespec="seconds") if real else None}

