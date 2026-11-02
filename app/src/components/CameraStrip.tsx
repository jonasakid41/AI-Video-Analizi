import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useEvidenceList } from "../lib/hooks";
import { fmtClock, Mapping } from "../lib/time";
import type { Evidence } from "../lib/types";
import { useUI } from "../store";

interface Seg {
  ev: Evidence;
  m: Mapping;
  start: number;
  end: number;
  spans: { t0: number; t1: number; r0: number; r1: number }[];
}

/** Vakadaki tüm kayıtlar ortak gerçek saat ekseninde: her kamera bir şerit, ardışık kesitler ve boşluklar görünür. */
export default function CameraStrip({ caseId, ev }: { caseId: number; ev: Evidence }) {
  const { data: list } = useEvidenceList(caseId);
  const time = useUI((s) => s.time);
  const markers = useUI((s) => s.markers);
  const seek = useUI((s) => s.seek);
  const [open, setOpen] = useState(true);
  const [hover, setHover] = useState<{ x: number; real: number; lane: string } | null>(null);

  const { lanes, t0, t1, untimed } = useMemo(() => {
    const segs: Seg[] = [];
    let untimed = 0;
    for (const e of list ?? []) {
      if (e.status !== "hazir" || !e.duration) continue;
      const m = new Mapping(e.time_mapping);
      const start = m.realSec(0);
      const end = m.realSec(e.duration);
      if (start === null || end === null) {
        untimed++;
        continue;
      }
      segs.push({ ev: e, m, start, end: Math.max(end, start + 1), spans: m.spans(e.duration) });
    }
    const lanes = new Map<string, Seg[]>();
    for (const s of segs) {
      const k = s.ev.camera || s.ev.original_name;
      lanes.set(k, [...(lanes.get(k) ?? []), s]);
    }
    const t0 = Math.min(...segs.map((s) => s.start));
    const t1 = Math.max(...segs.map((s) => s.end));
    return { lanes: [...lanes.entries()].sort((a, b) => a[0].localeCompare(b[0], "tr")), t0, t1, untimed };
  }, [list]);

  const segCount = lanes.reduce((n, [, s]) => n + s.length, 0);
  if (segCount < 2) return null;
  const span = Math.max(1, t1 - t0);
  const pct = (s: number) => ((s - t0) / span) * 100;
  const cur = new Mapping(ev.time_mapping).realSec(time);

  const click = (lane: Seg[], e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const real = t0 + ((e.clientX - r.left) / r.width) * span;
    for (const s of lane) {
      const sp = s.spans.find((x) => real >= x.r0 && real <= x.r1);
      if (sp) {
        const t = s.m.toMedia(real, s.ev.duration ?? 0) ?? sp.t0 + (real - sp.r0);
        seek(s.ev.id, Math.max(0, Math.min(t, (s.ev.duration ?? 1) - 0.05)));
        return;
      }
    }
    // Boşluğa tıklanırsa en yakın kesitin başına/sonuna git
    const near = [...lane].sort((a, b) => Math.min(Math.abs(a.start - real), Math.abs(a.end - real)) - Math.min(Math.abs(b.start - real), Math.abs(b.end - real)))[0];
    if (near) seek(near.ev.id, real < near.start ? 0 : Math.max(0, (near.ev.duration ?? 1) - 0.5));
  };

  return (
    <div className="border-t border-line px-2 py-1.5">
      <button className="flex w-full items-center gap-1.5 text-[11.5px] text-muted hover:text-text cursor-pointer" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        Tüm kameralar — ortak zaman çizelgesi
        <span className="ml-auto tabular text-faint">
          {fmtClock(t0)} → {fmtClock(t1)}
          {untimed > 0 && ` · ${untimed} video saatsiz`}
        </span>
      </button>
      {open && (
        <div className="mt-1 max-h-32 space-y-0.5 overflow-y-auto">
          {lanes.map(([name, segs]) => (
            <div key={name} className="flex items-center gap-2">
              <div className="w-28 shrink-0 truncate text-[11px] text-muted" title={name}>
                {name}
              </div>
              <div
                className="relative h-3.5 flex-1 cursor-pointer rounded-sm bg-panel-2"
                onClick={(e) => click(segs, e)}
                onMouseMove={(e) => {
                  const r = e.currentTarget.getBoundingClientRect();
                  setHover({ x: e.clientX - r.left, real: t0 + ((e.clientX - r.left) / r.width) * span, lane: name });
                }}
                onMouseLeave={() => setHover(null)}
              >
                {segs.flatMap((s) =>
                  s.spans.map((sp, i) => (
                    <div
                      key={`${s.ev.id}-${i}`}
                      title={`${s.ev.original_name}${s.spans.length > 1 ? ` (parça ${i + 1}/${s.spans.length})` : ""}\n${fmtClock(sp.r0)} → ${fmtClock(sp.r1)}`}
                      className={`absolute inset-y-0 rounded-sm ${s.ev.id === ev.id ? "bg-accent/70" : "bg-line-2 hover:bg-muted/60"}`}
                      style={{ left: `${pct(sp.r0)}%`, width: `${Math.max(0.4, pct(sp.r1) - pct(sp.r0))}%` }}
                    />
                  )),
                )}
                {markers
                  .filter((mk) => segs.some((s) => s.ev.id === mk.evidence_id))
                  .map((mk, i) => {
                    const s = segs.find((x) => x.ev.id === mk.evidence_id)!;
                    const real = s.m.realSec(mk.t);
                    if (real === null) return null;
                    return <div key={i} className="pointer-events-none absolute inset-y-0 w-0.5" style={{ left: `${pct(real)}%`, background: mk.color }} />;
                  })}
                {cur !== null && segs.some((s) => s.ev.id === ev.id) && (
                  <div className="pointer-events-none absolute -inset-y-0.5 w-0.5 bg-[#facc15]" style={{ left: `${pct(cur)}%` }} />
                )}
                {hover?.lane === name && (
                  <div className="pointer-events-none absolute bottom-full z-10 mb-1 -translate-x-1/2 whitespace-nowrap rounded bg-panel-3 px-1.5 py-0.5 text-[11px] tabular shadow" style={{ left: hover.x }}>
                    {fmtClock(hover.real)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
