import { Eye, EyeOff } from "lucide-react";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { mediaUrl } from "../lib/api";
import { IGNORABLE_KINDS, KIND_STYLE } from "../lib/format";
import { useActivity, useMapping, useTracks } from "../lib/hooks";
import { fmtClock, fmtMedia } from "../lib/time";
import type { Evidence, Finding, MotionEvent, MotionKind } from "../lib/types";
import { useUI } from "../store";

const H = 100;
const LANES = { seg: [0, 4], ev: [6, 23], act: [26, 46], person: [50, 60], vehicle: [63, 73], mark: [78, 90] } as const;

const IGNORABLE = IGNORABLE_KINDS as MotionKind[];

export default function Timeline({ ev, videoRef, findings }: { ev: Evidence; caseId: number; videoRef: RefObject<HTMLVideoElement | null>; findings: Finding[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const { data: act } = useActivity(ev);
  const { data: tracks } = useTracks(ev);
  const mapping = useMapping(ev);
  const markers = useUI((s) => s.markers);
  const clipIn = useUI((s) => s.clipIn);
  const clipOut = useUI((s) => s.clipOut);
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);
  const [hideMinor, setHideMinor] = useState(false);
  const dragging = useRef(false);
  const dur = ev.duration || act?.duration || 1;

  const gaps = useMemo(() => (ev.analysis_info.donusturme?.gaps ?? []).map(([a, b]) => [a, b] as [number, number]), [ev]);
  const jumps = ev.time_mapping?.gaps ?? [];
  const myMarkers = useMemo(() => markers.filter((m) => m.evidence_id === ev.id), [markers, ev.id]);
  const myFindings = useMemo(() => findings.filter((f) => f.evidence_id === ev.id && f.t !== null), [findings, ev.id]);
  const events = act?.events ?? [];

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const cv = canvas.current;
      const w = wrap.current?.clientWidth ?? 0;
      if (!cv || !w) return;
      const dpr = window.devicePixelRatio || 1;
      if (cv.width !== Math.round(w * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(H * dpr);
      }
      const g = cv.getContext("2d")!;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, H);
      const X = (t: number) => (t / dur) * w;
      g.fillStyle = "#0d141c";
      g.fillRect(0, 0, w, H);

      if (clipIn !== null && clipOut !== null && clipOut > clipIn) {
        g.fillStyle = "rgba(56,189,248,0.12)";
        g.fillRect(X(clipIn), 0, X(clipOut) - X(clipIn), H);
      }
      if (act) {
        for (const s of act.segments) {
          g.fillStyle = s.kind === "aktif" ? "rgba(56,189,248,0.55)" : "rgba(91,107,127,0.35)";
          g.fillRect(X(s.t0), LANES.seg[0], Math.max(1, X(s.t1) - X(s.t0)), LANES.seg[1] - LANES.seg[0]);
        }
        // Olaylar: hareketin ne olduğu, yazılı etiketlerle
        const [e0, e1] = LANES.ev;
        g.font = "600 10.5px Segoe UI";
        g.textBaseline = "middle";
        for (const e of events) {
          if (hideMinor && e.ignorable) continue;
          const st = KIND_STYLE[e.kind] ?? KIND_STYLE.belirsiz;
          const x0 = X(e.t0);
          const bw = Math.max(2, X(e.t1) - x0);
          g.globalAlpha = e.ignorable ? 0.45 : 0.9;
          g.fillStyle = st.color;
          g.fillRect(x0, e0, bw, e1 - e0);
          g.globalAlpha = 1;
          const label = e.kind === "nesne" ? e.label : st.name;
          const tw = g.measureText(label).width;
          if (bw > tw + 8) {
            g.fillStyle = e.ignorable ? "#d7e2d9" : "#06121c";
            g.fillText(label, x0 + 4, (e0 + e1) / 2 + 0.5);
          }
        }
        const n = act.buckets;
        const bw = w / n;
        const vis = act.activity.map((v, i) => (hideMinor && act.kinds?.[i] && IGNORABLE.includes(act.kinds[i]!) ? 0 : v));
        const maxA = Math.max(0.002, ...vis);
        const [a0, a1] = LANES.act;
        for (let i = 0; i < n; i++) {
          const v = Math.sqrt(vis[i] / maxA);
          if (v <= 0.02) continue;
          const h = v * (a1 - a0);
          const k = act.kinds?.[i];
          g.fillStyle = k ? KIND_STYLE[k].color : "#38bdf8";
          g.globalAlpha = 0.35 + 0.6 * v;
          g.fillRect(i * bw, a1 - h, Math.max(1, bw - 0.3), h);
        }
        g.globalAlpha = 1;
        const lane = (arr: number[], [y0, y1]: readonly [number, number], rgb: string) => {
          const m = Math.max(1, ...arr);
          for (let i = 0; i < n; i++) {
            if (!arr[i]) continue;
            g.fillStyle = `rgba(${rgb},${0.3 + 0.7 * Math.min(1, arr[i] / m)})`;
            g.fillRect(i * bw, y0, Math.max(1, bw), y1 - y0);
          }
        };
        lane(act.person, LANES.person, "56,189,248");
        lane(act.vehicle, LANES.vehicle, "245,158,11");
      } else {
        g.fillStyle = "#5b6b7f";
        g.font = "11px Segoe UI";
        g.fillText(ev.analyzed ? "" : "Analiz tamamlanınca aktivite ve olaylar burada görünecek", 8, 34);
      }
      for (const [a, b] of gaps) {
        g.fillStyle = "rgba(240,82,82,0.35)";
        g.fillRect(X(a), 0, Math.max(2, X(b) - X(a)), H);
      }
      for (const j of jumps) {
        g.strokeStyle = "rgba(245,158,11,0.9)";
        g.setLineDash([3, 3]);
        g.beginPath();
        g.moveTo(X(j.t), 0);
        g.lineTo(X(j.t), H);
        g.stroke();
        g.setLineDash([]);
      }
      const diamond = (t: number, color: string) => {
        const x = X(t);
        const y = (LANES.mark[0] + LANES.mark[1]) / 2;
        g.fillStyle = color;
        g.beginPath();
        g.moveTo(x, y - 5);
        g.lineTo(x + 5, y);
        g.lineTo(x, y + 5);
        g.lineTo(x - 5, y);
        g.closePath();
        g.fill();
      };
      for (const m of myMarkers) diamond(m.t, m.color);
      for (const f of myFindings) diamond(f.t!, f.status === "dogrulandi" ? "#34d399" : f.status === "reddedildi" ? "#5b6b7f" : "#e3eaf2");

      g.fillStyle = "#5b6b7f";
      g.font = "10px Segoe UI";
      g.textBaseline = "alphabetic";
      g.fillText("aktivite", 4, LANES.act[0] + 9);
      g.fillText("kişi", 4, LANES.person[1] - 2);
      g.fillText("araç", 4, LANES.vehicle[1] - 2);

      const t = videoRef.current?.currentTime ?? 0;
      g.fillStyle = "#facc15";
      g.fillRect(X(t) - 1, 0, 2, H);
      if (hover) {
        g.fillStyle = "rgba(255,255,255,0.5)";
        g.fillRect(hover.x, 0, 1, H);
      }
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [act, events, dur, gaps, jumps, myMarkers, myFindings, hover, clipIn, clipOut, videoRef, ev.analyzed, hideMinor]);

  const tAt = (clientX: number) => {
    const r = wrap.current!.getBoundingClientRect();
    const x = Math.min(r.width, Math.max(0, clientX - r.left));
    return { x, t: (x / r.width) * dur };
  };
  const seekTo = (clientX: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = tAt(clientX).t;
  };

  const sprite = ev.analysis_info.donusturme?.sprite;
  let spriteStyle: React.CSSProperties | null = null;
  if (hover && sprite?.times?.length) {
    let idx = 0;
    let best = Infinity;
    sprite.times.forEach((st, i) => {
      const d = Math.abs(st - hover.t);
      if (d < best) {
        best = d;
        idx = i;
      }
    });
    spriteStyle = {
      width: sprite.tile_w,
      height: sprite.tile_h,
      backgroundImage: `url(${mediaUrl(`/api/evidence/${ev.id}/sprite`)})`,
      backgroundPosition: `-${(idx % sprite.cols) * sprite.tile_w}px -${Math.floor(idx / sprite.cols) * sprite.tile_h}px`,
    };
  }
  const real = hover ? mapping.realSec(hover.t) : null;
  const hoverEvent: MotionEvent | undefined = hover ? events.find((e) => hover.t >= e.t0 - 0.3 && hover.t <= e.t1 + 0.3) : undefined;
  const hoverTracks = hover ? (tracks ?? []).filter((tr) => hover.t >= tr.t0 - 0.5 && hover.t <= tr.t1 + 0.5).slice(0, 5) : [];
  const counts = useMemo(() => {
    const c: Partial<Record<MotionKind, number>> = {};
    for (const e of events) c[e.kind] = (c[e.kind] ?? 0) + (e.t1 - e.t0);
    return c;
  }, [events]);

  return (
    <div className="mx-2 mb-1.5">
      {events.length > 0 && (
        <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10.5px] text-muted">
          {(Object.keys(KIND_STYLE) as MotionKind[]).filter((k) => counts[k]).map((k) => (
            <span key={k} className="flex items-center gap-1" title={`toplam ${Math.round(counts[k] ?? 0)} sn`}>
              <span className="size-2 rounded-sm" style={{ background: KIND_STYLE[k].color, opacity: IGNORABLE.includes(k) ? 0.6 : 1 }} />
              {KIND_STYLE[k].name}
              <span className="text-faint tabular">{fmtMedia(counts[k] ?? 0)}</span>
            </span>
          ))}
          <button
            className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-panel-3 hover:text-text cursor-pointer"
            onClick={() => setHideMinor(!hideMinor)}
            title="Ağaç/bitki/gölge, ışık değişimi ve yağmur/parazit gibi önemsiz hareketler"
          >
            {hideMinor ? <EyeOff className="size-3" /> : <Eye className="size-3" />}
            {hideMinor ? "önemsiz hareketler gizli" : "önemsiz hareketleri gizle"}
          </button>
        </div>
      )}
      <div
        ref={wrap}
        className="relative cursor-pointer select-none"
        style={{ height: H }}
        onMouseDown={(e) => {
          dragging.current = true;
          seekTo(e.clientX);
        }}
        onMouseMove={(e) => {
          setHover(tAt(e.clientX));
          if (dragging.current) seekTo(e.clientX);
        }}
        onMouseUp={() => (dragging.current = false)}
        onMouseLeave={() => {
          dragging.current = false;
          setHover(null);
        }}
      >
        <canvas ref={canvas} className="absolute inset-0 size-full rounded" style={{ height: H }} />
        {hover && (
          <div
            className="pointer-events-none absolute bottom-full z-20 mb-2 w-max max-w-[280px] -translate-x-1/2 overflow-hidden rounded-md border border-line-2 bg-panel shadow-xl"
            style={{ left: Math.min(Math.max(hover.x, 140), (wrap.current?.clientWidth ?? 0) - 140) }}
          >
            {spriteStyle && <div style={spriteStyle} className="mx-auto" />}
            <div className="space-y-0.5 px-2 py-1 text-[11.5px]">
              <div className="text-center tabular">
                {real !== null ? fmtClock(real) : fmtMedia(hover.t)}
                {real !== null && <span className="ml-1.5 text-faint">{fmtMedia(hover.t)}</span>}
              </div>
              {hoverEvent && (
                <div className="flex items-start gap-1.5">
                  <span className="mt-1 size-2 shrink-0 rounded-sm" style={{ background: KIND_STYLE[hoverEvent.kind]?.color }} />
                  <span>
                    {hoverEvent.kind === "nesne" ? hoverEvent.label : KIND_STYLE[hoverEvent.kind]?.name}
                    {hoverEvent.ignorable && <span className="text-faint"> · önemsiz</span>}
                    {hoverEvent.kind === "belirsiz" && <span className="text-warn"> · incelenmeli</span>}
                  </span>
                </div>
              )}
              {hoverTracks.map((tr) => (
                <div key={tr.id} className="truncate text-muted">
                  {tr.cls_tr}
                  {tr.color_text && ` · ${tr.color_text}`}
                  {tr.plate && <span className="font-mono text-warn"> · {tr.plate}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
