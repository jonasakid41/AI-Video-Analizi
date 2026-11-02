import { create } from "zustand";

export type PanelTab = "sor" | "bulgular" | "kisiler" | "plakalar" | "iyilestir" | "saat" | "bilgi";
export type DrawMode = null | "alan" | "cizgi" | "kutu";
export type Box = [number, number, number, number];

export interface Marker {
  evidence_id: number;
  t: number;
  color: string;
  label: string;
}

export interface Toast {
  id: number;
  kind: "info" | "ok" | "error";
  text: string;
}

interface UIState {
  caseId: number | null;
  evidenceId: number | null;
  time: number;
  seekReq: { evidenceId: number; t: number; nonce: number } | null;
  tab: PanelTab;
  overlay: { boxes: boolean; labels: boolean; rois: boolean };
  drawMode: DrawMode;
  selBox: Box | null;
  focusBox: Box | null;
  markers: Marker[];
  clipIn: number | null;
  clipOut: number | null;
  settingsOpen: boolean;
  settingsTab: "ai" | "analiz" | "sistem";
  toasts: Toast[];
  openCase: (id: number | null) => void;
  selectEvidence: (id: number | null) => void;
  seek: (evidenceId: number, t: number, box?: Box | null) => void;
  setTime: (t: number) => void;
  setTab: (t: PanelTab) => void;
  toggleOverlay: (k: keyof UIState["overlay"]) => void;
  setDrawMode: (m: DrawMode) => void;
  setSelBox: (b: Box | null) => void;
  setMarkers: (m: Marker[]) => void;
  setClip: (which: "in" | "out" | "clear", t?: number) => void;
  setSettingsOpen: (v: boolean, tab?: "ai" | "analiz" | "sistem") => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
  dismiss: (id: number) => void;
}

let toastId = 0;

export const useUI = create<UIState>((set, get) => ({
  caseId: null,
  evidenceId: null,
  time: 0,
  seekReq: null,
  tab: "sor",
  overlay: { boxes: true, labels: true, rois: true },
  drawMode: null,
  selBox: null,
  focusBox: null,
  markers: [],
  clipIn: null,
  clipOut: null,
  settingsOpen: false,
  settingsTab: "ai",
  toasts: [],
  openCase: (id) => set({ caseId: id, evidenceId: null, time: 0, markers: [], selBox: null, drawMode: null }),
  selectEvidence: (id) => {
    if (id !== get().evidenceId) set({ evidenceId: id, time: 0, seekReq: null, selBox: null, focusBox: null, clipIn: null, clipOut: null });
  },
  // İstek hangi video içinse yalnızca o videonun oynatıcısı uygular ve tüketir
  seek: (evidenceId, t, box) => {
    if (evidenceId !== get().evidenceId) set({ evidenceId, time: 0, selBox: null, clipIn: null, clipOut: null });
    set({ seekReq: { evidenceId, t, nonce: Date.now() + Math.random() }, focusBox: box ?? null });
  },
  setTime: (t) => set({ time: t }),
  setTab: (tab) => set({ tab }),
  toggleOverlay: (k) => set({ overlay: { ...get().overlay, [k]: !get().overlay[k] } }),
  setDrawMode: (drawMode) => set({ drawMode }),
  setSelBox: (selBox) => set({ selBox }),
  setMarkers: (markers) => set({ markers }),
  setClip: (which, t) => {
    if (which === "clear") set({ clipIn: null, clipOut: null });
    else if (which === "in") set({ clipIn: t ?? get().time });
    else set({ clipOut: t ?? get().time });
  },
  setSettingsOpen: (settingsOpen, tab) => set(tab ? { settingsOpen, settingsTab: tab } : { settingsOpen }),
  toast: (text, kind = "info") => {
    const id = ++toastId;
    set({ toasts: [...get().toasts, { id, kind, text }] });
    setTimeout(() => get().dismiss(id), kind === "error" ? 7000 : 3500);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

export const toast = (text: string, kind?: Toast["kind"]) => useUI.getState().toast(text, kind);
export const toastError = (e: unknown) => toast(e instanceof Error ? e.message : String(e), "error");
