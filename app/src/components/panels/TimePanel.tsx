import { useQueryClient } from "@tanstack/react-query";
import { History, ScanText, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { fmtDateTime, TIME_SOURCE } from "../../lib/format";
import { qk, useJob, useMapping, useTimeInfo } from "../../lib/hooks";
import { fmtClock, fmtIso, fmtMedia, fmtOffset, secToIso } from "../../lib/time";
import type { Evidence } from "../../lib/types";
import { toast, toastError, useUI } from "../../store";
import { Badge, Button, Empty, Field, inputCls, KV, Progress, Section } from "../ui";

export default function TimePanel({ ev }: { ev?: Evidence }) {
  const time = useUI((s) => s.time);
  const selBox = useUI((s) => s.selBox);
  const mapping = useMapping(ev);
  const { data: info } = useTimeInfo(ev?.id ?? null);
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const job = useJob(jobId);
  const [every, setEvery] = useState(10);
  const [realAtNow, setRealAtNow] = useState("");
  const [camStart, setCamStart] = useState("");
  const [reason, setReason] = useState("");
  const [applyAll, setApplyAll] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!ev || ev.status !== "hazir") return <Empty title="Bir video seçin" />;
  const s = ev.time;
  const cam = mapping.cameraSec(time);
  const real = mapping.realSec(time);

  const put = async (body: Record<string, unknown>, msg: string) => {
    setBusy(true);
    try {
      await api.put(`/api/evidence/${ev.id}/time`, { reason, apply_to_camera: applyAll, ...body });
      qc.invalidateQueries({ queryKey: qk.evidence(ev.case_id) });
      qc.invalidateQueries({ queryKey: qk.time(ev.id) });
      toast(msg, "ok");
      setReason("");
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  const scan = async () => {
    try {
      const r = await api.post<{ job_id: number }>(`/api/evidence/${ev.id}/time/osd`, { every, region: selBox });
      setJobId(r.job_id);
    } catch (e) {
      toastError(e);
    }
  };

  const toLocalInput = (sec: number | null) => (sec === null ? "" : secToIso(sec));
  const running = job && (job.status === "calisiyor" || job.status === "beklemede");

  return (
    <div className="space-y-5 p-3">
      <div className="grid grid-cols-3 gap-2 text-center">
        <Clock label="Gerçek saat" value={real !== null ? fmtClock(real) : "bilinmiyor"} strong />
        <Clock label="Kamera saati" value={cam !== null ? fmtClock(cam) : "bilinmiyor"} />
        <Clock label="Video içi" value={fmtMedia(time, true)} />
      </div>

      <KV
        rows={[
          ["Saat kaynağı", <Badge tone={s.kamera_saati_var ? "ok" : "warn"}>{TIME_SOURCE[s.kaynak] ?? s.kaynak}</Badge>],
          ["Düzeltme", s.duzeltme_farki_sn === null ? "yok (kamera saati doğru kabul ediliyor)" : `${fmtOffset(s.duzeltme_farki_sn)}${s.gunluk_kayma_sn ? ` · günlük kayma ${s.gunluk_kayma_sn.toFixed(1)} sn` : ""}`],
          ["Parçalar", `${s.parca_sayisi}${s.bosluklar.length ? ` · ${s.bosluklar.length} saat sıçraması/kayıt boşluğu` : ""}`],
        ]}
      />

      <Section title="1 · Kamera saatini oku">
        <p className="text-[12px] leading-snug text-muted">
          Görüntüdeki tarih/saat yazısı belirli aralıklarla okunur. Kayıt boşlukları ve saat sıçramaları otomatik bulunur. Yazı köşelerde değilse oynatıcıda “Bölge seç” ile saat yazısını seçin.
        </p>
        <div className="flex items-center gap-2">
          <select value={every} onChange={(e) => setEvery(Number(e.target.value))} className={`${inputCls} w-36`}>
            {[5, 10, 30, 60].map((n) => (
              <option key={n} value={n}>
                her {n} sn
              </option>
            ))}
          </select>
          <Button variant="subtle" icon={<ScanText className="size-4" />} onClick={scan} busy={!!running}>
            {selBox ? "Seçili bölgeden oku" : "Ekran saatini oku"}
          </Button>
        </div>
        {running && <Progress value={job!.progress} />}
        {job?.status === "hata" && <div className="text-[12px] text-danger">{job.message}</div>}
        {job?.status === "tamamlandi" && <div className="text-[12px] text-ok">{job.result.okuma} okuma · {job.result.parca} parça</div>}
      </Section>

      <Section title="2 · Gerçek saate göre düzelt">
        <p className="text-[12px] leading-snug text-muted">
          Oynatıcıyı saati bilinen bir ana getirin (ör. DVR ekranının güvenilir bir saatle yan yana fotoğrafı, bilinen bir olay) ve o andaki gerçek saati girin. İki farklı anda referans girerseniz saatin günlük kayması da hesaplanır.
        </p>
        <Field label={`Şu anki karede (${fmtMedia(time)}) gerçek saat`}>
          <div className="flex gap-2">
            <input type="datetime-local" step={1} className={inputCls} value={realAtNow || toLocalInput(real ?? cam)} onChange={(e) => setRealAtNow(e.target.value)} />
            <Button variant="primary" busy={busy} onClick={() => put({ references: [{ t_media: time, real: realAtNow || toLocalInput(real ?? cam) }] }, "Referans eklendi; tüm zamanlar güncellendi")}>
              Ekle
            </Button>
          </div>
        </Field>
        {!s.kamera_saati_var && (
          <Field label="ya da videonun başlangıcındaki kamera saati" hint="Ekranda saat yazısı yoksa ve dosya adında tarih bulunamadıysa kullanın.">
            <div className="flex gap-2">
              <input type="datetime-local" step={1} className={inputCls} value={camStart} onChange={(e) => setCamStart(e.target.value)} />
              <Button variant="subtle" disabled={!camStart} busy={busy} onClick={() => put({ camera_start: camStart }, "Başlangıç saati ayarlandı")}>
                Ayarla
              </Button>
            </div>
          </Field>
        )}
        <Field label="Gerekçe (rapora ve geçmişe yazılır)">
          <input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="ör. El koyma anında DVR ekranı fotoğraflandı" />
        </Field>
        {ev.camera && (
          <label className="flex cursor-pointer items-center gap-2 text-[12.5px]">
            <input type="checkbox" checked={applyAll} onChange={(e) => setApplyAll(e.target.checked)} />
            “{ev.camera}” kamerasının diğer videolarına da uygula
          </label>
        )}
        {ev.time_mapping.corrections.length > 0 && (
          <div className="space-y-1">
            {ev.time_mapping.corrections.map(([c, r], i) => (
              <div key={i} className="flex items-center gap-2 rounded-md bg-panel-2 px-2 py-1.5 text-[12px] tabular">
                <span className="text-muted">kamera</span> {fmtIso(c)} <span className="text-muted">→ gerçek</span> {fmtIso(r)}
                <span className="flex-1" />
                <button
                  className="text-faint hover:text-danger cursor-pointer"
                  title="Referansı kaldır"
                  onClick={() => put({ corrections: ev.time_mapping.corrections.filter((_, j) => j !== i) }, "Referans kaldırıldı")}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Section>

      {!!info?.versions.length && (
        <Section title={<span className="flex items-center gap-1.5"><History className="size-3.5" /> Değişiklik geçmişi</span>}>
          <div className="space-y-1 text-[12px]">
            {info.versions.map((v) => (
              <div key={v.version} className="flex gap-2">
                <span className="w-6 text-faint">v{v.version}</span>
                <span className="flex-1">{v.reason || "—"}</span>
                <span className="text-faint">{fmtDateTime(v.created_at)}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
      {!!info?.readings.length && (
        <details className="text-[12px]">
          <summary className="cursor-pointer text-muted">Ekran saati okumaları ({info.readings.length})</summary>
          <div className="mt-1.5 max-h-48 space-y-0.5 overflow-y-auto">
            {info.readings.map((r, i) => (
              <div key={i} className="flex gap-3 tabular">
                <span className="w-14 text-faint">{fmtMedia(r.t)}</span>
                <span>{fmtIso(r.parsed)}</span>
                <span className="truncate text-faint">“{r.text}”</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function Clock({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`rounded-lg border px-2 py-2 ${strong ? "border-accent/40 bg-accent/8" : "border-line bg-panel-2"}`}>
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`mt-0.5 tabular ${strong ? "text-[13px] font-semibold" : "text-[12.5px]"}`}>{value}</div>
    </div>
  );
}
