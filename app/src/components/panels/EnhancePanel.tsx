import { AlertTriangle, FolderOpen, Maximize2, SquareDashedMousePointer, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, fileUrl, frameUrl, openFolder } from "../../lib/api";
import { useDebounced, useJob, useMapping } from "../../lib/hooks";
import { fmtClock, fmtMedia } from "../../lib/time";
import type { Evidence } from "../../lib/types";
import { toastError, useUI } from "../../store";
import { Badge, Button, Empty, Modal, Progress, Section } from "../ui";

type Op = { id: string; label: string; hint: string; param?: { key: string; label: string; min: number; max: number; step: number; def: number } };

const OPS: Op[] = [
  { id: "coklu_kare", label: "Çok kareli birleştirme", hint: "Komşu kareleri hizalayıp ortalar. Durağan nesnelerde (park etmiş araç plakası) gerçek bilgiyle gürültüyü azaltır.", param: { key: "kare", label: "Kare", min: 3, max: 15, step: 2, def: 7 } },
  { id: "deinterlace", label: "Satır birleştirme", hint: "Taraklanma (interlace) çizgilerini giderir.", },
  { id: "gurultu", label: "Gürültü azaltma", hint: "Gece çekimlerindeki kumlanmayı azaltır.", param: { key: "siddet", label: "Şiddet", min: 2, max: 20, step: 1, def: 7 } },
  { id: "clahe", label: "Yerel kontrast (CLAHE)", hint: "Karanlık ve parlak bölgelerdeki ayrıntıyı ortaya çıkarır.", param: { key: "siddet", label: "Şiddet", min: 0.5, max: 6, step: 0.5, def: 2.5 } },
  { id: "gama", label: "Gama", hint: "Karanlık görüntüyü aydınlatır (>1).", param: { key: "deger", label: "Değer", min: 0.4, max: 3, step: 0.1, def: 1.4 } },
  { id: "keskinlestir", label: "Keskinleştirme", hint: "Kenarları belirginleştirir.", param: { key: "miktar", label: "Miktar", min: 0.2, max: 2.5, step: 0.1, def: 1 } },
  { id: "gri", label: "Gri ton", hint: "Renk gürültüsünü kaldırır; plaka/yazı okumayı kolaylaştırabilir." },
];

type Preset = { id: string; label: string; hint: string; enabled: Record<string, boolean>; params: Record<string, number> };

const PRESETS: Preset[] = [
  { id: "genel", label: "Genel", hint: "Yerel kontrast ve keskinleştirme.", enabled: { clahe: true, keskinlestir: true }, params: {} },
  {
    id: "gece", label: "Gece / IR", hint: "Siyah-beyaz ve karanlık kayıtlar: gürültü azaltma, güçlü yerel kontrast, aydınlatma; renk gürültüsü kaldırılır.",
    enabled: { gurultu: true, clahe: true, gama: true, keskinlestir: true, gri: true }, params: { gurultu: 9, clahe: 3.5, gama: 1.3, keskinlestir: 0.8 },
  },
  {
    id: "plaka", label: "Plaka / yazı", hint: "Durağan araç plakası ya da yazı: çok kareli birleştirme, kontrast, gri ton.",
    enabled: { coklu_kare: true, clahe: true, keskinlestir: true, gri: true }, params: { coklu_kare: 7, clahe: 2, keskinlestir: 1.2 },
  },
];

const SCALE = [
  { id: "", label: "Yok" },
  { id: "buyut:2", label: "2× (matematiksel)" },
  { id: "buyut:4", label: "4× (matematiksel)" },
  { id: "ai_buyut:2", label: "2× AI" },
  { id: "ai_buyut:4", label: "4× AI" },
];

export default function EnhancePanel({ ev }: { caseId: number; ev?: Evidence }) {
  const time = useDebounced(useUI((s) => s.time), 350);
  const selBox = useUI((s) => s.selBox);
  const setDrawMode = useUI((s) => s.setDrawMode);
  const setSelBox = useUI((s) => s.setSelBox);
  const mapping = useMapping(ev);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({ clahe: true, keskinlestir: true });
  const [params, setParams] = useState<Record<string, number>>({});
  const [scale, setScale] = useState("buyut:2");
  const [jobId, setJobId] = useState<number | null>(null);
  const [big, setBig] = useState<string | null>(null);
  const [preset, setPreset] = useState("genel");
  const job = useJob(jobId);
  const pic = ev?.analysis_info?.analiz?.goruntu;
  const night = !!pic && (pic.renksiz_oran >= 0.6 || pic.dusuk_isik_oran >= 0.6);

  const applyPreset = (p: Preset) => {
    setPreset(p.id);
    setEnabled(p.enabled);
    setParams(p.params);
  };
  // Siyah-beyaz/karanlık kayıtta gece ayarı önerilir (video değişince bir kez)
  useEffect(() => {
    applyPreset(PRESETS.find((p) => p.id === (night ? "gece" : "genel"))!);
  }, [ev?.id, night]);

  if (!ev || ev.status !== "hazir") return <Empty title="Bir video seçin" />;

  const run = async () => {
    const ops: { op: string; params?: Record<string, number> }[] = [];
    for (const o of OPS) {
      if (o.id === "gri") continue;
      if (enabled[o.id]) ops.push({ op: o.id, params: o.param ? { [o.param.key]: params[o.id] ?? o.param.def } : undefined });
    }
    if (enabled.gri) ops.push({ op: "gri" });
    if (scale) {
      const [op, k] = scale.split(":");
      ops.push({ op, params: { kat: Number(k) } });
    }
    try {
      const r = await api.post<{ job_id: number }>(`/api/evidence/${ev.id}/enhance`, { t: time, box: selBox, ops });
      setJobId(r.job_id);
    } catch (e) {
      toastError(e);
    }
  };

  const ai = scale.startsWith("ai_");
  const running = job && (job.status === "calisiyor" || job.status === "beklemede");
  const res = job?.status === "tamamlandi" ? job.result : null;

  return (
    <div className="space-y-4 p-3">
      <div className="flex gap-3">
        <div className="relative h-[84px] w-[140px] shrink-0 overflow-hidden rounded bg-black">
          <img src={frameUrl(ev.id, time, 280, selBox)} alt="" className="size-full object-contain" />
        </div>
        <div className="min-w-0 flex-1 space-y-1.5 text-[12.5px]">
          <div className="tabular">
            <span className="text-muted">An: </span>
            {mapping.hasCamera ? fmtClock(mapping.realSec(time)) : fmtMedia(time, true)}
          </div>
          <div className="text-muted">{selBox ? "Seçili bölge iyileştirilecek" : "Karenin tamamı iyileştirilecek"}</div>
          <div className="flex gap-1.5">
            <Button size="sm" variant="subtle" icon={<SquareDashedMousePointer className="size-3.5" />} onClick={() => setDrawMode("kutu")}>
              Bölge seç
            </Button>
            {selBox && (
              <Button size="sm" variant="ghost" onClick={() => setSelBox(null)}>
                Temizle
              </Button>
            )}
          </div>
        </div>
      </div>

      <Section title="Hazır ayar">
        <div className="grid grid-cols-3 gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              title={p.hint}
              onClick={() => applyPreset(p)}
              className={`rounded-md border px-2 py-1.5 text-[12px] cursor-pointer ${preset === p.id ? "border-accent/60 bg-accent/15 text-accent" : "border-line text-muted hover:text-text"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {night && <div className="text-[11.5px] leading-snug text-muted">Bu kayıt siyah-beyaz ya da karanlık olduğu için "Gece / IR" ayarı önerildi.</div>}
      </Section>

      <Section title="Klasik işlemler (tekrarlanabilir)">
        <div className="space-y-1">
          {OPS.map((o) => (
            <div key={o.id} className="rounded-md px-2 py-1.5 hover:bg-panel-2">
              <label className="flex cursor-pointer items-center gap-2" title={o.hint}>
                <input type="checkbox" checked={!!enabled[o.id]} onChange={(e) => setEnabled({ ...enabled, [o.id]: e.target.checked })} />
                <span className="flex-1">{o.label}</span>
              </label>
              {o.param && enabled[o.id] && (
                <div className="ml-6 mt-1 flex items-center gap-2 text-[12px] text-muted">
                  {o.param.label}
                  <input
                    type="range"
                    min={o.param.min}
                    max={o.param.max}
                    step={o.param.step}
                    value={params[o.id] ?? o.param.def}
                    onChange={(e) => setParams({ ...params, [o.id]: Number(e.target.value) })}
                    className="flex-1"
                  />
                  <span className="w-8 text-right tabular">{params[o.id] ?? o.param.def}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Büyütme">
        <div className="grid grid-cols-3 gap-1">
          {SCALE.map((s) => (
            <button
              key={s.id}
              onClick={() => setScale(s.id)}
              className={`rounded-md border px-2 py-1.5 text-[12px] cursor-pointer ${scale === s.id ? (s.id.startsWith("ai_") ? "border-warn/60 bg-warn/15 text-warn" : "border-accent/60 bg-accent/15 text-accent") : "border-line text-muted hover:text-text"}`}
            >
              {s.label}
            </button>
          ))}
        </div>
        {ai && (
          <div className="flex gap-2 rounded-md border border-warn/40 bg-warn/10 p-2.5 text-[12px] leading-snug text-warn">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>
              AI büyütme görüntüye gerçekte olmayan ayrıntı ekleyebilir. Çıktı görünür bir filigran taşır ve yalnızca soruşturma ipucu olarak kullanılmalıdır; delil yerine
              orijinal kare kullanılmalıdır.
            </span>
          </div>
        )}
      </Section>

      <Button variant="primary" className="w-full" onClick={run} busy={!!running} icon={<Wand2 className="size-4" />}>
        İyileştir
      </Button>
      {running && <Progress value={job!.progress} />}
      {job?.status === "hata" && <div className="text-[12.5px] text-danger">{job.message}</div>}

      {res && (
        <Section
          title="Sonuç"
          actions={
            <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(res.image ? `${res.image}` : "").catch(toastError)}>
              Klasör
            </Button>
          }
        >
          <div className="grid grid-cols-2 gap-2">
            {[
              ["Orijinal", res.original],
              ["İyileştirilmiş", res.image],
            ].map(([label, p]) => (
              <button key={label} onClick={() => setBig(p)} className="group relative overflow-hidden rounded-md border border-line bg-black cursor-pointer">
                <img src={fileUrl(p)} alt={label} className="aspect-video w-full object-contain" />
                <span className="absolute left-1 top-1 rounded bg-black/70 px-1.5 text-[11px]">{label}</span>
                <Maximize2 className="absolute right-1 top-1 size-3.5 opacity-0 group-hover:opacity-100" />
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {res.chain.map((c: { ad: string }, i: number) => (
              <Badge key={i}>{c.ad}</Badge>
            ))}
            {res.ai && <Badge tone="warn">AI — ipucu</Badge>}
            <Badge>
              {res.size[0]}×{res.size[1]}
            </Badge>
          </div>
        </Section>
      )}
      <Modal open={!!big} onClose={() => setBig(null)} title="Görüntü" width="max-w-6xl">
        {big && <img src={fileUrl(big)} alt="" className="mx-auto max-h-[75vh] object-contain" style={{ imageRendering: "auto" }} />}
      </Modal>
    </div>
  );
}
