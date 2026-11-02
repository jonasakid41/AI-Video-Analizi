import { useQueryClient } from "@tanstack/react-query";
import { Film, FolderOpen, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api, confirmDialog, openFolder } from "../lib/api";
import { fmtDateTime } from "../lib/format";
import { qk, useCases } from "../lib/hooks";
import type { Case, EngineInfo } from "../lib/types";
import { toastError, useUI } from "../store";
import { Button, Empty, Field, IconButton, inputCls, Modal, Spinner } from "./ui";

export default function CasesPage({ info }: { info: EngineInfo }) {
  const { data: cases, isLoading } = useCases();
  const openCase = useUI((s) => s.openCase);
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);

  const list = useMemo(
    () => (cases ?? []).filter((c) => !q || (c.name + " " + c.description).toLocaleLowerCase("tr").includes(q.toLocaleLowerCase("tr"))),
    [cases, q],
  );

  const remove = async (c: Case) => {
    if (!(await confirmDialog(`"${c.name}" vakası ve tüm videoları, analizleri, bulguları kalıcı olarak silinsin mi?`, "Vakayı sil"))) return;
    try {
      await api.del(`/api/cases/${c.id}`);
      qc.invalidateQueries({ queryKey: qk.cases });
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Vakalar</h1>
            <p className="mt-1 text-muted">Her vaka; videolar, analizler, sorular ve bulgularla birlikte bu bilgisayarda saklanır.</p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" icon={<FolderOpen className="size-4" />} onClick={() => openFolder(info.data_dir).catch(toastError)}>
              Veri klasörü
            </Button>
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
              Yeni vaka
            </Button>
          </div>
        </div>

        {(cases?.length ?? 0) > 4 && (
          <div className="relative mb-4">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-faint" />
            <input className={`${inputCls} pl-8`} placeholder="Vaka ara" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="size-6" />
          </div>
        ) : list.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line-2">
            <Empty icon={<Film className="size-9" />} title={cases?.length ? "Aramaya uyan vaka yok" : "Henüz vaka yok"}>
              Yeni bir vaka oluşturun ve kamera kayıtlarını sürükleyip bırakın. VLC'nin açamadığı DVR dosyaları da desteklenir.
            </Empty>
            {!cases?.length && (
              <div className="flex justify-center pb-10">
                <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                  İlk vakayı oluştur
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {list.map((c) => (
              <div
                key={c.id}
                onClick={() => openCase(c.id)}
                className="group cursor-pointer rounded-xl border border-line bg-panel p-4 transition-colors hover:border-accent/50 hover:bg-panel-2"
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[15px] font-semibold">{c.name}</div>
                    {c.description && <div className="mt-0.5 line-clamp-2 text-[12.5px] text-muted">{c.description}</div>}
                  </div>
                  <IconButton
                    title="Vakayı sil"
                    className="opacity-0 group-hover:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(c);
                    }}
                  >
                    <Trash2 className="size-4" />
                  </IconButton>
                </div>
                <div className="mt-3 flex gap-4 text-[12px] text-muted">
                  <span>{c.evidence_count} video</span>
                  <span>{c.finding_count} bulgu</span>
                  <span className="ml-auto">{fmtDateTime(c.updated_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <NewCase open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}

function NewCase({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const openCase = useUI((s) => s.openCase);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const c = await api.post<Case>("/api/cases", { name, description: desc });
      qc.invalidateQueries({ queryKey: qk.cases });
      setName("");
      setDesc("");
      onClose();
      openCase(c.id);
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
      title="Yeni vaka"
      width="max-w-md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Vazgeç
          </Button>
          <Button variant="primary" onClick={submit} busy={busy} disabled={!name.trim()}>
            Oluştur
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Vaka adı">
          <input
            autoFocus
            className={inputCls}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="ör. 2026/1452 — Otopark olayı"
          />
        </Field>
        <Field label="Açıklama (isteğe bağlı)">
          <textarea className={`${inputCls} h-24 py-2`} value={desc} onChange={(e) => setDesc(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}
