import type { EngineInfo } from "./types";

let base = "";
let token = "";
let dataDirPath = "";

export const dataDir = () => dataDirPath;
export const caseExportsDir = (caseId: number) => `${dataDirPath}\\cases\\${caseId}\\exports`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const inTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Motor hazır olana kadar bekler. Tarayıcıda geliştirme için VITE_ENGINE_PORT / VITE_ENGINE_TOKEN kullanılır. */
export async function connect(onWait?: (msg: string) => void): Promise<EngineInfo> {
  if (!inTauri()) {
    const port = Number(import.meta.env.VITE_ENGINE_PORT || 0);
    const tok = String(import.meta.env.VITE_ENGINE_TOKEN || "");
    if (!port) throw new Error("Tarayıcı modunda VITE_ENGINE_PORT tanımlanmalı");
    base = `http://127.0.0.1:${port}`;
    token = tok;
    return { ready: true, port, token: tok, data_dir: "", portable: true, error: null };
  }
  const { invoke } = await import("@tauri-apps/api/core");
  const started = Date.now();
  for (;;) {
    const info = await invoke<EngineInfo>("engine_info");
    if (info.error) throw new Error(info.error);
    if (info.ready) {
      base = `http://127.0.0.1:${info.port}`;
      token = info.token;
      dataDirPath = info.data_dir;
      return info;
    }
    const s = Math.round((Date.now() - started) / 1000);
    onWait?.(s < 4 ? "Analiz motoru başlatılıyor…" : `Analiz motoru başlatılıyor… (${s} sn)`);
    if (Date.now() - started > 180_000) throw new Error("Analiz motoru 3 dakika içinde başlamadı");
    await new Promise((r) => setTimeout(r, 300));
  }
}

function url(path: string, params?: Record<string, string | number | boolean | undefined | null>) {
  const u = new URL(base + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
    }
  }
  return u.toString();
}

let engineErrorCb: ((msg: string) => void) | null = null;
let refreshing: Promise<boolean> | null = null;

/** Motor kalıcı olarak kapanırsa çağrılır (arayüz hata ekranı gösterir). */
export const onEngineError = (cb: (msg: string) => void) => (engineErrorCb = cb);

/** Motor yeniden başlatıldıysa yeni port/token'ı alır. Bağlantı yeniden kurulduysa true döner. */
export function refresh(): Promise<boolean> {
  if (!inTauri()) return Promise.resolve(false);
  refreshing ??= (async () => {
    const { invoke } = await import("@tauri-apps/api/core");
    const started = Date.now();
    while (Date.now() - started < 30_000) {
      const info = await invoke<EngineInfo>("engine_info");
      if (info.error) {
        engineErrorCb?.(info.error);
        return false;
      }
      if (info.ready) {
        const changed = base !== `http://127.0.0.1:${info.port}` || token !== info.token;
        base = `http://127.0.0.1:${info.port}`;
        token = info.token;
        if (changed) return true;
      }
      await new Promise((r) => setTimeout(r, 400));
    }
    return false;
  })().finally(() => (refreshing = null));
  return refreshing;
}

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, any>, retry = true): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url(path, params), {
      method,
      headers: { "x-aiva-token": token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    if (retry && (await refresh())) return request<T>(method, path, body, params, false);
    throw new ApiError(0, "Analiz motoruna ulaşılamıyor");
  }
  if (!res.ok) {
    let msg = `İstek başarısız (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: any) => d.msg).join(", ");
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, any>) => request<T>("GET", path, undefined, params),
  post: <T>(path: string, body: unknown = {}, params?: Record<string, any>) => request<T>("POST", path, body, params),
  put: <T>(path: string, body: unknown = {}) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown = {}) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

// Medya etiketleri (video/img) başlık gönderemez; token "k" sorgu parametresiyle gider
export const mediaUrl = (path: string, params?: Record<string, any>) => url(path, { ...params, k: token });
export const fileUrl = (rel: string | null | undefined) => (rel ? url("/api/files", { path: rel, k: token }) : "");
export const frameUrl = (evidenceId: number, t: number, w = 320, crop?: number[] | null) =>
  url(`/api/evidence/${evidenceId}/frame`, {
    t: t.toFixed(3),
    w,
    crop: crop ? crop.map((v) => v.toFixed(4)).join(",") : undefined,
    k: token,
  });
export const wsUrl = () => `${base.replace("http", "ws")}/api/events?k=${encodeURIComponent(token)}`;

export async function pickFiles(title: string, images = false): Promise<string[]> {
  if (!inTauri()) return [];
  const { open } = await import("@tauri-apps/plugin-dialog");
  const filters = images
    ? [{ name: "Fotoğraflar", extensions: ["jpg", "jpeg", "png", "bmp", "webp"] }]
    : [
        { name: "Tüm dosyalar", extensions: ["*"] },
        {
          name: "Video ve kayıt dosyaları",
          extensions: ["mp4", "mkv", "avi", "mov", "wmv", "asf", "flv", "ts", "m2ts", "mts", "mpg", "mpeg", "vob",
            "264", "h264", "265", "h265", "hevc", "dav", "bin", "dvr", "webm", "3gp", "mxf", "ogv"],
        },
      ];
  const sel = await open({ title, multiple: !images, directory: false, filters });
  if (!sel) return [];
  return Array.isArray(sel) ? sel : [sel];
}

export async function confirmDialog(message: string, title = "Onay"): Promise<boolean> {
  if (!inTauri()) return window.confirm(message);
  const { ask } = await import("@tauri-apps/plugin-dialog");
  return ask(message, { title, kind: "warning", okLabel: "Evet", cancelLabel: "Vazgeç" });
}

export async function onFileDrop(cb: (paths: string[]) => void, onHover?: (over: boolean) => void): Promise<() => void> {
  if (!inTauri()) return () => {};
  const { getCurrentWebview } = await import("@tauri-apps/api/webview");
  return getCurrentWebview().onDragDropEvent((e) => {
    const p = e.payload;
    if (p.type === "over" || p.type === "enter") onHover?.(true);
    else if (p.type === "leave") onHover?.(false);
    else if (p.type === "drop") {
      onHover?.(false);
      if (p.paths.length) cb(p.paths);
    }
  });
}

export const openFolder = (path: string) => api.post("/api/open-folder", {}, { path });
