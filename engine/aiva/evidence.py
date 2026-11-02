"""Delil (video) işlemleri ve yükleme işi.

Yükleme adımları: kopyala + SHA-256 → içerik tanıma → strateji zinciri → kayıpsız kopya
→ çalışma kopyası (proxy) → önizleme → başlangıç zaman eşlemesi → (otomatik analiz).
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from datetime import datetime
from pathlib import Path

from . import cases, db, events, history, jobs, paths, settings, worker
from .media import convert, frames, opener
from .media.sniff import hex_head, sniff
from .timecorr.mapping import TimeMapping
from .timecorr.parse import parse_filename
from .util import dumps, imwrite, loads, now_iso, remove_tree

log = logging.getLogger(__name__)

STATUS_LABELS = {
    "beklemede": "Sırada",
    "donusturuluyor": "Dönüştürülüyor",
    "hazir": "Hazır",
    "hata": "Açılamadı",
}


def folder(ev: dict) -> Path:
    return paths.evidence_dir(ev["case_id"], ev["id"])


def evidence_file(ev: dict) -> Path | None:
    for name in ("evidence.mkv", "evidence.nut"):
        p = folder(ev) / name
        if p.exists():
            return p
    return None


def proxy_file(ev: dict) -> Path:
    return folder(ev) / "proxy.mp4"


def get(evidence_id: int) -> dict | None:
    return db.row("SELECT * FROM evidence WHERE id = ?", (evidence_id,))


def require(evidence_id: int) -> dict:
    ev = get(evidence_id)
    if not ev:
        raise KeyError("Video bulunamadı")
    return ev


def public(ev: dict) -> dict:
    out = {k: v for k, v in ev.items() if k not in ("probe", "sniff", "strategy", "analysis_info")}
    out["status_label"] = STATUS_LABELS.get(ev["status"], ev["status"])
    out["sniff"] = loads(ev.get("sniff"), {})
    out["strategy"] = loads(ev.get("strategy"), {})
    out["analysis_info"] = loads(ev.get("analysis_info"), {})
    m = get_mapping(ev["id"])
    out["time"] = m.summary()
    out["camera_start"] = m.to_camera(0).isoformat() if m.has_camera_time else None
    out["real_start"] = m.to_real(0).isoformat() if m.has_camera_time else None
    out["time_mapping"] = m.to_dict()
    return out


def list_for_case(case_id: int) -> list[dict]:
    return [public(e) for e in db.rows("SELECT * FROM evidence WHERE case_id = ? ORDER BY camera, id", (case_id,))]


def add(case_id: int, source_paths: list[str], camera: str = "") -> list[int]:
    if not cases.get(case_id):
        raise KeyError("Vaka bulunamadı")
    ids = []
    for sp in source_paths:
        p = Path(sp)
        if not p.is_file():
            raise FileNotFoundError(f"Dosya bulunamadı: {sp}")
        eid = db.insert("evidence", {
            "case_id": case_id, "original_name": p.name, "source_path": str(p),
            "size": p.stat().st_size, "camera": camera or _guess_camera(p.name),
            "status": "beklemede", "created_at": now_iso(),
        })
        ids.append(eid)
        jobs.submit("ingest", {"evidence_id": eid}, case_id=case_id, evidence_id=eid)
    cases.touch(case_id)
    return ids


def _guess_camera(name: str) -> str:
    import re
    m = re.search(r"(?i)(?:ch|cam|kamera|channel)[\s_-]?0*(\d{1,3})", name)
    return f"Kamera {int(m.group(1))}" if m else ""


def update(evidence_id: int, camera: str | None = None) -> dict:
    if camera is not None:
        db.update("evidence", evidence_id, {"camera": camera})
    ev = require(evidence_id)
    events.publish("evidence", evidence=public(ev))
    return public(ev)


def delete(evidence_id: int) -> None:
    ev = require(evidence_id)
    # Önce bu videonun işleri durdurulur; yoksa açık dosyalar silinemez ya da iş yarım yazmaya devam eder
    active = [j["id"] for j in jobs.list_jobs(active_only=True) if j["evidence_id"] == evidence_id]
    if active and not jobs.cancel_and_wait(active):
        raise ValueError("Videodaki işlem durdurulamadı; birkaç saniye sonra tekrar deneyin")
    d = paths.cases_dir() / str(ev["case_id"]) / "evidence" / str(evidence_id)
    try:
        remove_tree(d)
    except PermissionError as e:
        raise ValueError("Video dosyaları başka bir program tarafından kullanılıyor; kapatıp tekrar deneyin") from e
    db.execute("DELETE FROM evidence WHERE id = ?", (evidence_id,))
    history.log("video_silindi", ev["case_id"], evidence_id, ad=ev["original_name"])


# --- zaman eşlemesi ----------------------------------------------------------------

def get_mapping(evidence_id: int) -> TimeMapping:
    r = db.row("SELECT data FROM time_mappings WHERE evidence_id = ? ORDER BY version DESC LIMIT 1", (evidence_id,))
    return TimeMapping.from_dict(loads(r["data"]) if r else None)


def save_mapping(evidence_id: int, mapping: TimeMapping, reason: str = "") -> dict:
    ev = require(evidence_id)
    v = db.row("SELECT COALESCE(MAX(version), 0) v FROM time_mappings WHERE evidence_id = ?", (evidence_id,))["v"]  # type: ignore[index]
    db.insert("time_mappings", {"evidence_id": evidence_id, "version": v + 1, "data": dumps(mapping.to_dict()),
                                "reason": reason, "created_at": now_iso()})
    history.log("saat_eslemesi_guncellendi", ev["case_id"], evidence_id, surum=v + 1, gerekce=reason,
                ozet=mapping.summary())
    events.publish("evidence", evidence=public(require(evidence_id)))
    return mapping.to_dict()


def mapping_versions(evidence_id: int) -> list[dict]:
    out = db.rows("SELECT version, reason, created_at, data FROM time_mappings WHERE evidence_id = ? ORDER BY version DESC",
                  (evidence_id,))
    for r in out:
        r["data"] = loads(r["data"], {})
    return out


def _initial_mapping(ev: dict, info: dict) -> TimeMapping | None:
    dt = parse_filename(ev["original_name"])
    if dt:
        return TimeMapping.from_start(dt, source="dosya_adi")
    ct = (info.get("metadata") or {}).get("creation_time")
    if ct:
        try:
            parsed = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone().replace(tzinfo=None)
            if parsed.year >= 2000:
                return TimeMapping.from_start(parsed, source="metadata")
        except ValueError:
            pass
    return None


# --- yükleme işi ---------------------------------------------------------------------

def _set_status(eid: int, status: str, detail: str = "", **extra) -> None:
    db.update("evidence", eid, {"status": status, "status_detail": detail, **extra})
    ev = get(eid)
    if ev:
        events.publish("evidence", evidence=public(ev))


def _copy_with_hash(src: Path, dst: Path, progress) -> str:
    """Kopya önce .part adıyla yazılır, tamamlanınca yerine taşınır: yarıda kalan kopya asla
    "orijinal" sanılmaz (delil bütünlüğü)."""
    h = hashlib.sha256()
    total = max(1, src.stat().st_size)
    done = 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    try:
        with src.open("rb") as fi, part.open("wb") as fo:
            for chunk in iter(lambda: fi.read(8 << 20), b""):
                h.update(chunk)
                fo.write(chunk)
                done += len(chunk)
                progress(done / total)
        if done != src.stat().st_size:
            raise OSError("Kaynak dosya kopyalama sırasında değişti")
        part.replace(dst)
    finally:
        part.unlink(missing_ok=True)
    os.chmod(dst, stat.S_IREAD)
    return h.hexdigest()


@jobs.register("ingest")
def ingest_job(ctx: jobs.JobContext, params: dict) -> dict:
    """Hangi adımda biterse bitsin video "Dönüştürülüyor" durumunda takılı kalmaz."""
    eid = params["evidence_id"]
    try:
        return _ingest(ctx, params)
    except jobs.Cancelled:
        if get(eid):
            _set_status(eid, "hata", "Dönüştürme iptal edildi. Başlatmak için “Yeniden dene”.")
        raise
    except Exception as e:
        cur = get(eid)
        if cur and cur["status"] != "hata":
            _set_status(eid, "hata", str(e) or e.__class__.__name__)
        raise


def recover() -> None:
    """Açılışta: uygulama kapandığı ya da motor yeniden başladığı için yarıda kalan dönüştürmeler."""
    for ev in db.rows("SELECT id FROM evidence WHERE status IN ('beklemede','donusturuluyor')"):
        db.update("evidence", ev["id"], {
            "status": "hata",
            "status_detail": "Dönüştürme yarıda kaldı (uygulama kapandı ya da motor yeniden başladı). "
                             "“Yeniden dene” ile tekrar başlatın."})


def _ingest(ctx: jobs.JobContext, params: dict) -> dict:
    eid = params["evidence_id"]
    ev = require(eid)
    d = folder(ev)
    src = Path(ev["source_path"])
    _set_status(eid, "donusturuluyor", "Kopyalanıyor")

    original = d / "original" / ev["original_name"]
    if not original.exists():
        digest = _copy_with_hash(src, original, lambda v: ctx.progress(0.10 * v, "Kopyalanıyor ve SHA-256 hesaplanıyor"))
        history.log("video_eklendi", ev["case_id"], eid, ad=ev["original_name"], sha256=digest, boyut=ev["size"])
    else:
        # Yeniden dönüştürme: tamamlanmış kopya yeniden doğrulanır; hash değiştiyse işlem durur
        from .util import sha256_file
        ctx.progress(0.05, "Orijinal kopyanın SHA-256 değeri doğrulanıyor")
        digest = sha256_file(original)
        if ev["sha256"] and digest != ev["sha256"]:
            _set_status(eid, "hata", "Orijinal kopyanın SHA-256 değeri kayıtlı değerle uyuşmuyor")
            history.log("butunluk_hatasi", ev["case_id"], eid, beklenen=ev["sha256"], bulunan=digest)
            raise RuntimeError("Orijinal kopyanın SHA-256 değeri değişmiş; dosya bozulmuş ya da değiştirilmiş olabilir.")
    db.update("evidence", eid, {"sha256": digest})

    ctx.progress(0.11, "Biçim tanınıyor")
    s = sniff(original)
    spec, attempts = opener.choose(original, s)
    db.update("evidence", eid, {"sniff": dumps(s.to_dict())})
    if spec is None:
        diag = d / "teshis.txt"
        diag.write_text(_diagnostics(original, s, attempts), encoding="utf-8")
        _set_status(eid, "hata", "Dosya açılamadı. Teşhis paketi oluşturuldu.",
                    strategy=dumps({"denemeler": [a.to_dict() for a in attempts]}))
        history.log("donusturme_basarisiz", ev["case_id"], eid, bicim=s.label)
        raise RuntimeError(f"Dosya açılamadı ({s.label}). {len(attempts)} strateji denendi.")

    info = opener.probe(original, spec)
    db.update("evidence", eid, {"strategy": dumps({**spec.to_dict(), "denemeler": [a.to_dict() for a in attempts]}),
                                "probe": dumps(info)})

    _set_status(eid, "donusturuluyor", "Kayıpsız kopya oluşturuluyor")
    stats = _isolated_remux(ctx, original, spec, d, s, attempts)
    ev_path = Path(stats["path"])
    einfo = opener.probe(ev_path, opener.OpenSpec("evidence"))
    v = opener.video_stream_info(einfo)
    duration = einfo.get("duration") or v.get("duration") or 0.0
    db.update("evidence", eid, {"duration": duration, "width": v.get("width"), "height": v.get("height"),
                                "fps": v.get("fps"), "codec": v.get("codec")})

    _set_status(eid, "donusturuluyor", "Çalışma kopyası hazırlanıyor")
    try:
        pinfo = worker.run("aiva.media.convert:proxy_task",
                           {"src": str(ev_path), "dst": str(proxy_file(ev)), "vinfo": v}, ctx,
                           on_progress=lambda val, m=None: ctx.progress(0.45 + 0.45 * val, "Çalışma kopyası hazırlanıyor"))
    except (worker.WorkerCrashed, worker.WorkerStalled, worker.WorkerError) as e:
        if isinstance(e, worker.WorkerError):
            (d / "teshis.txt").write_text(_diagnostics(original, s, attempts) + f"\n\nÇalışma kopyası hatası ({e.kind}): "
                                          f"{e}\n{e.trace}", encoding="utf-8")
        _set_status(eid, "hata", f"Çalışma kopyası oluşturulamadı: {e}. Teşhis paketi Bilgi sekmesinde.")
        raise RuntimeError(f"Çalışma kopyası oluşturulamadı: {e}. Kayıpsız kopya hazır; yeniden dönüştürmeyi deneyin.") from e

    ctx.progress(0.92, "Önizleme şeridi")
    sprite = frames.make_sprite(ev_path, duration or 1.0, d / "sprite.jpg")
    got = frames.frame_at(ev_path, min(duration * 0.1, 5.0))
    if got:
        imwrite(d / "thumb.jpg", frames.resize_to_width(got[1], 480), 82)

    if not get_mapping(eid).has_camera_time:
        m = _initial_mapping(ev, info)
        if m:
            m.gaps = [{"t": g[1], "jump": round(g[1] - g[0], 3)} for g in stats["gaps"]]
            save_mapping(eid, m, f"Otomatik ({'dosya adı' if m.source == 'dosya_adi' else 'dosya bilgisi'})")

    if stats["gaps"]:
        db.execute("DELETE FROM segments WHERE evidence_id = ? AND kind = 'bosluk'", (eid,))
        for a, b in stats["gaps"]:
            db.insert("segments", {"evidence_id": eid, "kind": "bosluk", "t0": a, "t1": b, "info": None})

    analysis_info = {"donusturme": {**{k: v for k, v in stats.items() if k != "path"}, "proxy": pinfo,
                                    "sprite": sprite}}
    db.update("evidence", eid, {"has_proxy": 1, "analysis_info": dumps(analysis_info)})
    _set_status(eid, "hazir", f"{spec.name} · {pinfo.get('encoder_label') or 'yeniden paketleme'}")
    history.log("donusturuldu", ev["case_id"], eid, strateji=spec.name, kap=stats["container"],
                proxy=pinfo["mode"], kodlayici=pinfo.get("encoder"), bosluk_sayisi=len(stats["gaps"]))
    cases.touch(ev["case_id"])

    if params.get("analyze", settings.load()["analysis"]["auto_analyze"]):
        jobs.submit("analyze", {"evidence_id": eid}, case_id=ev["case_id"], evidence_id=eid)
    return {"evidence_id": eid, "strategy": spec.name, "duration": duration}


def _isolated_remux(ctx: jobs.JobContext, original: Path, spec, d: Path, s, attempts) -> dict:
    """Kayıpsız kopyayı ayrı süreçte çıkarır. Çökme ya da takılmada bir kez hataya dayanıklı
    modla yeniden dener; o da olmazsa teşhis paketi yazıp anlaşılır bir hata verir."""
    tries = [spec]
    if any(k not in spec.options for k in opener.TOLERANT):
        tries.append(opener.OpenSpec(spec.name + " + hata toleransı", spec.format, spec.offset,
                                     {**spec.options, **opener.TOLERANT}, spec.raw, spec.fps))
    problems: list[str] = []
    last: Exception | None = None
    for i, sp in enumerate(tries):
        label = "Kayıpsız kopya oluşturuluyor" + (" (hataya dayanıklı mod)" if i else "")
        try:
            return worker.run("aiva.media.convert:remux_task",
                              {"src": str(original), "spec": sp.to_dict(), "dst_base": str(d / "evidence")}, ctx,
                              on_progress=lambda v, m=None, label=label: ctx.progress(0.12 + 0.33 * v, m or label))
        except (worker.WorkerCrashed, worker.WorkerStalled, worker.WorkerError) as e:
            log.warning("Kayıpsız kopya başarısız (iş %s, %s): %s", ctx.job_id, sp.name, e)
            detail = f" ({e.kind})\n{e.trace}" if isinstance(e, worker.WorkerError) else ""
            problems.append(f"{sp.name}: {e}{detail}")
            last = e
            for ext in (".mkv", ".nut"):
                (d / "evidence").with_suffix(ext).unlink(missing_ok=True)
    (d / "teshis.txt").write_text(_diagnostics(original, s, attempts) + "\n\nKayıpsız kopya denemeleri:\n" +
                                  "\n".join(f"  - {p}" for p in problems), encoding="utf-8")
    if isinstance(last, worker.WorkerError):
        msg = str(last) if str(last).startswith("Kayıpsız kopya") else f"Kayıpsız kopya oluşturulamadı: {last}"
        raise RuntimeError(f"{msg}. Teşhis paketi Bilgi sekmesinde.")
    raise RuntimeError("Dosya açıldı ama baştan sona kopyalanamadı (çözücü çöktü ya da takıldı). "
                       "Dosyanın bir bölümü bozuk olabilir. Teşhis paketi Bilgi sekmesinde.")


def _diagnostics(path: Path, s, attempts) -> str:
    lines = [
        "AI Video Analizi — Teşhis paketi",
        f"Dosya: {path.name}",
        f"Boyut: {path.stat().st_size} bayt",
        f"Tanıma: {s.label} (tür={s.kind}, ofset={s.offset}, güven={s.confidence})",
        "",
        "Denenen stratejiler:",
    ]
    for a in attempts:
        lines.append(f"  - {a.spec.name}: {'başarılı' if a.ok else 'başarısız'} — {a.error}")
    lines += ["", "İlk 4 KB (hex):", hex_head(path)]
    return "\n".join(lines)
