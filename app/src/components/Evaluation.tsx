import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, Check, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtPct, fmtUsd } from "../lib/format";
import { qk, useCatalog, useEvaluations, useJobs, useSettings } from "../lib/hooks";
import type { Evaluation, Settings } from "../lib/types";
import { toast, toastError } from "../store";
import { Badge, Button, inputCls, Modal, Progress, Spinner } from "./ui";

const MAX = 5;

/** Aynı adayları birden çok görsel modele doğrulatıp karşılaştırır. */
export function EvalDialog({ queryId, labeledCount, open, onClose }: { queryId: number; labeledCount: number; open: boolean; onClose: () => void }) {
  const { data: settings } = useSettings();
  const { data: catalog, isLoading } = useCatalog(open);
  const qc = useQueryClient();
  const [sel, setSel] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [est, setEst] = useState<{ candidates: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const vision = useMemo(() => (catalog?.models ?? []).filter((m) => m.image), [catalog]);

  // Varsayılan seçim: mevcut doğrulayıcı + en ucuz ücretsiz + en ucuz ücretli (JSON destekli)
  useEffect(() => {
    if (!open || !vision.length || sel.length) return;
    const pick = new Set<string>();
    if (settings?.ai.roles.verifier) pick.add(settings.ai.roles.verifier);
    const structured = vision.filter((m) => m.structured);
    const free = structured.find((m) => m.free);
    const paid = [...structured].filter((m) => !m.free).sort((a, b) => a.price_in_m - b.price_in_m)[0];
    if (free) pick.add(free.id);
    if (paid) pick.add(paid.id);
    setSel([...pick].slice(0, 3));
  }, [open, vision, settings, sel.length]);

  useEffect(() => {
    if (!open || !sel.length) return setEst(null);
    const h = setTimeout(() => {
      api.post<{ candidates: number; total: number }>(`/api/queries/${queryId}/evaluate`, { models: sel, dry_run: true }).then(setEst).catch(() => setEst(null));
    }, 300);
    return () => clearTimeout(h);
  }, [open, sel, queryId]);

  const list = useMemo(() => {
    const ql = q.toLowerCase();
    return vision.filter((m) => sel.includes(m.id) || !ql || m.id.toLowerCase().includes(ql) || m.name.toLowerCase().includes(ql)).slice(0, 150);
  }, [vision, q, sel]);

  const toggle = (id: string) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= MAX ? s : [...s, id]));

  const run = async () => {
    setBusy(true);
    try {
      await api.post(`/api/queries/${queryId}/evaluate`, { models: sel });
      qc.invalidateQueries({ queryKey: ["evals", queryId] });
      toast("Karşılaştırma başladı (İşler menüsünden izleyebilirsiniz)");
      onClose();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Modelleri karşılaştır"
      width="max-w-2xl"
      footer={
        <>
          <span className="mr-auto self-center text-[12.5px] text-muted">
            {est ? `${est.candidates} aday × ${sel.length} model · tahmini ${fmtUsd(est.total)}` : sel.length ? "Tahmin hesaplanıyor…" : "Model seçin"}
          </span>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" onClick={run} busy={busy} disabled={!sel.length}>
            Karşılaştır
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-[12.5px] leading-relaxed text-muted">
          Bu sorunun yerel adayları seçtiğiniz modellere aynı şekilde doğrulatılır. {labeledCount > 0 ? (
            <>İşaretlediğiniz <b className="text-text">{labeledCount}</b> sonuç doğru cevap kabul edilir; her model için isabet ve duyarlılık hesaplanır.</>
          ) : (
            <span className="text-warn">Henüz sonuç işaretlemediniz; yalnızca eşleşme sayısı, maliyet ve süre karşılaştırılır. Sonuç kartlarındaki ✓ / ✗ ile doğru cevabı işaretleyin.</span>
          )}
        </p>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-faint" />
          <input className={`${inputCls} pl-8`} placeholder="Model ara" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="max-h-80 overflow-y-auto rounded-md border border-line">
            {list.map((m) => {
              const on = sel.includes(m.id);
              return (
                <button key={m.id} onClick={() => toggle(m.id)} className={`flex w-full items-center gap-2.5 border-b border-line px-2.5 py-1.5 text-left last:border-0 cursor-pointer ${on ? "bg-accent/10" : "hover:bg-panel-2"}`}>
                  <span className={`flex size-4 shrink-0 items-center justify-center rounded border ${on ? "border-accent bg-accent-strong" : "border-line-2"}`}>{on && <Check className="size-3 text-white" />}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px]">{m.name}</div>
                    <div className="truncate font-mono text-[11px] text-faint">{m.id}</div>
                  </div>
                  {m.id === settings?.ai.roles.verifier && <Badge tone="accent">şu an</Badge>}
                  {m.free ? <Badge tone="ok">ücretsiz</Badge> : <span className="text-[11px] text-muted tabular">${m.price_in_m}/M</span>}
                </button>
              );
            })}
          </div>
        )}
        <div className="text-[11.5px] text-faint">En fazla {MAX} model seçilebilir.</div>
      </div>
    </Modal>
  );
}

export function EvalResults({ queryId }: { queryId: number }) {
  const { data: evals } = useEvaluations(queryId);
  const { data: jobs } = useJobs();
  const { data: settings } = useSettings();
  const qc = useQueryClient();
  if (!evals?.length) return null;
  const useModel = async (m: string) => {
    if (!settings) return;
    try {
      const next = await api.put<Settings>("/api/settings", { ai: { roles: { ...settings.ai.roles, verifier: m } } });
      qc.setQueryData(qk.settings, next);
      toast(`Kare doğrulama modeli: ${m}`, "ok");
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <div className="space-y-2">
      {evals.map((ev: Evaluation) => {
        const job = jobs?.find((j) => j.kind === "evaluate" && (j.params as any)?.evaluation_id === ev.id && (j.status === "calisiyor" || j.status === "beklemede"));
        const labeled = ev.results.some((r) => r.precision !== undefined);
        const best = labeled
          ? [...ev.results].sort((a, b) => ((b.precision ?? 0) + (b.recall ?? 0)) - ((a.precision ?? 0) + (a.recall ?? 0)) || a.cost - b.cost)[0]?.model
          : undefined;
        return (
          <div key={ev.id} className="rounded-lg border border-line bg-panel-2 p-2.5">
            <div className="mb-1.5 flex items-center gap-2 text-[12px]">
              <BarChart3 className="size-3.5 text-accent" />
              <span className="font-medium">Model karşılaştırması</span>
              {ev.status === "hata" && <Badge tone="danger">hata</Badge>}
              {job && <span className="text-accent">{job.message}</span>}
            </div>
            {job && <Progress value={job.progress} className="mb-2" />}
            {ev.error && <div className="text-[12px] text-danger">{ev.error}</div>}
            {ev.results.length > 0 && (
              <table className="w-full text-[11.5px] tabular">
                <thead className="text-faint">
                  <tr className="text-left">
                    <th className="pb-1 font-medium">Model</th>
                    <th className="pb-1 text-right font-medium" title="Modelin 'eşleşti' dediği aday sayısı">Eşleşen</th>
                    {labeled && <th className="pb-1 text-right font-medium" title="Eşleşti dediklerinin ne kadarı gerçekten doğru">İsabet</th>}
                    {labeled && <th className="pb-1 text-right font-medium" title="Doğru sonuçların ne kadarını buldu">Duyarlılık</th>}
                    <th className="pb-1 text-right font-medium">Maliyet</th>
                    <th className="pb-1 text-right font-medium">Süre</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {ev.results.map((r) => (
                    <tr key={r.model} className="border-t border-line align-middle">
                      <td className="max-w-[130px] truncate py-1 font-mono" title={r.model + (r.errors.length ? `\n${r.errors.join("\n")}` : "")}>
                        {r.model === best && <span className="mr-1 text-ok">★</span>}
                        {r.model.split("/").pop()}
                        {r.errors.length > 0 && <span className="ml-1 text-danger">!</span>}
                      </td>
                      <td className="text-right">
                        {r.matched}/{r.answered}
                      </td>
                      {labeled && <td className="text-right">{fmtPct(r.precision)}</td>}
                      {labeled && <td className="text-right">{fmtPct(r.recall)}</td>}
                      <td className="text-right">{fmtUsd(r.cost)}</td>
                      <td className="text-right">{r.seconds.toFixed(0)} sn</td>
                      <td className="text-right">
                        {settings?.ai.roles.verifier === r.model ? (
                          <Badge tone="accent">kullanılıyor</Badge>
                        ) : (
                          <button className="text-accent hover:underline cursor-pointer" onClick={() => useModel(r.model)}>
                            kullan
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}
