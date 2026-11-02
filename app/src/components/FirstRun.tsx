import { useQueryClient } from "@tanstack/react-query";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { qk, useSystem } from "../lib/hooks";
import { toastError } from "../store";
import { Button, Field, inputCls, Modal } from "./ui";

/** İlk açılış: bilgilendirme + isteğe bağlı API anahtarı + donanım bilgisi. */
export default function FirstRun() {
  const qc = useQueryClient();
  const { data: sys } = useSystem();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const accept = async () => {
    setBusy(true);
    try {
      if (key.trim()) await api.put("/api/settings/api-key", { key: key.trim() });
      await api.put("/api/settings", { notice_accepted: true });
      await qc.invalidateQueries({ queryKey: qk.settings });
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={() => {}}
      dismissable={false}
      title="AI Video Analizi'ne hoş geldiniz"
      width="max-w-xl"
      footer={
        <Button variant="primary" onClick={accept} busy={busy}>
          Okudum, başla
        </Button>
      }
    >
      <div className="space-y-5 leading-relaxed">
        <div className="flex gap-3 rounded-lg border border-line-2 bg-panel-2 p-3.5">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-ok" />
          <div className="space-y-2 text-[13px]">
            <p>
              Uygulama tamamen bilgisayarınızda çalışır. Hesap, kayıt ya da kullanım istatistiği yoktur. Tüm veriler
              uygulama klasöründeki <b>data</b> klasöründe durur.
            </p>
            <p>
              Yapay zekâya soru sorduğunuzda yalnızca seçilen kareler ya da kısa kesitler, seçtiğiniz AI sağlayıcısına
              (OpenRouter) gönderilir. Başka hiçbir veri bilgisayarınızdan çıkmaz.
            </p>
            <p className="text-muted">
              Yapay zekâ sonuçları soruşturma ipucudur; kesin bulgu sayılmadan önce kontrol edilmelidir. Kayıtların
              kullanımına ilişkin yasal sorumluluk kullanıcıya aittir.
            </p>
          </div>
        </div>
        <Field
          label={
            <span className="flex items-center gap-1.5">
              <KeyRound className="size-3.5" /> OpenRouter API anahtarı (isteğe bağlı)
            </span>
          }
          hint="Anahtar olmadan da videolar dönüştürülür, yerelde analiz edilir ve yerel arama yapılabilir. Anahtar Windows tarafından şifrelenerek saklanır."
        >
          <input className={inputCls} type="password" placeholder="sk-or-v1-…" value={key} onChange={(e) => setKey(e.target.value)} />
        </Field>
        {sys && (
          <div className="grid grid-cols-2 gap-2 text-[12.5px]">
            <div className="rounded-md border border-line bg-panel-2 px-3 py-2">
              <div className="text-muted">Yerel analiz</div>
              <div className="font-medium">{sys.inference.label}</div>
            </div>
            <div className="rounded-md border border-line bg-panel-2 px-3 py-2">
              <div className="text-muted">Video kodlayıcı</div>
              <div className="font-medium">{sys.encoders.find((e) => e.name === sys.encoder)?.label ?? sys.encoder}</div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
