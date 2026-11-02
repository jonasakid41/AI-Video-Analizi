import { useQueryClient } from "@tanstack/react-query";
import { Bookmark, CheckCircle2, CircleSlash, Crosshair, Film, Sparkles } from "lucide-react";
import { api, fileUrl, frameUrl } from "../lib/api";
import { fmtPct } from "../lib/format";
import { qk } from "../lib/hooks";
import { fmtIso, fmtMedia } from "../lib/time";
import type { ResultItem } from "../lib/types";
import { toast, toastError, useUI } from "../store";
import { Badge, IconButton } from "./ui";

export default function ResultCard({ r, caseId, label, onLabel }: { r: ResultItem; caseId: number; label?: boolean; onLabel?: (v: boolean | null) => void }) {
  const seek = useUI((s) => s.seek);
  const qc = useQueryClient();
  const v = r.verdict;
  const img = r.thumb ? fileUrl(r.thumb) : frameUrl(r.evidence_id, r.t, 320, null);
  const when = r.real_t ? fmtIso(r.real_t) : `${fmtMedia(r.t)} (video içi)`;
  // Yerel adayla çakışan yapay zekâ bulgusu: gerekçesi kartta görünsün (yapay zekâ adaylarında zaten başlıkta)
  const aiReason = r.cls_tr?.startsWith("yapay zekâ") ? null : r.reasons?.find((x) => x.startsWith("yapay zekâ"));

  const addFinding = async () => {
    try {
      await api.post(`/api/cases/${caseId}/findings`, {
        evidence_id: r.evidence_id,
        t: r.t,
        title: `${r.cls_tr ?? "Görüntü"}${r.plate ? " · " + r.plate : ""} — ${r.real_t ? fmtIso(r.real_t, false) : fmtMedia(r.t)}`,
        note: [v?.explanation, r.color_text && `Renk: ${r.color_text}`, r.video_analysis?.text].filter(Boolean).join("\n"),
        source: v ? "ai" : "yerel",
        confidence: v?.confidence ?? null,
        box: r.box,
        data: { result_id: r.id, plate: v?.plate ?? r.plate },
      });
      qc.invalidateQueries({ queryKey: qk.findings(caseId) });
      toast("Bulgulara eklendi", "ok");
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <div className={`flex gap-2.5 rounded-lg border p-2 ${v?.match ? "border-ok/40 bg-ok/5" : v ? "border-line bg-panel-2/60" : "border-line bg-panel-2"}`}>
      <button
        className="relative h-[68px] w-[92px] shrink-0 overflow-hidden rounded bg-black cursor-pointer"
        onClick={() => seek(r.evidence_id, r.t, r.box)}
        title="Bu ana git"
      >
        <img src={img} alt="" loading="lazy" className="size-full object-cover" />
        {r.kind === "kare" && <Film className="absolute right-1 top-1 size-3 text-white/80" />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[12.5px] font-semibold tabular">{when}</span>
          <span className="flex-1" />
          {v ? (
            v.match ? (
              <Badge tone="ok">
                <CheckCircle2 className="size-3" />
                {fmtPct(v.confidence)}
              </Badge>
            ) : (
              <Badge>
                <CircleSlash className="size-3" />
                uymuyor
              </Badge>
            )
          ) : (
            <Badge title="Yerel analiz puanı">aday</Badge>
          )}
        </div>
        <div className="truncate text-[11.5px] text-muted" title={r.video}>
          {r.camera || r.video}
          {r.cls_tr && ` · ${r.cls_tr}`}
          {r.color_text && ` · ${r.color_text}`}
        </div>
        {aiReason && (
          <div className="flex items-center gap-1 truncate text-[11.5px] text-accent" title={aiReason}>
            <Sparkles className="size-3 shrink-0" />
            {aiReason}
          </div>
        )}
        {(v?.plate || r.plate) && <div className="font-mono text-[12px] text-warn">{v?.plate || r.plate}</div>}
        {v?.explanation && <div className="mt-0.5 line-clamp-3 text-[12px] leading-snug">{v.explanation}</div>}
        {r.video_analysis?.text && (
          <div className="mt-1 rounded bg-panel-3 px-2 py-1 text-[11.5px] leading-snug">
            <span className="text-accent">Video analizi: </span>
            {r.video_analysis.text}
          </div>
        )}
        {r.video_analysis?.error && <div className="mt-1 text-[11.5px] text-danger">{r.video_analysis.error}</div>}
      </div>
      <div className="flex flex-col">
        <IconButton title="Bu ana git" className="size-7" onClick={() => seek(r.evidence_id, r.t, r.box)}>
          <Crosshair className="size-3.5" />
        </IconButton>
        <IconButton title="Bulgulara ekle" className="size-7" onClick={addFinding}>
          <Bookmark className="size-3.5" />
        </IconButton>
        {onLabel && (
          <div className="mt-auto flex flex-col gap-0.5" title="Doğru cevabı işaretleyin (model karşılaştırması için)">
            <button
              onClick={() => onLabel(label === true ? null : true)}
              className={`rounded px-1 text-[11px] font-bold cursor-pointer ${label === true ? "bg-ok/25 text-ok" : "text-faint hover:text-ok"}`}
              aria-label="Doğru sonuç"
            >
              ✓
            </button>
            <button
              onClick={() => onLabel(label === false ? null : false)}
              className={`rounded px-1 text-[11px] font-bold cursor-pointer ${label === false ? "bg-danger/25 text-danger" : "text-faint hover:text-danger"}`}
              aria-label="Yanlış sonuç"
            >
              ✗
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
