import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Film, Hexagon, Minus, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, confirmDialog, fileUrl, mediaUrl, onFileDrop, pickFiles } from "../lib/api";
import { useEvidenceList, useJobs, useRois } from "../lib/hooks";
import { fmtIso, fmtMedia } from "../lib/time";
import type { Evidence, Roi, Track } from "../lib/types";
import { toast, toastError, useUI } from "../store";
import { Badge, Button, Empty, IconButton, Modal, Progress } from "./ui";

export default function EvidenceList({ caseId }: { caseId: number }) {
  const { data: list } = useEvidenceList(caseId);
  const { data: jobs } = useJobs();
  const evidenceId = useUI((s) => s.evidenceId);
  const selectEvidence = useUI((s) => s.selectEvidence);
  const qc = useQueryClient();
  const [hover, setHover] = useState(false);

  const add = async (paths: string[]) => {
    if (!paths.length) return;
    try {
      await api.post(`/api/cases/${caseId}/evidence`, { paths });
      qc.invalidateQueries({ queryKey: ["evidence", caseId] });
      toast(`${paths.length} dosya eklendi; dönüştürme başladı`, "ok");
    } catch (e) {
      toastError(e);
    }
  };

  useEffect(() => {
    let off: (() => void) | undefined;
    onFileDrop(add, setHover).then((f) => (off = f));
    return () => off?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const jobFor = useMemo(() => {
    const m = new Map<number, { progress: number; message: string; kind: string }>();
    for (const j of jobs ?? []) {
      if (j.evidence_id && (j.status === "calisiyor" || j.status === "beklemede") && !m.has(j.evidence_id)) {
        m.set(j.evidence_id, { progress: j.progress, message: j.message, kind: j.kind });
      }
    }
    return m;
  }, [jobs]);

  const groups = useMemo(() => {
    const g = new Map<string, Evidence[]>();
    for (const e of list ?? []) {
      const k = e.camera || "Kamera belirtilmemiş";
      g.set(k, [...(g.get(k) ?? []), e]);
    }
    for (const arr of g.values()) arr.sort((a, b) => (a.real_start ?? "").localeCompare(b.real_start ?? "") || a.id - b.id);
    return [...g.entries()];
  }, [list]);

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-muted">Videolar</span>
        <Button size="sm" variant="primary" icon={<Plus className="size-3.5" />} onClick={async () => add(await pickFiles("Kamera kayıtlarını seçin"))}>
          Ekle
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!list?.length ? (
          <Empty icon={<Upload className="size-8" />} title="Video yok">
            Dosyaları buraya sürükleyin ya da “Ekle” ile seçin. MP4, AVI, MKV, DAV, ham H.264/H.265 ve diğer DVR biçimleri desteklenir.
          </Empty>
        ) : (
          groups.map(([cam, evs]) => (
            <div key={cam} className="py-1">
              {groups.length > 1 && <div className="px-3 pb-1 pt-2 text-[11px] font-semibold text-faint">{cam}</div>}
              {evs.map((e) => (
                <EvidenceRow key={e.id} e={e} active={e.id === evidenceId} job={jobFor.get(e.id)} onClick={() => selectEvidence(e.id)} />
              ))}
            </div>
          ))
        )}
      </div>
      {evidenceId && <RoiList evidenceId={evidenceId} />}
      {hover && (
        <div className="pointer-events-none absolute inset-2 flex items-center justify-center rounded-xl border-2 border-dashed border-accent bg-accent/10 text-accent">
          Bırakın: vakaya eklensin
        </div>
      )}
    </div>
  );
}

function EvidenceRow({ e, active, job, onClick }: { e: Evidence; active: boolean; job?: { progress: number; message: string; kind: string }; onClick: () => void }) {
  const qc = useQueryClient();
  const remove = async (ev: React.MouseEvent) => {
    ev.stopPropagation();
    if (!(await confirmDialog(`"${e.original_name}" ve tüm analiz sonuçları silinsin mi? (Orijinal dosyanız etkilenmez.)`, "Videoyu sil"))) return;
    try {
      await api.del(`/api/evidence/${e.id}`);
      qc.invalidateQueries({ queryKey: ["evidence", e.case_id] });
    } catch (err) {
      toastError(err);
    }
  };
  const tone = e.status === "hazir" ? "ok" : e.status === "hata" ? "danger" : "accent";
  return (
    <div
      onClick={onClick}
      className={`group mx-1.5 flex cursor-pointer gap-2.5 rounded-lg p-1.5 ${active ? "bg-accent/12 ring-1 ring-accent/40" : "hover:bg-panel-2"}`}
    >
      <div className="relative h-[42px] w-[74px] shrink-0 overflow-hidden rounded bg-panel-3">
        {e.has_proxy ? (
          <img src={mediaUrl(`/api/evidence/${e.id}/thumb`, { v: e.status })} alt="" className="size-full object-cover" />
        ) : (
          <div className="flex size-full items-center justify-center text-faint">
            {e.status === "hata" ? <AlertTriangle className="size-4 text-danger" /> : <Film className="size-4" />}
          </div>
        )}
        {e.duration ? <span className="absolute bottom-0.5 right-0.5 rounded bg-black/70 px-1 text-[10px] tabular">{fmtMedia(e.duration)}</span> : null}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <span className="truncate text-[12.5px] font-medium" title={e.original_name}>
            {e.original_name}
          </span>
          <span className="flex-1" />
          <button onClick={remove} className="hidden text-faint hover:text-danger group-hover:block cursor-pointer" title="Sil">
            <Trash2 className="size-3.5" />
          </button>
        </div>
        {job ? (
          <div className="mt-1 space-y-1">
            <div className="truncate text-[11px] text-accent" title={job.message}>
              {job.message}
            </div>
            <Progress value={job.progress} />
          </div>
        ) : (
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted">
            {e.status !== "hazir" && <Badge tone={tone}>{e.status_label}</Badge>}
            {e.status === "hazir" && (
              <span className="tabular" title="Videonun başlangıç saati (düzeltilmiş)">
                {e.real_start ? fmtIso(e.real_start) : <span className="text-warn">saat bilinmiyor</span>}
              </span>
            )}
            {e.status === "hazir" && !e.analyzed && <Badge>analiz bekliyor</Badge>}
          </div>
        )}
      </div>
    </div>
  );
}

function RoiList({ evidenceId }: { evidenceId: number }) {
  const { data: rois } = useRois(evidenceId);
  const drawMode = useUI((s) => s.drawMode);
  const setDrawMode = useUI((s) => s.setDrawMode);
  const qc = useQueryClient();
  const [events, setEvents] = useState<{ roi: Roi; items: Track[] } | null>(null);
  const seek = useUI((s) => s.seek);

  const showEvents = async (r: Roi) => {
    try {
      setEvents({ roi: r, items: await api.get<Track[]>(`/api/rois/${r.id}/events`) });
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <div className="border-t border-line px-3 py-2.5">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-muted">Alanlar</span>
        <div className="flex gap-0.5">
          <IconButton title="Alan çiz (çokgen)" active={drawMode === "alan"} onClick={() => setDrawMode(drawMode === "alan" ? null : "alan")}>
            <Hexagon className="size-4" />
          </IconButton>
          <IconButton title="Çizgi çiz (geçiş sayımı)" active={drawMode === "cizgi"} onClick={() => setDrawMode(drawMode === "cizgi" ? null : "cizgi")}>
            <Minus className="size-4 -rotate-45" />
          </IconButton>
        </div>
      </div>
      {drawMode === "alan" || drawMode === "cizgi" ? (
        <div className="rounded-md bg-accent/10 px-2 py-1.5 text-[11.5px] text-accent">
          {drawMode === "alan" ? "Görüntüye tıklayarak köşeleri ekleyin; bitirmek için çift tıklayın ya da Enter'a basın." : "Çizginin iki ucuna tıklayın."} Esc ile vazgeçin.
        </div>
      ) : !rois?.length ? (
        <div className="text-[11.5px] text-faint">Belirli bir bölgeyi sorgulamak için alan ya da çizgi çizin.</div>
      ) : (
        <div className="space-y-0.5">
          {rois.map((r) => (
            <div key={r.id} className="group flex items-center gap-2 rounded px-1.5 py-1 hover:bg-panel-2">
              {r.kind === "alan" ? <Hexagon className="size-3.5 text-warn" /> : <Minus className="size-3.5 -rotate-45 text-warn" />}
              <button className="flex-1 truncate text-left text-[12.5px] cursor-pointer" onClick={() => showEvents(r)} title="Bu alandaki olaylar">
                {r.name}
              </button>
              <button
                className="hidden text-faint hover:text-danger group-hover:block cursor-pointer"
                title="Sil"
                onClick={async () => {
                  await api.del(`/api/rois/${r.id}`).catch(toastError);
                  qc.invalidateQueries({ queryKey: ["rois", evidenceId] });
                }}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
      <Modal open={!!events} onClose={() => setEvents(null)} title={`“${events?.roi.name}” — olaylar`}>
        {events && !events.items.length ? (
          <Empty title="Bu alanda kayıtlı hareket yok" />
        ) : (
          <div className="space-y-1">
            {events?.items.map((t) => (
              <button
                key={t.id}
                onClick={() => {
                  seek(t.evidence_id, t.enter_t ?? t.t0);
                  setEvents(null);
                }}
                className="flex w-full items-center gap-3 rounded-md p-1.5 text-left hover:bg-panel-2 cursor-pointer"
              >
                {t.thumb ? <img src={fileUrl(t.thumb)} className="h-10 w-10 rounded object-cover" alt="" /> : <div className="size-10 rounded bg-panel-3" />}
                <div className="min-w-0 flex-1">
                  <div className="font-medium">
                    {t.cls_tr} {t.plate && <span className="font-mono text-warn">{t.plate}</span>}
                  </div>
                  <div className="text-[12px] text-muted">
                    {t.event === "cizgi_gecti" ? `Çizgiyi geçti (${t.direction})` : `Alanda ${t.inside_s?.toFixed(0)} sn`} · {t.color_text}
                  </div>
                </div>
                <span className="text-[12px] tabular text-muted">{t.real_enter ? fmtIso(t.real_enter, false) : fmtMedia(t.enter_t)}</span>
              </button>
            ))}
          </div>
        )}
      </Modal>
    </div>
  );
}

