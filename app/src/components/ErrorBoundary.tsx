import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportError } from "../lib/api";

type Props = { children: ReactNode; area: string; resetKey?: unknown; full?: boolean };
type State = { error: Error | null };

/** Bir bileşendeki çizim hatası tüm arayüzü kaldırmasın (önceden geriye siyah ekran kalıyordu).
 *  Hata data/logs/arayuz.log dosyasına yazılır; yalnızca o bölüm hata mesajı gösterir. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportError(this.props.area, error, info.componentStack ?? "");
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const retry = () => this.setState({ error: null });
    if (this.props.full) {
      return (
        <div className="flex h-full items-center justify-center p-10">
          <div className="max-w-lg space-y-3 rounded-xl border border-danger/40 bg-panel p-6">
            <div className="flex items-center gap-2 text-danger">
              <AlertTriangle className="size-5" />
              <h1 className="text-base font-semibold">Arayüzde beklenmeyen bir hata oluştu</h1>
            </div>
            <p className="selectable break-words font-mono text-[12px] text-muted">{error.message}</p>
            <p className="text-[12.5px] text-faint">
              Verileriniz etkilenmedi. Ayrıntı <span className="font-mono">data/logs/arayuz.log</span> dosyasına yazıldı.
            </p>
            <div className="flex gap-2">
              <button onClick={() => window.location.reload()} className="rounded-md bg-accent-strong px-3 py-1.5 text-[12.5px] font-medium text-white cursor-pointer">
                Yeniden yükle
              </button>
              <button onClick={retry} className="rounded-md border border-line-2 px-3 py-1.5 text-[12.5px] text-muted hover:text-text cursor-pointer">
                Devam et
              </button>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="m-3 space-y-2 rounded-lg border border-danger/40 bg-danger/5 p-3 text-[12.5px]">
        <div className="flex items-center gap-2 font-medium text-danger">
          <AlertTriangle className="size-4" />
          Bu bölüm görüntülenemedi
        </div>
        <div className="selectable break-words font-mono text-[11.5px] text-muted">{error.message}</div>
        <button onClick={retry} className="flex items-center gap-1.5 rounded-md border border-line-2 px-2.5 py-1 text-[12px] text-muted hover:text-text cursor-pointer">
          <RotateCcw className="size-3.5" />
          Tekrar dene
        </button>
      </div>
    );
  }
}
