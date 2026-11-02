"""Dosya türünü uzantıya değil içeriğe bakarak tahmin eder.

Sonuç, dönüştürücünün hangi demuxer'ı ve hangi başlık atlama ofsetini deneyeceğini belirler.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

HEAD_BYTES = 64 * 1024
SCAN_BYTES = 4 * 1024 * 1024

ASF_GUID = bytes.fromhex("3026B2758E66CF11A6D900AA0062CE6C")
EBML = bytes.fromhex("1A45DFA3")
MXF = bytes.fromhex("060E2B34")
PS_PACK = b"\x00\x00\x01\xba"


@dataclass
class SniffResult:
    kind: str                     # mp4, matroska, avi, asf, flv, mpegps, mpegts, dhav, hikvision, h264, hevc, mxf, ogg, unknown
    label: str                    # kullanıcıya gösterilen açıklama
    format_hint: str | None       # PyAV/FFmpeg demuxer adı
    offset: int = 0               # tescilli başlık varsa veri başlangıcı
    confidence: float = 0.5
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _is_ts(buf: bytes, start: int = 0) -> bool:
    try:
        return all(buf[start + i * 188] == 0x47 for i in range(4))
    except IndexError:
        return False


def find_annexb(buf: bytes, start: int = 0) -> tuple[int, str] | None:
    """İlk geçerli H.264/H.265 parametre seti NAL'ını bulur. (ofset, codec) döner."""
    i = start
    n = len(buf)
    while True:
        i = buf.find(b"\x00\x00\x01", i)
        if i < 0 or i + 4 >= n:
            return None
        b = buf[i + 3]
        sc = i - 1 if i > 0 and buf[i - 1] == 0 else i
        # H.265 VPS/SPS/PPS (32/33/34): forbidden bit 0, layer id 0
        hevc_type = (b >> 1) & 0x3F
        if b & 0x80 == 0 and hevc_type in (32, 33) and buf[i + 4] in (0x01,):
            return sc, "hevc"
        # H.264 SPS (7) / PPS (8): nal_ref_idc > 0
        if b & 0x80 == 0 and (b & 0x1F) == 7 and (b & 0x60):
            return sc, "h264"
        i += 3


def sniff(path: Path) -> SniffResult:
    with path.open("rb") as f:
        head = f.read(HEAD_BYTES)
    if len(head) < 16:
        return SniffResult("unknown", "Dosya çok küçük veya boş", None, confidence=0.0)

    if head[4:8] == b"ftyp" or head[4:8] in (b"moov", b"mdat", b"free", b"wide"):
        brand = head[8:12].decode("latin-1", "replace")
        r = SniffResult("mp4", f"MP4/MOV (marka: {brand.strip()})", "mov", confidence=0.95)
        # Hikvision ".mp4" dışa aktarımları çoğu zaman içerde MPEG-PS taşır
        if PS_PACK in head[:4096] and b"moov" not in head:
            r.notes.append("MP4 kabında MPEG-PS işaretleri var (Hikvision olabilir)")
        return r
    if head[:4] in (b"IMKH", b"4HKH"):
        off = head.find(PS_PACK)
        return SniffResult("hikvision", "Hikvision dışa aktarımı (IMKH başlıklı MPEG-PS)", "mpeg",
                           offset=off if off > 0 else 40, confidence=0.9)
    if head[:4] == b"DHAV" or head.find(b"DHAV", 0, 4096) >= 0:
        return SniffResult("dhav", "Dahua DAV kaydı", "dhav", offset=max(0, head.find(b"DHAV")), confidence=0.9)
    if head[:4] == b"RIFF" and head[8:11] == b"AVI":
        return SniffResult("avi", "AVI", "avi", confidence=0.95)
    if head[:16] == ASF_GUID:
        return SniffResult("asf", "WMV/ASF", "asf", confidence=0.95)
    if head[:4] == EBML:
        return SniffResult("matroska", "Matroska/WebM (MKV)", "matroska", confidence=0.95)
    if head[:3] == b"FLV":
        return SniffResult("flv", "Flash Video (FLV)", "flv", confidence=0.95)
    if head[:4] == MXF:
        return SniffResult("mxf", "MXF", "mxf", confidence=0.9)
    if head[:4] == b"OggS":
        return SniffResult("ogg", "Ogg", "ogg", confidence=0.9)
    if head[:4] == PS_PACK:
        return SniffResult("mpegps", "MPEG Program Stream (PS/VOB)", "mpeg", confidence=0.9)
    if _is_ts(head):
        return SniffResult("mpegts", "MPEG Transport Stream (TS)", "mpegts", confidence=0.9)

    # Tanınmayan başlık: ilk birkaç MB içinde bilinen bir yapı ara (tescilli başlık atlama)
    with path.open("rb") as f:
        scan = f.read(SCAN_BYTES)
    ps = scan.find(PS_PACK)
    ts = next((i for i in range(0, min(len(scan) - 800, 1 << 20)) if scan[i] == 0x47 and _is_ts(scan, i)), -1)
    ab = find_annexb(scan)
    candidates: list[SniffResult] = []
    if ps >= 0:
        candidates.append(SniffResult("mpegps", "Başında tanınmayan başlık olan MPEG-PS", "mpeg", offset=ps,
                                      confidence=0.6, notes=[f"{ps} bayt başlık atlanacak"]))
    if ts >= 0:
        candidates.append(SniffResult("mpegts", "Başında tanınmayan başlık olan MPEG-TS", "mpegts", offset=ts,
                                      confidence=0.6, notes=[f"{ts} bayt başlık atlanacak"]))
    if ab is not None:
        off, codec = ab
        label = "Ham H.264 akışı" if codec == "h264" else "Ham H.265/HEVC akışı"
        if off > 0:
            label += " (başında tanınmayan başlık var)"
        candidates.append(SniffResult(codec, label, codec, offset=off, confidence=0.7 if off == 0 else 0.55,
                                      notes=[f"{off} bayt başlık atlanacak"] if off else []))
    if candidates:
        return min(candidates, key=lambda c: (c.offset, -c.confidence))
    return SniffResult("unknown", "Tanınmayan biçim", None, confidence=0.0)


def hex_head(path: Path, n: int = 4096) -> str:
    with path.open("rb") as f:
        data = f.read(n)
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hx:<47}  {asc}")
    return "\n".join(lines)
