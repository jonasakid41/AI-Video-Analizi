import { Crosshair, ImageUp, ScanFace, Search } from "lucide-react";
import { useState } from "react";
import { api, fileUrl, pickFiles } from "../../lib/api";
import { usePeople, useEvidenceList } from "../../lib/hooks";
import { fmtIso, fmtMedia } from "../../lib/time";
import type { Evidence, Face } from "../../lib/types";
import { toastError, useUI } from "../../store";
import { Badge, Button, Empty, IconButton, Section, Spinner } from "../ui";

export default function PeoplePanel({ caseId }: { caseId: number; ev?: Evidence }) {
  const { data: people, isLoading } = usePeople(caseId);
  const { data: evs } = useEvidenceList(caseId);
  const seek = useUI((s) => s.seek);
  const [threshold, setThreshold] = useState(0.36);
  const [search, setSearch] = useState<{ label: string; matches: Face[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const names = new Map((evs ?? []).map((e) => [e.id, e.camera || e.original_name]));

  const run = async (body: { face_id?: number; image_path?: string }, label: string) => {
    setBusy(true);
    try {
      const r = await api.post<{ matches: Face[] }>(`/api/cases/${caseId}/face-search`, { ...body, threshold });
      setSearch({ label, matches: r.matches });
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 p-3">
      <div className="rounded-lg border border-line bg-panel-2 p-3">
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            icon={<ImageUp className="size-3.5" />}
            busy={busy}
            onClick={async () => {
              const [p] = await pickFiles("Aranacak kişinin fotoğrafını seçin", true);
              if (p) run({ image_path: p }, "Seçilen fotoğraf");
            }}
          >
            Fotoğrafla ara
          </Button>
          <label className="flex flex-1 items-center gap-2 text-[12px] text-muted" title="Düşük eşik daha çok (ama daha az kesin) sonuç verir">
            Eşik
            <input type="range" min={0.3} max={0.6} step={0.02} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} className="flex-1" />
            <span className="w-8 tabular">{threshold.toFixed(2)}</span>
          </label>
        </div>
        <p className="mt-2 text-[11.5px] leading-snug text-faint">
          Yüz benzerliği bir soruşturma ipucudur, kimlik tespiti değildir. Düşük çözünürlük, açı ve ışık sonuçları etkiler; her eşleşmeyi gözle doğrulayın.
        </p>
      </div>

      {search && (
        <Section title={`Arama sonuçları — ${search.label}`} actions={<button className="text-[12px] text-muted hover:text-text cursor-pointer" onClick={() => setSearch(null)}>kapat</button>}>
          {!search.matches.length ? (
            <div className="text-[12.5px] text-muted">Eşleşme bulunamadı. Eşiği düşürmeyi deneyin.</div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {search.matches.map((m) => (
                <button key={m.id} onClick={() => seek(m.evidence_id, m.t, m.box)} className="overflow-hidden rounded-md border border-line bg-panel-2 text-left hover:border-accent/50 cursor-pointer">
                  <img src={fileUrl(m.thumb)} alt="" className="aspect-square w-full object-cover" />
                  <div className="p-1.5 text-[11px]">
                    <div className="flex items-center justify-between">
                      <Badge tone={m.strength === "güçlü" ? "ok" : "warn"}>%{Math.round((m.similarity ?? 0) * 100)}</Badge>
                    </div>
                    <div className="mt-0.5 truncate text-muted tabular">{m.real_t ? fmtIso(m.real_t, false) : fmtMedia(m.t)}</div>
                    <div className="truncate text-faint">{names.get(m.evidence_id)}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Section>
      )}

      <Section title="Görülen kişiler (yüz gruplarına göre)">
        {isLoading ? (
          <Spinner />
        ) : !people?.length ? (
          <Empty icon={<ScanFace className="size-8" />} title="Yüz bulunamadı">
            Analiz, kişi kutularının üst kısmında yeterli büyüklükte (en az ~20 piksel) yüz aradığında burada listelenir.
          </Empty>
        ) : (
          <div className="space-y-2">
            {people.map((p) => (
              <div key={p.person} className="rounded-lg border border-line bg-panel-2 p-2">
                <div className="flex gap-2.5">
                  <img src={fileUrl(p.best.thumb)} alt="" className="size-16 rounded object-cover" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium">Kişi {p.person + 1}</span>
                      <Badge>{p.face_count} görüntü</Badge>
                      <span className="flex-1" />
                      <IconButton title="Bu yüzle tüm vakada ara" className="size-7" onClick={() => run({ face_id: p.best.id }, `Kişi ${p.person + 1}`)}>
                        <Search className="size-3.5" />
                      </IconButton>
                    </div>
                    <div className="mt-1 space-y-0.5">
                      {p.appearances.map((a, i) => (
                        <button key={i} onClick={() => seek(a.evidence_id, a.t0)} className="flex w-full items-center gap-1.5 text-left text-[11.5px] text-muted hover:text-text cursor-pointer">
                          <Crosshair className="size-3" />
                          <span className="truncate">{names.get(a.evidence_id)}</span>
                          <span className="ml-auto tabular">
                            {a.real_t0 ? fmtIso(a.real_t0, false) : fmtMedia(a.t0)}
                            {a.t1 > a.t0 + 1 && `–${a.real_t1 ? fmtIso(a.real_t1, false) : fmtMedia(a.t1)}`}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                {p.faces.length > 1 && (
                  <div className="mt-2 flex gap-1 overflow-x-auto">
                    {p.faces.slice(1, 10).map((f) => (
                      <button key={f.id} onClick={() => seek(f.evidence_id, f.t, f.box)} className="shrink-0 cursor-pointer" title={f.real_t ? fmtIso(f.real_t) : fmtMedia(f.t)}>
                        <img src={fileUrl(f.thumb)} alt="" className="size-10 rounded object-cover opacity-85 hover:opacity-100" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
