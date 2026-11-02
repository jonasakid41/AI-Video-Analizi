// Sürüm derlemesinde Windows konsol penceresi açılmaz
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

/// Motor beklenmedik şekilde kapanırsa en fazla bu kadar yeniden başlatılır
const MAX_RESTARTS: u32 = 3;

use serde::Serialize;
use tauri::{Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

#[derive(Clone, Serialize, Default)]
struct EngineInfo {
    ready: bool,
    port: u16,
    token: String,
    data_dir: String,
    portable: bool,
    error: Option<String>,
}

#[derive(Default)]
struct Engine {
    info: Arc<Mutex<EngineInfo>>,
    child: Arc<Mutex<Option<Child>>>,
    stopping: Arc<AtomicBool>,
}

#[tauri::command]
fn engine_info(state: State<Engine>) -> EngineInfo {
    state.info.lock().unwrap().clone()
}

fn exe_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Geliştirme modunda depo kökü (app/src-tauri → ../..)
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

fn writable(dir: &Path) -> bool {
    if fs::create_dir_all(dir).is_err() {
        return false;
    }
    let probe = dir.join(".yazma_testi");
    let ok = fs::write(&probe, b"ok").is_ok();
    let _ = fs::remove_file(&probe);
    ok
}

/// Taşınabilir düzen: exe'nin yanındaki data/. Yazılamıyorsa (ör. Program Files) %LOCALAPPDATA%.
fn resolve_data_dir() -> (PathBuf, bool) {
    if let Ok(d) = std::env::var("AIVA_DATA_DIR") {
        return (PathBuf::from(d), true);
    }
    if cfg!(debug_assertions) {
        return (repo_root().join("data"), true);
    }
    let local = exe_dir().join("data");
    if writable(&local) {
        return (local, true);
    }
    let fallback = std::env::var("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| exe_dir())
        .join("AIVideoAnalizi")
        .join("data");
    let _ = fs::create_dir_all(&fallback);
    (fallback, false)
}

fn engine_command(data_dir: &Path) -> Command {
    let mut cmd;
    let models;
    if cfg!(debug_assertions) {
        let root = repo_root();
        cmd = Command::new(root.join("engine").join(".venv").join("Scripts").join("python.exe"));
        cmd.args(["-m", "aiva"]).current_dir(root.join("engine"));
        models = root.join("models");
    } else {
        let dir = exe_dir();
        cmd = Command::new(dir.join("engine").join("aiva-engine.exe"));
        cmd.current_dir(dir.join("engine"));
        models = dir.join("models");
    }
    cmd.env("AIVA_DATA_DIR", data_dir)
        .env("AIVA_MODELS_DIR", models)
        .env("AIVA_PARENT_PID", std::process::id().to_string())
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped());
    let logs = data_dir.join("logs");
    let _ = fs::create_dir_all(&logs);
    match fs::File::create(logs.join("motor_stderr.log")) {
        Ok(f) => cmd.stderr(f),
        Err(_) => cmd.stderr(Stdio::null()),
    };
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn start_engine(engine: &Engine, data_dir: PathBuf, portable: bool) {
    let info = engine.info.clone();
    let child_slot = engine.child.clone();
    {
        let mut i = info.lock().unwrap();
        i.data_dir = data_dir.display().to_string();
        i.portable = portable;
    }
    let stopping = engine.stopping.clone();
    std::thread::spawn(move || {
        let fail = |msg: String| {
            let mut i = info.lock().unwrap();
            i.ready = false;
            i.error = Some(msg);
        };
        let mut restarts = 0u32;
        loop {
            let mut child = match engine_command(&data_dir).spawn() {
                Ok(c) => c,
                Err(e) => return fail(format!("Analiz motoru başlatılamadı: {e}")),
            };
            let stdout = child.stdout.take();
            *child_slot.lock().unwrap() = Some(child);
            let Some(stdout) = stdout else {
                return fail("Analiz motorunun çıktısı okunamadı".into());
            };
            let mut was_ready = false;
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                if let Some(json) = line.strip_prefix("AIVA_READY ") {
                    match serde_json::from_str::<serde_json::Value>(json) {
                        Ok(v) => {
                            let mut i = info.lock().unwrap();
                            i.port = v["port"].as_u64().unwrap_or(0) as u16;
                            i.token = v["token"].as_str().unwrap_or_default().to_string();
                            i.ready = i.port != 0;
                            i.error = None;
                            was_ready = i.ready;
                        }
                        Err(e) => fail(format!("Motor yanıtı çözümlenemedi: {e}")),
                    }
                    // Okumaya devam et: boru dolup motor kilitlenmesin
                }
            }
            // Motor kapandı
            if let Some(mut c) = child_slot.lock().unwrap().take() {
                let _ = c.wait();
            }
            if stopping.load(Ordering::SeqCst) {
                return;
            }
            info.lock().unwrap().ready = false;
            restarts += 1;
            if !was_ready || restarts > MAX_RESTARTS {
                return fail("Analiz motoru beklenmedik şekilde kapandı. Uygulamayı yeniden başlatın. Ayrıntı: data/logs/motor_stderr.log".into());
            }
            // Arayüz engine_info ile yeni port/token'ı alıp yeniden bağlanır
            std::thread::sleep(Duration::from_millis(800));
        }
    });
}

fn stop_engine(engine: &Engine) {
    engine.stopping.store(true, Ordering::SeqCst);
    if let Some(mut child) = engine.child.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn main() {
    let (data_dir, portable) = resolve_data_dir();
    let engine = Engine::default();
    start_engine(&engine, data_dir.clone(), portable);

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(engine)
        .invoke_handler(tauri::generate_handler![engine_info])
        .setup(move |app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("AI Video Analizi")
                .inner_size(1480.0, 920.0)
                .min_inner_size(1120.0, 700.0)
                .maximized(true)
                .data_directory(data_dir.join("webview"))
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("uygulama başlatılamadı");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_engine(&handle.state::<Engine>());
        }
    });
}
