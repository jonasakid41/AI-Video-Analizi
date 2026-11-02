import { useQueryClient } from "@tanstack/react-query";
import { Crosshair, FileDown, FileSearch, FolderOpen, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, caseExportsDir, confirmDialog, fileUrl, openFolder } from "../../lib/api";
import { fmtPct } from "../../lib/format";
import { qk, useEvidenceList, useFindings, useJob } from "../../lib/hooks";
import { fmtIso, fmtMedia } from "../../lib/time";
import type { Finding } from "../../lib/types";
import { toast, toastError, useUI } from "../../store";
import { Badge, Button, Empty, IconButton, Progress } from "../ui";

const STATUSES: { id: Finding["status"]; label: string; cls: string }[] = [
  { id: "aday", label: "Aday", cls: "bg-panel-3 text-text" },
  { id: "dogrulandi", label: "Doğrulandı", cls: "bg-ok/20 text-ok" },
  { id: "reddedildi", label: "Reddedildi", cls: "bg-danger/15 text-danger" },
];

export default function FindingsPanel({ caseId }: { caseId: number }) {
  const { data: findings } = useFindings(caseId);
  const { data: evs } = useEvidenceList(caseId);
  const [includeCand, setIncludeCand] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);
  const names = new Map((evs ?? []).map((e) => [e.id, e.camera || e.original_name]));

  const report = async () => {
    try {
      const r = await api.post<{ job_id: number }>(`/api/cases/${caseId}/report`, { include_candidates: includeCand });
      setJobId(r.job_id);
    } catch (e) {
      toastError(e);
    }
  };

  const confirmed = findings?.filter((f) => f.status === "dogrulandi").length ?? 0;
  return (
    <div className="space-y-3 p-3">
      <div className="rounded-lg border border-line bg-panel-2 p-3">
        <div className="flex items-center gap-2">
          <FileDown className="size-4 text-accent" />
          <span className="font-medium">Vaka raporu (PDF)</span>
        </div>
        <p className="mt-1 text-[12px] text-muted">
          Videolar ve SHA-256 değerleri, saat düzeltmeleri, {includeCand ? "tüm" : "doğrulanmış"} bulgular, yapay zekâ kullanımı ve işlem geçmişi.
        </p>
        <div className="mt-2 flex items-center gap-2">
          <label className="flex flex-1 cursor-pointer items-center gap-1.5 text-[12px] text-muted">
            <input type="checkbox" checked={includeCand} onChange={(e) => setIncludeCand(e.target.checked)} />
            Aday bulguları da ekle
          </label>
          <Button size="sm" variant="primary" onClick={report} busy={job?.status === "calisiyor" || job?.status === "beklemede"}>
            Rapor oluştur
          </Button>
        </div>
        {job && (job.status === "calisiyor" || job.status === "beklemede") && <Progress value={job.progress} className="mt-2" />}
        {job?.status === "tamamlandi" && (
          <div className="mt-2 flex items-center gap-2 text-[12px] text-ok">
            Rapor hazır.
            <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(job.result.path).catch(toastError)}>
              Klasörü aç
            </Button>
          </div>
        )}
        {job?.status === "hata" && <div className="mt-2 text-[12px] text-danger">{job.message}</div>}
        {confirmed === 0 && !includeCand && !!findings?.length && (
          <div className="mt-2 text-[11.5px] text-warn">Henüz doğrulanmış bulgu yok; rapora yalnızca doğrulananlar girer.</div>
        )}
      </div>

      {!findings?.length ? (
        <Empty icon={<FileSearch className="size-8" />} title="Bulgu yok">
          Oynatıcıdaki yer imi düğmesiyle (B) ya da soru sonuçlarından bulgu ekleyin. Bulgular rapora girmeden önce doğrulanmalıdır.
        </Empty>
      ) : (
        <div className="space-y-2">
          {findings.map((f) => (
            <FindingCard key={f.id} f={f} caseId={caseId} video={f.evidence_id ? names.get(f.evidence_id) : undefined} />
          ))}
        </div>
      )}
      <div className="flex justify-end">
        <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(caseExportsDir(caseId)).catch(() => toast("Henüz dışa aktarılmış dosya yok"))}>
          Dışa aktarımlar klasörü
        </Button>
      </div>
    </div>
  );
}

function FindingCard({ f, caseId, video }: { f: Finding; caseId: number; video?: string }) {
  const qc = useQueryClient();
  const seek = useUI((s) => s.seek);
  const [note, setNote] = useState(f.note);
  const patch = async (body: Partial<Finding>) => {
    try {
      await api.patch(`/api/findings/${f.id}`, body);
      qc.invalidateQueries({ queryKey: qk.findings(caseId) });
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <div className="rounded-lg border border-line bg-panel-2 p-2.5">
      <div className="flex gap-2.5">
        {f.image ? (
          <button className="h-[60px] w-[96px] shrink-0 overflow-hidden rounded bg-black cursor-pointer" onClick={() => f.evidence_id && f.t !== null && seek(f.evidence_id, f.t, (f.data.box as any) ?? null)}>
            <img src={fileUrl(f.image)} alt="" className="size-full object-cover" />
          </button>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1">
            <div className="flex-1 font-medium leading-snug">{f.title}</div>
            {f.evidence_id && f.t !== null && (
              <IconButton title="Bu ana git" className="size-6" onClick={() => seek(f.evidence_id!, f.t!, (f.data.box as any) ?? null)}>
                <Crosshair className="size-3.5" />
              </IconButton>
            )}
            <IconButton
              title="Sil"
              className="size-6"
              onClick={async () => {
                if (!(await confirmDialog("Bulgu silinsin mi?"))) return;
                await api.del(`/api/findings/${f.id}`).catch(toastError);
                qc.invalidateQueries({ queryKey: qk.findings(caseId) });
              }}
            >
              <Trash2 className="size-3.5" />
            </IconButton>
          </div>
          <div className="text-[11.5px] text-muted tabular">
            {f.real_t ? fmtIso(f.real_t) : f.t !== null ? fmtMedia(f.t) : ""} {video && `· ${video}`}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-[11px]">
            <Badge>{f.source === "ai" ? "AI" : f.source === "yerel" ? "yerel analiz" : "elle"}</Badge>
            {f.confidence !== null && <Badge>{fmtPct(f.confidence)}</Badge>}
          </div>
        </div>
      </div>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== f.note && patch({ note })}
        placeholder="Not ekleyin…"
        rows={note ? 2 : 1}
        className="mt-2 w-full resize-none rounded-md border border-line bg-panel px-2 py-1.5 text-[12.5px] outline-none focus:border-accent/60"
      />
      <div className="mt-1.5 flex gap-1">
        {STATUSES.map((s) => (
          <button
            key={s.id}
            onClick={() => patch({ status: s.id })}
            className={`flex-1 rounded py-1 text-[12px] font-medium cursor-pointer ${f.status === s.id ? s.cls : "text-muted hover:bg-panel-3"}`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
