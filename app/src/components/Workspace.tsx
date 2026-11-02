import { CalendarClock, Car, FileSearch, Info, MessageSquareText, ScanFace, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { useEvidence, useEvidenceList, useFindings } from "../lib/hooks";
import { type PanelTab, useUI } from "../store";
import EvidenceList from "./EvidenceList";
import AskPanel from "./panels/AskPanel";
import EnhancePanel from "./panels/EnhancePanel";
import FindingsPanel from "./panels/FindingsPanel";
import InfoPanel from "./panels/InfoPanel";
import PeoplePanel from "./panels/PeoplePanel";
import PlatesPanel from "./panels/PlatesPanel";
import TimePanel from "./panels/TimePanel";
import Player from "./Player";
import { Badge, Tabs } from "./ui";

export default function Workspace({ caseId }: { caseId: number }) {
  const evidenceId = useUI((s) => s.evidenceId);
  const selectEvidence = useUI((s) => s.selectEvidence);
  const tab = useUI((s) => s.tab);
  const setTab = useUI((s) => s.setTab);
  const { data: list } = useEvidenceList(caseId);
  const ev = useEvidence(caseId, evidenceId);
  const { data: findings } = useFindings(caseId);

  // İlk hazır videoyu otomatik seç
  useEffect(() => {
    if (!evidenceId && list?.length) {
      selectEvidence((list.find((e) => e.status === "hazir") ?? list[0]).id);
    }
  }, [evidenceId, list, selectEvidence]);

  const confirmed = findings?.filter((f) => f.status === "dogrulandi").length ?? 0;
  const items: { id: PanelTab; label: string; icon: React.ReactNode; badge?: React.ReactNode }[] = [
    { id: "sor", label: "Sor", icon: <MessageSquareText className="size-4" /> },
    { id: "bulgular", label: "Bulgular", icon: <FileSearch className="size-4" />,
      badge: findings?.length ? <Badge tone={confirmed ? "ok" : "default"}>{findings.length}</Badge> : undefined },
    { id: "kisiler", label: "Kişiler", icon: <ScanFace className="size-4" /> },
    { id: "plakalar", label: "Plakalar", icon: <Car className="size-4" /> },
    { id: "iyilestir", label: "İyileştir", icon: <Sparkles className="size-4" /> },
    { id: "saat", label: "Saat", icon: <CalendarClock className="size-4" />,
      badge: ev && ev.status === "hazir" && !ev.time.kamera_saati_var ? <span className="size-1.5 rounded-full bg-warn" /> : undefined },
    { id: "bilgi", label: "Bilgi", icon: <Info className="size-4" /> },
  ];

  return (
    <div className="grid h-full grid-cols-[264px_minmax(0,1fr)_420px] 2xl:grid-cols-[288px_minmax(0,1fr)_460px]">
      <aside className="min-h-0 border-r border-line bg-panel">
        <EvidenceList caseId={caseId} />
      </aside>
      <main className="min-h-0 min-w-0 bg-bg">
        <Player caseId={caseId} ev={ev} />
      </main>
      <aside className="flex min-h-0 flex-col border-l border-line bg-panel">
        <Tabs value={tab} onChange={setTab} items={items} compact />
        <div className="min-h-0 flex-1 overflow-y-auto">
          {tab === "sor" && <AskPanel caseId={caseId} ev={ev} />}
          {tab === "bulgular" && <FindingsPanel caseId={caseId} />}
          {tab === "kisiler" && <PeoplePanel caseId={caseId} ev={ev} />}
          {tab === "plakalar" && <PlatesPanel caseId={caseId} ev={ev} />}
          {tab === "iyilestir" && <EnhancePanel caseId={caseId} ev={ev} />}
          {tab === "saat" && <TimePanel ev={ev} />}
          {tab === "bilgi" && <InfoPanel caseId={caseId} ev={ev} />}
        </div>
      </aside>
    </div>
  );
}

