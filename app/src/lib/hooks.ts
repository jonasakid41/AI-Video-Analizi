import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, refresh, wsUrl } from "./api";
import { Mapping } from "./time";
import type {
  Activity, Case, Catalog, DetectionRow, Evaluation, Evidence, Face, Finding, HistoryRow, Job, Person, QueryRow, Roi, Settings,
  SystemInfo, TimeMappingData, Track,
} from "./types";

export const qk = {
  cases: ["cases"] as const,
  case: (id: number) => ["case", id] as const,
  evidence: (caseId: number) => ["evidence", caseId] as const,
  activity: (eid: number) => ["activity", eid] as const,
  tracks: (eid: number) => ["tracks", eid] as const,
  dets: (eid: number, chunk: number) => ["dets", eid, chunk] as const,
  rois: (eid: number) => ["rois", eid] as const,
  plates: (eid: number) => ["plates", eid] as const,
  faces: (eid: number) => ["faces", eid] as const,
  people: (caseId: number) => ["people", caseId] as const,
  findings: (caseId: number) => ["findings", caseId] as const,
  queries: (caseId: number) => ["queries", caseId] as const,
  query: (id: number) => ["query", id] as const,
  history: (caseId: number) => ["history", caseId] as const,
  time: (eid: number) => ["time", eid] as const,
  jobs: ["jobs"] as const,
  settings: ["settings"] as const,
  system: ["system"] as const,
  catalog: ["catalog"] as const,
};

export const useCases = () => useQuery({ queryKey: qk.cases, queryFn: () => api.get<Case[]>("/api/cases") });
export const useCase = (id: number | null) =>
  useQuery({ queryKey: qk.case(id ?? 0), queryFn: () => api.get<Case>(`/api/cases/${id}`), enabled: !!id });
export const useEvidenceList = (caseId: number | null) =>
  useQuery({ queryKey: qk.evidence(caseId ?? 0), queryFn: () => api.get<Evidence[]>(`/api/cases/${caseId}/evidence`), enabled: !!caseId });

export function useEvidence(caseId: number | null, evidenceId: number | null): Evidence | undefined {
  const { data } = useEvidenceList(caseId);
  return useMemo(() => data?.find((e) => e.id === evidenceId), [data, evidenceId]);
}

export function useMapping(ev: Evidence | undefined) {
  return useMemo(() => new Mapping(ev?.time_mapping as TimeMappingData | undefined), [ev?.time_mapping]);
}

const ready = (ev?: Evidence) => !!ev && ev.status === "hazir";

export const useActivity = (ev?: Evidence) =>
  useQuery({ queryKey: qk.activity(ev?.id ?? 0), queryFn: () => api.get<Activity>(`/api/evidence/${ev!.id}/activity`, { buckets: 800 }),
    enabled: ready(ev) && !!ev?.analyzed });
export const useTracks = (ev?: Evidence) =>
  useQuery({ queryKey: qk.tracks(ev?.id ?? 0), queryFn: () => api.get<Track[]>(`/api/evidence/${ev!.id}/tracks`), enabled: ready(ev) && !!ev?.analyzed });
export const useRois = (eid: number | null) =>
  useQuery({ queryKey: qk.rois(eid ?? 0), queryFn: () => api.get<Roi[]>(`/api/evidence/${eid}/rois`), enabled: !!eid });
export const usePlates = (ev?: Evidence) =>
  useQuery({ queryKey: qk.plates(ev?.id ?? 0), queryFn: () => api.get<Track[]>(`/api/evidence/${ev!.id}/plates`), enabled: ready(ev) && !!ev?.analyzed });
export const useFaces = (ev?: Evidence) =>
  useQuery({ queryKey: qk.faces(ev?.id ?? 0), queryFn: () => api.get<Face[]>(`/api/evidence/${ev!.id}/faces`), enabled: ready(ev) && !!ev?.analyzed });
export const usePeople = (caseId: number | null) =>
  useQuery({ queryKey: qk.people(caseId ?? 0), queryFn: () => api.get<Person[]>(`/api/cases/${caseId}/people`), enabled: !!caseId });
export const useFindings = (caseId: number | null) =>
  useQuery({ queryKey: qk.findings(caseId ?? 0), queryFn: () => api.get<Finding[]>(`/api/cases/${caseId}/findings`), enabled: !!caseId });
export const useQueries = (caseId: number | null) =>
  useQuery({ queryKey: qk.queries(caseId ?? 0), queryFn: () => api.get<QueryRow[]>(`/api/cases/${caseId}/queries`), enabled: !!caseId });
export const useQueryRow = (id: number | null) =>
  useQuery({ queryKey: qk.query(id ?? 0), queryFn: () => api.get<QueryRow>(`/api/queries/${id}`), enabled: !!id });
export const useEvaluations = (queryId: number | null) =>
  useQuery({ queryKey: ["evals", queryId ?? 0], queryFn: () => api.get<Evaluation[]>(`/api/queries/${queryId}/evaluations`), enabled: !!queryId });
export const useHistory = (caseId: number | null) =>
  useQuery({ queryKey: qk.history(caseId ?? 0), queryFn: () => api.get<HistoryRow[]>(`/api/cases/${caseId}/history`), enabled: !!caseId });
export const useTimeInfo = (eid: number | null) =>
  useQuery({
    queryKey: qk.time(eid ?? 0),
    queryFn: () => api.get<{ mapping: TimeMappingData; summary: any; versions: { version: number; reason: string; created_at: string }[]; readings: { t: number; text: string; parsed: string }[] }>(`/api/evidence/${eid}/time`),
    enabled: !!eid,
  });
export const useSettings = () => useQuery({ queryKey: qk.settings, queryFn: () => api.get<Settings>("/api/settings") });
export const useSystem = () => useQuery({ queryKey: qk.system, queryFn: () => api.get<SystemInfo>("/api/system"), staleTime: 60_000 });
export const useCatalog = (enabled = true) =>
  useQuery({ queryKey: qk.catalog, queryFn: () => api.get<Catalog>("/api/models"), staleTime: 3600_000, enabled, retry: 1 });

export const usePower = () =>
  useQuery({ queryKey: ["power"], queryFn: () => api.get<{ on_battery: boolean; percent: number | null }>("/api/power"), refetchInterval: 60_000 });

export const useJobs = () =>
  useQuery({ queryKey: qk.jobs, queryFn: () => api.get<Job[]>("/api/jobs"), refetchInterval: 15_000 });

/** Belirli bir anın çevresindeki tespitler: 20 sn'lik parçalar halinde önbelleklenir. */
export const CHUNK = 20;
export function useDetectionChunk(ev: Evidence | undefined, t: number) {
  const chunk = Math.floor(t / CHUNK);
  return useQuery({
    queryKey: qk.dets(ev?.id ?? 0, chunk),
    queryFn: () => api.get<DetectionRow[]>(`/api/evidence/${ev!.id}/detections/range`, { t0: chunk * CHUNK - 1, t1: (chunk + 1) * CHUNK + 1 }),
    enabled: ready(ev) && !!ev?.analyzed,
    staleTime: Infinity,
  });
}

function invalidateForJob(qc: QueryClient, j: Job) {
  const cid = j.case_id ?? 0;
  const eid = j.evidence_id ?? 0;
  const inv = (key: readonly unknown[]) => qc.invalidateQueries({ queryKey: key });
  switch (j.kind) {
    case "ingest":
      inv(qk.evidence(cid));
      inv(qk.cases);
      break;
    case "analyze":
      inv(qk.evidence(cid));
      inv(qk.activity(eid));
      inv(qk.tracks(eid));
      inv(qk.plates(eid));
      inv(qk.faces(eid));
      inv(qk.people(cid));
      qc.removeQueries({ queryKey: ["dets", eid] });
      break;
    case "osd_scan":
      inv(qk.evidence(cid));
      inv(qk.time(eid));
      break;
    case "query":
      inv(qk.queries(cid));
      break;
    case "report":
      inv(qk.history(cid));
      break;
    case "evaluate":
      qc.invalidateQueries({ queryKey: ["evals"] });
      break;
  }
  inv(qk.history(cid));
}

/** Motor olaylarını (WebSocket) dinler; iş ve video güncellemelerini önbelleğe işler. */
export function useEngineEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let retry = 500;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let reconnecting = false;
    const open = () => {
      if (stop) return;
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        retry = 500;
        // Motor yeniden başladıysa tüm veriler (ve medya adresleri) yeni bağlantıyla yenilenir
        if (reconnecting) qc.invalidateQueries();
        else qc.invalidateQueries({ queryKey: qk.jobs });
        reconnecting = false;
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "job") {
          const j: Job = msg.job;
          qc.setQueryData<Job[]>(qk.jobs, (old) => {
            const list = old ? [...old] : [];
            const i = list.findIndex((x) => x.id === j.id);
            if (i >= 0) list[i] = j;
            else list.unshift(j);
            return list.slice(0, 200);
          });
          if (["tamamlandi", "hata", "iptal"].includes(j.status)) invalidateForJob(qc, j);
        } else if (msg.type === "evidence") {
          const e: Evidence = msg.evidence;
          qc.setQueryData<Evidence[]>(qk.evidence(e.case_id), (old) =>
            old ? old.map((x) => (x.id === e.id ? e : x)).concat(old.some((x) => x.id === e.id) ? [] : [e]) : old);
        } else if (msg.type === "query") {
          qc.invalidateQueries({ queryKey: qk.queries(msg.case_id) });
          qc.invalidateQueries({ queryKey: qk.query(msg.query_id) });
        } else if (msg.type === "analysis") {
          qc.removeQueries({ queryKey: ["dets", msg.evidence_id] });
        }
      };
      ws.onclose = () => {
        if (stop) return;
        reconnecting = true;
        timer = setTimeout(async () => {
          await refresh().catch(() => false);
          open();
        }, retry);
        retry = Math.min(retry * 2, 8000);
      };
    };
    open();
    return () => {
      stop = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [qc]);
}

/** Değer belirli bir süre değişmeden kalınca güncellenir (ör. oynatırken kare önizlemesi). */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setV(value), ms);
    return () => clearTimeout(h);
  }, [value, ms]);
  return v;
}

/** Bir işin sonucunu izler (iş listesi önbelleğinden). */
export function useJob(id: number | null): Job | undefined {
  const { data } = useJobs();
  return useMemo(() => data?.find((j) => j.id === id), [data, id]);
}
