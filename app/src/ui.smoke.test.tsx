// @vitest-environment jsdom
// Tüm sekmeleri ve pencereleri sahte motor verisiyle çizer; çalışma anı hatalarını yakalar.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { useUI } from "./store";

const ev = {
  id: 1, case_id: 1, original_name: "CH01_20261028143000.mp4", source_path: "C:\\x.mp4", sha256: "ab".repeat(32), size: 1234567,
  camera: "Kamera 1", status: "hazir", status_label: "Hazır", status_detail: "Doğrudan açma", duration: 30, width: 640, height: 360,
  fps: 12, codec: "h264", has_proxy: 1, analyzed: 1, created_at: "2026-11-02T10:00:00+03:00",
  sniff: { kind: "mp4", label: "MP4/MOV" },
  strategy: { name: "Doğrudan açma", denemeler: [{ strateji: "Doğrudan açma", basarili: true, cozulen_kare: 30, hata: "" }, { strateji: "Hata toleranslı", basarili: false, cozulen_kare: 0, hata: "x" }] },
  analysis_info: {
    donusturme: { container: "matroska", gaps: [], dropped: 0, keyframe_interval: 2, proxy: { mode: "kodlama", encoder: "h264_nvenc", encoder_label: "NVIDIA NVENC" }, sprite: { times: [1, 2], tile_w: 160, tile_h: 90, cols: 10, count: 2 } },
    analiz: { sure_sn: { toplam: 4.1 }, aygit: "DmlExecutionProvider", dedektor: "yolox_s", analiz_edilen_kare: 60, aktif_bolum: 1, aktif_sure_sn: 20, hareket_ozeti: { cevre: 4, nesne: 2 }, goruntu: { renksiz_oran: 1, dusuk_isik_oran: 0.8, iyilestirilen_kare: 40, yakinlastirma_tespiti: 12, parcali_tarama: { izgara: 2, kare: 30 } }, birlesen_iz: 3, izler: { "kişi": 2 }, iz_sayisi: 2, yuz_sayisi: 3, kisi_kumesi: 1, plakalar: ["34 ABC 123"], yuz_tanima: true, plaka_okuma: true, gorsel_arama: true },
  },
  time: { kamera_saati_var: true, kaynak: "osd", duzeltme_farki_sn: -222, gunluk_kayma_sn: null, parca_sayisi: 2, bosluklar: [{ t: 18, jump: 600 }] },
  camera_start: "2026-10-28T14:33:42", real_start: "2026-10-28T14:30:00",
  time_mapping: { pieces: [{ t_from: 0, offset: 1793197422 }, { t_from: 18, offset: 1793198022 }], corrections: [["2026-10-28T14:33:47", "2026-10-28T14:30:05"]], tz: "Europe/Istanbul", source: "osd", gaps: [{ t: 18, jump: 600 }] },
};
const track = { id: 7, evidence_id: 1, cls: "car", cls_tr: "otomobil", t0: 2, t1: 8, real_t0: "2026-10-28T14:30:02", real_t1: "2026-10-28T14:30:08", n: 10, conf: 0.9, thumb: "cases/1/t.jpg", colors: { govde: [["beyaz", 0.8]] }, color_text: "beyaz", plate: "34 ABC 123", plate_conf: 0.95, face_count: 0, reads: [] };
const face = { id: 3, evidence_id: 1, track_id: 5, t: 4, real_t: "2026-10-28T14:30:04", score: 0.9, quality: 0.8, thumb: "f.jpg", cluster: 0, box: [0.1, 0.1, 0.1, 0.1] };
const result = { id: "i7", kind: "iz", evidence_id: 1, t: 5, box: [0.1, 0.2, 0.3, 0.3], score: 2, track_id: 7, t0: 2, t1: 8, cls: "car", cls_tr: "otomobil", thumb: "t.jpg", real_t: "2026-10-28T14:30:05", camera: "Kamera 1", video: "CH01.mp4", color_text: "beyaz", plate: "34 ABC 123", reasons: ["yapay zekâ notu: Beyaz bir otomobil park alanına giriyor", "otomobil"], verdict: { match: true, confidence: 0.9, explanation: "Beyaz araç görünüyor.", plate: "34 ABC 123" } };
const settings = {
  notice_accepted: true,
  ai: { base_url: "https://openrouter.ai/api/v1", profile: "dengeli", roles: { planner: "a/b", verifier: "c/d", video: "e/f" }, data_collection_deny: true, zdr: false, max_candidates: 40, batch_size: 8, budget_per_query_usd: 0.5, send_context_frame: true, timeout_s: 120 },
  analysis: { auto_analyze: true, sample_fps: 2, scan_fps: 1, detector: "yolox_s", min_conf: 0.35, faces: true, plates: true, clip: true, motion_threshold: 0.004, device: "auto" },
  time: { tz: "Europe/Istanbul" }, api_key_set: true, api_key_masked: "sk-or-…1234", ai_ready: true, ai_source: "api",
  profiles: { ucretsiz: { label: "Ücretsiz", roles: {} }, dengeli: { label: "Dengeli", roles: {} } },
};

const fixtures: [RegExp, unknown][] = [
  [/^\/api\/cases\/1\/evidence$/, [ev, { ...ev, id: 2, original_name: "CH02.mp4", camera: "Kamera 2", time_mapping: { ...ev.time_mapping, pieces: [{ t_from: 0, offset: 1793199000 }], corrections: [] } }]],
  [/^\/api\/queries\/9\/evaluations$/, [{
    id: 1, case_id: 1, query_id: 9, models: ["c/d", "e/f"], status: "tamamlandi", error: null, created_at: "", finished_at: "",
    results: [
      { model: "c/d", candidates: 1, answered: 1, matched: 1, cost: 0.001, seconds: 3, errors: [], labeled: 1, tp: 1, fp: 0, fn: 0, tn: 0, precision: 1, recall: 1, accuracy: 1 },
      { model: "e/f", candidates: 1, answered: 1, matched: 0, cost: 0, seconds: 5, errors: [], labeled: 1, tp: 0, fp: 0, fn: 1, tn: 0, precision: null, recall: 0, accuracy: 0 },
    ],
  }]],
  [/^\/api\/cases\/1\/findings$/, [{ id: 1, case_id: 1, evidence_id: 1, t: 5, title: "Beyaz araç", note: "", source: "ai", confidence: 0.9, image: "b.jpg", status: "dogrulandi", status_label: "Doğrulandı", data: { box: null }, created_at: "", real_t: "2026-10-28T14:30:05", camera_t: "2026-10-28T14:33:47" }]],
  [/^\/api\/cases\/1\/queries$/, [{ id: 9, question: "Beyaz araç geçti mi?", status: "tamamlandi", answer: "Evet, 14:30:05'te.", cost: 0.002, created_at: "", finished_at: "", error: null, options: { mode: "dogrula" } }]],
  [/^\/api\/queries\/9$/, { id: 9, question: "Beyaz araç geçti mi?", status: "tamamlandi", answer: "Evet.", cost: 0.002, created_at: "", finished_at: "", error: null, options: { mode: "dogrula", notes: ["not"] }, plan: { intent: "ara", time_from: "14:00", time_to: null, classes: ["car"], colors: [{ target: "govde", color: "beyaz" }], plate: null, visual_query_en: "a white car", verify_question: "?", needs_motion: false }, results: [result], labels: { i7: true } }],
  [/^\/api\/cases\/1\/people$/, [{ person: 0, face_count: 3, best: face, faces: [face, { ...face, id: 4 }], appearances: [{ evidence_id: 1, t0: 4, t1: 9, count: 3, real_t0: "2026-10-28T14:30:04", real_t1: null }] }]],
  [/^\/api\/cases\/1\/history$/, [{ id: 1, case_id: 1, evidence_id: 1, action: "video_eklendi", detail: { ad: "CH01.mp4" }, created_at: "2026-11-02T10:00:00+03:00" }]],
  [/^\/api\/cases\/1$/, { id: 1, name: "Otopark", description: "", created_at: "", updated_at: "", evidence_count: 1, finding_count: 1 }],
  [/^\/api\/cases$/, [{ id: 1, name: "Otopark", description: "açıklama", created_at: "", updated_at: "2026-11-02T10:00:00", evidence_count: 1, finding_count: 1 }]],
  [/^\/api\/evidence\/1\/activity$/, { duration: 30, buckets: 4, activity: [0, 0.01, 0.02, 0], kinds: [null, "cevre", "nesne", null], person: [0, 1, 1, 0], vehicle: [0, 0, 1, 0], segments: [{ kind: "aktif", t0: 2, t1: 10 }],
    events: [{ t0: 2, t1: 6, real_t0: null, real_t1: null, kind: "cevre", label: "ağaç/bitki/gölge (tekrarlayan)", detail: "", ignorable: true, tracks: [] },
             { t0: 7, t1: 9, real_t0: null, real_t1: null, kind: "nesne", label: "1 kişi", detail: "kişi · üst: kırmızı", ignorable: false, tracks: [7] }] }],
  [/^\/api\/evidence\/1\/tracks$/, [track]],
  [/^\/api\/evidence\/1\/plates$/, [{ ...track, reads: [{ id: 1, t: 5, text: "34 ABC 123", raw: "34ABC123", conf: 0.9, valid_tr: 1, thumb: null }] }]],
  [/^\/api\/evidence\/1\/rois$/, [{ id: 2, evidence_id: 1, name: "Giriş kapısı", kind: "alan", points: [[0, 0], [1, 0], [1, 1]], created_at: "" }]],
  [/^\/api\/evidence\/1\/detections\/range$/, [{ track_id: 7, t: 5, cls: "car", conf: 0.9, x: 0.1, y: 0.1, w: 0.2, h: 0.2 }]],
  [/^\/api\/evidence\/1\/time$/, { mapping: ev.time_mapping, summary: ev.time, versions: [{ version: 2, reason: "DVR fotoğrafı", created_at: "2026-11-02T10:00:00" }], readings: [{ t: 5, text: "28-10-2026 14:33:47", parsed: "2026-10-28T14:33:47" }] }],
  [/^\/api\/evidence\/1\/diagnostics$/, { path: null, text: "" }],
  [/^\/api\/settings$/, settings],
  [/^\/api\/system$/, { version: "0.1.0", data_dir: "C:\\data", models_dir: "C:\\models", frozen: true, encoders: [{ name: "h264_nvenc", label: "NVIDIA NVENC", ok: true }], encoder: "h264_nvenc", inference: { onnxruntime: "1.24", providers: ["DmlExecutionProvider"], gpu: true, label: "GPU (DirectML)" }, models: [{ key: "yolox_s", label: "Nesne tespiti", license: "Apache-2.0", ok: true, size_mb: 36 }] }],
  [/^\/api\/models$/, { models: [{ id: "c/d", name: "Model D", description: "", context: 1000, input: ["text", "image"], image: true, video: false, structured: true, free: false, price_in_m: 0.3, price_out_m: 1.2 }, { id: "e/f", name: "Video F", description: "", context: 1000, input: ["video", "image"], image: true, video: true, structured: true, free: true, price_in_m: 0, price_out_m: 0 }], total: 2, image_count: 2, video_count: 1, free_vision: 1, fetched_at: "2026-11-02 10:00" }],
  [/^\/api\/power$/, { on_battery: true, percent: 64 }],
  [/^\/api\/ai\/cli$/, [{ tool: "claude", label: "Claude Code", path: "C:\\Users\\x\\.local\\bin\\claude.exe", found: true, version: "2.1.282 (Claude Code)", experimental: false, login: "claude",
    models: [{ id: "cli:claude:opus", name: "Opus (en güçlü)" }, { id: "cli:claude:sonnet", name: "Sonnet (dengeli)" }, { id: "cli:claude:haiku", name: "Haiku (hızlı)" }] },
    { tool: "codex", label: "OpenAI Codex CLI", path: null, found: false, version: null, experimental: true, login: "codex login", models: [] }]],
  [/^\/api\/evidence\/1\/ai-notes$/, [
    { id: 1, t: 5, real_t: "2026-10-28T14:30:05", text: "Beyaz bir otomobil park alanına giriyor", notable: true, people: 0, vehicles: 1 },
    { id: 2, t: 9, real_t: "2026-10-28T14:30:09", text: "değişiklik yok", notable: false, people: 0, vehicles: 1 },
  ]],
  [/^\/api\/update$/, { current: "0.1.2", can_apply: true, reason: null, check_on_start: false, last_check: "2026-11-02T10:00:00", staged: null, result: null,
    latest: { current: "0.1.2", latest: "0.2.0", newer: true, title: "AI Video Analizi v0.2.0", notes: "## Yenilikler\n**Hızlı** arama", published_at: "2026-11-02T10:00:00Z", page: null, checked_at: "", asset: { name: "AIVideoAnalizi-0.2.0-win64.zip", size: 600 * 2 ** 20, url: "u", sha256: "ab" } } }],
  // Eski sürümün kaydettiği, şemaya uymayan model planı (classes/colors yok)
  [/^\/api\/cases\/2\/queries$/, [{ id: 10, question: "Kırmızı mont?", status: "tamamlandi", answer: "Sonuç yok.", cost: 0, created_at: "", finished_at: "", error: null, options: { mode: "dogrula" } }]],
  [/^\/api\/queries\/10$/, { id: 10, question: "Kırmızı mont?", status: "tamamlandi", answer: "Sonuç yok.", cost: 0, created_at: "", finished_at: "", error: null, options: {}, plan: { intent: "ara" }, results: [], labels: {} }],
  [/^\/api\/queries\/10\/evaluations$/, []],
  [/^\/api\/jobs$/, [{ id: 1, case_id: 1, evidence_id: 1, kind: "analyze", status: "calisiyor", progress: 0.4, message: "Nesne, yüz ve plaka analizi", params: {}, result: null, created_at: "" }]],
];

vi.mock("./lib/api", () => {
  const get = vi.fn(async (path: string) => {
    const hit = fixtures.find(([re]) => re.test(path));
    if (!hit) throw new Error(`Fixture yok: ${path}`);
    return structuredClone(hit[1]);
  });
  return {
    api: { get, post: vi.fn(async () => ({})), put: vi.fn(async () => settings), patch: vi.fn(async () => ({})), del: vi.fn(async () => ({})) },
    ApiError: Error, connect: vi.fn(), mediaUrl: () => "", fileUrl: (p: string) => (p ? `file:${p}` : ""), frameUrl: () => "",
    wsUrl: () => "ws://127.0.0.1:1/api/events", pickFiles: vi.fn(async () => []), confirmDialog: vi.fn(async () => false),
    onFileDrop: vi.fn(async () => () => {}), openFolder: vi.fn(async () => ({})), dataDir: () => "C:\\data",
    caseExportsDir: () => "C:\\data\\cases\\1\\exports",
    refresh: vi.fn(async () => false), onEngineError: vi.fn(), reportError: vi.fn(), applyUpdate: vi.fn(async () => {}),
  };
});

beforeAll(() => {
  const noop = () => {};
  const ctx = new Proxy({}, { get: (_t, k) => (k === "measureText" ? () => ({ width: 10 }) : noop), set: () => true });
  HTMLCanvasElement.prototype.getContext = (() => ctx) as any;
  HTMLMediaElement.prototype.play = async () => {};
  HTMLMediaElement.prototype.pause = () => {};
  (globalThis as any).WebSocket = class {
    close() {}
  };
});
afterEach(() => cleanup());

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("arayüz duman testi", () => {
  it("vaka listesi", async () => {
    const { default: CasesPage } = await import("./components/CasesPage");
    wrap(<CasesPage info={{ ready: true, port: 1, token: "x", data_dir: "C:\\data", portable: true, error: null }} />);
    expect(await screen.findByText("Otopark")).toBeTruthy();
  });

  it("çalışma alanı: tüm sekmeler", async () => {
    useUI.setState({ caseId: 1, evidenceId: 1, tab: "sor" });
    const { default: Workspace } = await import("./components/Workspace");
    wrap(<Workspace caseId={1} />);
    expect(await screen.findByText("CH01_20261028143000.mp4")).toBeTruthy();
    expect(await screen.findByText("Beyaz araç geçti mi?")).toBeTruthy();
    expect(await screen.findByText("Beyaz araç görünüyor.")).toBeTruthy();
    expect(screen.getByText(/yapay zekâ notu: Beyaz bir otomobil/)).toBeTruthy(); // yapay zekânın bulduğu an
    expect(screen.getByText("otomobil")).toBeTruthy(); // plan etiketi Türkçe
    expect(screen.getByText("Tüm kameralar — ortak zaman çizelgesi")).toBeTruthy();
    expect(await screen.findByText("ağaç/bitki/gölge")).toBeTruthy(); // hareket türü açıklaması
    fireEvent.click(screen.getByText("önemsiz hareketleri gizle"));
    expect(screen.getByText("önemsiz hareketler gizli")).toBeTruthy();
    expect(await screen.findByText("Model karşılaştırması")).toBeTruthy();
    expect(screen.getByText("1 sonuç işaretli")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Doğru sonuç" })).toBeTruthy();

    const tabs = screen.getByRole("tablist");
    const go = (name: string) => fireEvent.click(within(tabs).getByRole("tab", { name: new RegExp(name) }));
    go("Bulgular");
    expect(await screen.findByText("Vaka raporu (PDF)")).toBeTruthy();
    go("Kişiler");
    expect(await screen.findByText("Kişi 1")).toBeTruthy();
    go("Plakalar");
    expect((await screen.findAllByText("34 ABC 123")).length).toBeGreaterThan(0);
    go("İyileştir");
    expect(await screen.findByText("Çok kareli birleştirme")).toBeTruthy();
    expect(screen.getByText(/"Gece \/ IR" ayarı önerildi/)).toBeTruthy(); // siyah-beyaz kayıt
    go("Saat");
    expect(await screen.findByText("1 · Kamera saatini oku")).toBeTruthy();
    expect(screen.getByText(/−3 dk 42 sn/)).toBeTruthy();
    go("Bilgi");
    expect(await screen.findByText("Denenen açma yöntemleri")).toBeTruthy();
    expect(await screen.findByText("Beyaz bir otomobil park alanına giriyor")).toBeTruthy(); // ön inceleme notu
    expect(screen.queryByText("değişiklik yok")).toBeNull(); // önemsiz notlar varsayılan olarak gizli
    expect(screen.getByRole("button", { name: "Yeniden incele" })).toBeTruthy();
    expect(screen.getByText(/NVIDIA NVENC/)).toBeTruthy();
    expect(screen.getByText(/ağaç\/bitki\/gölge .*\(önemsiz\)/)).toBeTruthy();
    expect(screen.getByText(/siyah-beyaz \(gece\/IR\)/)).toBeTruthy();
    expect(screen.getByText(/parçalı tarama 2×2 \(30 kare\).*yakınlaştırmayla 12 ek tespit.*3 kopuk iz birleştirildi/)).toBeTruthy();
  });

  it("ayarlar penceresi: tüm sekmeler", async () => {
    const { default: SettingsDialog } = await import("./components/SettingsDialog");
    wrap(<SettingsDialog open onClose={() => {}} info={{ ready: true, port: 1, token: "x", data_dir: "C:\\data", portable: true, error: null }} />);
    expect(await screen.findByText("OpenRouter API anahtarı")).toBeTruthy();
    expect(screen.getByText("Sorularda videonun tamamını yapay zekâya taratın")).toBeTruthy();
    const pick = (await screen.findByRole("combobox", { name: "Claude Code modeli" })) as HTMLSelectElement;
    expect(pick.value).toBe("opus"); // varsayılan: en güçlü model
    expect(await screen.findByText("Claude Code")).toBeTruthy(); // bilgisayardaki CLI aracı
    expect(screen.getByRole("button", { name: "Kullan" })).toBeTruthy();
    expect(screen.getByText(/Kurulu değil.*codex login/)).toBeTruthy();
    expect(await screen.findByText(/2 model/)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Yerel analiz" }));
    expect(await screen.findByText("Plaka okuma")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Sistem" }));
    expect(await screen.findByText("Yerel modeller")).toBeTruthy();
    expect(await screen.findByText("AI Video Analizi v0.2.0")).toBeTruthy();
    expect(screen.getByText("İndir ve kur")).toBeTruthy();
    expect(screen.getByText(/600 MB/)).toBeTruthy();
    fireEvent.click(screen.getByText("Sürüm notlarını göster"));
    expect(screen.getByText(/Yenilikler\s+Hızlı arama/)).toBeTruthy(); // Markdown düz metne çevrilir
  });

  it("indirilmiş güncelleme, yeniden açılışta denetim yapılmadan da kurulabilir", async () => {
    fixtures.unshift([/^\/api\/update$/, { current: "0.1.2", can_apply: true, reason: null, check_on_start: false, last_check: null, latest: null,
      staged: { version: "0.1.3", dir: "C:\\x", created_at: "" }, result: null }]);
    try {
      const { default: UpdateSection } = await import("./components/UpdateSection");
      wrap(<UpdateSection save={async () => {}} />);
      expect(await screen.findByText("v0.1.3 indirildi ve doğrulandı.")).toBeTruthy();
      expect(screen.getByText("Yeniden başlat ve kur")).toBeTruthy();
    } finally {
      fixtures.shift();
    }
  });

  it("eksik alanlı plan ve çizim hatası arayüzü kapatmaz", async () => {
    const { default: AskPanel } = await import("./components/panels/AskPanel");
    wrap(<AskPanel caseId={2} />);
    expect(await screen.findByText("Kırmızı mont?")).toBeTruthy();
    expect(await screen.findByText("Sonuç yok.")).toBeTruthy();
    const { default: ErrorBoundary } = await import("./components/ErrorBoundary");
    const { reportError } = await import("./lib/api");
    const Boom = () => {
      throw new Error("patladı");
    };
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    wrap(
      <>
        <ErrorBoundary area="test">
          <Boom />
        </ErrorBoundary>
        <div>komşu bölüm</div>
      </>,
    );
    quiet.mockRestore();
    expect(screen.getByText("Bu bölüm görüntülenemedi")).toBeTruthy();
    expect(screen.getByText("patladı")).toBeTruthy();
    expect(screen.getByText("komşu bölüm")).toBeTruthy();
    expect(reportError).toHaveBeenCalledWith("test", expect.any(Error), expect.any(String));
  });

  it("üst çubuk: pilde analiz uyarısı ve iş menüsü", async () => {
    useUI.setState({ caseId: 1 });
    const { default: TopBar } = await import("./components/TopBar");
    wrap(<TopBar info={{ ready: true, port: 1, token: "x", data_dir: "C:\\data", portable: true, error: null }} />);
    expect(await screen.findByText(/Pilde %64/)).toBeTruthy();
    expect(await screen.findByText("1 iş")).toBeTruthy();
    expect(await screen.findByText("Otopark")).toBeTruthy();
    expect(await screen.findByText("Yeni sürüm: v0.2.0")).toBeTruthy();
  });

  it("dönüştürme ekranı: hata ve yarıda kalma durumları", async () => {
    const { default: Player } = await import("./components/Player");
    const failed = { ...ev, status: "hata", status_detail: "Dosya açıldı ama baştan sona kopyalanamadı" } as any;
    const { unmount } = wrap(<Player caseId={1} ev={failed} />);
    expect(await screen.findByText("Yeniden dene")).toBeTruthy();
    expect(screen.getByText(/baştan sona kopyalanamadı/)).toBeTruthy();
    unmount();
    wrap(<Player caseId={1} ev={{ ...ev, status: "donusturuluyor", status_detail: "Kayıpsız kopya oluşturuluyor" } as any} />);
    expect(await screen.findByText("Yeniden başlat")).toBeTruthy(); // çalışan iş yoksa (yarıda kalmış)
  });

  it("ilk açılış penceresi", async () => {
    const { default: FirstRun } = await import("./components/FirstRun");
    wrap(<FirstRun />);
    expect(await screen.findByText("Okudum, başla")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Kapat" })).toBeNull();
  });
});
