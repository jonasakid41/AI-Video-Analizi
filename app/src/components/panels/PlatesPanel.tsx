import { Car, Search } from "lucide-react";
import { useState } from "react";
import { api, fileUrl } from "../../lib/api";
import { fmtPct } from "../../lib/format";
import { useEvidenceList, usePlates } from "../../lib/hooks";
import { fmtIso, fmtMedia } from "../../lib/time";
import type { Evidence, Track } from "../../lib/types";
import { toastError, useUI } from "../../store";
import { Badge, Button, Empty, inputCls, Section, Spinner } from "../ui";

export default function PlatesPanel({ caseId, ev }: { caseId: number; ev?: Evidence }) {
  const { data: plates, isLoading } = usePlates(ev);
  const { data: evs } = useEvidenceList(caseId);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Track[] | null>(null);
  const [busy, setBusy] = useState(false);
  const names = new Map((evs ?? []).map((e) => [e.id, e.camera || e.original_name]));

  const search = async () => {
    if (q.trim().length < 2) return;
    setBusy(true);
    try {
      setHits(await api.get<Track[]>(`/api/cases/${caseId}/plate-search`, { q: q.trim() }));
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 p-3">
      <div className="flex gap-2">
        <input
          className={`${inputCls} font-mono uppercase`}
          placeholder="Plaka ya da bir kısmı (ör. 34 ABC, 123)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <Button variant="primary" onClick={search} busy={busy} icon={<Search className="size-4" />}>
          Ara
        </Button>
      </div>
      {hits && (
        <Section title={`Vaka genelinde "${q}"`} actions={<button className="text-[12px] text-muted hover:text-text cursor-pointer" onClick={() => setHits(null)}>kapat</button>}>
          {hits.length ? hits.map((t) => <PlateRow key={t.id} t={t} video={names.get(t.evidence_id)} />) : <div className="text-[12.5px] text-muted">Eşleşen plaka yok.</div>}
        </Section>
      )}
      <Section title={ev ? "Bu videodaki plakalar" : "Plakalar"}>
        {!ev ? (
          <div className="text-muted">Bir video seçin.</div>
        ) : isLoading ? (
          <Spinner />
        ) : !plates?.length ? (
          <Empty icon={<Car className="size-8" />} title="Okunan plaka yok">
            Plakalar, tespit edilen araçların (genişliği en az ~100 piksel) alt kısmında okunur. Uzak ya da bulanık plakalar için kareyi “İyileştir” sekmesinde büyütüp soru sorabilirsiniz.
          </Empty>
        ) : (
          plates.map((t) => <PlateRow key={t.id} t={t} />)
        )}
      </Section>
    </div>
  );
}

function PlateRow({ t, video }: { t: Track; video?: string }) {
  const seek = useUI((s) => s.seek);
  return (
    <button onClick={() => seek(t.evidence_id, t.t0)} className="flex w-full items-center gap-3 rounded-lg border border-line bg-panel-2 p-2 text-left hover:border-accent/50 cursor-pointer">
      {t.thumb ? <img src={fileUrl(t.thumb)} alt="" className="h-12 w-16 rounded object-cover" /> : <div className="h-12 w-16 rounded bg-panel-3" />}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="rounded border border-white/70 bg-white px-1.5 font-mono text-[13px] font-bold tracking-wide text-black">{t.plate}</span>
          {t.similarity !== undefined && <Badge tone="accent">%{Math.round(t.similarity * 100)} benzer</Badge>}
          {t.plate_conf !== null && <span className="text-[11px] text-muted">güven {fmtPct(t.plate_conf)}</span>}
        </div>
        <div className="mt-0.5 truncate text-[11.5px] text-muted">
          {t.cls_tr} {t.color_text && `· ${t.color_text}`} {video && `· ${video}`}
        </div>
      </div>
      <span className="text-[12px] tabular text-muted">{t.real_t0 ? fmtIso(t.real_t0, false) : fmtMedia(t.t0)}</span>
    </button>
  );
}
