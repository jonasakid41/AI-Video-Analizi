"""Sentetik CCTV test videosu üreticisi.

Sahne: sabit arka plan, 2–8 sn arası soldan sağa yürüyen "kişi" (kırmızı üst, mavi alt),
10–16 sn arası plakalı bir "araç". Sol üstte kamera saati (OSD) yazar; saat bilerek
`osd_offset` kadar kaydırılabilir ve `gap_at` anında `gap_s` kadar sıçratılabilir.
"""

from __future__ import annotations

import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

BASE_REAL = datetime(2026, 10, 28, 14, 30, 0)


@dataclass
class Scene:
    width: int = 640
    height: int = 360
    fps: int = 12
    seconds: float = 20.0
    osd_offset: float = 0.0        # kamera saati - gerçek saat (sn)
    gap_at: float | None = None    # bu medya anından sonra kamera saati sıçrar
    gap_s: float = 0.0
    plate: str = "34 ABC 123"

    @property
    def n_frames(self) -> int:
        return int(self.seconds * self.fps)

    def camera_time(self, t: float) -> datetime:
        cam = BASE_REAL + timedelta(seconds=t + self.osd_offset)
        if self.gap_at is not None and t >= self.gap_at:
            cam += timedelta(seconds=self.gap_s)
        return cam


def render(scene: Scene, i: int) -> np.ndarray:
    w, h = scene.width, scene.height
    t = i / scene.fps
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (70, 75, 80)
    cv2.rectangle(img, (0, int(h * 0.62)), (w, h), (95, 95, 95), -1)          # yol
    cv2.rectangle(img, (int(w * 0.05), int(h * 0.15)), (int(w * 0.30), int(h * 0.62)), (60, 90, 120), -1)
    cv2.rectangle(img, (int(w * 0.65), int(h * 0.20)), (int(w * 0.95), int(h * 0.62)), (90, 70, 60), -1)
    rng = np.random.default_rng(i)
    img = cv2.add(img, rng.integers(0, 6, img.shape, dtype=np.uint8))       # sensör gürültüsü

    if 2.0 <= t <= 8.0:  # kişi
        p = (t - 2.0) / 6.0
        x = int(w * 0.05 + p * w * 0.8)
        ph = int(h * 0.30)
        top = int(h * 0.60) - ph
        cv2.rectangle(img, (x, top), (x + ph // 4, top + ph // 2), (40, 40, 220), -1)       # kırmızı üst
        cv2.rectangle(img, (x, top + ph // 2), (x + ph // 4, top + ph), (160, 60, 20), -1)  # mavi alt
        cv2.circle(img, (x + ph // 8, top - ph // 10), ph // 10, (150, 180, 220), -1)

    if 10.0 <= t <= 16.0:  # araç
        p = (t - 10.0) / 6.0
        cw, ch = int(w * 0.34), int(h * 0.20)
        x = int(w * 0.9 - p * w * 0.8)
        y = int(h * 0.70)
        cv2.rectangle(img, (x, y), (x + cw, y + ch), (235, 235, 235), -1)                    # beyaz araç
        cv2.rectangle(img, (x + cw // 8, y - ch // 2), (x + cw * 7 // 8, y), (200, 200, 205), -1)
        pw, phh = int(cw * 0.60), int(ch * 0.32)
        px, py = x + (cw - pw) // 2, y + ch - phh - 4
        cv2.rectangle(img, (px, py), (px + pw, py + phh), (255, 255, 255), -1)
        cv2.rectangle(img, (px, py), (px + pw, py + phh), (0, 0, 0), 1)
        fs = phh / 30.0
        cv2.putText(img, scene.plate, (px + 4, py + phh - 5), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), 2, cv2.LINE_AA)

    cam = scene.camera_time(t)
    osd = cam.strftime("%d-%m-%Y %H:%M:%S")
    cv2.rectangle(img, (6, 6), (6 + 300, 34), (0, 0, 0), -1)
    cv2.putText(img, osd, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, "KAMERA 01", (w - 150, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def encoder_available(name: str) -> bool:
    if name not in av.codecs_available:
        return False
    try:
        ctx = av.CodecContext.create(name, "w")
        ctx.width, ctx.height = 256, 144
        ctx.pix_fmt = "yuvj420p" if name == "mjpeg" else "yuv420p"
        ctx.time_base = Fraction(1, 25)
        ctx.framerate = 25
        ctx.open()
        return True
    except Exception:  # noqa: BLE001
        return False


def write(path: Path, scene: Scene, fmt: str, codec: str, pix_fmt: str = "yuv420p",
          options: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w", format=fmt) as out:
        st = out.add_stream(codec, rate=scene.fps)
        st.width, st.height = scene.width, scene.height
        st.pix_fmt = pix_fmt
        if options:
            st.options = options
        for i in range(scene.n_frames):
            frame = av.VideoFrame.from_ndarray(render(scene, i), format="bgr24")
            for pkt in st.encode(frame):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    return path


def _sw_hevc() -> str | None:
    for c in ("libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_mf"):
        if encoder_available(c):
            return c
    return None


def build_corpus(dest: Path, seconds: float = 6.0) -> dict[str, dict]:
    """Test seti üretir. {dosya_adı: {"expect": beklenen_tür | None, ...}} döner."""
    dest.mkdir(parents=True, exist_ok=True)
    sc = Scene(seconds=seconds)
    out: dict[str, dict] = {}

    def add(name: str, expect: str | None, **extra):
        out[name] = {"expect": expect, **extra}

    write(dest / "h264.mp4", sc, "mp4", "libx264", options={"bf": "0"})
    add("h264.mp4", "mp4")
    write(dest / "h264.mkv", sc, "matroska", "libx264")
    add("h264.mkv", "matroska")
    write(dest / "mpeg2.mpg", sc, "mpeg", "mpeg2video")
    add("mpeg2.mpg", "mpegps")
    write(dest / "h264.ts", sc, "mpegts", "libx264")
    add("h264.ts", "mpegts")
    write(dest / "mjpeg.avi", sc, "avi", "mjpeg", pix_fmt="yuvj420p")
    add("mjpeg.avi", "avi")
    write(dest / "mpeg4.avi", sc, "avi", "mpeg4")
    add("mpeg4.avi", "avi")
    if encoder_available("wmv2"):
        write(dest / "wmv2.wmv", sc, "asf", "wmv2")
        add("wmv2.wmv", "asf")
    if encoder_available("flv"):
        write(dest / "flv1.flv", sc, "flv", "flv")
        add("flv1.flv", "flv")
    if encoder_available("libvpx-vp9"):
        write(dest / "vp9.webm", sc, "webm", "libvpx-vp9", options={"deadline": "realtime", "cpu-used": "8"})
        add("vp9.webm", "matroska")
    write(dest / "raw.264", sc, "h264", "libx264", options={"bf": "0"})
    add("raw.264", "h264", raw=True)
    hevc = _sw_hevc()
    if hevc:
        hopts = {"x265-params": "log-level=none"} if hevc == "libx265" else None
        write(dest / "hevc.mkv", sc, "matroska", hevc, options=hopts)
        add("hevc.mkv", "matroska")
        write(dest / "raw.h265", sc, "hevc", hevc, options=hopts)
        add("raw.h265", "hevc", raw=True)

    # Yanıltıcı / sorunlu dosyalar
    shutil.copy(dest / "h264.mp4", dest / "yanlis_uzanti.dav")
    add("yanlis_uzanti.dav", "mp4")
    shutil.copy(dest / "h264.ts", dest / "uzantisiz")
    add("uzantisiz", "mpegts")
    rnd = random.Random(7)
    junk = bytes(rnd.choice(range(1, 255)) for _ in range(777)).replace(b"\x00", b"\x01")
    (dest / "tescilli_baslik.bin").write_bytes(b"XVR1" + junk + (dest / "mpeg2.mpg").read_bytes())
    add("tescilli_baslik.bin", "mpegps", offset=True)
    (dest / "imkh_taklit.mp4").write_bytes(b"IMKH" + bytes(36) + (dest / "mpeg2.mpg").read_bytes())
    add("imkh_taklit.mp4", "hikvision")
    (dest / "baslikli_ham.264").write_bytes(junk + (dest / "raw.264").read_bytes())
    add("baslikli_ham.264", "h264", offset=True, raw=True)
    data = (dest / "h264.ts").read_bytes()
    (dest / "kesik.ts").write_bytes(data[: int(len(data) * 0.6)])
    add("kesik.ts", "mpegts", truncated=True)
    data = (dest / "h264.mp4").read_bytes()
    (dest / "bozuk.mp4").write_bytes(data[: len(data) // 3])  # moov sonda olduğu için açılamaz
    add("bozuk.mp4", None, expect_fail=True)
    return out


def build_vehicle_video(path: Path, base_image: Path, plate: str = "34 ABC 123", seconds: float = 12.0,
                        fps: int = 10) -> Path:
    """Gerçek bir fotoğraftaki kamyonun (YOLOX dog.jpg) üzerine plaka işlenmiş, hafif titreşimli video."""
    base = cv2.imdecode(np.fromfile(str(base_image), np.uint8), cv2.IMREAD_COLOR)
    px0, py0, px1, py1 = 520, 132, 640, 160          # kamyonun alt orta kısmı
    cv2.rectangle(base, (px0, py0), (px1, py1), (255, 255, 255), -1)
    cv2.rectangle(base, (px0, py0), (px1, py1), (0, 0, 0), 1)
    cv2.putText(base, plate, (px0 + 4, py1 - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    h, w = base.shape[:2]
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w", format="mp4") as out:
        st = out.add_stream("libx264", rate=fps)
        st.width, st.height, st.pix_fmt = w, h, "yuv420p"
        st.options = {"bf": "0"}
        for i in range(int(seconds * fps)):
            dx = int(3 * np.sin(i / 3))
            img = np.roll(base, dx, axis=1)
            img = cv2.add(img, np.random.default_rng(i).integers(0, 4, img.shape, dtype=np.uint8))
            cam = BASE_REAL + timedelta(seconds=i / fps)
            cv2.rectangle(img, (6, h - 34), (306, h - 6), (0, 0, 0), -1)
            cv2.putText(img, cam.strftime("%d-%m-%Y %H:%M:%S"), (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 255), 2, cv2.LINE_AA)
            for pkt in st.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    return path


def build_tree_video(path: Path, seconds: float = 20.0, fps: int = 10) -> Path:
    """Rüzgârda sallanan "ağaç" (hep aynı yerde salınan yeşil şekil) + 8–13 sn arası dedektörün
    tanımayacağı hareketli bir şekil. Beklenen: ağaç → çevresel (önemsiz), şekil → tanımlanamayan hareket."""
    W, H = 640, 360
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w", format="mp4") as out:
        st = out.add_stream("libx264", rate=fps)
        st.width, st.height, st.pix_fmt = W, H, "yuv420p"
        st.options = {"bf": "0"}
        for i in range(int(seconds * fps)):
            t = i / fps
            img = np.full((H, W, 3), (200, 180, 150), np.uint8)              # açık gökyüzü
            cv2.rectangle(img, (0, int(H * 0.65)), (W, H), (100, 100, 100), -1)
            sway = int(14 * np.sin(2 * np.pi * t * 0.9))
            cv2.ellipse(img, (110 + sway, 120), (60, 80), 0, 0, 360, (40, 140, 50), -1)
            cv2.ellipse(img, (90 - sway, 90), (35, 45), 0, 0, 360, (30, 120, 40), -1)
            cv2.rectangle(img, (104, 190), (118, 250), (40, 60, 90), -1)
            if 8.0 <= t <= 13.0:
                x = int(330 + (t - 8.0) / 5.0 * 250)
                cv2.rectangle(img, (x, 200), (x + 30, 245), (200, 200, 60), -1)
            img = cv2.add(img, np.random.default_rng(i).integers(0, 4, img.shape, dtype=np.uint8))
            for pkt in st.encode(av.VideoFrame.from_ndarray(img, format="bgr24")):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    return path


def build_from_real(path: Path, src: Path, seconds: float = 20.0, scale: float = 1.0,
                    canvas: tuple[int, int] | None = None, gray: bool = False, dark: float = 1.0,
                    freeze: float | None = None) -> Path:
    """Gerçek bir videodan türetilmiş test kaydı.
    scale + canvas: görüntü küçültülüp büyük bir tuvalin köşesine konur (geniş açılı kamerada uzaktaki kişiler);
    gray: siyah-beyaz (gece/IR) kayıt; dark: parlaklık çarpanı (<1 karanlık);
    freeze: bu saniyedeki kare `seconds` boyunca tekrarlanır (hareketsiz sahne: duran kişiler, park etmiş araçlar)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def source(ic, vs, fps):
        for fr in ic.decode(vs):
            t = float(fr.time or 0)
            if freeze is None:
                if t > seconds:
                    return
                yield t, fr.to_ndarray(format="bgr24")
            elif t >= freeze:
                img = fr.to_ndarray(format="bgr24")
                for i in range(int(seconds * fps)):
                    yield i / fps, img
                return

    with av.open(str(src)) as ic, av.open(str(path), "w", format="mp4") as out:
        vs = ic.streams.video[0]
        fps = float(vs.average_rate or 10)
        st = None
        for t, img in source(ic, vs, fps):
            if scale != 1.0:
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if canvas:
                cw, chh = canvas
                bg = np.full((chh, cw, 3), (95, 105, 100), np.uint8)
                y0 = chh - img.shape[0] - chh // 10
                bg[y0:y0 + img.shape[0], cw // 8:cw // 8 + img.shape[1]] = img
                img = bg
            if gray:
                img = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            if dark != 1.0:
                img = cv2.convertScaleAbs(img, alpha=dark)
            if st is None:
                st = out.add_stream("libx264", rate=Fraction(fps).limit_denominator(1000))
                st.width, st.height, st.pix_fmt = img.shape[1] // 2 * 2, img.shape[0] // 2 * 2, "yuv420p"
                st.options = {"bf": "0", "crf": "20"}
            for pkt in st.encode(av.VideoFrame.from_ndarray(img[:st.height, :st.width], format="bgr24")):
                out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    return path


# --- Hikvision dışa aktarımı taklidi: IMKH başlığı + MPEG-PS (PSM, bölünmüş PES) ---------------

# Gerçek bir dışa aktarımın ilk 40 baytı (H.265 video, G.711 ses 8 kHz)
IMKH_HEVC = bytes.fromhex("494d4b4802010000020005001071011040" "1f0000401f0000") + bytes(16)


def _pts5(v: int, prefix: int = 0b0010) -> bytes:
    return bytes([(prefix << 4) | (((v >> 30) & 7) << 1) | 1, (v >> 22) & 0xFF, (((v >> 15) & 0x7F) << 1) | 1,
                  (v >> 7) & 0xFF, ((v & 0x7F) << 1) | 1])


def _pack_header(scr: int) -> bytes:
    v = (1 << 46) | (((scr >> 30) & 7) << 43) | (1 << 42) | (((scr >> 15) & 0x7FFF) << 27) | (1 << 26) \
        | ((scr & 0x7FFF) << 11) | (1 << 10) | 1
    return b"\x00\x00\x01\xba" + v.to_bytes(6, "big") + ((6106 << 2) | 3).to_bytes(3, "big") + b"\xf8"


def _psm(entries: list[tuple[int, int]]) -> bytes:
    es_map = b"".join(bytes([t, sid, 0, 0]) for t, sid in entries)
    body = b"\xe0\xff" + (0).to_bytes(2, "big") + len(es_map).to_bytes(2, "big") + es_map
    return b"\x00\x00\x01\xbc" + (len(body) + 4).to_bytes(2, "big") + body + bytes(4)


def _pes(sid: int, payload: bytes, pts: int | None) -> bytes:
    hdr = (b"\x80\x80\x05" + _pts5(pts)) if pts is not None else b"\x80\x00\x00"
    return b"\x00\x00\x01" + bytes([sid]) + (len(hdr) + len(payload)).to_bytes(2, "big") + hdr + payload


def build_hikvision_ps(path: Path, codec: str = "libx265", size: tuple[int, int] = (2560, 1440),
                       seconds: float = 8.0, fps: int = 25, skip: int = 7, psm: bool = True,
                       pts_base: int = 1_000_000, jumps: dict[int, int] | None = None, chunk: int = 65000) -> dict:
    """Hikvision NVR/DVR dışa aktarımı gibi bir dosya. Büyük kareler birden çok PES paketine bölünür ve
    zaman damgası yalnızca ilk parçada bulunur; kayıt bir GOP'un ortasından başlar (skip kare atlanır);
    jumps = {kare no: 90 kHz kayma} kamera saatinin geri/ileri atlamasını taklit eder."""
    W, H = size
    ctx = av.CodecContext.create(codec, "w")
    ctx.width, ctx.height, ctx.pix_fmt = W, H, "yuv420p"
    ctx.time_base, ctx.framerate = Fraction(1, fps), Fraction(fps)
    ctx.options = ({"preset": "ultrafast", "x265-params": "keyint=25:min-keyint=25:bframes=0:repeat-headers=1:log-level=error"}
                   if codec == "libx265" else {"preset": "ultrafast", "bf": "0", "g": "25"})
    rng = np.random.default_rng(3)
    texture = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    packets: list[tuple[bytes, bool]] = []
    n = int(seconds * fps)
    for i in range(n + 1):
        frame = None
        if i < n:
            img = cv2.addWeighted(texture, 0.35, np.full_like(texture, 110), 0.65, 0)
            x = int(W * 0.1 + (W * 0.7) * i / n)
            cv2.rectangle(img, (x, H // 3), (x + W // 10, H // 3 + H // 4), (30, 40, 200), -1)
            frame = av.VideoFrame.from_ndarray(img, format="bgr24").reformat(format="yuv420p")
            frame.pts = i
        for p in ctx.encode(frame):
            packets.append((bytes(p), p.is_keyframe))
    out = bytearray(IMKH_HEVC if codec == "libx265" else IMKH_HEVC[:10] + b"\x01\x00" + IMKH_HEVC[12:])
    stype = 0x24 if codec == "libx265" else 0x1B
    pts = pts_base
    frames_written = 0
    for i, (data, key) in enumerate(packets[skip:], start=skip):
        pts += 90000 // fps + (jumps or {}).get(i, 0)
        out += _pack_header(pts - 3600)
        if key and psm:
            out += _psm([(stype, 0xE0), (0x90, 0xC0)])
        for k in range(0, len(data), chunk):
            out += _pes(0xE0, data[k:k + chunk], pts if k == 0 else None)
        out += _pes(0xC0, b"\xd5" * (8000 // fps), pts)  # G.711 A-law sessizlik
        frames_written += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    sizes = [len(d) for d, _k in packets]
    return {"frames": frames_written, "max_frame": max(sizes), "split_frames": sum(s > chunk for s in sizes)}


def build_osd_video(path: Path, osd_offset: float = 222.0, gap_at: float | None = 10.0,
                    gap_s: float = 600.0, seconds: float = 20.0) -> Scene:
    sc = Scene(seconds=seconds, osd_offset=osd_offset, gap_at=gap_at, gap_s=gap_s)
    write(path, sc, "mp4", "libx264", options={"bf": "0"})
    return sc


if __name__ == "__main__":
    target = Path(os.environ.get("AIVA_CORPUS", Path(__file__).resolve().parents[2] / "testdata" / "corpus"))
    files = build_corpus(target)
    build_osd_video(target / "osd_yanlis_saat.mp4")
    print(f"{len(files) + 1} dosya üretildi: {target}")
