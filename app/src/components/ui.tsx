import { Loader2, X } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, useEffect } from "react";
import { useUI } from "../store";

type Variant = "primary" | "default" | "ghost" | "danger" | "subtle";

const variants: Record<Variant, string> = {
  primary: "bg-accent-strong text-white hover:bg-accent border-transparent",
  default: "bg-panel-3 text-text hover:bg-line border-line-2",
  ghost: "bg-transparent text-muted hover:text-text hover:bg-panel-3 border-transparent",
  danger: "bg-danger/15 text-danger hover:bg-danger/25 border-danger/30",
  subtle: "bg-panel-2 text-text hover:bg-panel-3 border-line",
};

export function Button({
  variant = "default", size = "md", icon, busy, className = "", children, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; icon?: ReactNode; busy?: boolean }) {
  const sz = size === "sm" ? "h-7 px-2.5 text-[12.5px] gap-1.5" : "h-8.5 px-3.5 gap-2";
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={`inline-flex items-center justify-center rounded-md border font-medium whitespace-nowrap transition-colors
        disabled:opacity-45 disabled:pointer-events-none cursor-pointer ${sz} ${variants[variant]} ${className}`}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function IconButton({
  title, active, className = "", children, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { title: string; active?: boolean }) {
  return (
    <button
      {...rest}
      title={title}
      aria-label={title}
      className={`inline-flex size-8 items-center justify-center rounded-md transition-colors cursor-pointer
        disabled:opacity-40 disabled:pointer-events-none
        ${active ? "bg-accent/20 text-accent" : "text-muted hover:text-text hover:bg-panel-3"} ${className}`}
    >
      {children}
    </button>
  );
}

export function Spinner({ className = "size-4" }: { className?: string }) {
  return <Loader2 className={`animate-spin text-accent ${className}`} />;
}

export function Badge({ children, tone = "default", title }: { children: ReactNode; tone?: "default" | "ok" | "warn" | "danger" | "accent"; title?: string }) {
  const t = {
    default: "bg-panel-3 text-muted border-line-2",
    ok: "bg-ok/12 text-ok border-ok/30",
    warn: "bg-warn/12 text-warn border-warn/30",
    danger: "bg-danger/12 text-danger border-danger/30",
    accent: "bg-accent/12 text-accent border-accent/30",
  }[tone];
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11.5px] font-medium whitespace-nowrap ${t}`}>
      {children}
    </span>
  );
}

export function Progress({ value, className = "" }: { value: number; className?: string }) {
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-panel-3 ${className}`}>
      <div className="h-full rounded-full bg-accent transition-[width] duration-300" style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }} />
    </div>
  );
}

export function Modal({
  open, onClose, title, children, footer, width = "max-w-2xl", dismissable = true,
}: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; width?: string; dismissable?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onMouseDown={onClose}>
      <div
        className={`flex max-h-[90vh] w-full ${width} flex-col overflow-hidden rounded-xl border border-line-2 bg-panel shadow-2xl`}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {dismissable && (
            <IconButton title="Kapat" onClick={onClose}>
              <X className="size-4" />
            </IconButton>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-[12.5px] font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="block text-[11.5px] leading-snug text-faint">{hint}</span>}
    </label>
  );
}

export const inputCls =
  "h-8.5 w-full rounded-md border border-line-2 bg-panel-2 px-2.5 text-text placeholder:text-faint outline-none focus:border-accent/70 focus:ring-2 focus:ring-accent/20";

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-1">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors ${checked ? "bg-accent-strong" : "bg-line-2"}`}
      >
        <span className={`absolute top-0.5 size-4 rounded-full bg-white transition-all ${checked ? "left-4.5" : "left-0.5"}`} />
      </button>
      <span>
        <span className="block">{label}</span>
        {hint && <span className="block text-[11.5px] leading-snug text-faint">{hint}</span>}
      </span>
    </label>
  );
}

/** compact: dar panellerde yalnızca etkin sekmenin adı yazılır, diğerleri simgeyle gösterilir. */
export function Tabs<T extends string>({
  value, onChange, items, compact = false,
}: { value: T; onChange: (v: T) => void; items: { id: T; label: string; icon?: ReactNode; badge?: ReactNode }[]; compact?: boolean }) {
  return (
    <div className="flex gap-0.5 border-b border-line px-1.5" role="tablist">
      {items.map((it) => {
        const active = value === it.id;
        const showLabel = !compact || active || !it.icon;
        return (
          <button
            key={it.id}
            role="tab"
            aria-selected={active}
            aria-label={it.label}
            title={it.label}
            onClick={() => onChange(it.id)}
            className={`relative flex items-center gap-1.5 whitespace-nowrap py-2.5 text-[12.5px] font-medium transition-colors cursor-pointer
              ${showLabel ? "px-2.5" : "px-2"} ${active ? "text-text" : "text-muted hover:text-text"}`}
          >
            {it.icon}
            {showLabel && it.label}
            {it.badge}
            {active && <span className="absolute inset-x-1.5 -bottom-px h-0.5 rounded bg-accent" />}
          </button>
        );
      })}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <div className="font-medium text-muted">{title}</div>
      {children && <div className="max-w-sm text-[12.5px] leading-relaxed text-faint">{children}</div>}
    </div>
  );
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,auto)_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="selectable min-w-0 break-words text-text">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Section({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted">{title}</h3>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useUI();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex -translate-x-1/2 flex-col items-center gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`pointer-events-auto max-w-xl cursor-pointer rounded-lg border px-4 py-2.5 shadow-xl ${
            t.kind === "error" ? "border-danger/40 bg-[#2a1416] text-[#ffb4b4]" : t.kind === "ok" ? "border-ok/40 bg-[#10251d] text-[#a7f3d0]" : "border-line-2 bg-panel-3"
          }`}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
