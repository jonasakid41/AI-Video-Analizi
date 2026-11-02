"""Yapay zekâ taraması ve ön incelemesi: videonun tamamını kare ızgaralarıyla modele gösterir.

Yerel analiz (dedektör, CLIP) yalnızca tanıdığı şeyleri aday yapar. Model yalnızca bu adayları görürse
videoyu doğrudan modele vermekten geri kalır (dedektörün sınıfında olmayan nesne, küçük ayrıntı, olay
kaçar). Bu yüzden model videonun tamamını görür; hareketli bölümler daha sık örneklenir:
  - ön inceleme (yüklemeden sonra): her kare için Türkçe not → ai_notes. Sorular önce bu notlarda aranır.
  - tarama (soru anında): not yoksa ya da notlar yetmezse soruya uyan kareleri model ızgaralardan seçer.
Seçilen anlar ardından tam çözünürlükte doğrulanır (verify).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .. import db, evidence, jobs, settings
from ..media import frames
from ..timecorr.mapping import TimeMapping
from ..util import loads, now_iso
from . import catalog, client, prompts
from .search import GRAY_RATIO, Candidate, media_windows, picture

log = logging.getLogger(__name__)

SHEET_W = 1536          # modellerin ayrıntıyı koruduğu uzun kenar
SHEETS_PER_CALL = 4
WORKERS = 3             # aynı anda en fazla bu kadar model çağrısı
TOP_HITS = 16           # taramadan doğrulamaya giden en fazla an


@dataclass
class Sheet:
    evidence_id: int
    jpeg: bytes
    tiles: list[tuple[int, float]]  # (kare numarası, medya zamanı)


def _ready(case_id: int, evidence_ids: list[int] | None) -> list[dict]:
    return [e for e in db.rows("SELECT * FROM evidence WHERE case_id = ? AND status = 'hazir' ORDER BY id", (case_id,))
            if not evidence_ids or e["id"] in evidence_ids]


def sample_times(ev: dict, windows: list[tuple[float, float]], max_frames: int, dense: float = 2.0,
                 sparse: float = 10.0) -> list[float]:
    """Hareketli bölümlerde sık, durağan bölümlerde seyrek; hareket olaylarının en belirgin anları da eklenir."""
    active = [(r["t0"], r["t1"]) for r in
              db.rows("SELECT t0, t1 FROM segments WHERE evidence_id = ? AND kind = 'aktif'", (ev["id"],))]
    total = sum(b - a for a, b in windows)
    if not active:
        dense = sparse = min(sparse, max(1.0, total / max(1, max_frames)))
    out: list[float] = []
    for a, b in windows:
        t = a + 0.25
        while t < b:
            out.append(t)
            t += dense if any(x <= t <= y for x, y in active) else sparse
    for r in db.rows("SELECT info FROM segments WHERE evidence_id = ? AND kind = 'olay'", (ev["id"],)):
        info = loads(r["info"], {}) or {}
        tp = info.get("t_tepe")
        if tp is not None and not info.get("onemsiz") and any(a <= tp <= b for a, b in windows):
            out.append(float(tp))
    out = sorted(set(round(t, 2) for t in out))
    merged: list[float] = []
    for t in out:
        if not merged or t - merged[-1] >= 0.8:
            merged.append(t)
    if len(merged) > max_frames:
        k = len(merged) / max_frames
        merged = [merged[int(i * k)] for i in range(max_frames)]
    return merged


def grab(path: Path, times: list[float]) -> list[tuple[float, np.ndarray]]:
    """Sıralı zamanlardaki kareler: yakın zamanlar için tek geçiş, uzaktakiler için atlama."""
    out: list[tuple[float, np.ndarray]] = []
    with frames.decoding(path, threads=False) as (c, vs):
        it = None
        cur = -1e9
        for t in sorted(times):
            if it is None or t - cur > 3.0 or t < cur:
                c.seek(int(max(0.0, t) / vs.time_base), stream=vs, backward=True, any_frame=False)
                it = c.decode(vs)
            for fr in it:
                ft = frames.frame_time(fr)
                if ft is None:
                    continue
                cur = ft
                if ft + 0.02 >= t:
                    out.append((ft, fr.to_ndarray(format="bgr24")))
                    break
    return out


def _clock(m: TimeMapping, t: float) -> str:
    r = m.to_real(t)
    if r is not None:
        return r.strftime("%d.%m %H:%M:%S")
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def _label(tile: np.ndarray, no: int, clock: str) -> None:
    h, w = tile.shape[:2]
    s = max(0.5, w / 420)
    th = max(1, int(round(2 * s)))
    (tw, tht), _ = cv2.getTextSize(str(no), cv2.FONT_HERSHEY_SIMPLEX, s, th)
    cv2.rectangle(tile, (0, 0), (tw + 12, tht + 14), (0, 220, 255), -1)
    cv2.putText(tile, str(no), (6, tht + 7), cv2.FONT_HERSHEY_SIMPLEX, s, (0, 0, 0), th, cv2.LINE_AA)
    cs = s * 0.6
    (cw, chh), _ = cv2.getTextSize(clock, cv2.FONT_HERSHEY_SIMPLEX, cs, 1)
    cv2.rectangle(tile, (0, h - chh - 10), (cw + 10, h), (0, 0, 0), -1)
    cv2.putText(tile, clock, (5, h - 5), cv2.FONT_HERSHEY_SIMPLEX, cs, (255, 255, 255), 1, cv2.LINE_AA)


def make_sheets(ev: dict, m: TimeMapping, times: list[float], grid: int = 3, start_no: int = 1) -> list[Sheet]:
    src = evidence.proxy_file(ev)
    path = Path(src) if src and Path(src).exists() else evidence.evidence_file(ev)
    if path is None or not times:
        return []
    got = grab(Path(path), times)
    cols = rows = max(1, min(4, int(grid)))
    tw = SHEET_W // cols
    sheets: list[Sheet] = []
    no = start_no
    for i in range(0, len(got), cols * rows):
        chunk = got[i:i + cols * rows]
        h0, w0 = chunk[0][1].shape[:2]
        th = max(2, int(round(tw * h0 / w0)))
        used = -(-len(chunk) // cols)
        canvas = np.zeros((used * th, cols * tw, 3), np.uint8)
        tiles = []
        for j, (t, img) in enumerate(chunk):
            r, k = divmod(j, cols)
            tile = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
            _label(tile, no, _clock(m, t))
            canvas[r * th:(r + 1) * th, k * tw:(k + 1) * tw] = tile
            tiles.append((no, t))
            no += 1
        sheets.append(Sheet(ev["id"], frames.encode_jpeg(canvas, 85), tiles))
    return sheets


def _call(model: str, system: str, schema: dict, text: str, sheets: list[Sheet], role: str,
          case_id: int | None, query_id: int | None) -> dict:
    content: list[dict] = [{"type": "text", "text": text}]
    for sh in sheets:
        content.append({"type": "text", "text": f"Izgara: kare {sh.tiles[0][0]}–{sh.tiles[-1][0]}"})
        content.append(client.image_part(sh.jpeg))
    try:
        return client.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": content}],
                           schema, role=role, case_id=case_id, query_id=query_id,
                           max_tokens=400 + 90 * sum(len(s.tiles) for s in sheets))
    finally:
        db.close_thread_connection()


def _run_batches(batches: list, fn: Callable, check: Callable[[], None] | None, progress) -> list[tuple[Any, Any]]:
    """fn(batch) çağrılarını paralel yürütür; (batch, sonuç ya da istisna) listesi döner."""
    out: list[tuple[Any, Any]] = []
    pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="aiva-ai")
    try:
        futs = {pool.submit(fn, b): b for b in batches}
        for k, f in enumerate(as_completed(futs), start=1):
            if check:
                check()
            try:
                out.append((futs[f], f.result()))
            except Exception as e:  # noqa: BLE001 — bir çağrının hatası taramanın kalanını durdurmaz
                log.warning("Yapay zekâ çağrısı başarısız: %s", e)
                out.append((futs[f], e))
            if progress:
                progress(k / len(batches))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return out


def _usage() -> dict:
    return {"cost": 0.0, "in": 0, "out": 0, "calls": 0, "errors": []}


def _add(usage: dict, res: Any) -> None:
    if isinstance(res, Exception):
        usage["errors"].append(str(res))
        return
    usage["cost"] += res["cost"]
    usage["in"] += res["usage"]["in"]
    usage["out"] += res["usage"]["out"]
    usage["calls"] += 1


def _candidate(ev: dict, m: TimeMapping, t: float, cid: str, conf: float, note: str, kind_tr: str) -> Candidate:
    r = m.to_real(t)
    return Candidate(id=cid, kind="kare", evidence_id=ev["id"], t=t, box=None, score=round(0.5 + conf, 4),
                     cls_tr=kind_tr, real_t=r.isoformat(timespec="seconds") if r else None, camera=ev["camera"],
                     video=ev["original_name"], color_text=note[:200], reasons=[f"{kind_tr}: {note[:120]}"],
                     gray=picture(ev).get("renksiz_oran", 0) >= GRAY_RATIO)


def _conf(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.3


# --- soru anında tarama -------------------------------------------------------------------

def scan(case_id: int, plan: dict, question: str, model: str, *, evidence_ids: list[int] | None = None,
         query_id: int | None = None, grid: int = 3, max_frames: int = 240, check=None,
         progress=None) -> tuple[list[Candidate], dict, list[str]]:
    usage = _usage()
    evs = _ready(case_id, evidence_ids)
    sheets: list[Sheet] = []
    where: dict[int, tuple[dict, TimeMapping, float]] = {}
    no = 1
    per_ev = max(24, max_frames // max(1, len(evs)))
    for ev in evs:
        m = evidence.get_mapping(ev["id"])
        windows, _ = media_windows(m, ev["duration"] or 0.0, plan.get("time_from"), plan.get("time_to"))
        if not windows:
            continue
        for sh in make_sheets(ev, m, sample_times(ev, windows, per_ev), grid, no):
            for n, t in sh.tiles:
                where[n] = (ev, m, t)
            no = sh.tiles[-1][0] + 1
            sheets.append(sh)
    if not sheets:
        return [], usage, []
    text = (f"Soru: {question}\nAraman gereken: {plan.get('verify_question') or question}\n"
            "Uyan ya da uyabilecek kareleri numaralarıyla listele.")
    batches = [sheets[i:i + SHEETS_PER_CALL] for i in range(0, len(sheets), SHEETS_PER_CALL)]
    results = _run_batches(batches, lambda b: _call(model, prompts.SCAN_SYSTEM, prompts.SCAN_SCHEMA, text, b,
                                                    "tarama", case_id, query_id), check, progress)
    best: dict[int, tuple[float, str]] = {}
    for batch, res in results:
        _add(usage, res)
        if isinstance(res, Exception):
            continue
        valid = {n for sh in batch for n, _t in sh.tiles}
        for h in (res.get("parsed") or {}).get("hits") or []:
            if not isinstance(h, dict):
                continue
            try:
                n = int(h.get("tile"))
            except (TypeError, ValueError):
                continue
            c = _conf(h.get("confidence"))
            if n in valid and c > best.get(n, (-1.0, ""))[0]:
                best[n] = (c, str(h.get("note") or ""))
    cands = []
    for n, (c, note) in sorted(best.items(), key=lambda kv: -kv[1][0])[:TOP_HITS]:
        ev, m, t = where[n]
        cands.append(_candidate(ev, m, t, f"a{ev['id']}_{int(t * 1000)}", c, note, "yapay zekâ taraması"))
    notes = [f"Yapay zekâ {len(where)} kareyi taradı ({len(evs)} video); {len(cands)} olası an buldu"]
    return cands, usage, notes


def estimate(case_id: int, plan: dict, model: str, evidence_ids: list[int] | None, grid: int, max_frames: int) -> float:
    evs = _ready(case_id, evidence_ids)
    n = 0
    for ev in evs:
        m = evidence.get_mapping(ev["id"])
        windows, _ = media_windows(m, ev["duration"] or 0.0, plan.get("time_from"), plan.get("time_to"))
        n += len(sample_times(ev, windows, max(24, max_frames // max(1, len(evs))))) if windows else 0
    sheets = -(-n // (grid * grid))
    calls = -(-sheets // SHEETS_PER_CALL)
    return catalog.estimate(model, 500 * calls, [(SHEET_W, SHEET_W * 9 // 16)] * sheets, 60 * n // 4)


# --- yüklemeden sonra ön inceleme ------------------------------------------------------------

def auto_review_enabled() -> bool:
    s = settings.load()["ai"]
    mode = s.get("auto_review", "auto")
    verifier = s["roles"].get("verifier") or ""
    if mode == "auto":
        return verifier.startswith("cli:") and client.configured(verifier)
    return bool(mode) and client.configured(verifier)


@jobs.register("ai_review")
def review_job(ctx: jobs.JobContext, params: dict) -> dict:
    eid = params["evidence_id"]
    ev = evidence.require(eid)
    s = settings.load()["ai"]
    model = s["roles"]["verifier"]
    if not client.configured(model):
        raise RuntimeError("Yapay zekâ bağlantısı yok (API anahtarı ya da CLI aracı gerekir)")
    m = evidence.get_mapping(eid)
    ctx.progress(0.02, "Kareler hazırlanıyor")
    times = sample_times(ev, [(0.0, float(ev["duration"] or 0.0))], int(s.get("review_max_frames", 600)),
                         dense=3.0, sparse=15.0)
    sheets = make_sheets(ev, m, times, int(s.get("scan_grid", 3)))
    batches = [sheets[i:i + SHEETS_PER_CALL] for i in range(0, len(sheets), SHEETS_PER_CALL)]
    text = f"Kamera: {ev['camera'] or ev['original_name']}. Her kare için not yaz."
    ctx.progress(0.05, f"Yapay zekâ videoyu izliyor ({len(times)} kare)")
    results = _run_batches(batches, lambda b: _call(model, prompts.REVIEW_SYSTEM, prompts.REVIEW_SCHEMA, text, b,
                                                    "inceleme", ev["case_id"], None),
                           ctx.check, lambda v: ctx.progress(0.05 + 0.9 * v, f"Yapay zekâ videoyu izliyor ({len(times)} kare)"))
    usage = _usage()
    rows = []
    for batch, res in results:
        _add(usage, res)
        if isinstance(res, Exception):
            continue
        at = {n: t for sh in batch for n, t in sh.tiles}
        for tl in (res.get("parsed") or {}).get("tiles") or []:
            if not isinstance(tl, dict):
                continue
            try:
                n = int(tl.get("tile"))
            except (TypeError, ValueError):
                continue
            text_ = str(tl.get("text") or "").strip()
            if n not in at or not text_:
                continue
            rows.append((eid, round(at[n], 3), text_[:500], int(bool(tl.get("notable"))),
                         tl.get("people") if isinstance(tl.get("people"), int) else None,
                         tl.get("vehicles") if isinstance(tl.get("vehicles"), int) else None, model, now_iso()))
    if not rows and usage["errors"]:
        raise RuntimeError(f"Yapay zekâ incelemesi yapılamadı: {usage['errors'][0]}")
    with db.tx() as c:
        c.execute("DELETE FROM ai_notes WHERE evidence_id = ?", (eid,))
        c.executemany("INSERT INTO ai_notes (evidence_id, t, text, notable, people, vehicles, model, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return {"kare": len(times), "not": len(rows), "onemli": sum(r[3] for r in rows), "maliyet_usd": round(usage["cost"], 4),
            "hata": usage["errors"][:3]}


def notes(evidence_id: int, m: TimeMapping | None = None) -> list[dict]:
    m = m or evidence.get_mapping(evidence_id)
    out = []
    for r in db.rows("SELECT id, t, text, notable, people, vehicles FROM ai_notes WHERE evidence_id = ? ORDER BY t",
                     (evidence_id,)):
        rt = m.to_real(r["t"])
        out.append({**r, "notable": bool(r["notable"]), "real_t": rt.isoformat(timespec="seconds") if rt else None})
    return out


def from_notes(case_id: int, plan: dict, question: str, model: str, *, evidence_ids: list[int] | None = None,
               query_id: int | None = None) -> tuple[list[Candidate], dict, set[int]]:
    """Ön inceleme notlarından soruyla ilgili anları modele seçtirir (yalnızca metin; hızlı ve ucuz).
    Dönüş: (adaylar, kullanım, notu olan video kimlikleri)."""
    usage = _usage()
    lines: list[str] = []
    where: dict[str, tuple[dict, TimeMapping, float, str]] = {}
    covered: set[int] = set()
    for ev in _ready(case_id, evidence_ids):
        rows = db.rows("SELECT id, t, text FROM ai_notes WHERE evidence_id = ? ORDER BY t", (ev["id"],))
        if not rows:
            continue
        covered.add(ev["id"])
        m = evidence.get_mapping(ev["id"])
        windows, _ = media_windows(m, ev["duration"] or 0.0, plan.get("time_from"), plan.get("time_to"))
        for r in rows:
            if not any(a <= r["t"] <= b for a, b in windows) or r["text"].lower().startswith("değişiklik yok"):
                continue
            key = f"n{r['id']}"
            where[key] = (ev, m, r["t"], r["text"])
            lines.append(f"{key} | {ev['camera'] or ev['original_name']} | {_clock(m, r['t'])} | {r['text']}")
    if not lines:
        return [], usage, covered
    best: dict[str, tuple[float, str]] = {}
    for i in range(0, len(lines), 800):
        try:
            res = client.chat(model, [{"role": "system", "content": prompts.NOTES_SYSTEM},
                                      {"role": "user", "content": f"Soru: {question}\nNotlar:\n" + "\n".join(lines[i:i + 800])}],
                              prompts.NOTES_SCHEMA, role="not_secimi", case_id=case_id, query_id=query_id, max_tokens=1500)
        except client.AIError as e:
            usage["errors"].append(str(e))
            continue
        _add(usage, res)
        for h in (res.get("parsed") or {}).get("hits") or []:
            if isinstance(h, dict) and str(h.get("id")) in where:
                c = _conf(h.get("confidence"))
                if c > best.get(str(h["id"]), (-1.0, ""))[0]:
                    best[str(h["id"])] = (c, str(h.get("note") or ""))
    cands = []
    for key, (c, why) in sorted(best.items(), key=lambda kv: -kv[1][0])[:TOP_HITS]:
        ev, m, t, text = where[key]
        cands.append(_candidate(ev, m, t, f"a{ev['id']}_{int(t * 1000)}", c, text, "yapay zekâ notu"))
    return cands, usage, covered
