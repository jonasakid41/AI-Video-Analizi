import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, ChevronDown, ChevronRight, MessageSquareText, Send, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { CLASS_TR, fmtUsd, TARGET_TR } from "../../lib/format";
import { qk, useJobs, useQueries, useQueryRow, useRois, useSettings } from "../../lib/hooks";
import type { Evidence, QueryRow } from "../../lib/types";
import { toastError, useUI } from "../../store";
import { EvalDialog, EvalResults } from "../Evaluation";
import ResultCard from "../ResultCard";
import { Badge, Button, Empty, IconButton, Progress, Spinner } from "../ui";

const MODES = [
  { id: "hizli", label: "Hızlı", hint: "Yalnızca yerel analiz. İnternet ve anahtar gerekmez, ücretsiz." },
  { id: "dogrula", label: "Doğrulamalı", hint: "Yerel adaylar seçtiğiniz görsel modele doğrulatılır." },
  { id: "derin", label: "Derin", hint: "Ek olarak en iyi adayların çevresindeki kısa video kesiti modele izletilir (hareket/eylem soruları için)." },
] as const;

const EXAMPLES = [
  "14:00–15:00 arası kırmızı üstlü biri geçti mi?",
  "34 ABC 123 plakalı araç ne zaman geldi?",
  "Beyaz bir kamyonet görüldü mü?",
  "Sırt çantalı kişileri bul",
];

export default function AskPanel({ caseId, ev }: { caseId: number; ev?: Evidence }) {
  const { data: settings } = useSettings();
  const { data: queries } = useQueries(caseId);
  const { data: rois } = useRois(ev?.id ?? null);
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<string>("dogrula");
  const [scope, setScope] = useState<string>("hepsi");
  const [estimate, setEstimate] = useState<{ cost_usd: number; candidates: number; free: boolean; notes: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const keyMissing = settings && !settings.ai_ready;
  useEffect(() => {
    if (keyMissing) setMode("hizli");
  }, [keyMissing]);
  useEffect(() => {
    if (queries?.length && openId === null) setOpenId(queries[0].id);
  }, [queries, openId]);

  const body = () => ({
    question: text.trim(),
    mode,
    evidence_ids: scope === "bu" && ev ? [ev.id] : undefined,
    roi_id: scope.startsWith("roi:") ? Number(scope.slice(4)) : undefined,
  });

  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ query_id: number }>(`/api/cases/${caseId}/queries`, body());
      setText("");
      setEstimate(null);
      setOpenId(r.query_id);
      qc.invalidateQueries({ queryKey: qk.queries(caseId) });
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const ask = async () => {
    if (text.trim().length < 3) return;
    if (mode === "hizli") return run();
    setBusy(true);
    try {
      const est = await api.post<{ cost_usd: number; candidates: number; free: boolean; notes: string[] }>(`/api/cases/${caseId}/queries/estimate`, body());
      setBusy(false);
      if (est.cost_usd > 0.0005 && !est.free) setEstimate(est);
      else await run();
    } catch (e) {
      setBusy(false);
      toastError(e);
    }
  };

  return (
    <div className="flex flex-col">
      <div className="space-y-2.5 border-b border-line p-3">
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setEstimate(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || !e.shiftKey)) {
              e.preventDefault();
              ask();
            }
          }}
          rows={3}
          placeholder="Videolar hakkında Türkçe bir soru yazın… (Enter: gönder, Shift+Enter: yeni satır)"
          className="w-full resize-none rounded-lg border border-line-2 bg-panel-2 px-3 py-2 leading-relaxed outline-none placeholder:text-faint focus:border-accent/70"
        />
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-line-2 bg-panel-2 p-0.5">
            {MODES.map((m) => (
              <button
                key={m.id}
                title={m.hint}
                disabled={m.id !== "hizli" && !!keyMissing}
                onClick={() => setMode(m.id)}
                className={`rounded px-2 py-1 text-[12px] font-medium cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 ${mode === m.id ? "bg-accent-strong text-white" : "text-muted hover:text-text"}`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <select value={scope} onChange={(e) => setScope(e.target.value)} className="h-7.5 min-w-0 flex-1 rounded-md border border-line-2 bg-panel-2 px-1.5 text-[12px] cursor-pointer">
            <option value="hepsi">Tüm videolar</option>
            {ev && <option value="bu">Yalnızca bu video</option>}
            {rois?.map((r) => (
              <option key={r.id} value={`roi:${r.id}`}>
                Alan: {r.name}
              </option>
            ))}
          </select>
          <Button variant="primary" size="sm" onClick={ask} busy={busy} disabled={text.trim().length < 3} icon={<Send className="size-3.5" />}>
            Sor
          </Button>
        </div>
        {keyMissing && (
          <div className="text-[11.5px] text-warn">
            {settings?.ai_source === "cli"
              ? "Seçili CLI aracı bu bilgisayarda bulunamadı; yalnızca yerel arama yapılabilir. Ayarlar > Yapay zekâ'dan aracı yeniden tarayın."
              : "Yapay zekâ bağlı değil; yalnızca yerel arama yapılabilir. Ayarlar'dan OpenRouter anahtarı girin ya da bilgisayarınızdaki Claude Code / Codex / Gemini CLI aracını seçin."}
          </div>
        )}
        {estimate && (
          <div className="flex items-center gap-2 rounded-md border border-warn/40 bg-warn/10 px-2.5 py-2 text-[12.5px]">
            <span className="flex-1">
              {estimate.candidates} aday modele gönderilecek. Tahmini maliyet <b>{fmtUsd(estimate.cost_usd)}</b>.
            </span>
            <Button size="sm" variant="ghost" onClick={() => setEstimate(null)}>
              Vazgeç
            </Button>
            <Button size="sm" variant="primary" onClick={run} busy={busy}>
              Devam
            </Button>
          </div>
        )}
      </div>

      {!queries?.length ? (
        <div className="p-3">
          <Empty icon={<MessageSquareText className="size-8" />} title="Henüz soru sorulmadı">
            Saat, renk, nesne türü, plaka ya da çizdiğiniz bir alanla ilgili soru sorabilirsiniz.
          </Empty>
          <div className="flex flex-wrap justify-center gap-1.5">
            {EXAMPLES.map((x) => (
              <button key={x} onClick={() => setText(x)} className="rounded-full border border-line-2 px-2.5 py-1 text-[12px] text-muted hover:border-accent/50 hover:text-text cursor-pointer">
                {x}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="divide-y divide-line">
          {queries.map((q) => (
            <QueryItem key={q.id} q={q} caseId={caseId} open={openId === q.id} onToggle={() => setOpenId(openId === q.id ? -1 : q.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function QueryItem({ q, caseId, open, onToggle }: { q: QueryRow; caseId: number; open: boolean; onToggle: () => void }) {
  const { data: full } = useQueryRow(open ? q.id : null);
  const { data: jobs } = useJobs();
  const setMarkers = useUI((s) => s.setMarkers);
  const qc = useQueryClient();
  const [onlyMatch, setOnlyMatch] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);
  const { data: settings } = useSettings();
  const canCompare = !!settings?.ai_ready;
  const labels = full?.labels ?? {};
  const labeledCount = Object.keys(labels).length;
  const setLabel = async (id: string, v: boolean | null) => {
    try {
      const r = await api.put<{ labels: Record<string, boolean> }>(`/api/queries/${q.id}/labels`, { labels: { [id]: v } });
      qc.setQueryData<QueryRow>(qk.query(q.id), (old) => (old ? { ...old, labels: r.labels } : old));
    } catch (e) {
      toastError(e);
    }
  };
  const job = jobs?.find((j) => j.kind === "query" && (j.params as any)?.query_id === q.id && (j.status === "calisiyor" || j.status === "beklemede"));
  const running = q.status === "calisiyor" || q.status === "beklemede";
  const results = useMemo(() => full?.results ?? [], [full]);
  const verified = results.some((r) => r.verdict);
  const shown = onlyMatch ? results.filter((r) => r.verdict?.match) : results;

  useEffect(() => {
    if (!open || !results.length) return;
    setMarkers(results.map((r) => ({ evidence_id: r.evidence_id, t: r.t, color: r.verdict?.match ? "#34d399" : "#f59e0b", label: r.id })));
  }, [open, results, setMarkers]);

  const plan = full?.plan;
  const mode = { hizli: "Hızlı", dogrula: "Doğrulamalı", derin: "Derin" }[q.options?.mode ?? "dogrula"];

  return (
    <div className="p-3">
      <div className="flex cursor-pointer items-start gap-2" onClick={onToggle}>
        {open ? <ChevronDown className="mt-0.5 size-4 text-muted" /> : <ChevronRight className="mt-0.5 size-4 text-muted" />}
        <div className="min-w-0 flex-1">
          <div className="font-medium leading-snug">{q.question}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
            <Badge>{mode}</Badge>
            {q.status === "hata" && <Badge tone="danger">hata</Badge>}
            {q.cost > 0 && <span>{fmtUsd(q.cost)}</span>}
          </div>
        </div>
        <IconButton
          title="Sil"
          className="size-7"
          onClick={async (e) => {
            e.stopPropagation();
            await api.del(`/api/queries/${q.id}`).catch(toastError);
            qc.invalidateQueries({ queryKey: qk.queries(caseId) });
          }}
        >
          <Trash2 className="size-3.5" />
        </IconButton>
      </div>
      {running && (
        <div className="ml-6 mt-2 space-y-1">
          <div className="flex items-center gap-2 text-[12px] text-accent">
            <Spinner className="size-3.5" />
            {job?.message ?? "Sırada"}
          </div>
          <Progress value={job?.progress ?? 0} />
        </div>
      )}
      {open && !running && (
        <div className="ml-6 mt-2.5 space-y-2.5">
          {q.status === "hata" && <div className="rounded-md bg-danger/10 px-2.5 py-2 text-[12.5px] text-danger">{q.error}</div>}
          {full?.answer && <div className="selectable whitespace-pre-wrap rounded-lg bg-panel-2 px-3 py-2.5 leading-relaxed">{full.answer}</div>}
          {plan && (
            <div className="flex flex-wrap gap-1 text-[11px]">
              {(plan.time_from || plan.time_to) && <Badge tone="accent">saat {plan.time_from ?? "…"}–{plan.time_to ?? "…"}</Badge>}
              {(plan.classes ?? []).map((c) => (
                <Badge key={c}>{CLASS_TR[c] ?? c}</Badge>
              ))}
              {(plan.colors ?? []).map((c, i) => (
                <Badge key={i}>
                  {c.color}
                  {TARGET_TR[c.target] ? ` ${TARGET_TR[c.target]}` : ""}
                </Badge>
              ))}
              {plan.plate && <Badge tone="warn">plaka {plan.plate}</Badge>}
            </div>
          )}
          {full?.options?.notes?.map((n, i) => (
            <div key={i} className="text-[11.5px] text-warn">
              {n}
            </div>
          ))}
          {results.length > 0 && (
            <div className="flex items-center justify-between text-[12px] text-muted">
              <span>
                {results.length} sonuç{verified && ` · ${results.filter((r) => r.verdict?.match).length} eşleşme`}
              </span>
              {verified && (
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" checked={onlyMatch} onChange={(e) => setOnlyMatch(e.target.checked)} />
                  yalnızca eşleşenler
                </label>
              )}
            </div>
          )}
          {results.length > 0 && q.status === "tamamlandi" && (
            <div className="flex items-center gap-2 rounded-md border border-line bg-panel-2/60 px-2.5 py-1.5 text-[12px] text-muted">
              <span className="flex-1">
                {labeledCount ? `${labeledCount} sonuç işaretli` : "Doğru sonuçları ✓ / ✗ ile işaretleyip modelleri karşılaştırabilirsiniz"}
              </span>
              <Button size="sm" variant="subtle" icon={<BarChart3 className="size-3.5" />} disabled={!canCompare} title={canCompare ? "" : "Yapay zekâ bağlantısı gerekir (API anahtarı ya da CLI aracı)"} onClick={() => setEvalOpen(true)}>
                Modelleri karşılaştır
              </Button>
            </div>
          )}
          <EvalResults queryId={q.id} />
          <div className="space-y-1.5">
            {shown.map((r) => (
              <ResultCard key={r.id} r={r} caseId={caseId} label={labels[r.id]} onLabel={(v) => setLabel(r.id, v)} />
            ))}
          </div>
          <EvalDialog queryId={q.id} labeledCount={labeledCount} open={evalOpen} onClose={() => setEvalOpen(false)} />
        </div>
      )}
    </div>
  );
}
