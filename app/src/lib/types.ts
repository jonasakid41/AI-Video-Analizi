// Motor API'sinin döndürdüğü nesneler

export type JobStatus = "beklemede" | "calisiyor" | "tamamlandi" | "hata" | "iptal" | "yarida_kaldi";

export interface Job {
  id: number;
  case_id: number | null;
  evidence_id: number | null;
  kind: string;
  status: JobStatus;
  progress: number;
  message: string;
  params: Record<string, unknown>;
  result: any;
  error?: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface Case {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  evidence_count: number;
  finding_count: number;
}

export interface Piece {
  t_from: number;
  offset: number;
}

export interface TimeMappingData {
  pieces: Piece[];
  corrections: [string, string][];
  tz: string;
  source: string;
  gaps: { t: number; jump: number }[];
}

export interface TimeSummary {
  kamera_saati_var: boolean;
  kaynak: string;
  duzeltme_farki_sn: number | null;
  gunluk_kayma_sn: number | null;
  parca_sayisi: number;
  bosluklar: { t: number; jump: number }[];
}

export interface SpriteInfo {
  times: number[];
  tile_w: number;
  tile_h: number;
  cols: number;
  count: number;
}

export interface AnalysisStats {
  sure_sn: Record<string, number>;
  aygit: string;
  dedektor: string;
  analiz_edilen_kare: number;
  aktif_bolum: number;
  aktif_sure_sn: number;
  izler: Record<string, number>;
  iz_sayisi: number;
  yuz_sayisi: number;
  kisi_kumesi: number;
  plakalar: string[];
  hareket_ozeti?: Record<string, number>;
  yuz_tanima: boolean;
  plaka_okuma: boolean;
  gorsel_arama: boolean;
}

export interface Evidence {
  id: number;
  case_id: number;
  original_name: string;
  source_path: string;
  sha256: string;
  size: number;
  camera: string;
  status: "beklemede" | "donusturuluyor" | "hazir" | "hata";
  status_label: string;
  status_detail: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  codec: string | null;
  has_proxy: number;
  analyzed: number;
  created_at: string;
  sniff: { kind?: string; label?: string; offset?: number; notes?: string[] };
  strategy: { name?: string; format?: string | null; offset?: number; denemeler?: Attempt[] };
  analysis_info: {
    donusturme?: {
      container?: string;
      gaps?: [number, number][];
      dropped?: number;
      keyframe_interval?: number | null;
      proxy?: { mode: string; encoder?: string | null; encoder_label?: string };
      sprite?: SpriteInfo;
    };
    analiz?: AnalysisStats;
  };
  time: TimeSummary;
  camera_start: string | null;
  real_start: string | null;
  time_mapping: TimeMappingData;
}

export interface Attempt {
  strateji: string;
  basarili: boolean;
  cozulen_kare: number;
  hata: string;
}

export interface Track {
  id: number;
  evidence_id: number;
  cls: string;
  cls_tr: string;
  t0: number;
  t1: number;
  real_t0: string | null;
  real_t1: string | null;
  n: number;
  conf: number;
  thumb: string | null;
  colors: Record<string, [string, number][]>;
  color_text: string;
  plate: string | null;
  plate_conf: number | null;
  face_count: number;
  similarity?: number;
  enter_t?: number;
  exit_t?: number;
  inside_s?: number;
  real_enter?: string | null;
  event?: string;
  direction?: string;
  reads?: PlateRead[];
}

export interface PlateRead {
  id: number;
  t: number;
  text: string;
  raw: string;
  conf: number;
  valid_tr: number;
  thumb: string | null;
}

export interface DetectionRow {
  track_id: number | null;
  t: number;
  cls: string;
  conf: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type MotionKind = "nesne" | "cevre" | "isik" | "parazit" | "belirsiz";

export interface MotionEvent {
  t0: number;
  t1: number;
  real_t0: string | null;
  real_t1: string | null;
  kind: MotionKind;
  label: string;
  detail: string;
  ignorable: boolean;
  tracks: number[];
}

export interface Activity {
  duration: number;
  buckets: number;
  activity: number[];
  kinds?: (MotionKind | null)[];
  person: number[];
  vehicle: number[];
  segments: { kind: string; t0: number; t1: number }[];
  events?: MotionEvent[];
}

export interface Face {
  id: number;
  evidence_id: number;
  track_id: number | null;
  t: number;
  real_t: string | null;
  score: number;
  quality: number;
  thumb: string | null;
  cluster: number | null;
  box: [number, number, number, number];
  similarity?: number;
  strength?: string;
}

export interface Person {
  person: number;
  face_count: number;
  best: Face;
  faces: Face[];
  appearances: { evidence_id: number; t0: number; t1: number; count: number; real_t0: string | null; real_t1: string | null }[];
}

export interface Roi {
  id: number;
  evidence_id: number;
  name: string;
  kind: "alan" | "cizgi";
  points: [number, number][];
  created_at: string;
}

export interface Verdict {
  match: boolean;
  confidence: number;
  explanation: string;
  plate: string | null;
}

export interface ResultItem {
  id: string;
  kind: "iz" | "kare";
  evidence_id: number;
  t: number;
  box: [number, number, number, number] | null;
  score: number;
  track_id: number | null;
  t0: number | null;
  t1: number | null;
  cls: string | null;
  cls_tr: string | null;
  thumb: string | null;
  real_t: string | null;
  camera: string;
  video: string;
  color_text: string;
  plate: string | null;
  reasons: string[];
  verdict?: Verdict;
  video_analysis?: { candidate: string; t0: number; t1: number; text?: string; error?: string };
}

export interface QueryPlan {
  intent: string;
  time_from: string | null;
  time_to: string | null;
  classes: string[];
  colors: { target: string; color: string }[];
  plate: string | null;
  visual_query_en: string;
  verify_question: string;
  needs_motion: boolean;
  source?: string;
  warning?: string;
}

export interface QueryRow {
  id: number;
  case_id?: number;
  question: string;
  status: string;
  answer: string | null;
  cost: number;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  options: { mode?: string; notes?: string[]; models?: Record<string, string>; evidence_ids?: number[]; roi_id?: number };
  plan?: QueryPlan;
  results?: ResultItem[];
  labels?: Record<string, boolean>;
}

export interface EvalRow {
  model: string;
  candidates: number;
  answered: number;
  matched: number;
  cost: number;
  seconds: number;
  errors: string[];
  labeled?: number;
  tp?: number;
  fp?: number;
  fn?: number;
  tn?: number;
  precision?: number | null;
  recall?: number | null;
  accuracy?: number | null;
}

export interface Evaluation {
  id: number;
  case_id: number;
  query_id: number;
  models: string[];
  results: EvalRow[];
  status: string;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Finding {
  id: number;
  case_id: number;
  evidence_id: number | null;
  t: number | null;
  title: string;
  note: string;
  source: string;
  confidence: number | null;
  image: string | null;
  status: "aday" | "dogrulandi" | "reddedildi";
  status_label: string;
  data: { box?: number[] | null; [k: string]: unknown };
  created_at: string;
  camera_t?: string | null;
  real_t?: string | null;
}

export interface HistoryRow {
  id: number;
  case_id: number | null;
  evidence_id: number | null;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  description: string;
  context: number | null;
  input: string[];
  image: boolean;
  video: boolean;
  structured: boolean;
  free: boolean;
  price_in_m: number;
  price_out_m: number;
}

export interface Catalog {
  models: ModelInfo[];
  total: number;
  image_count: number;
  video_count: number;
  free_vision: number;
  fetched_at: string;
  warning?: string;
}

export interface Settings {
  notice_accepted: boolean;
  ai: {
    base_url: string;
    profile: string;
    roles: { planner: string; verifier: string; video: string };
    data_collection_deny: boolean;
    zdr: boolean;
    max_candidates: number;
    batch_size: number;
    budget_per_query_usd: number;
    send_context_frame: boolean;
    timeout_s: number;
  };
  analysis: {
    auto_analyze: boolean;
    sample_fps: number;
    scan_fps: number;
    detector: string;
    min_conf: number;
    faces: boolean;
    plates: boolean;
    clip: boolean;
    motion_threshold: number;
    device: string;
  };
  time: { tz: string };
  update?: { check_on_start: boolean; last_check: string | null };
  ui?: { last_case?: number | null };
  api_key_set: boolean;
  api_key_masked: string;
  profiles: Record<string, { label: string; roles: Record<string, string> }>;
}

export interface UpdateInfo {
  current: string;
  latest: string;
  newer: boolean;
  title: string;
  notes: string;
  published_at: string | null;
  page: string | null;
  checked_at: string;
  asset: { name: string; size: number; url: string; sha256: string | null } | null;
}

export interface UpdateStatus {
  current: string;
  can_apply: boolean;
  reason: string | null;
  check_on_start: boolean;
  last_check: string | null;
  latest: UpdateInfo | null;
  staged: { version: string; dir: string; created_at: string } | null;
  result: { ok: boolean; version: string; error?: string | null } | null;
}

export interface SystemInfo {
  version: string;
  data_dir: string;
  models_dir: string;
  frozen: boolean;
  encoders: { name: string; label: string; ok: boolean }[];
  encoder: string;
  inference: { onnxruntime: string; providers: string[]; gpu: boolean; label: string };
  models: { key: string; label: string; license: string; ok: boolean; size_mb: number }[];
}

export interface EngineInfo {
  ready: boolean;
  port: number;
  token: string;
  data_dir: string;
  portable: boolean;
  error: string | null;
}
