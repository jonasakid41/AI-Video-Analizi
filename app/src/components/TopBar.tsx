import { ArrowLeft, BatteryWarning, Cpu, ListChecks, Settings as SettingsIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { JOB_LABELS, STATUS_LABELS } from "../lib/format";
import { useCase, useJobs, usePower, useSettings, useUpdateStatus } from "../lib/hooks";
import type { EngineInfo, Job } from "../lib/types";
import { toastError, useUI } from "../store";
import { Badge, IconButton, Progress } from "./ui";

export default function TopBar({ info }: { info: EngineInfo }) {
  const caseId = useUI((s) => s.caseId);
  const openCase = useUI((s) => s.openCase);
  const setSettingsOpen = useUI((s) => s.setSettingsOpen);
  const { data: c } = useCase(caseId);
  const { data: settings } = useSettings();
  const { data: power } = usePower();
  const { data: jobs } = useJobs();
  const { data: upd } = useUpdateStatus();
  const busy =(jobs ?? []).some((j) => j.status === "calisiyor" && (j.kind === "analyze" || j.kind === "ingest" || j.kind === "enhance"));

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
      {caseId ? (
        <IconButton title="Vakalara dön" onClick={() => openCase(null)}>
          <ArrowLeft className="size-4.5" />
        </IconButton>
      ) : (
        <img src="/icon.png" alt="" className="ml-1 size-6" />
      )}
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="font-semibold tracking-tight">AI Video Analizi</span>
        {c && (
          <>
            <span className="text-faint">/</span>
            <span className="truncate text-muted">{c.name}</span>
          </>
        )}
      </div>
      <div className="flex-1" />
      {power?.on_battery && busy && (
        <Badge tone="warn" title="Ekran kartı pil tasarrufu nedeniyle yavaşlayabilir; uzun analizlerde şarj aletini takmanız önerilir.">
          <BatteryWarning className="size-3.5" />
          Pilde{power.percent !== null ? ` %${power.percent}` : ""} — analiz yavaşlayabilir
        </Badge>
      )}
      {!info.portable && (
        <Badge tone="warn" title={`Veriler: ${info.data_dir}`}>
          Veriler AppData'da
        </Badge>
      )}
      {settings && (
        <button
          onClick={() => setSettingsOpen(true)}
          className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-[12px] text-muted hover:bg-panel-3 hover:text-text md:flex cursor-pointer"
          title="Yapay zekâ profili"
        >
          <Cpu className="size-3.5" />
          {settings.profiles[settings.ai.profile]?.label ?? "Özel"}
          {!settings.api_key_set && <Badge tone="warn">anahtar yok</Badge>}
        </button>
      )}
      {(upd?.latest?.newer || upd?.staged) && (
        <button onClick={() => setSettingsOpen(true, "sistem")} className="cursor-pointer" title="Ayarlar → Sistem → Güncelleme">
          <Badge tone="accent">{upd.staged ? `v${upd.staged.version} kurulmaya hazır` : `Yeni sürüm: v${upd.latest?.latest}`}</Badge>
        </button>
      )}
      <JobsMenu />
      <IconButton title="Ayarlar" onClick={() => setSettingsOpen(true)}>
        <SettingsIcon className="size-4.5" />
      </IconButton>
    </header>
  );
}

function JobsMenu() {
  const { data: jobs } = useJobs();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = (jobs ?? []).filter((j) => j.status === "calisiyor" || j.status === "beklemede");
  const recent = (jobs ?? []).filter((j) => !active.includes(j)).slice(0, 8);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, [open]);

  const overall = active.length ? active.reduce((a, j) => a + j.progress, 0) / active.length : 0;
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={`flex h-8 items-center gap-2 rounded-md px-2.5 text-[12.5px] cursor-pointer ${active.length ? "bg-accent/12 text-accent" : "text-muted hover:bg-panel-3 hover:text-text"}`}
      >
        <ListChecks className="size-4" />
        {active.length ? (
          <>
            <span>{active.length} iş</span>
            <span className="w-14">
              <Progress value={overall} />
            </span>
          </>
        ) : (
          <span>İşler</span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-40 w-[380px] rounded-lg border border-line-2 bg-panel p-2 shadow-2xl">
          {active.length === 0 && recent.length === 0 && <div className="p-4 text-center text-muted">Henüz iş yok</div>}
          {active.map((j) => (
            <JobRow key={j.id} j={j} />
          ))}
          {recent.length > 0 && <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-faint">Son işler</div>}
          {recent.map((j) => (
            <JobRow key={j.id} j={j} />
          ))}
        </div>
      )}
    </div>
  );
}

function JobRow({ j }: { j: Job }) {
  const running = j.status === "calisiyor" || j.status === "beklemede";
  const tone = j.status === "hata" ? "danger" : j.status === "tamamlandi" ? "ok" : running ? "accent" : "default";
  return (
    <div className="rounded-md px-2 py-2 hover:bg-panel-2">
      <div className="flex items-center gap-2">
        <span className="font-medium">{JOB_LABELS[j.kind] ?? j.kind}</span>
        <Badge tone={tone}>{STATUS_LABELS[j.status] ?? j.status}</Badge>
        <span className="flex-1" />
        {running && (
          <IconButton title="İptal et" className="size-6" onClick={() => api.post(`/api/jobs/${j.id}/cancel`).catch(toastError)}>
            <X className="size-3.5" />
          </IconButton>
        )}
      </div>
      <div className="mt-1 truncate text-[12px] text-muted" title={j.message}>
        {j.message}
      </div>
      {running && <Progress value={j.progress} className="mt-1.5" />}
    </div>
  );
}
