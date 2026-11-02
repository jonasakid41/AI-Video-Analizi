//! Güncelleyici kipi: `guncelleyici.exe --apply-update <yeni> <kök> <data> <pid> <sürüm> <exe adı>`
//!
//! Çalışan exe ve motor DLL'leri kilitli olduğu için dosyalar uygulama açıkken değiştirilemez.
//! Uygulama kendini data/updates/guncelleyici.exe olarak kopyalayıp bu kipte başlatır ve kapanır.
//! Güncelleyici uygulamanın kapanmasını bekler, eski dosyaları <kök>/_eski_surum/ altına taşır,
//! yenilerini koyar ve yeni sürümü açar. Bir adım başarısız olursa eski dosyalar geri konur.
//! Sonuç data/updates/sonuc.json dosyasına yazılır; yedeği yeni sürümün motoru açılışta siler.

use std::ffi::OsString;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use crate::append_log;

pub const EXE: &str = "AIVideoAnalizi.exe";
const BACKUP: &str = "_eski_surum";

pub fn run(args: &[String]) {
    let [staged, root, data, pid, version, exe_name] = args else {
        return;
    };
    let (staged, root, data) = (PathBuf::from(staged), PathBuf::from(root), PathBuf::from(data));
    let log = data.join("logs").join("guncelleme.log");
    append_log(&log, &format!("v{version} kuruluyor: {} -> {}", staged.display(), root.display()));
    wait_for_exit(pid.parse().unwrap_or(0));

    let result = swap(&staged, &root, &log);
    let upd = data.join("updates");
    let _ = fs::remove_file(upd.join("hazir.json"));
    let res = match &result {
        Ok(()) => {
            append_log(&log, "Güncelleme tamamlandı");
            serde_json::json!({ "ok": true, "version": version })
        }
        Err(e) => {
            append_log(&log, &format!("Güncelleme başarısız, eski sürüm geri yüklendi: {e}"));
            let _ = fs::remove_dir_all(upd.join("staging"));
            serde_json::json!({ "ok": false, "version": version, "error": e })
        }
    };
    let _ = fs::write(upd.join("sonuc.json"), res.to_string());

    let new_exe = root.join(EXE);
    let exe = if result.is_ok() && new_exe.is_file() { new_exe } else { root.join(exe_name) };
    if let Err(e) = Command::new(&exe).current_dir(&root).spawn() {
        append_log(&log, &format!("Uygulama yeniden açılamadı ({}): {e}", exe.display()));
    }
}

/// Uygulama exe'si kapanana kadar (en fazla 60 sn) bekler
fn wait_for_exit(pid: u32) {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE};
    if pid == 0 {
        return;
    }
    unsafe {
        if let Ok(h) = OpenProcess(PROCESS_SYNCHRONIZE, false, pid) {
            WaitForSingleObject(h, 60_000);
            let _ = CloseHandle(h);
        }
    }
}

fn swap(staged: &Path, root: &Path, log: &Path) -> Result<(), String> {
    let backup = root.join(BACKUP);
    if backup.exists() {
        fs::remove_dir_all(&backup).map_err(|e| format!("Eski yedek silinemedi: {e}"))?;
    }
    fs::create_dir_all(&backup).map_err(|e| format!("Yedek klasörü oluşturulamadı: {e}"))?;
    let names: Vec<OsString> = fs::read_dir(staged)
        .map_err(|e| format!("Yeni sürüm klasörü okunamadı: {e}"))?
        .filter_map(|e| e.ok().map(|e| e.file_name()))
        .filter(|n| n != "data" && n != BACKUP)
        .collect();
    let (mut moved_old, mut placed_new) = (Vec::new(), Vec::new());
    let res = replace_all(&names, staged, root, &backup, &mut moved_old, &mut placed_new);
    if res.is_err() {
        for n in &placed_new {
            let p = root.join(n);
            let _ = if p.is_dir() { fs::remove_dir_all(&p) } else { fs::remove_file(&p) };
        }
        for n in &moved_old {
            if let Err(e) = retry(|| fs::rename(backup.join(n), root.join(n))) {
                append_log(log, &format!("{} geri konamadı: {e}", n.to_string_lossy()));
            }
        }
        let _ = fs::remove_dir(&backup); // yalnızca boşsa silinir
    }
    res
}

fn replace_all(
    names: &[OsString],
    staged: &Path,
    root: &Path,
    backup: &Path,
    moved_old: &mut Vec<OsString>,
    placed_new: &mut Vec<OsString>,
) -> Result<(), String> {
    for n in names {
        let cur = root.join(n);
        if cur.exists() {
            // Kapanan süreçlerin kilitleri ya da virüs tarayıcısı yüzünden kısa süre beklenebilir
            retry(|| fs::rename(&cur, backup.join(n)))
                .map_err(|e| format!("{} taşınamadı (kullanımda olabilir): {e}", n.to_string_lossy()))?;
            moved_old.push(n.clone());
        }
        move_path(&staged.join(n), &cur).map_err(|e| format!("{} yerleştirilemedi: {e}", n.to_string_lossy()))?;
        placed_new.push(n.clone());
    }
    Ok(())
}

fn retry(mut f: impl FnMut() -> std::io::Result<()>) -> std::io::Result<()> {
    let mut last = None;
    for _ in 0..120 {
        match f() {
            Ok(()) => return Ok(()),
            Err(e) => last = Some(e),
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err(last.unwrap())
}

/// Aynı sürücüde yeniden adlandırır; olmazsa (farklı sürücü) kopyalayıp kaynağı siler
fn move_path(src: &Path, dst: &Path) -> std::io::Result<()> {
    if fs::rename(src, dst).is_ok() {
        return Ok(());
    }
    if src.is_dir() {
        copy_dir(src, dst)?;
        let _ = fs::remove_dir_all(src);
    } else {
        fs::copy(src, dst)?;
        let _ = fs::remove_file(src);
    }
    Ok(())
}

fn copy_dir(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for e in fs::read_dir(src)? {
        let e = e?;
        let to = dst.join(e.file_name());
        if e.file_type()?.is_dir() {
            copy_dir(&e.path(), &to)?;
        } else {
            fs::copy(e.path(), to)?;
        }
    }
    Ok(())
}

/// Güncelleyiciyi uygulamadan bağımsız başlatır (uygulama kapanınca o da kapanmasın)
pub fn spawn(helper: &Path, args: &[String]) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const DETACHED_PROCESS: u32 = 0x0000_0008;
    const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;
    let mut last = None;
    for flags in [DETACHED_PROCESS | CREATE_BREAKAWAY_FROM_JOB, DETACHED_PROCESS] {
        match Command::new(helper).args(args).creation_flags(flags).spawn() {
            Ok(_) => return Ok(()),
            Err(e) => last = Some(e),
        }
    }
    Err(format!("Güncelleyici başlatılamadı: {}", last.map(|e| e.to_string()).unwrap_or_default()))
}
