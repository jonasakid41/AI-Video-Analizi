import { useQueryClient } from "@tanstack/react-query";
import { Copy, FolderOpen, RefreshCw, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { api, caseExportsDir, dataDir, openFolder } from "../../lib/api";
import { ACTION_LABELS, fmtBytes, fmtDateTime, IGNORABLE_KINDS, KIND_STYLE } from "../../lib/format";
import { qk, useHistory } from "../../lib/hooks";
import { fmtDuration } from "../../lib/time";
import type { AnalysisStats, Evidence } from "../../lib/types";
import { toast, toastError } from "../../store";
import { Badge, Button, Empty, inputCls, KV, Section } from "../ui";

const pct = (v: number) => `%${Math.round(v * 100)}`;

/** Kayıpsız kopyada düzeltilen damgalar ve kamera saatinin geri sıçramaları (kare atılmaz) */
function timestampText(fixed?: number, jumps?: [number, number][]): string {
  const parts: string[] = [];
  if (fixed) parts.push(`${fixed} karenin damgası düzeltildi`);
  if (jumps?.length) parts.push(`kamera saati ${jumps.length} kez geri atladı (${jumps.map(([, s]) => `${Math.round(s)} sn`).join(", ")}); zaman çizgisi kesintisiz sürdürüldü`);
  return parts.length ? parts.join(" · ") : "düzgün";
}

/** Siyah-beyaz (gece/IR), düşük ışık ve küçük nesneler için yapılan uyarlamalar */
function pictureText(g?: AnalysisStats["goruntu"]): string {
  if (!g) return "—";
  const parts = [
    g.renksiz_oran >= 0.6 ? "siyah-beyaz (gece/IR) — renk yerine ton kaydedildi" : g.renksiz_oran >= 0.1 ? `kısmen siyah-beyaz (${pct(g.renksiz_oran)})` : "renkli",
  ];
  if (g.dusuk_isik_oran >= 0.1) parts.push(`düşük ışık ${pct(g.dusuk_isik_oran)}`);
  if (g.iyilestirilen_kare) parts.push(`${g.iyilestirilen_kare} kare kontrast artırılarak tarandı`);
  if (g.yakinlastirma_tespiti) parts.push(`yakınlaştırmayla ${g.yakinlastirma_tespiti} ek tespit`);
  return parts.join(" · ");
}

export default function InfoPanel({ caseId, ev }: { caseId: number; ev?: Evidence }) {
  const { data: history } = useHistory(caseId);
  return (
    <div className="space-y-5 p-3">
      {ev ? <EvidenceInfo ev={ev} /> : <Empty title="Bir video seçin" />}
      <Section
        title="Vaka işlem geçmişi"
        actions={
          <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(caseExportsDir(caseId)).catch(toastError)}>
            Dışa aktarımlar
          </Button>
        }
      >
        <div className="max-h-80 space-y-1 overflow-y-auto text-[12px]">
          {(history ?? []).map((h) => (
            <div key={h.id} className="flex gap-2">
              <span className="w-24 shrink-0 text-faint">{fmtDateTime(h.created_at)}</span>
              <span className="min-w-0 flex-1 truncate" title={JSON.stringify(h.detail)}>
                {ACTION_LABELS[h.action] ?? h.action}
                {typeof h.detail?.ad === "string" && <span className="text-muted"> · {h.detail.ad}</span>}
                {typeof h.detail?.soru === "string" && <span className="text-muted"> · {h.detail.soru}</span>}
              </span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function EvidenceInfo({ ev }: { ev: Evidence }) {
  const qc = useQueryClient();
  const [camera, setCamera] = useState(ev.camera);
  const [diag, setDiag] = useState<string | null>(null);
  const [fps, setFps] = useState(2);
  useEffect(() => setCamera(ev.camera), [ev.id, ev.camera]);
  useEffect(() => {
    if (ev.status === "hata") api.get<{ text: string }>(`/api/evidence/${ev.id}/diagnostics`).then((d) => setDiag(d.text)).catch(() => {});
    else setDiag(null);
  }, [ev.id, ev.status]);

  const conv = ev.analysis_info.donusturme;
  const stats = ev.analysis_info.analiz;
  const folder = `${dataDir()}\\cases\\${ev.case_id}\\evidence\\${ev.id}`;

  const saveCamera = async () => {
    if (camera === ev.camera) return;
    try {
      await api.patch(`/api/evidence/${ev.id}`, { camera });
      qc.invalidateQueries({ queryKey: qk.evidence(ev.case_id) });
    } catch (e) {
      toastError(e);
    }
  };
  const reanalyze = async () => {
    try {
      await api.post(`/api/evidence/${ev.id}/analyze`, { options: { sample_fps: fps } });
      toast("Analiz yeniden başlatıldı", "info");
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <>
      <Section title="Video">
        <KV
          rows={[
            ["Dosya", ev.original_name],
            ["Kamera", <input className={`${inputCls} h-7`} value={camera} onChange={(e) => setCamera(e.target.value)} onBlur={saveCamera} placeholder="ör. Kamera 1 — Giriş" />],
            ["Boyut", fmtBytes(ev.size)],
            [
              "SHA-256",
              <span className="flex items-start gap-1">
                <span className="break-all font-mono text-[11px]">{ev.sha256 || "—"}</span>
                {ev.sha256 && (
                  <button className="text-faint hover:text-text cursor-pointer" title="Kopyala" onClick={() => navigator.clipboard.writeText(ev.sha256).then(() => toast("Kopyalandı"))}>
                    <Copy className="size-3.5" />
                  </button>
                )}
              </span>,
            ],
            ["Biçim", ev.sniff.label ?? "—"],
            ["Açma yöntemi", ev.strategy.name ?? "—"],
            ["Görüntü", ev.width ? `${ev.codec} · ${ev.width}×${ev.height} · ${ev.fps?.toFixed(2)} fps` : "—"],
            ["Süre", fmtDuration(ev.duration)],
            ["Kayıpsız kopya", conv ? `${conv.container === "nut" ? "NUT" : "MKV"} kabı${conv.audio_codec ? ` · ses: ${conv.audio_codec}` : " · ses yok"}${conv.dropped ? ` · ${conv.dropped} ses/bozuk paket atlandı` : ""}` : "—"],
            ["Zaman damgası", conv ? timestampText(conv.fixed_timestamps, conv.clock_jumps) : "—"],
            ["Çalışma kopyası", conv?.proxy ? (conv.proxy.mode === "kodlama" ? conv.proxy.encoder_label : "yeniden paketleme (kayıpsız)") : "—"],
            ["Kayıt boşluğu", conv?.gaps?.length ? `${conv.gaps.length} adet` : "yok"],
          ]}
        />
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(folder).catch(toastError)}>
            Video klasörü
          </Button>
          <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} onClick={() => api.post(`/api/evidence/${ev.id}/reingest`).then(() => toast("Yeniden dönüştürülüyor")).catch(toastError)}>
            Yeniden dönüştür
          </Button>
        </div>
      </Section>

      {ev.strategy.denemeler && ev.strategy.denemeler.length > 1 && (
        <Section title="Denenen açma yöntemleri">
          <div className="space-y-1 text-[12px]">
            {ev.strategy.denemeler.map((a, i) => (
              <div key={i} className="flex items-center gap-2">
                <Badge tone={a.basarili ? "ok" : "default"}>{a.basarili ? "başarılı" : "olmadı"}</Badge>
                <span className="flex-1 truncate" title={a.hata}>
                  {a.strateji}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {diag && (
        <Section title={<span className="flex items-center gap-1.5"><Wrench className="size-3.5" /> Teşhis paketi</span>}>
          <p className="text-[12px] text-muted">Bu dosya şu an açılamıyor. Aşağıdaki teşhis bilgisi yeni biçim desteği eklemek için kullanılabilir (dosya video içermez).</p>
          <pre className="selectable max-h-64 overflow-auto rounded-md bg-black/40 p-2 font-mono text-[10.5px] leading-snug">{diag}</pre>
        </Section>
      )}

      {ev.status === "hazir" && (
        <Section title="Yerel analiz">
          {stats ? (
            <KV
              rows={[
                ["Bulunanlar", Object.entries(stats.izler).map(([k, v]) => `${v} ${k}`).join(", ") || "—"],
                ["Yüz / kişi", `${stats.yuz_sayisi} yüz · ${stats.kisi_kumesi} farklı kişi`],
                ["Plakalar", stats.plakalar.length ? stats.plakalar.join(", ") : "—"],
                ["Hareketli süre", `${fmtDuration(stats.aktif_sure_sn)} (${stats.aktif_bolum} bölüm)`],
                ["Hareket türleri", stats.hareket_ozeti && Object.keys(stats.hareket_ozeti).length
                  ? Object.entries(stats.hareket_ozeti).sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => `${KIND_STYLE[k]?.name ?? k} ${fmtDuration(v)}${IGNORABLE_KINDS.includes(k) ? " (önemsiz)" : ""}`).join(" · ")
                  : "—"],
                ["Görüntü", pictureText(stats.goruntu)],
                ["Süre / aygıt", `${stats.sure_sn.toplam?.toFixed(1)} sn · ${stats.aygit === "DmlExecutionProvider" ? "GPU (DirectML)" : "CPU"}`],
              ]}
            />
          ) : (
            <div className="text-[12.5px] text-muted">Henüz analiz edilmedi.</div>
          )}
          <div className="flex items-center gap-2">
            <select value={fps} onChange={(e) => setFps(Number(e.target.value))} className={`${inputCls} h-7 w-40`} title="Hareketli bölümlerde saniyede incelenecek kare">
              {[1, 2, 3, 5].map((n) => (
                <option key={n} value={n}>
                  saniyede {n} kare
                </option>
              ))}
            </select>
            <Button size="sm" variant="subtle" onClick={reanalyze}>
              {stats ? "Yeniden analiz et" : "Analiz et"}
            </Button>
          </div>
        </Section>
      )}
    </>
  );
}
