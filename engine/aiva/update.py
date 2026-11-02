"""Uygulama içi güncelleme.

Akış:
1. `check()` GitHub'daki son sürümü sorar (yalnızca kullanıcı isteyince ya da ayarda açıksa açılışta).
2. `guncelleme` işi ZIP'i indirir, SHA-256'sını doğrular ve `data/updates/staging/` altına açar.
   Hazır olunca `data/updates/hazir.json` yazılır.
3. Dosyaların yerine konması motorun işi değildir: çalışan exe ve DLL'ler kilitlidir. Masaüstü kabuğu
   kendini `guncelleyici.exe` olarak kopyalar, uygulama kapanınca eski dosyaları `_eski_surum/` klasörüne
   taşıyıp yenilerini koyar ve yeni sürümü açar. Sonuç `data/updates/sonuc.json` dosyasına yazılır.
4. Yeni sürüm açılışta `cleanup()` ile yedeği ve geçici dosyaları siler.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import zipfile
from pathlib import Path
from typing import Any

import httpx

from . import __version__, jobs, paths, settings
from .util import now_iso, remove_tree

log = logging.getLogger(__name__)

REPO = "jonasakid41/AI-Video-Analizi"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSET_RE = re.compile(r"^AIVideoAnalizi-[\w.]+-win64\.zip$")
SHA_RE = re.compile(r"SHA-256\W{0,12}([0-9a-fA-F]{64})")
EXE = "AIVideoAnalizi.exe"
BACKUP = "_eski_surum"

# Testlerde sahte GitHub yanıtı için
transport: httpx.BaseTransport | None = None

_last: dict | None = None
_lock = threading.Lock()


class UpdateError(ValueError):
    pass


def updates_dir() -> Path:
    p = paths.data_dir() / "updates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def _client(timeout: httpx.Timeout | float) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, transport=transport,
                        headers={"User-Agent": f"AIVideoAnalizi/{__version__}",
                                 "Accept": "application/vnd.github+json"})


def check() -> dict:
    """Son sürümü sorar. Dışarıya giden tek istek budur; kimlik ya da kullanım bilgisi gönderilmez."""
    global _last
    try:
        with _client(20.0) as cli:
            r = cli.get(LATEST_URL)
    except httpx.HTTPError as e:
        raise UpdateError(f"GitHub'a bağlanılamadı ({e.__class__.__name__}). İnternet bağlantınızı kontrol edin.") from e
    if r.status_code == 404:
        raise UpdateError("Yayımlanmış bir sürüm bulunamadı")
    if r.status_code == 403:
        raise UpdateError("GitHub istek sınırına ulaşıldı; bir saat sonra yeniden deneyin")
    if r.status_code != 200:
        raise UpdateError(f"GitHub yanıt vermedi ({r.status_code})")
    rel = r.json()
    latest = str(rel.get("tag_name") or "").lstrip("vV")
    notes = str(rel.get("body") or "")
    asset = next((a for a in rel.get("assets") or [] if ASSET_RE.match(str(a.get("name", "")))), None)
    info: dict[str, Any] = {
        "current": __version__, "latest": latest, "newer": parse_version(latest) > parse_version(__version__),
        "title": rel.get("name") or f"v{latest}", "notes": notes, "published_at": rel.get("published_at"),
        "page": rel.get("html_url"), "asset": None, "checked_at": now_iso(),
    }
    if asset:
        digest = str(asset.get("digest") or "")
        sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
        if not sha and (m := SHA_RE.search(notes)):
            sha = m.group(1)
        info["asset"] = {"name": asset["name"], "size": int(asset.get("size") or 0),
                         "url": asset.get("browser_download_url"), "sha256": sha.lower() if sha else None}
    with _lock:
        _last = info
    settings.update({"update": {"last_check": info["checked_at"]}})
    return info


def can_apply() -> tuple[bool, str | None]:
    if not paths.is_frozen():
        return False, "Geliştirme sürümünde güncelleme uygulanamaz; derlenmiş paketi kullanın."
    root = paths.app_root()
    probe = root / ".yazma_testi"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        return False, "Uygulama klasörüne yazılamıyor. Uygulamayı yazılabilir bir klasöre (ör. Masaüstü) taşıyın."
    return True, None


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def staged() -> dict | None:
    s = _read_json(updates_dir() / "hazir.json")
    if not s or not (Path(s.get("dir", "")) / EXE).is_file():
        return None
    return s


def status() -> dict:
    ok, reason = can_apply()
    s = settings.load()["update"]
    return {"current": __version__, "can_apply": ok, "reason": reason, "check_on_start": bool(s.get("check_on_start")),
            "last_check": s.get("last_check"), "latest": _last, "staged": staged(),
            "result": _read_json(updates_dir() / "sonuc.json")}


def _job_info(version: str) -> dict:
    info = check()  # paket sonradan değiştirilmiş olabilir; özet her indirmede yeniden alınır
    if info["latest"] != version:
        raise UpdateError(f"GitHub'daki son sürüm artık v{info['latest']}; yeniden denetleyin")
    asset = info.get("asset")
    if not asset or not asset.get("url"):
        raise UpdateError("Bu sürümde Windows paketi bulunamadı")
    if not str(asset["url"]).startswith(DOWNLOAD_PREFIX):
        raise UpdateError("Paket adresi beklenen GitHub deposuna ait değil; indirme durduruldu")
    if not asset.get("sha256"):
        raise UpdateError("Paketin SHA-256 değeri bulunamadı; güvenlik için indirme durduruldu")
    return info


def _download(ctx: jobs.JobContext, asset: dict, dest: Path) -> None:
    part = dest.with_suffix(".part")
    h = hashlib.sha256()
    done = 0
    total = asset["size"] or 1
    try:
        with _client(httpx.Timeout(30.0, read=60.0)) as cli, cli.stream("GET", asset["url"]) as r:
            if r.status_code != 200:
                raise UpdateError(f"Paket indirilemedi ({r.status_code})")
            total = int(r.headers.get("content-length") or total)
            with part.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    ctx.progress(0.85 * done / total, f"İndiriliyor ({done / 2**20:.0f} / {total / 2**20:.0f} MB)")
    except httpx.HTTPError as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"İndirme yarıda kesildi ({e.__class__.__name__}); yeniden deneyin") from e
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if h.hexdigest() != asset["sha256"]:
        part.unlink(missing_ok=True)
        raise UpdateError("İndirilen paketin SHA-256 değeri yayımlanan değerle uyuşmuyor; dosya silindi")
    part.replace(dest)


def _long(p: Path) -> Path:
    """Windows'ta 260 karakter sınırını aşan yollar için uzun yol öneki. Motor DLL'leri paket içinde
    derin klasörlerde; uygulama uzun bir yola kurulduysa açma ve silme bu önek olmadan başarısız oluyordu."""
    s = str(p.absolute())
    if os.name != "nt" or s.startswith("\\\\"):
        return p
    return Path("\\\\?\\" + s)


def _extract(ctx: jobs.JobContext, zpath: Path, dest: Path) -> Path:
    remove_tree(_long(dest))
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zpath) as z:
        members = z.infolist()
        total = sum(m.file_size for m in members) or 1
        done = 0
        for m in members:
            rel = os.path.normpath(m.filename)
            if rel.startswith("..") or os.path.isabs(rel) or ":" in rel:
                raise UpdateError(f"Pakette geçersiz dosya yolu var: {m.filename}")
            z.extract(m, _long(dest))
            done += m.file_size
            ctx.progress(0.85 + 0.14 * done / total, "Paket açılıyor")
    app = dest / "AIVideoAnalizi" if (dest / "AIVideoAnalizi" / EXE).is_file() else dest
    if not (app / EXE).is_file() or not (app / "engine" / "aiva-engine.exe").is_file():
        raise UpdateError("Paket beklenen dosyaları içermiyor (AIVideoAnalizi.exe, engine/aiva-engine.exe)")
    return app


@jobs.register("guncelleme")
def download_job(ctx: jobs.JobContext, params: dict) -> dict:
    version = str(params["version"])
    info = _job_info(version)
    d = updates_dir()
    discard()
    zpath = d / info["asset"]["name"]
    try:
        ctx.progress(0.0, "İndiriliyor")
        _download(ctx, info["asset"], zpath)
        app = _extract(ctx, zpath, d / "staging")
    except BaseException:
        remove_tree(_long(d / "staging"))
        raise
    finally:
        zpath.unlink(missing_ok=True)
    (d / "hazir.json").write_text(json.dumps({"version": version, "dir": str(app), "created_at": now_iso()},
                                             ensure_ascii=False), encoding="utf-8")
    ctx.progress(1.0, f"v{version} kurulmaya hazır")
    return {"version": version}


def start_download(version: str) -> int:
    ok, reason = can_apply()
    if not ok:
        raise UpdateError(reason)
    running = [j for j in jobs.list_jobs(active_only=True) if j["kind"] == "guncelleme"]
    if running:
        return running[0]["id"]
    return jobs.submit("guncelleme", {"version": version})


def discard() -> None:
    d = updates_dir()
    (d / "hazir.json").unlink(missing_ok=True)
    remove_tree(_long(d / "staging"))


def ack_result() -> None:
    (updates_dir() / "sonuc.json").unlink(missing_ok=True)


def cleanup() -> None:
    """Açılışta: başarılı güncellemeden kalan yedeği ve geçici dosyaları siler."""
    d = updates_dir()
    res = _read_json(d / "sonuc.json")
    try:
        if res and res.get("ok") and paths.is_frozen():
            remove_tree(_long(paths.app_root() / BACKUP))
        st = _read_json(d / "hazir.json")
        if (res and res.get("ok")) or (st and parse_version(str(st.get("version"))) <= parse_version(__version__)):
            discard()
        (d / "guncelleyici.exe").unlink(missing_ok=True)
    except OSError as e:  # güncelleyici henüz kapanmamış olabilir; bir sonraki açılışta silinir
        log.info("Güncelleme artıkları silinemedi: %s", e)


def startup() -> None:
    cleanup()
    if settings.load()["update"].get("check_on_start"):
        def run() -> None:
            try:
                check()
            except Exception as e:  # noqa: BLE001 — açılış denetimi sessizce başarısız olabilir
                log.info("Açılış güncelleme denetimi başarısız: %s", e)
        threading.Thread(target=run, name="aiva-update-check", daemon=True).start()
