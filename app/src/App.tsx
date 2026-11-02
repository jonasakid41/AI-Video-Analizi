import { AlertTriangle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import CasesPage from "./components/CasesPage";
import FirstRun from "./components/FirstRun";
import SettingsDialog from "./components/SettingsDialog";
import TopBar from "./components/TopBar";
import { Spinner, Toasts } from "./components/ui";
import Workspace from "./components/Workspace";
import { api, connect, onEngineError } from "./lib/api";
import { useEngineEvents, useSettings, useUpdateStatus } from "./lib/hooks";
import type { EngineInfo } from "./lib/types";
import { toast, useUI } from "./store";

export default function App() {
  const [info, setInfo] = useState<EngineInfo | null>(null);
  const [wait, setWait] = useState("Analiz motoru başlatılıyor…");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    onEngineError(setError);
    connect(setWait).then(setInfo).catch((e) => setError(String(e.message || e)));
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-10">
        <div className="max-w-lg space-y-3 rounded-xl border border-danger/40 bg-panel p-6">
          <div className="flex items-center gap-2 text-danger">
            <AlertTriangle className="size-5" />
            <h1 className="text-base font-semibold">Uygulama başlatılamadı</h1>
          </div>
          <p className="selectable text-muted">{error}</p>
          <p className="text-[12.5px] text-faint">
            Uygulama klasörünün tamamının (engine ve models klasörleri dahil) aynı yerde olduğundan emin olun.
            Ayrıntılı kayıt: <span className="font-mono">data/logs</span>
          </p>
        </div>
      </div>
    );
  }
  if (!info) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <img src="/icon.png" alt="" className="size-20 opacity-90" />
        <div className="flex items-center gap-2 text-muted">
          <Spinner />
          {wait}
        </div>
      </div>
    );
  }
  return <Main info={info} />;
}

function Main({ info }: { info: EngineInfo }) {
  useEngineEvents();
  const caseId = useUI((s) => s.caseId);
  const openCase = useUI((s) => s.openCase);
  const settingsOpen = useUI((s) => s.settingsOpen);
  const setSettingsOpen = useUI((s) => s.setSettingsOpen);
  const { data: settings } = useSettings();
  const { data: upd } = useUpdateStatus();
  const restored = useRef(false);

  // Güncelleyicinin sonucu bir kez bildirilir
  const result = upd?.result;
  const announced = useRef(false);
  useEffect(() => {
    if (!result || announced.current) return;
    announced.current = true;
    if (result.ok) toast(`Güncelleme tamamlandı: v${result.version}`, "ok");
    else toast(`v${result.version} kurulamadı, önceki sürüm geri yüklendi: ${result.error ?? ""}`, "error");
    api.post("/api/update/ack").catch(() => {});
  }, [result]);

  // Son açılan vaka data/settings.json'da hatırlanır
  useEffect(() => {
    if (!settings || restored.current) return;
    restored.current = true;
    const last = settings.ui?.last_case;
    if (last) api.get(`/api/cases/${last}`).then(() => openCase(last)).catch(() => {});
  }, [settings, openCase]);
  useEffect(() => {
    if (restored.current) api.put("/api/settings", { ui: { last_case: caseId } }).catch(() => {});
  }, [caseId]);

  return (
    <div className="flex h-full flex-col">
      <TopBar info={info} />
      <div className="min-h-0 flex-1">{caseId ? <Workspace caseId={caseId} /> : <CasesPage info={info} />}</div>
      {settings && !settings.notice_accepted && <FirstRun />}
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} info={info} />
      <Toasts />
    </div>
  );
}
