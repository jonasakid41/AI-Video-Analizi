import { useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api, applyUpdate, confirmDialog } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { qk, useJobs, useUpdateStatus } from "../lib/hooks";
import type { UpdateStatus } from "../lib/types";
import { toast, toastError } from "../store";
import { Badge, Button, Progress, Section, Spinner, Toggle } from "./ui";

// Sürüm notları Markdown; burada düz metin olarak gösterilir
const plain = (md: string) => md.replace(/\*\*|`/g, "").replace(/^#+\s*/gm, "").trim();

export default function UpdateSection({ save }: { save: (p: Record<string, unknown>) => Promise<void> }) {
  const { data: st } = useUpdateStatus();
  const { data: jobs } = useJobs();
  const qc = useQueryClient();
  const [checking, setChecking] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);

  const updJobs = (jobs ?? []).filter((j) => j.kind === "guncelleme");
  const job = updJobs.find((j) => j.status === "calisiyor" || j.status === "beklemede");
  const lastFailed = !job && !st?.staged && updJobs[0]?.status === "hata" ? updJobs[0] : null;
  const set = (v: UpdateStatus) => qc.setQueryData(qk.update, v);

  const check = async () => {
    setChecking(true);
    try {
      const s = await api.post<UpdateStatus>("/api/update/check");
      set(s);
      if (s.latest && !s.latest.newer) toast("En güncel sürümü kullanıyorsunuz", "ok");
    } catch (e) {
      toastError(e);
    } finally {
      setChecking(false);
    }
  };
  const download = async (version: string) => {
    try {
      await api.post("/api/update/download", { version });
      qc.invalidateQueries({ queryKey: qk.jobs });
    } catch (e) {
      toastError(e);
    }
  };
  const install = async (version: string) => {
    const running = (jobs ?? []).some((j) => j.status === "calisiyor" && j.kind !== "guncelleme");
    const ok = await confirmDialog(
      `Uygulama kapanacak, v${version} kurulacak ve yeniden açılacak.${running ? " Çalışan işler yarıda kalır." : ""} Vakalarınız ve ayarlarınız korunur.`,
      "Güncellemeyi kur",
    );
    if (ok) await applyUpdate().catch(toastError);
  };

  if (!st) {
    return (
      <Section title="Güncelleme">
        <Spinner />
      </Section>
    );
  }
  const latest = st.latest;
  return (
    <Section
      title="Güncelleme"
      actions={
        <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} busy={checking} onClick={check}>
          Güncellemeleri denetle
        </Button>
      }
    >
      <div className="space-y-2.5 text-[12.5px]">
        <div className="text-muted">
          Kurulu sürüm <b className="text-text">v{st.current}</b>
          {st.last_check && ` · son denetim ${fmtDateTime(st.last_check)}`}
        </div>
        {latest && !latest.newer && !st.staged && <div className="text-ok">En güncel sürümü kullanıyorsunuz.</div>}
        {/* İndirilmiş paket, uygulama yeniden açıldıktan sonra da (denetim yapılmadan) kurulabilir */}
        {st.staged && (
          <div className="flex items-center gap-2 rounded-md border border-ok/40 bg-ok/10 p-2.5">
            <span className="flex-1 text-ok">v{st.staged.version} indirildi ve doğrulandı.</span>
            <Button size="sm" variant="ghost" onClick={() => api.del<UpdateStatus>("/api/update/staged").then(set).catch(toastError)}>
              Sil
            </Button>
            {st.can_apply ? (
              <Button size="sm" variant="primary" onClick={() => install(st.staged!.version)}>
                Yeniden başlat ve kur
              </Button>
            ) : (
              <span className="text-warn">{st.reason}</span>
            )}
          </div>
        )}
        {latest?.newer && !st.staged && (
          <div className="space-y-2 rounded-md border border-accent/40 bg-accent/10 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="accent">Yeni sürüm</Badge>
              <b>{latest.title}</b>
              <span className="text-muted">
                {latest.published_at && fmtDateTime(latest.published_at)}
                {latest.asset && ` · ${Math.round(latest.asset.size / 2 ** 20)} MB`}
              </span>
            </div>
            {latest.notes && (
              <>
                <button onClick={() => setNotesOpen(!notesOpen)} className="text-[12px] text-accent cursor-pointer">
                  {notesOpen ? "Sürüm notlarını gizle" : "Sürüm notlarını göster"}
                </button>
                {notesOpen && (
                  <div className="selectable max-h-56 overflow-y-auto whitespace-pre-wrap rounded bg-panel-2 p-2 text-[12px] leading-relaxed">
                    {plain(latest.notes)}
                  </div>
                )}
              </>
            )}
            {job ? (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-accent">
                  <Spinner className="size-3.5" />
                  <span className="flex-1">{job.message ?? "Sırada"}</span>
                  <Button size="sm" variant="ghost" onClick={() => api.post(`/api/jobs/${job.id}/cancel`).catch(toastError)}>
                    İptal
                  </Button>
                </div>
                <Progress value={job.progress} />
              </div>
            ) : st.can_apply ? (
              <Button size="sm" variant="primary" icon={<Download className="size-3.5" />} disabled={!latest.asset} onClick={() => download(latest.latest)}>
                İndir ve kur
              </Button>
            ) : (
              <div className="text-warn">{st.reason}</div>
            )}
          </div>
        )}
        {lastFailed && <div className="text-danger">Son indirme başarısız: {lastFailed.message}</div>}
        {st.result && !st.result.ok && (
          <div className="text-danger">
            v{st.result.version} kurulamadı, önceki sürüm geri yüklendi: {st.result.error}
          </div>
        )}
        <Toggle
          checked={st.check_on_start}
          onChange={async (v) => {
            await save({ update: { check_on_start: v } });
            qc.invalidateQueries({ queryKey: qk.update });
          }}
          label="Açılışta güncellemeleri denetle"
          hint="Açılışta GitHub'a yalnızca son sürüm bilgisini sormak için bağlanılır; kişisel bilgi ya da kullanım verisi gönderilmez."
        />
        <p className="text-[11.5px] leading-snug text-faint">
          İndirilen paketin SHA-256 değeri yayımlanan değerle karşılaştırılır. Kurulumda yalnızca program dosyaları değişir; data klasöründeki vakalar ve ayarlar korunur. Sorun olursa önceki sürüm otomatik geri yüklenir.
        </p>
      </div>
    </Section>
  );
}
