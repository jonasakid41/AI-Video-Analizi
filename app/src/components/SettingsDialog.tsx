import { useQueryClient } from "@tanstack/react-query";
import { Check, FolderOpen, KeyRound, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api, openFolder } from "../lib/api";
import { qk, useCatalog, useSettings, useSystem } from "../lib/hooks";
import type { EngineInfo, ModelInfo, Settings } from "../lib/types";
import { toast, toastError } from "../store";
import { Badge, Button, Field, inputCls, KV, Modal, Section, Spinner, Tabs, Toggle } from "./ui";

type Tab = "ai" | "analiz" | "sistem";

export default function SettingsDialog({ open, onClose, info }: { open: boolean; onClose: () => void; info: EngineInfo }) {
  const [tab, setTab] = useState<Tab>("ai");
  const { data: s } = useSettings();
  const qc = useQueryClient();

  const save = async (patch: Record<string, unknown>) => {
    try {
      const next = await api.put<Settings>("/api/settings", patch);
      qc.setQueryData(qk.settings, next);
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Ayarlar" width="max-w-3xl">
      <div className="-mx-5 -mt-4 mb-4">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { id: "ai", label: "Yapay zekâ" },
            { id: "analiz", label: "Yerel analiz" },
            { id: "sistem", label: "Sistem" },
          ]}
        />
      </div>
      {!s ? <Spinner /> : tab === "ai" ? <AiTab s={s} save={save} /> : tab === "analiz" ? <AnalysisTab s={s} save={save} /> : <SystemTab info={info} />}
    </Modal>
  );
}

function AiTab({ s, save }: { s: Settings; save: (p: Record<string, unknown>) => Promise<void> }) {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const isOR = s.ai.base_url.includes("openrouter");
  const catalog = useCatalog(true);

  const saveKey = async (del = false) => {
    setBusy(true);
    try {
      const next = del ? await api.del<Settings>("/api/settings/api-key") : await api.put<Settings>("/api/settings/api-key", { key: key.trim() });
      qc.setQueryData(qk.settings, next);
      setKey("");
      toast(del ? "Anahtar silindi" : "Anahtar kaydedildi (Windows ile şifrelendi)", "ok");
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Section title="OpenRouter API anahtarı">
        {s.api_key_set ? (
          <div className="flex items-center gap-2">
            <Badge tone="ok">
              <Check className="size-3" /> kayıtlı
            </Badge>
            <span className="font-mono text-[12.5px] text-muted">{s.api_key_masked}</span>
            <span className="flex-1" />
            <Button size="sm" variant="danger" onClick={() => saveKey(true)} busy={busy}>
              Sil
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input className={inputCls} type="password" placeholder="sk-or-v1-…" value={key} onChange={(e) => setKey(e.target.value)} />
            <Button variant="primary" icon={<KeyRound className="size-4" />} disabled={key.trim().length < 8} busy={busy} onClick={() => saveKey()}>
              Kaydet
            </Button>
          </div>
        )}
        <p className="text-[11.5px] leading-snug text-faint">
          Anahtar openrouter.ai üzerinden ücretsiz alınabilir. Ücretli modellerin maliyeti sizin OpenRouter hesabınızdan düşer; uygulama hiçbir ücret almaz.
        </p>
      </Section>

      <Section title="Profil">
        <div className="grid grid-cols-4 gap-2">
          {Object.entries(s.profiles).map(([id, p]) => (
            <button
              key={id}
              onClick={() => save({ ai: { profile: id } })}
              className={`rounded-lg border p-2.5 text-left cursor-pointer ${s.ai.profile === id ? "border-accent bg-accent/10" : "border-line hover:border-line-2"}`}
            >
              <div className="font-medium">{p.label}</div>
              <div className="mt-0.5 text-[11px] leading-snug text-faint">
                {id === "ucretsiz" ? "Ücretsiz modeller; hız sınırı olabilir" : id === "ekonomik" ? "En düşük maliyet" : id === "dengeli" ? "Önerilen" : "En güçlü modeller"}
              </div>
            </button>
          ))}
        </div>
      </Section>

      <Section
        title="Görevlere göre model"
        actions={
          <button className="flex items-center gap-1 text-[12px] text-muted hover:text-text cursor-pointer" onClick={() => api.get("/api/models", { refresh: true }).then(() => qc.invalidateQueries({ queryKey: qk.catalog })).catch(toastError)}>
            <RefreshCw className="size-3" /> listeyi yenile
          </button>
        }
      >
        {catalog.isLoading ? (
          <Spinner />
        ) : catalog.error ? (
          <div className="text-[12.5px] text-warn">Model listesi alınamadı (internet bağlantısını kontrol edin). Model kimliğini elle yazabilirsiniz.</div>
        ) : (
          catalog.data && (
            <div className="text-[11.5px] text-faint">
              {catalog.data.total} model · {catalog.data.image_count} görsel · {catalog.data.video_count} video · güncelleme {catalog.data.fetched_at}
            </div>
          )
        )}
        <ModelPicker label="Soru çözümleme (metin)" value={s.ai.roles.planner} need="text" models={catalog.data?.models} onChange={(v) => save({ ai: { roles: { ...s.ai.roles, planner: v } } })} />
        <ModelPicker label="Kare doğrulama (görsel)" value={s.ai.roles.verifier} need="image" models={catalog.data?.models} onChange={(v) => save({ ai: { roles: { ...s.ai.roles, verifier: v } } })} />
        <ModelPicker label="Video analizi (video)" value={s.ai.roles.video} need="video" models={catalog.data?.models} onChange={(v) => save({ ai: { roles: { ...s.ai.roles, video: v } } })} />
      </Section>

      <Section title="Gizlilik ve maliyet">
        {isOR && (
          <>
            <Toggle checked={s.ai.data_collection_deny} onChange={(v) => save({ ai: { data_collection_deny: v } })} label="Görüntüler model eğitiminde kullanılmasın" hint="Veri saklayan/eğitimde kullanan sağlayıcılar dışarıda bırakılır. Bazı ücretsiz modeller kullanılamayabilir." />
            <Toggle checked={s.ai.zdr} onChange={(v) => save({ ai: { zdr: v } })} label="Yalnızca sıfır veri saklama (ZDR) sağlayıcıları" hint="En sıkı ayar; uygun sağlayıcısı olmayan modeller hata verir." />
          </>
        )}
        <Toggle checked={s.ai.send_context_frame} onChange={(v) => save({ ai: { send_context_frame: v } })} label="Yakın görüntünün yanında sahnenin tamamını da gönder" hint="Doğruluğu artırır, maliyeti yaklaşık iki katına çıkarır." />
        <div className="grid grid-cols-3 gap-3">
          <Field label="Soru başına bütçe (USD)">
            <input type="number" min={0} step={0.05} className={inputCls} defaultValue={s.ai.budget_per_query_usd} onBlur={(e) => save({ ai: { budget_per_query_usd: Number(e.target.value) } })} />
          </Field>
          <Field label="En fazla aday">
            <input type="number" min={4} max={200} className={inputCls} defaultValue={s.ai.max_candidates} onBlur={(e) => save({ ai: { max_candidates: Number(e.target.value) } })} />
          </Field>
          <Field label="İstek başına aday">
            <input type="number" min={1} max={16} className={inputCls} defaultValue={s.ai.batch_size} onBlur={(e) => save({ ai: { batch_size: Number(e.target.value) } })} />
          </Field>
        </div>
      </Section>

      <details>
        <summary className="cursor-pointer text-[12.5px] text-muted">Gelişmiş: yerel model sunucusu</summary>
        <div className="mt-3">
          <Field label="API adresi (OpenAI uyumlu)" hint="Varsayılan: https://openrouter.ai/api/v1 — Ollama için ör. http://127.0.0.1:11434/v1, LM Studio için http://127.0.0.1:1234/v1">
            <input className={inputCls} defaultValue={s.ai.base_url} onBlur={(e) => e.target.value && save({ ai: { base_url: e.target.value.trim() } })} />
          </Field>
        </div>
      </details>
    </div>
  );
}

function ModelPicker({ label, value, need, models, onChange }: { label: string; value: string; need: "text" | "image" | "video"; models?: ModelInfo[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [onlyFree, setOnlyFree] = useState(false);
  const current = models?.find((m) => m.id === value);
  const list = useMemo(() => {
    const ql = q.toLowerCase();
    return (models ?? [])
      .filter((m) => (need === "video" ? m.video : need === "image" ? m.image : true))
      .filter((m) => !onlyFree || m.free)
      .filter((m) => !ql || m.id.toLowerCase().includes(ql) || m.name.toLowerCase().includes(ql))
      .slice(0, 120);
  }, [models, need, q, onlyFree]);

  return (
    <div className="rounded-lg border border-line bg-panel-2 p-2.5">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[12px] text-muted">{label}</div>
          <div className="truncate font-mono text-[12.5px]">{value}</div>
        </div>
        {current ? <Price m={current} /> : models ? <Badge tone="warn">listede yok</Badge> : null}
        <Button size="sm" variant="subtle" onClick={() => setOpen(!open)}>
          {open ? "Kapat" : "Değiştir"}
        </Button>
      </div>
      {open && (
        <div className="mt-2.5 space-y-2">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2 top-2 size-4 text-faint" />
              <input autoFocus className={`${inputCls} h-8 pl-7`} placeholder="Model ara ya da kimliği yazıp Enter'a basın" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => {
                if (e.key === "Enter" && q.includes("/")) {
                  onChange(q.trim());
                  setOpen(false);
                }
              }} />
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-muted">
              <input type="checkbox" checked={onlyFree} onChange={(e) => setOnlyFree(e.target.checked)} />
              ücretsiz
            </label>
          </div>
          <div className="max-h-64 overflow-y-auto rounded-md border border-line">
            {list.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  onChange(m.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 border-b border-line px-2.5 py-1.5 text-left last:border-0 hover:bg-panel-3 cursor-pointer ${m.id === value ? "bg-accent/10" : ""}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px]">{m.name}</div>
                  <div className="truncate font-mono text-[11px] text-faint">{m.id}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {m.video && <Badge tone="accent">video</Badge>}
                  {m.structured && <Badge>JSON</Badge>}
                </div>
                <Price m={m} />
              </button>
            ))}
            {!list.length && <div className="p-3 text-center text-[12px] text-muted">Uygun model yok</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function Price({ m }: { m: ModelInfo }) {
  if (m.free) return <Badge tone="ok">ücretsiz</Badge>;
  return (
    <span className="shrink-0 text-right text-[11px] leading-tight text-muted tabular" title="1 milyon token başına USD (girdi / çıktı)">
      ${m.price_in_m} / ${m.price_out_m}
      <span className="block text-faint">1M token</span>
    </span>
  );
}

function AnalysisTab({ s, save }: { s: Settings; save: (p: Record<string, unknown>) => Promise<void> }) {
  const a = s.analysis;
  const set = (k: string, v: unknown) => save({ analysis: { [k]: v } });
  return (
    <div className="space-y-5">
      <Toggle checked={a.auto_analyze} onChange={(v) => set("auto_analyze", v)} label="Dönüştürmeden sonra otomatik analiz et" />
      <div className="grid grid-cols-2 gap-4">
        <Field label="Hareketli bölümlerde inceleme hızı" hint="Yüksek değer küçük/hızlı nesneleri yakalar ama süreyi uzatır.">
          <select className={inputCls} value={a.sample_fps} onChange={(e) => set("sample_fps", Number(e.target.value))}>
            {[1, 2, 3, 5, 8].map((n) => (
              <option key={n} value={n}>
                saniyede {n} kare
              </option>
            ))}
          </select>
        </Field>
        <Field label="Nesne tespit modeli" hint="Hafif model, ekran kartı belleği az olan bilgisayarlar içindir.">
          <select className={inputCls} value={a.detector} onChange={(e) => set("detector", e.target.value)}>
            <option value="yolox_s">YOLOX-S (önerilen)</option>
            <option value="yolox_tiny">YOLOX-Tiny (hafif)</option>
          </select>
        </Field>
        <Field label={`Tespit eşiği: %${Math.round(a.min_conf * 100)}`}>
          <input type="range" min={0.2} max={0.7} step={0.05} defaultValue={a.min_conf} onMouseUp={(e) => set("min_conf", Number((e.target as HTMLInputElement).value))} className="w-full" />
        </Field>
        <Field label="İşlem birimi">
          <select className={inputCls} value={a.device} onChange={(e) => set("device", e.target.value)}>
            <option value="auto">Otomatik (ekran kartı varsa)</option>
            <option value="cpu">Yalnızca işlemci</option>
          </select>
        </Field>
      </div>
      <div className="space-y-1">
        <Toggle checked={a.faces} onChange={(v) => set("faces", v)} label="Yüz tespiti ve kişi gruplama" hint="Yüzler bilgisayarda işlenir; buluta gönderilmez." />
        <Toggle checked={a.plates} onChange={(v) => set("plates", v)} label="Plaka okuma" />
        <Toggle checked={a.clip} onChange={(v) => set("clip", v)} label="Görsel arama indeksi" hint="“Kırmızı mont”, “beyaz kamyonet” gibi aramaları yerelde mümkün kılar." />
      </div>
      <p className="text-[11.5px] text-faint">Değişiklikler yeni analizlerde geçerli olur. Mevcut videoyu “Bilgi” sekmesinden yeniden analiz edebilirsiniz.</p>
    </div>
  );
}

function SystemTab({ info }: { info: EngineInfo }) {
  const { data: sys } = useSystem();
  if (!sys) return <Spinner />;
  return (
    <div className="space-y-5">
      <Section title="Uygulama">
        <KV
          rows={[
            ["Sürüm", sys.version],
            [
              "Veri klasörü",
              <span className="flex items-center gap-2">
                <span className="break-all font-mono text-[11.5px]">{sys.data_dir}</span>
                <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => openFolder(sys.data_dir).catch(toastError)}>
                  Aç
                </Button>
              </span>,
            ],
            ["Düzen", info.portable ? "Taşınabilir (exe'nin yanında)" : "Uygulama klasörü yazılabilir değil; veriler AppData altında"],
            ["Yerel analiz", `${sys.inference.label} · ONNX Runtime ${sys.inference.onnxruntime}`],
          ]}
        />
      </Section>
      <Section title="Video kodlayıcılar">
        <div className="flex flex-wrap gap-1.5">
          {sys.encoders.map((e) => (
            <Badge key={e.name} tone={e.name === sys.encoder ? "ok" : e.ok ? "default" : "danger"}>
              {e.label}
              {e.name === sys.encoder ? " · kullanılıyor" : !e.ok ? " · yok" : ""}
            </Badge>
          ))}
        </div>
      </Section>
      <Section title="Yerel modeller">
        <div className="space-y-1 text-[12.5px]">
          {sys.models.map((m) => (
            <div key={m.key} className="flex items-center gap-2">
              <Badge tone={m.ok ? "ok" : "danger"}>{m.ok ? "hazır" : "eksik"}</Badge>
              <span className="flex-1">{m.label}</span>
              <span className="text-faint">{m.license}</span>
              <span className="w-16 text-right text-faint tabular">{m.size_mb ? `${m.size_mb} MB` : ""}</span>
            </div>
          ))}
        </div>
      </Section>
      <p className="text-[11.5px] leading-snug text-faint">
        AI Video Analizi açık kaynaklı ve ücretsizdir (GPL-3.0). Hesap, telemetri ya da kullanım kaydı yoktur; dışarıya yalnızca sizin başlattığınız yapay zekâ istekleri gider.
      </p>
    </div>
  );
}
