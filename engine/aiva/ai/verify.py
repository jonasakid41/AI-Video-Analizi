"""Adayları seçilen görsel modele doğrulatma ve kısa video kesiti analizi."""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np

from .. import evidence
from ..media import encoders, frames
from . import catalog, client, prompts
from .search import Candidate

CROP_MAX = 512
CONTEXT_W = 640


def _crop(img: np.ndarray, box: list[float] | None, pad: float = 0.25) -> np.ndarray:
    if not box:
        return img
    H, W = img.shape[:2]
    x, y, w, h = box
    x0, y0 = max(0, int((x - w * pad) * W)), max(0, int((y - h * pad) * H))
    x1, y1 = min(W, int((x + w * (1 + pad)) * W)), min(H, int((y + h * (1 + pad)) * H))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return img
    return img[y0:y1, x0:x1]


def _fit(img: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    s = max(h, w)
    if s > max_side:
        f = max_side / s
        return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
    if s < 160:
        f = 160 / s
        return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_CUBIC)
    return img


def _context(img: np.ndarray, box: list[float] | None) -> np.ndarray:
    ctx = frames.resize_to_width(img, CONTEXT_W).copy()
    if box:
        H, W = ctx.shape[:2]
        x, y, w, h = box
        cv2.rectangle(ctx, (int(x * W), int(y * H)), (int((x + w) * W), int((y + h) * H)), (0, 255, 255), 2)
    return ctx


def candidate_images(c: Candidate, with_context: bool) -> tuple[list[np.ndarray], np.ndarray | None]:
    ev = evidence.require(c.evidence_id)
    src = evidence.evidence_file(ev)
    if src is None:
        return [], None
    got = frames.frame_at(src, c.t)
    if got is None:
        return [], None
    _t, img = got
    out = [_fit(_crop(img, c.box), CROP_MAX)] if c.box else [_fit(img, 768)]
    if with_context and c.box:
        out.append(_context(img, c.box))
    return out, img


def label(c: Candidate) -> str:
    when = c.real_t.replace("T", " ") if c.real_t else f"video içi {c.t:.1f}. sn"
    where = c.camera or c.video
    extra = f", {c.cls_tr}" if c.cls_tr else ""
    return f"Aday {c.id} — {where}, saat {when}{extra}"


def estimate(model: str, cands: list[Candidate], with_context: bool, batch: int) -> float:
    imgs = []
    for _ in cands:
        imgs.append((CROP_MAX, CROP_MAX))
        if with_context:
            imgs.append((CONTEXT_W, 360))
    batches = max(1, -(-len(cands) // batch))
    return catalog.estimate(model, 400 * batches + 40 * len(cands), imgs, 60 * len(cands))


def _rows(parsed: Any) -> list[dict]:
    rows = parsed.get("results") if isinstance(parsed, dict) else parsed
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _scalar(v: Any) -> str:
    return str(v).strip() if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def verdict(r: dict) -> dict:
    """Modelin aday cevabını şemaya uydurur (ör. "false" metni, %80 gibi güven, nesne olarak plaka)."""
    m = r.get("match")
    match = m if isinstance(m, bool) else _scalar(m).lower() in ("true", "evet", "yes", "1")
    try:
        conf = float(_scalar(r.get("confidence")).lstrip("%") or 0)
    except ValueError:
        conf = 0.0
    if conf > 1:
        conf /= 100
    return {"match": match, "confidence": max(0.0, min(1.0, conf)), "explanation": _scalar(r.get("explanation"))[:400],
            "plate": _scalar(r.get("plate")) or None}


def verify(cands: list[Candidate], question: str, model: str, *, case_id: int, query_id: int,
           batch: int = 8, with_context: bool = True, progress=None) -> tuple[dict[str, dict], dict]:
    out: dict[str, dict] = {}
    usage = {"cost": 0.0, "in": 0, "out": 0, "calls": 0, "errors": []}
    for bi in range(0, len(cands), batch):
        group = cands[bi:bi + batch]
        content: list[dict] = [{"type": "text", "text": f"Soru: {question}\n\nAşağıdaki {len(group)} adayı değerlendir."}]
        sent = []
        for c in group:
            imgs, _full = candidate_images(c, with_context)
            if not imgs:
                continue
            content.append({"type": "text", "text": label(c) + (" (yakın görüntü ve sahnenin tamamı)" if len(imgs) > 1 else "")})
            for im in imgs:
                content.append(client.image_part(frames.encode_jpeg(im, 86)))
            sent.append(c)
        if not sent:
            continue
        try:
            res = client.chat(model, [{"role": "system", "content": prompts.VERIFY_SYSTEM},
                                      {"role": "user", "content": content}],
                              prompts.VERIFY_SCHEMA, role="dogrulayici", case_id=case_id, query_id=query_id,
                              max_tokens=200 + 120 * len(sent))
        except client.AIError as e:
            usage["errors"].append(str(e))
            if "anahtar" in str(e) or "bakiye" in str(e).lower():
                break
            continue
        usage["cost"] += res["cost"]
        usage["in"] += res["usage"]["in"]
        usage["out"] += res["usage"]["out"]
        usage["calls"] += 1
        ids = {c.id for c in sent}
        for r in _rows(res["parsed"]):
            rid = str(r.get("id", "")).replace("Aday", "").strip()
            if rid in ids:
                out[rid] = verdict(r)
        if progress:
            progress(min(1.0, (bi + batch) / len(cands)))
    return out, usage


def make_clip(evidence_id: int, t0: float, t1: float, width: int = 640) -> bytes:
    """Proxy'den küçük bir MP4 kesiti (modele göndermek için)."""
    ev = evidence.require(evidence_id)
    src = evidence.proxy_file(ev)
    enc = encoders.choose()
    buf = io.BytesIO()
    with frames.decoding(Path(src)) as (ic, vs):
        fps = float(vs.average_rate or 10)
        out_fps = min(fps, 8.0)
        ic.seek(int(max(0.0, t0) / vs.time_base), stream=vs, backward=True, any_frame=False)
        with av.open(buf, "w", format="mp4", options={"movflags": "frag_keyframe+empty_moov"}) as out:
            os_ = out.add_stream(enc, rate=Fraction(out_fps).limit_denominator(100))
            h = int(round((ev["height"] or 360) * width / (ev["width"] or 640))) // 2 * 2
            os_.width, os_.height, os_.pix_fmt = width, h, encoders.pix_fmt_for(enc)
            os_.options = encoders.options_for(enc)
            n = 0
            next_t = t0
            for fr in ic.decode(vs):
                ft = float(fr.time or 0)
                if ft < t0 - 1e-3:
                    continue
                if ft > t1:
                    break
                if ft + 1e-6 < next_t:
                    continue
                next_t = ft + 1.0 / out_fps
                f2 = fr.reformat(width=width, height=h, format=os_.pix_fmt)
                f2.pts = n
                n += 1
                for p in os_.encode(f2):
                    out.mux(p)
            for p in os_.encode(None):
                out.mux(p)
    return buf.getvalue()


def analyze_clip(c: Candidate, question: str, model: str, *, case_id: int, query_id: int,
                 half: float = 6.0) -> tuple[dict | None, dict]:
    t0, t1 = max(0.0, c.t - half), c.t + half
    usage = {"cost": 0.0, "in": 0, "out": 0}
    info = catalog.get(model)
    start_label = label(c)
    try:
        if info is None or info.get("video"):
            mp4 = make_clip(c.evidence_id, t0, t1)
            content = [{"type": "text", "text": f"Soru: {question}\nKesit: {start_label}. Kesit, adayın {half:.0f} sn "
                                                f"öncesinden başlar ve {2 * half:.0f} sn sürer."},
                       client.video_part(mp4, "static")]
        else:
            ev = evidence.require(c.evidence_id)
            src = evidence.evidence_file(ev)
            content = [{"type": "text", "text": f"Soru: {question}\nAşağıda {start_label} anının çevresinden "
                                                f"sırayla alınmış kareler var (her biri ~2 sn arayla)."}]
            for k in range(6):
                got = frames.frame_at(src, t0 + k * (t1 - t0) / 5)  # type: ignore[arg-type]
                if got:
                    content.append(client.image_part(frames.encode_jpeg(frames.resize_to_width(got[1], 640), 82)))
        res = client.chat(model, [{"role": "system", "content": prompts.VIDEO_SYSTEM},
                                  {"role": "user", "content": content}],
                          None, role="video", case_id=case_id, query_id=query_id, max_tokens=500)
        usage = {"cost": res["cost"], "in": res["usage"]["in"], "out": res["usage"]["out"]}
        return {"candidate": c.id, "t0": t0, "t1": t1, "text": res["content"].strip()}, usage
    except client.AIError as e:
        return {"candidate": c.id, "t0": t0, "t1": t1, "error": str(e)}, usage
