// Motordaki TimeMapping'in istemci karşılığı: oynatma sırasında gerçek saati her karede hesaplamak için.
// Tüm saatler kameranın yerel duvar saatidir; Date nesneleri UTC alanlarıyla okunur (saat dilimi kayması olmaz).
import type { TimeMappingData } from "./types";

export function isoToSec(iso: string): number {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(\.\d+)?/);
  if (!m) return NaN;
  const ms = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return ms / 1000 + (m[7] ? parseFloat(m[7]) : 0);
}

export function secToIso(s: number): string {
  const d = new Date(Math.round(s * 1000));
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

export class Mapping {
  private pieces: { t_from: number; offset: number }[];
  private corr: [number, number][];

  constructor(data?: TimeMappingData | null) {
    this.pieces = data?.pieces ?? [];
    this.corr = (data?.corrections ?? [])
      .map(([c, r]) => [isoToSec(c), isoToSec(r)] as [number, number])
      .filter(([a, b]) => !isNaN(a) && !isNaN(b))
      .sort((a, b) => a[0] - b[0]);
  }

  get hasCamera() {
    return this.pieces.length > 0;
  }

  cameraSec(t: number): number | null {
    if (!this.pieces.length) return null;
    let p = this.pieces[0];
    for (const q of this.pieces) if (q.t_from <= t) p = q;
    return t + p.offset;
  }

  correct(cam: number): number {
    const c = this.corr;
    if (!c.length) return cam;
    if (c.length === 1) return cam + (c[0][1] - c[0][0]);
    let i = 0;
    while (i < c.length - 2 && cam >= c[i + 1][0]) i++;
    const [x0, y0] = c[i];
    const [x1, y1] = c[i + 1];
    const slope = x1 !== x0 ? (y1 - y0) / (x1 - x0) : 1;
    return y0 + (cam - x0) * slope;
  }

  realSec(t: number): number | null {
    const c = this.cameraSec(t);
    return c === null ? null : this.correct(c);
  }

  uncorrect(real: number): number {
    const c = this.corr;
    if (!c.length) return real;
    if (c.length === 1) return real - (c[0][1] - c[0][0]);
    let i = 0;
    while (i < c.length - 2 && real >= c[i + 1][1]) i++;
    const [x0, y0] = c[i];
    const [x1, y1] = c[i + 1];
    let slope = x1 !== x0 ? (y1 - y0) / (x1 - x0) : 1;
    if (slope <= 0) slope = 1; // geçersiz referanslarda sıfıra bölme olmasın
    return x0 + (real - y0) / slope;
  }

  /** Kesintisiz kayıt parçaları: video aralığı [t0, t1] → gerçek saat aralığı [r0, r1]. */
  spans(duration: number): { t0: number; t1: number; r0: number; r1: number }[] {
    return this.pieces
      .map((p, i) => {
        const t1 = i + 1 < this.pieces.length ? this.pieces[i + 1].t_from : duration;
        return { t0: p.t_from, t1, r0: this.correct(p.t_from + p.offset), r1: this.correct(t1 + p.offset) };
      })
      .filter((s) => s.t1 > s.t0);
  }

  /** Gerçek saate karşılık gelen video içi zaman (o an kayıt yoksa null). */
  toMedia(real: number, duration: number): number | null {
    if (!this.pieces.length) return null;
    const cam = this.uncorrect(real);
    for (let i = 0; i < this.pieces.length; i++) {
      const p = this.pieces[i];
      const end = i + 1 < this.pieces.length ? this.pieces[i + 1].t_from : duration;
      const t = cam - p.offset;
      if (t >= p.t_from - 1e-6 && t < end) return t;
    }
    return null;
  }
}

const p2 = (n: number) => String(n).padStart(2, "0");

export function fmtClock(sec: number | null, withDate = true): string {
  if (sec === null || isNaN(sec)) return "—";
  const d = new Date(Math.round(sec * 1000));
  const time = `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`;
  if (!withDate) return time;
  return `${p2(d.getUTCDate())}.${p2(d.getUTCMonth() + 1)}.${d.getUTCFullYear()} ${time}`;
}

export function fmtIso(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "—";
  return fmtClock(isoToSec(iso), withDate);
}

export function fmtMedia(t: number | null | undefined, ms = false): string {
  if (t === null || t === undefined || isNaN(t)) return "—";
  const s = Math.max(0, t);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const base = `${h > 0 ? h + ":" : ""}${p2(m)}:${p2(sec)}`;
  return ms ? `${base}.${String(Math.floor((s % 1) * 1000)).padStart(3, "0")}` : base;
}

export function fmtDuration(s: number | null | undefined): string {
  if (!s) return "—";
  if (s < 60) return `${s.toFixed(0)} sn`;
  if (s < 3600) return `${Math.floor(s / 60)} dk ${Math.round(s % 60)} sn`;
  return `${Math.floor(s / 3600)} sa ${Math.round((s % 3600) / 60)} dk`;
}

export function fmtOffset(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const sign = s < 0 ? "−" : "+";
  const a = Math.abs(s);
  const h = Math.floor(a / 3600);
  const m = Math.floor((a % 3600) / 60);
  const sec = Math.round(a % 60);
  return `${sign}${h ? h + " sa " : ""}${m ? m + " dk " : ""}${sec} sn`;
}
