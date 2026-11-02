"""Görüntü iyileştirme.

Klasik işlemler deterministik ve tekrarlanabilirdir (parametreleri kaydedilir).
AI büyütme (Real-ESRGAN) görüntüye olmayan detay ekleyebilir; çıktı görünür filigran taşır ve
"soruşturma ipucu, delil değildir" olarak işaretlenir. Yüz "restorasyonu" bilerek yoktur.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import cv2
import numpy as np

from . import evidence, history, jobs, paths
from .analyze import lowlight, runtime
from .media import frames
from .util import dumps, imwrite

AI_WATERMARK = "AI ile iyileştirilmiştir — soruşturma ipucudur, delil değildir"

OPS = {
    "parlaklik": "Parlaklık / kontrast",
    "gama": "Gama",
    "clahe": "Yerel kontrast (CLAHE)",
    "esitle": "Histogram eşitleme",
    "gurultu": "Gürültü azaltma",
    "keskinlestir": "Keskinleştirme",
    "deinterlace": "Satır birleştirme (deinterlace)",
    "gri": "Gri ton",
    "buyut": "Matematiksel büyütme (Lanczos)",
    "coklu_kare": "Çok kareli birleştirme",
    "ai_buyut": "AI büyütme (Real-ESRGAN)",
}


def _f(params: dict, key: str, default: float, lo: float, hi: float) -> float:
    try:
        v = float(params.get(key, default))
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def apply_classic(img: np.ndarray, op: str, p: dict) -> np.ndarray:
    if op == "parlaklik":
        a = _f(p, "kontrast", 1.2, 0.2, 3.0)
        b = _f(p, "parlaklik", 10, -100, 100)
        return cv2.convertScaleAbs(img, alpha=a, beta=b)
    if op == "gama":
        g = _f(p, "deger", 1.4, 0.2, 4.0)
        lut = np.array([((i / 255.0) ** (1.0 / g)) * 255 for i in range(256)], np.uint8)
        return cv2.LUT(img, lut)
    if op == "clahe":
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        cl = cv2.createCLAHE(clipLimit=_f(p, "siddet", 2.5, 0.5, 8.0), tileGridSize=(8, 8))
        lab[..., 0] = cl.apply(lab[..., 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if op == "esitle":
        ycc = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
        ycc[..., 0] = cv2.equalizeHist(ycc[..., 0])
        return cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)
    if op == "gurultu":
        h = _f(p, "siddet", 7, 1, 25)
        if lowlight.frame_stats(img)[0]:
            # Siyah-beyaz (gece/IR) kare: tek kanalda temizlenir, sahte renk lekesi oluşmaz ve daha hızlıdır
            g = cv2.fastNlMeansDenoising(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None, h, 7, 21)
            return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        return cv2.fastNlMeansDenoisingColored(img, None, h, h, 7, 21)
    if op == "keskinlestir":
        amount = _f(p, "miktar", 1.0, 0.1, 3.0)
        sigma = _f(p, "yaricap", 1.2, 0.3, 5.0)
        blur = cv2.GaussianBlur(img, (0, 0), sigma)
        return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)
    if op == "deinterlace":
        even = img[0::2]
        return cv2.resize(even, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    if op == "gri":
        return cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if op == "buyut":
        k = _f(p, "kat", 2, 1, 8)
        return cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4)
    raise ValueError(f"Bilinmeyen işlem: {op}")


def multi_frame(path: Path, t: float, box: list[float] | None, n: int = 7, step: float | None = None) -> np.ndarray:
    """Komşu kareleri hizalayıp (ECC) ortalar: durağan nesnelerde gerçek bilgiyle gürültü azaltır."""
    with frames.decoding(path, threads=False) as (c, vs):
        fps = float(vs.average_rate or 25)
    step = step or 1.0 / fps
    times = [t + (i - n // 2) * step for i in range(n)]
    imgs = []
    for tt in times:
        got = frames.frame_at(path, max(0.0, tt))
        if got:
            imgs.append(_crop(got[1], box))
    if not imgs:
        raise ValueError("Kare alınamadı")
    ref = imgs[len(imgs) // 2].astype(np.float32)
    ref_g = cv2.cvtColor(ref.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    acc = np.zeros_like(ref)
    used = 0
    for im in imgs:
        if im.shape != ref.shape:
            continue
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(ref_g, g, warp, cv2.MOTION_EUCLIDEAN,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4), None, 5)
            aligned = cv2.warpAffine(im, warp, (ref.shape[1], ref.shape[0]),
                                     flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
        except cv2.error:
            continue
        acc += aligned.astype(np.float32)
        used += 1
    if used == 0:
        return imgs[len(imgs) // 2]
    return np.clip(acc / used, 0, 255).astype(np.uint8)


def ai_upscale(img: np.ndarray, factor: int = 4, tile: int = 256, pad: int = 16, progress=None) -> np.ndarray:
    key = "esrgan_x4" if factor >= 4 else "esrgan_x2"
    s = 4 if factor >= 4 else 2
    sess = runtime.session(key)
    h, w = img.shape[:2]
    if max(h, w) > 1400:
        raise ValueError("AI büyütme için seçilen bölge çok büyük. Daha küçük bir alan seçin (en fazla 1400 px).")
    rgb = img[..., ::-1].astype(np.float32) / 255.0
    out = np.zeros((h * s, w * s, 3), np.float32)
    tiles = [(y, x) for y in range(0, h, tile) for x in range(0, w, tile)]
    for i, (y, x) in enumerate(tiles):
        y0, x0 = max(0, y - pad), max(0, x - pad)
        y1, x1 = min(h, y + tile + pad), min(w, x + tile + pad)
        patch = rgb[y0:y1, x0:x1].transpose(2, 0, 1)[None]
        with jobs.gpu_lock:
            res = sess.run(None, {"input": np.ascontiguousarray(patch)})[0][0].transpose(1, 2, 0)
        ty0, tx0 = (y - y0) * s, (x - x0) * s
        th, tw = min(tile, h - y) * s, min(tile, w - x) * s
        out[y * s:y * s + th, x * s:x * s + tw] = res[ty0:ty0 + th, tx0:tx0 + tw]
        if progress:
            progress((i + 1) / len(tiles))
    return (np.clip(out, 0, 1) * 255).round().astype(np.uint8)[..., ::-1].copy()


def watermark(img: np.ndarray, text: str = AI_WATERMARK) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(img[..., ::-1])
    W, H = pil.size
    size = max(12, W // 40)
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except OSError:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(pil, "RGBA")
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.rectangle([0, H - th - 12, min(W, tw + 16), H], fill=(0, 0, 0, 170))
    draw.text((8, H - th - 8), text, font=font, fill=(255, 210, 0, 255))
    return np.array(pil)[..., ::-1].copy()


def _crop(img: np.ndarray, box: list[float] | None) -> np.ndarray:
    if not box:
        return img
    H, W = img.shape[:2]
    x, y, w, h = box
    x0, y0 = max(0, int(x * W)), max(0, int(y * H))
    x1, y1 = min(W, int((x + w) * W)), min(H, int((y + h) * H))
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise ValueError("Seçilen bölge çok küçük")
    return img[y0:y1, x0:x1].copy()


def run(evidence_id: int, t: float, box: list[float] | None, ops: list[dict], progress=None) -> dict:
    ev = evidence.require(evidence_id)
    src = evidence.evidence_file(ev)
    if src is None:
        raise ValueError("Video henüz dönüştürülmedi")
    got = frames.frame_at(src, t)
    if got is None:
        raise ValueError("Kare alınamadı")
    ft, full = got
    original = _crop(full, box)
    img = original
    chain = []
    is_ai = False
    for i, step in enumerate(ops):
        op = step.get("op")
        params = step.get("params") or {}
        if op == "coklu_kare":
            img = multi_frame(src, ft, box, int(_f(params, "kare", 7, 3, 25)))
        elif op == "ai_buyut":
            img = ai_upscale(img, int(_f(params, "kat", 4, 2, 4)),
                             progress=(lambda v, i=i: progress((i + v) / max(1, len(ops)))) if progress else None)
            is_ai = True
        else:
            img = apply_classic(img, op, params)
        chain.append({"islem": op, "ad": OPS.get(op, op), "parametreler": params})
        if progress:
            progress((i + 1) / max(1, len(ops)))
    if is_ai:
        img = watermark(img)
    m = evidence.get_mapping(evidence_id)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = paths.exports_dir(ev["case_id"]) / "iyilestirme"
    base = out_dir / f"{stamp}_v{evidence_id}_{int(ft * 1000)}"
    imwrite(base.with_name(base.name + "_orijinal.png"), original)
    imwrite(base.with_suffix(".png"), img)
    cam, real = m.to_camera(ft), m.to_real(ft)
    meta = {
        "video": ev["original_name"], "video_sha256": ev["sha256"], "medya_zamani_sn": round(ft, 4),
        "kamera_saati": cam.isoformat() if cam else None, "gercek_saat": real.isoformat() if real else None,
        "bolge": box, "islem_zinciri": chain, "ai_iyilestirme": is_ai,
        "uyari": AI_WATERMARK if is_ai else None,
        "cikti_sha256": hashlib.sha256(base.with_suffix(".png").read_bytes()).hexdigest(),
        "olusturma": stamp,
    }
    base.with_suffix(".json").write_text(dumps(meta), encoding="utf-8")
    rel = lambda p: p.resolve().relative_to(paths.data_dir().resolve()).as_posix()  # noqa: E731
    history.log("iyilestirme", ev["case_id"], evidence_id, t=round(ft, 3), islemler=[c["islem"] for c in chain], ai=is_ai)
    return {"image": rel(base.with_suffix(".png")), "original": rel(base.with_name(base.name + "_orijinal.png")),
            "meta": rel(base.with_suffix(".json")), "ai": is_ai, "chain": chain, "t": ft,
            "size": [int(img.shape[1]), int(img.shape[0])]}


@jobs.register("enhance")
def enhance_job(ctx: jobs.JobContext, params: dict) -> dict:
    return run(params["evidence_id"], float(params["t"]), params.get("box"), params.get("ops") or [],
               progress=lambda v: ctx.progress(v, "İyileştiriliyor"))
