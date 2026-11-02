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
