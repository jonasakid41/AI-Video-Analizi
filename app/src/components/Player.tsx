import { useQueryClient } from "@tanstack/react-query";
import {
  Bookmark, Camera, ChevronFirst, ChevronLast, Eye, EyeOff, Maximize2, Pause, Play, Scissors, ScanSearch, SkipBack,
  SkipForward, SquareDashedMousePointer, Tag,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { CLASS_TR, clsColor } from "../lib/format";
import { CHUNK, qk, useDetectionChunk, useEvidenceList, useFindings, useJobs, useMapping, useRois, useTracks } from "../lib/hooks";
import { fmtClock, fmtMedia } from "../lib/time";
import type { DetectionRow, Evidence, Finding } from "../lib/types";
import { type Box, toast, toastError, useUI } from "../store";
import CameraStrip from "./CameraStrip";
import Timeline from "./Timeline";
import { Badge, Button, Empty, Field, IconButton, inputCls, Modal, Progress, Spinner } from "./ui";

const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];
// Kesit bitince sonraki kesite geçildiğinde yeni oynatıcının otomatik başlaması için
let autoplayNext = false;

export default function Player({ caseId, ev }: { caseId: number; ev?: Evidence }) {
  if (!ev) {
    return <Empty icon={<Camera className="size-10" />} title="Bir video seçin">Soldaki listeden bir video seçin ya da yeni video ekleyin.</Empty>;
  }
  if (ev.status !== "hazir") return <NotReady ev={ev} />;
  return <ReadyPlayer key={ev.id} caseId={caseId} ev={ev} />;
}

/** Dönüştürme sürerken ilerleme + iptal; hata ya da yarıda kalmada yeniden deneme. */
function NotReady({ ev }: { ev: Evidence }) {
  const { data: jobs } = useJobs();
  const setTab = useUI((s) => s.setTab);
  const job = jobs?.find((j) => j.evidence_id === ev.id && j.kind === "ingest" && (j.status === "calisiyor" || j.status === "beklemede"));
  const retry = () => api.post(`/api/evidence/${ev.id}/reingest`).then(() => toast("Yeniden dönüştürülüyor")).catch(toastError);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      {ev.status === "hata" ? (
        <>
          <Badge tone="danger">Dönüştürülemedi</Badge>
          <div className="max-w-md text-muted">{ev.status_detail}</div>
          <div className="flex gap-2">
            <Button variant="primary" onClick={retry}>
              Yeniden dene
            </Button>
            <Button variant="ghost" onClick={() => setTab("bilgi")}>
              Ayrıntılar ve teşhis paketi
            </Button>
          </div>
        </>
      ) : job ? (
        <>
          <Spinner className="size-6" />
          <div className="text-muted">{job.message || ev.status_detail}</div>
          <div className="flex w-72 items-center gap-2">
            <Progress value={job.progress} className="flex-1" />
            <span className="w-10 text-right text-[12px] tabular text-muted">%{Math.round(job.progress * 100)}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => api.post(`/api/jobs/${job.id}/cancel`).then(() => toast("İptal ediliyor…")).catch(toastError)}>
            İptal et
          </Button>
        </>
      ) : (
        <>
          <Spinner className="size-6" />
          <div className="text-muted">{ev.status_detail || "Dönüştürme sırada"}</div>
          <Button variant="ghost" size="sm" onClick={retry}>
            Yeniden başlat
          </Button>
        </>
      )}
    </div>
  );
}

function ReadyPlayer({ caseId, ev }: { caseId: number; ev: Evidence }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const clockRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const ui = useUI();
  const { overlay, drawMode, selBox, focusBox, seekReq, time, clipIn, clipOut } = ui;
  const mapping = useMapping(ev);
  const { data: tracks } = useTracks(ev);
  const { data: rois } = useRois(ev.id);
  const { data: findings } = useFindings(caseId);
  const { data: allEvidence } = useEvidenceList(caseId);
  const dets0 = useDetectionChunk(ev, time);
  const dets1 = useDetectionChunk(ev, time + CHUNK);
  const fps = ev.fps || 25;

  // Aynı kameranın ardışık kesitleri (gerçek başlangıç saatine göre)
  const siblings = useMemo(
    () => (allEvidence ?? [])
      .filter((e) => e.status === "hazir" && e.camera === ev.camera)
      .sort((a, b) => (a.real_start ?? "").localeCompare(b.real_start ?? "") || a.id - b.id),
    [allEvidence, ev.camera],
  );
  const idx = siblings.findIndex((e) => e.id === ev.id);
  const prevSeg = ev.camera && idx > 0 ? siblings[idx - 1] : undefined;
  const nextSeg = ev.camera && idx >= 0 && idx < siblings.length - 1 ? siblings[idx + 1] : undefined;
  const goSegment = (target: Evidence | undefined, play: boolean) => {
    if (!target) return;
    autoplayNext = play;
    ui.seek(target.id, 0);
  };

  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [zoom, setZoom] = useState({ z: 1, x: 0, y: 0 });
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [hoverPt, setHoverPt] = useState<[number, number] | null>(null);
  const [dragBox, setDragBox] = useState<[number, number, number, number] | null>(null);
  const [roiName, setRoiName] = useState<{ kind: "alan" | "cizgi"; points: [number, number][] } | null>(null);
  const [findingOpen, setFindingOpen] = useState(false);
  const focusUntil = useRef(0);
  const panRef = useRef<{ x: number; y: number; zx: number; zy: number } | null>(null);

  const trackInfo = useMemo(() => new Map((tracks ?? []).map((t) => [t.id, t])), [tracks]);
  const rows = useMemo(() => [...(dets0.data ?? []), ...(dets1.data ?? [])], [dets0.data, dets1.data]);
  const byTrack = useMemo(() => {
    const m = new Map<number | string, DetectionRow[]>();
    for (const r of rows) {
      const k = r.track_id ?? `${r.t}-${r.x}`;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    for (const arr of m.values()) arr.sort((a, b) => a.t - b.t);
    return m;
  }, [rows]);

  // --- dış istekler: konuma git ---------------------------------------------------------
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !seekReq || seekReq.evidenceId !== ev.id) return;
    v.currentTime = Math.max(0, seekReq.t);
    if (ui.focusBox) focusUntil.current = performance.now() + 5000;
    useUI.setState({ seekReq: null }); // tüketildi: başka bir oynatıcı yeniden uygulamasın
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekReq]);

  // Bulgu kutusu açıldığı anda belirlenir: kullanıcının seçimi ya da hâlâ vurgulanan sonuç kutusu
  const [findingBox, setFindingBox] = useState<Box | null>(null);
  const openFinding = () => {
    setFindingBox(selBox ?? (performance.now() < focusUntil.current ? focusBox : null));
    setFindingOpen(true);
  };

  // --- görüntü alanı ve koordinat dönüşümleri -------------------------------------------------
  const content = useCallback(() => {
    const v = videoRef.current;
    const st = stageRef.current;
    if (!v || !st) return null;
    const cw = st.clientWidth;
    const ch = st.clientHeight;
    const vw = v.videoWidth || ev.width || 16;
    const vh = v.videoHeight || ev.height || 9;
    const s = Math.min(cw / vw, ch / vh);
    return { ox: (cw - vw * s) / 2, oy: (ch - vh * s) / 2, w: vw * s, h: vh * s, cw, ch };
  }, [ev.width, ev.height]);

  const toNorm = useCallback(
    (clientX: number, clientY: number): [number, number] | null => {
      const st = stageRef.current;
      const c = content();
      if (!st || !c) return null;
      const r = st.getBoundingClientRect();
      const lx = ((clientX - r.left) / r.width) * c.cw;
      const ly = ((clientY - r.top) / r.height) * c.ch;
      return [Math.min(1, Math.max(0, (lx - c.ox) / c.w)), Math.min(1, Math.max(0, (ly - c.oy) / c.h))];
    },
    [content],
  );

  // --- çizim döngüsü --------------------------------------------------------------------------
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const v = videoRef.current;
      const cv = canvasRef.current;
      const c = content();
      if (!v || !cv || !c) return;
      const dpr = window.devicePixelRatio || 1;
      if (cv.width !== Math.round(c.cw * dpr) || cv.height !== Math.round(c.ch * dpr)) {
        cv.width = Math.round(c.cw * dpr);
        cv.height = Math.round(c.ch * dpr);
      }
      const g = cv.getContext("2d")!;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, c.cw, c.ch);
      const t = v.currentTime;
      const P = (x: number, y: number): [number, number] => [c.ox + x * c.w, c.oy + y * c.h];
      const lw = 2 / zoom.z;

      // Saat göstergesi (her kare)
      if (clockRef.current) {
        const real = mapping.realSec(t);
        const cam = mapping.cameraSec(t);
        const diff = real !== null && cam !== null && Math.abs(real - cam) >= 1;
        clockRef.current.innerHTML =
          `<span class="text-[17px] font-semibold tabular">${real !== null ? fmtClock(real) : fmtMedia(t, true)}</span>` +
          (diff ? `<span class="ml-2 text-[11.5px] text-muted tabular">kamera ${fmtClock(cam, false)}</span>` : "") +
          `<span class="ml-2 text-[11.5px] text-faint tabular">${fmtMedia(t, true)} / ${fmtMedia(ev.duration)}</span>`;
      }

      if (overlay.rois) {
        for (const r of rois ?? []) {
          g.strokeStyle = "rgba(245,158,11,0.9)";
          g.fillStyle = "rgba(245,158,11,0.10)";
          g.lineWidth = lw;
          g.setLineDash(r.kind === "cizgi" ? [8 / zoom.z, 5 / zoom.z] : []);
          g.beginPath();
          r.points.forEach(([x, y], i) => (i ? g.lineTo(...P(x, y)) : g.moveTo(...P(x, y))));
          if (r.kind === "alan") {
            g.closePath();
            g.fill();
          }
          g.stroke();
          g.setLineDash([]);
          const [lx, ly] = P(r.points[0][0], r.points[0][1]);
          g.font = `${12 / zoom.z}px Segoe UI`;
          g.fillStyle = "rgba(245,158,11,1)";
          g.fillText(r.name, lx + 4 / zoom.z, ly - 4 / zoom.z);
        }
      }

      if (overlay.boxes) {
        g.font = `600 ${11.5 / zoom.z}px Segoe UI`;
        for (const [key, arr] of byTrack) {
          let a: DetectionRow | undefined;
          let b: DetectionRow | undefined;
          for (const r of arr) {
            if (r.t <= t) a = r;
            if (r.t > t) {
              b = r;
              break;
            }
          }
          let box: [number, number, number, number] | null = null;
          if (a && b && b.t - a.t <= 1.6) {
            const k = (t - a.t) / (b.t - a.t);
            box = [a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k, a.w + (b.w - a.w) * k, a.h + (b.h - a.h) * k];
          } else if (a && t - a.t <= 0.6) box = [a.x, a.y, a.w, a.h];
          else if (b && b.t - t <= 0.3) box = [b.x, b.y, b.w, b.h];
          if (!box) continue;
          const row = (a ?? b)!;
          const tr = typeof key === "number" ? trackInfo.get(key) : undefined;
          const col = clsColor(tr?.cls ?? row.cls);
          const [x, y] = P(box[0], box[1]);
          g.strokeStyle = col;
          g.lineWidth = lw;
          g.strokeRect(x, y, box[2] * c.w, box[3] * c.h);
          if (overlay.labels) {
            const label = `${CLASS_TR[tr?.cls ?? row.cls] ?? row.cls}${tr?.plate ? " · " + tr.plate : ""}`;
            const tw = g.measureText(label).width + 8 / zoom.z;
            g.fillStyle = col;
            g.fillRect(x, y - 15 / zoom.z, tw, 15 / zoom.z);
            g.fillStyle = "#06121c";
            g.fillText(label, x + 4 / zoom.z, y - 4 / zoom.z);
          }
        }
      }

      const fb = focusBox && performance.now() < focusUntil.current ? focusBox : null;
      for (const [bx, color, dash] of [
        [fb, "#facc15", [6, 4]],
        [selBox, "#22d3ee", []],
        [dragBox, "#22d3ee", [5, 4]],
      ] as [Box | null, string, number[]][]) {
        if (!bx) continue;
        const [x, y] = P(bx[0], bx[1]);
        g.strokeStyle = color;
        g.lineWidth = 2.5 / zoom.z;
        g.setLineDash(dash.map((d) => d / zoom.z));
        g.strokeRect(x, y, bx[2] * c.w, bx[3] * c.h);
        g.setLineDash([]);
      }

      if (draft.length) {
        g.strokeStyle = "#22d3ee";
        g.fillStyle = "#22d3ee";
        g.lineWidth = lw;
        g.beginPath();
        draft.forEach(([x, y], i) => (i ? g.lineTo(...P(x, y)) : g.moveTo(...P(x, y))));
        if (hoverPt) g.lineTo(...P(hoverPt[0], hoverPt[1]));
        g.stroke();
        for (const [x, y] of draft) {
          const [px, py] = P(x, y);
          g.beginPath();
          g.arc(px, py, 3.5 / zoom.z, 0, Math.PI * 2);
          g.fill();
        }
      }
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [content, overlay, rois, byTrack, trackInfo, mapping, focusBox, selBox, dragBox, draft, hoverPt, zoom.z, ev.duration]);

  // --- oynatma kontrolleri ------------------------------------------------------------------
  const v = () => videoRef.current!;
  const toggle = () => (v().paused ? v().play() : v().pause());
  const step = (frames: number) => {
    v().pause();
    v().currentTime = Math.max(0, Math.min((ev.duration ?? 0) - 0.001, v().currentTime + frames / fps));
  };
  const jump = (s: number) => (v().currentTime = Math.max(0, v().currentTime + s));
  const setRate = (r: number) => {
    setSpeed(r);
    v().playbackRate = r;
  };

  const exportFrame = async () => {
    try {
      await api.post(`/api/evidence/${ev.id}/export-frame`, { t: v().currentTime });
      toast("Kare kaydedildi (PNG + bilgi dosyası). Bilgi sekmesinden klasörü açabilirsiniz.", "ok");
    } catch (e) {
      toastError(e);
    }
  };

  const finishDraft = useCallback(
    (points: [number, number][]) => {
      if (drawMode === "alan" && points.length >= 3) setRoiName({ kind: "alan", points });
      else if (drawMode === "cizgi" && points.length === 2) setRoiName({ kind: "cizgi", points });
      setDraft([]);
    },
    [drawMode],
  );

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const vid = videoRef.current;
      if (!vid) return;
      switch (e.key) {
        case " ":
          e.preventDefault();
          toggle();
          break;
        case "ArrowLeft":
          e.preventDefault();
          e.shiftKey ? jump(-1) : e.ctrlKey ? jump(-10) : step(-1);
          break;
        case "ArrowRight":
          e.preventDefault();
          e.shiftKey ? jump(1) : e.ctrlKey ? jump(10) : step(1);
          break;
        case "j":
        case "J":
          setRate(SPEEDS[Math.max(0, SPEEDS.indexOf(speed) - 1)]);
          break;
        case "k":
        case "K":
          vid.pause();
          break;
        case "l":
        case "L":
          setRate(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(speed) + 1)]);
          if (vid.paused) vid.play();
          break;
        case "e":
        case "E":
          exportFrame();
          break;
        case "b":
        case "B":
          openFinding();
          break;
        case "i":
        case "I":
          ui.setClip("in", vid.currentTime);
          break;
        case "o":
        case "O":
          ui.setClip("out", vid.currentTime);
          break;
        case "r":
        case "R":
          ui.setDrawMode(drawMode === "alan" ? null : "alan");
          break;
        case "Escape":
          setDraft([]);
          setDragBox(null);
          ui.setDrawMode(null);
          break;
        case "Enter":
          if (draft.length) finishDraft(draft);
          break;
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  // --- fare: çizim, kutu seçimi, kaydırma, yakınlaştırma --------------------------------------------
  const onMouseDown = (e: React.MouseEvent) => {
    const p = toNorm(e.clientX, e.clientY);
    if (!p) return;
    if (drawMode === "kutu") {
      setDragBox([p[0], p[1], 0, 0]);
      return;
    }
    if (drawMode === "alan" || drawMode === "cizgi") {
      const next = [...draft, p];
      if (drawMode === "cizgi" && next.length === 2) finishDraft(next);
      else setDraft(next);
      return;
    }
    if (zoom.z > 1) panRef.current = { x: e.clientX, y: e.clientY, zx: zoom.x, zy: zoom.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    const p = toNorm(e.clientX, e.clientY);
    if (dragBox && p) setDragBox([dragBox[0], dragBox[1], p[0] - dragBox[0], p[1] - dragBox[1]]);
    if (draft.length) setHoverPt(p);
    if (panRef.current) {
      const d = panRef.current;
      setZoom((z) => ({ ...z, x: d.zx + (e.clientX - d.x), y: d.zy + (e.clientY - d.y) }));
    }
  };
  const onMouseUp = () => {
    panRef.current = null;
    if (dragBox) {
      const [x, y, w, h] = dragBox;
      const b: Box = [Math.min(x, x + w), Math.min(y, y + h), Math.abs(w), Math.abs(h)];
      if (b[2] > 0.01 && b[3] > 0.01) ui.setSelBox(b);
      setDragBox(null);
      ui.setDrawMode(null);
    }
  };
  const onWheel = (e: React.WheelEvent) => {
    const st = stageRef.current?.parentElement;
    if (!st) return;
    const r = st.getBoundingClientRect();
    const mx = e.clientX - r.left - r.width / 2;
    const my = e.clientY - r.top - r.height / 2;
    setZoom((z) => {
      const nz = Math.min(10, Math.max(1, z.z * (e.deltaY < 0 ? 1.18 : 1 / 1.18)));
      if (nz === 1) return { z: 1, x: 0, y: 0 };
      const k = nz / z.z;
      return { z: nz, x: mx - (mx - z.x) * k, y: my - (my - z.y) * k };
    });
  };

  const saveRoi = async (name: string) => {
    if (!roiName) return;
    try {
      await api.post(`/api/evidence/${ev.id}/rois`, { name: name || (roiName.kind === "alan" ? "Alan" : "Çizgi"), kind: roiName.kind, points: roiName.points });
      qc.invalidateQueries({ queryKey: qk.rois(ev.id) });
      toast("Alan kaydedildi", "ok");
    } catch (e) {
      toastError(e);
    }
    setRoiName(null);
    ui.setDrawMode(null);
  };

  const exportClip = async () => {
    if (clipIn === null || clipOut === null || clipOut <= clipIn) return;
    try {
      await api.post(`/api/evidence/${ev.id}/export-clip`, { t0: clipIn, t1: clipOut });
      toast("Kesit dışa aktarılıyor (İşler menüsünden izleyebilirsiniz)", "info");
    } catch (e) {
      toastError(e);
    }
  };

  const cursor = drawMode ? "crosshair" : zoom.z > 1 ? (panRef.current ? "grabbing" : "grab") : "default";

  return (
    <div className="flex h-full flex-col">
      <div
        className="relative min-h-0 flex-1 overflow-hidden bg-black"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => {
          panRef.current = null;
          setHoverPt(null);
        }}
        onDoubleClick={() => {
          if (drawMode === "alan" && draft.length >= 3) finishDraft(draft);
          else if (!drawMode) setZoom({ z: 1, x: 0, y: 0 });
        }}
        style={{ cursor }}
      >
        <div
          ref={stageRef}
          className="absolute inset-0 origin-center"
          style={{ transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.z})` }}
        >
          <video
            ref={videoRef}
            src={mediaUrl(`/api/evidence/${ev.id}/proxy`)}
            className="absolute inset-0 size-full object-contain"
            preload="auto"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onTimeUpdate={(e) => ui.setTime(e.currentTarget.currentTime)}
            onEnded={() => nextSeg && goSegment(nextSeg, true)}
            onLoadedData={(e) => {
              if (autoplayNext) {
                autoplayNext = false;
                e.currentTarget.play().catch(() => {});
              }
            }}
            onSeeked={(e) => ui.setTime(e.currentTarget.currentTime)}
            onError={() => toast("Video oynatılamadı. Bilgi sekmesinden yeniden dönüştürmeyi deneyin.", "error")}
          />
          <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 size-full" />
        </div>
        {zoom.z > 1 && (
          <div className="absolute right-3 top-3">
            <Badge tone="accent">{zoom.z.toFixed(1)}× · çift tık: sıfırla</Badge>
          </div>
        )}
        {drawMode === "kutu" && (
          <div className="absolute left-1/2 top-3 -translate-x-1/2">
            <Badge tone="accent">Bölgeyi sürükleyerek seçin · Esc: vazgeç</Badge>
          </div>
        )}
      </div>

      <div className="border-t border-line bg-panel">
        <div className="flex items-center gap-1 px-2 py-1.5">
          <IconButton title="Başa git" onClick={() => (v().currentTime = 0)}>
            <ChevronFirst className="size-4" />
          </IconButton>
          <IconButton title="10 sn geri (Ctrl+←)" onClick={() => jump(-10)}>
            <SkipBack className="size-4" />
          </IconButton>
          <IconButton title="1 kare geri (←)" onClick={() => step(-1)}>
            <span className="text-[11px] font-bold">−1</span>
          </IconButton>
          <button
            onClick={toggle}
            title="Oynat / durdur (Boşluk)"
            className="mx-0.5 flex size-9 items-center justify-center rounded-full bg-accent-strong text-white hover:bg-accent cursor-pointer"
          >
            {playing ? <Pause className="size-4.5" /> : <Play className="ml-0.5 size-4.5" />}
          </button>
          <IconButton title="1 kare ileri (→)" onClick={() => step(1)}>
            <span className="text-[11px] font-bold">+1</span>
          </IconButton>
          <IconButton title="10 sn ileri (Ctrl+→)" onClick={() => jump(10)}>
            <SkipForward className="size-4" />
          </IconButton>
          <IconButton title="Sona git" onClick={() => (v().currentTime = (ev.duration ?? 0) - 0.05)}>
            <ChevronLast className="size-4" />
          </IconButton>
          <select
            value={speed}
            onChange={(e) => setRate(Number(e.target.value))}
            className="ml-1 h-7 rounded border border-line-2 bg-panel-2 px-1 text-[12px] cursor-pointer"
            title="Oynatma hızı (J / L)"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
          {(prevSeg || nextSeg) && (
            <div className="ml-2 flex items-center rounded-md border border-line-2" title="Aynı kameranın ardışık kesitleri">
              <IconButton title={prevSeg ? `Önceki kesit: ${prevSeg.original_name}` : "Önceki kesit yok"} className="size-7" disabled={!prevSeg} onClick={() => goSegment(prevSeg, false)}>
                <ChevronFirst className="size-3.5" />
              </IconButton>
              <span className="px-1 text-[11px] tabular text-muted">
                {idx + 1}/{siblings.length}
              </span>
              <IconButton title={nextSeg ? `Sonraki kesit: ${nextSeg.original_name}` : "Sonraki kesit yok"} className="size-7" disabled={!nextSeg} onClick={() => goSegment(nextSeg, false)}>
                <ChevronLast className="size-3.5" />
              </IconButton>
            </div>
          )}
          <div ref={clockRef} className="ml-3 min-w-0 flex-1 truncate" />
          <div className="flex items-center gap-0.5">
            <IconButton title={overlay.boxes ? "Tespit kutularını gizle" : "Tespit kutularını göster"} onClick={() => ui.toggleOverlay("boxes")} active={overlay.boxes}>
              {overlay.boxes ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            </IconButton>
            <IconButton title="Etiketler" onClick={() => ui.toggleOverlay("labels")} active={overlay.labels}>
              <Tag className="size-4" />
            </IconButton>
            <IconButton title="Bölge seç (iyileştirme / bulgu için)" active={drawMode === "kutu"} onClick={() => ui.setDrawMode(drawMode === "kutu" ? null : "kutu")}>
              <SquareDashedMousePointer className="size-4" />
            </IconButton>
            {selBox && (
              <button className="text-[11.5px] text-accent hover:underline cursor-pointer" onClick={() => ui.setSelBox(null)} title="Seçimi kaldır">
                seçim ✕
              </button>
            )}
            <span className="mx-1 h-5 w-px bg-line" />
            <IconButton title="Bu kareyi kaydet (E)" onClick={exportFrame}>
              <Camera className="size-4" />
            </IconButton>
            <IconButton title="Bulgu ekle (B)" onClick={openFinding}>
              <Bookmark className="size-4" />
            </IconButton>
            <IconButton title="Bu kareyi iyileştir" onClick={() => ui.setTab("iyilestir")}>
              <ScanSearch className="size-4" />
            </IconButton>
            <IconButton title="Tam ekran" onClick={() => stageRef.current?.parentElement?.requestFullscreen?.()}>
              <Maximize2 className="size-4" />
            </IconButton>
          </div>
        </div>
        <Timeline ev={ev} caseId={caseId} videoRef={videoRef} findings={findings ?? []} />
        <CameraStrip caseId={caseId} ev={ev} />
        <div className="flex items-center gap-2 border-t border-line px-3 py-1.5 text-[12px] text-muted">
          <Scissors className="size-3.5" />
          <span>Kesit:</span>
          <button className="rounded px-1.5 py-0.5 hover:bg-panel-3 cursor-pointer" onClick={() => ui.setClip("in", v().currentTime)} title="Başlangıç (I)">
            Başlangıç {clipIn !== null ? fmtMedia(clipIn) : "—"}
          </button>
          <button className="rounded px-1.5 py-0.5 hover:bg-panel-3 cursor-pointer" onClick={() => ui.setClip("out", v().currentTime)} title="Bitiş (O)">
            Bitiş {clipOut !== null ? fmtMedia(clipOut) : "—"}
          </button>
          {clipIn !== null && clipOut !== null && clipOut > clipIn && (
            <>
              <Button size="sm" variant="subtle" onClick={exportClip}>
                Kesiti dışa aktar ({fmtMedia(clipOut - clipIn)})
              </Button>
              <button className="text-faint hover:text-text cursor-pointer" onClick={() => ui.setClip("clear")}>
                temizle
              </button>
            </>
          )}
          <span className="flex-1" />
          <span className="hidden text-faint xl:inline">Boşluk oynat · ←/→ kare · Shift 1 sn · J/K/L hız · tekerlek yakınlaştır</span>
        </div>
      </div>

      <RoiNameDialog draft={roiName} onSave={saveRoi} onCancel={() => { setRoiName(null); ui.setDrawMode(null); }} />
      {findingOpen && (
        <NewFinding
          caseId={caseId}
          ev={ev}
          t={videoRef.current?.currentTime ?? 0}
          box={findingBox}
          realLabel={fmtClock(mapping.realSec(videoRef.current?.currentTime ?? 0))}
          onClose={() => setFindingOpen(false)}
        />
      )}
    </div>
  );
}

function RoiNameDialog({ draft, onSave, onCancel }: { draft: { kind: string } | null; onSave: (n: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  useEffect(() => setName(""), [draft]);
  return (
    <Modal
      open={!!draft}
      onClose={onCancel}
      title={draft?.kind === "cizgi" ? "Çizgiye ad verin" : "Alana ad verin"}
      width="max-w-sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Vazgeç
          </Button>
          <Button variant="primary" onClick={() => onSave(name)}>
            Kaydet
          </Button>
        </>
      }
    >
      <input autoFocus className={inputCls} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onSave(name)} placeholder={draft?.kind === "cizgi" ? "ör. Bariyer" : "ör. Giriş kapısı"} />
    </Modal>
  );
}

function NewFinding({ caseId, ev, t, box, realLabel, onClose }: { caseId: number; ev: Evidence; t: number; box: Box | null; realLabel: string; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const save = async () => {
    setBusy(true);
    try {
      await api.post<Finding>(`/api/cases/${caseId}/findings`, { evidence_id: ev.id, t, title: title || `Bulgu — ${realLabel}`, note, source: "elle", box });
      qc.invalidateQueries({ queryKey: qk.findings(caseId) });
      toast("Bulgu eklendi", "ok");
      onClose();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title="Bulgu ekle"
      width="max-w-md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" busy={busy} onClick={save}>
            Ekle
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="text-[12.5px] text-muted">
          {ev.original_name} · {realLabel} {box ? "· seçili bölge işaretlenecek" : ""}
        </div>
        <Field label="Başlık">
          <input autoFocus className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`Bulgu — ${realLabel}`} />
        </Field>
        <Field label="Not">
          <textarea className={`${inputCls} h-24 py-2`} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}
