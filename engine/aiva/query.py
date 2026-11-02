"""Soru sorma işi ve bulgular.

Modlar:
  hizli  — yalnızca yerel arama (internet/anahtar gerekmez, ücretsiz)
  dogrula — yerel adaylar seçilen görsel modele doğrulatılır (varsayılan)
  derin  — ek olarak en iyi adayların çevresindeki kısa video kesiti modele izletilir
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from . import cases, db, events, evidence, history, jobs, paths, settings
from .ai import catalog, client, planner, prompts
from .ai import search as searchmod
from .ai import verify as verifymod
from .util import dumps, imwrite, loads, now_iso

MODES = {"hizli": "Hızlı (yerel)", "dogrula": "AI doğrulamalı", "derin": "Derin (video analizi)"}


def create(case_id: int, question: str, options: dict) -> dict:
    if not cases.get(case_id):
        raise KeyError("Vaka bulunamadı")
    question = question.strip()
    if len(question) < 3:
        raise ValueError("Soru çok kısa")
    mode = options.get("mode") or "dogrula"
    if mode != "hizli" and not client.configured():
        mode = "hizli"
        options["mode_note"] = "API anahtarı olmadığı için yalnızca yerel arama yapıldı"
    options["mode"] = mode
    qid = db.insert("queries", {"case_id": case_id, "question": question, "options": dumps(options),
                                "status": "beklemede", "created_at": now_iso()})
    jid = jobs.submit("query", {"query_id": qid}, case_id=case_id)
    return {"query_id": qid, "job_id": jid, "mode": mode}


def get(query_id: int) -> dict:
    q = db.row("SELECT * FROM queries WHERE id = ?", (query_id,))
    if not q:
        raise KeyError("Sorgu bulunamadı")
    for k in ("options", "plan", "results"):
        q[k] = loads(q[k], {} if k != "results" else [])
    q["labels"] = loads(q.get("labels"), {}) or {}
    return q


def list_for_case(case_id: int, limit: int = 100) -> list[dict]:
    out = db.rows("SELECT id, question, status, answer, cost, created_at, finished_at, error, options FROM queries "
                  "WHERE case_id = ? ORDER BY id DESC LIMIT ?", (case_id, limit))
    for q in out:
        q["options"] = loads(q["options"], {})
    return out


def delete(query_id: int) -> None:
    db.execute("DELETE FROM queries WHERE id = ?", (query_id,))


def estimate(case_id: int, question: str, options: dict) -> dict:
    """Çalıştırmadan önce yaklaşık maliyet (yerel plan + yerel adaylarla)."""
    s = settings.load()["ai"]
    plan = planner.local_plan(question)
    cands, notes = searchmod.find(case_id, plan, options.get("evidence_ids"), options.get("roi_id"),
                                  int(options.get("max_candidates") or s["max_candidates"]))
    mode = options.get("mode") or "dogrula"
    cost = 0.0
    if mode != "hizli" and cands:
        cost += catalog.estimate(s["roles"]["planner"], 700, [], 300)
        cost += verifymod.estimate(s["roles"]["verifier"], cands, s["send_context_frame"], int(s["batch_size"]))
        if mode == "derin":
            cost += 3 * catalog.estimate(s["roles"]["video"], 25000, [], 400)
    free = all((catalog.get(s["roles"][r]) or {}).get("free") for r in ("planner", "verifier"))
    return {"candidates": len(cands), "cost_usd": round(cost, 4), "free": free, "mode": mode, "notes": notes}


def _event_lines(items: list[dict], limit: int = 25) -> list[str]:
    lines = []
    for i in items[:limit]:
        when = _tr_dt(i.get("real_t")) or f"{i['t']:.0f}. sn"
        dur = (i.get("t1") or i["t"]) - (i.get("t0") or i["t"])
        if dur >= 1:
            when += f" ({dur:.0f} sn)"
        detail = f" — {i['color_text']}" if i.get("color_text") else ""
        flag = " (incelenmeli)" if i.get("cls_tr") == "tanımlanamayan hareket" else ""
        lines.append(f"• {when} · {i.get('camera') or i.get('video')}: {i.get('cls_tr') or 'hareket'}{detail}{flag}")
    if len(items) > limit:
        lines.append(f"• … ve {len(items) - limit} olay daha (sonuç listesinde)")
    return lines


def _summary(question: str, items: list[dict], model: str | None, case_id: int, qid: int,
             notes: list[str] | None = None, events_mode: bool = False) -> tuple[str, float]:
    notes = notes or []
    if events_mode and items:
        local = "Önemli olaylar (zaman sırasıyla):\n" + "\n".join(_event_lines(items))
        if model and client.configured():
            try:
                res = client.chat(model, [{"role": "system", "content": prompts.ANSWER_SYSTEM},
                                          {"role": "user", "content": f"Soru: {question}\nOlay listesi:\n{local}"}],
                                  role="ozet", case_id=case_id, query_id=qid, max_tokens=600)
                return res["content"].strip(), res["cost"]
            except client.AIError:
                pass
        return local, 0.0
    matched = [i for i in items if i.get("verdict", {}).get("match")]
    verified = any("verdict" in i for i in items)
    if verified and not matched:
        return _local_answer(question, items, notes), 0.0
    use = matched or items[:8]
    if model and client.configured() and use:
        lines = []
        for i in use[:12]:
            v = i.get("verdict") or {}
            when = _tr_dt(i.get("real_t")) or f"{i['t']:.0f}. sn"
            lines.append(f"- {when} | {i.get('camera') or i.get('video')} | {i.get('cls_tr') or 'kare'} | "
                         f"{v.get('explanation') or i.get('color_text') or ''} | plaka: {v.get('plate') or i.get('plate') or '-'}")
        try:
            res = client.chat(model, [{"role": "system", "content": prompts.ANSWER_SYSTEM},
                                      {"role": "user", "content": f"Soru: {question}\nSonuçlar:\n" + "\n".join(lines)}],
                              role="ozet", case_id=case_id, query_id=qid, max_tokens=500)
            return res["content"].strip(), res["cost"]
        except client.AIError:
            pass
    return _local_answer(question, items, notes), 0.0


def _tr_dt(iso: str | None) -> str:
    """2026-10-28T14:52:10 → 28.10.2026 14:52:10"""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M:%S")
    except ValueError:
        return iso.replace("T", " ")


def _local_answer(question: str, items: list[dict], notes: list[str] | tuple = ()) -> str:
    reasons = [n for n in notes if n] if notes else []
    if not items:
        msg = "Bu soruya uyan bir sonuç bulunamadı."
        if reasons:
            return msg + " Nedeni: " + " ".join(r.rstrip(".") + "." for r in reasons[:3])
        return msg + " Saat aralığını genişletmeyi ya da soruyu farklı ifade etmeyi deneyin."
    matched = [i for i in items if i.get("verdict", {}).get("match")]
    verified = any("verdict" in i for i in items)
    use = matched if verified else items
    if verified and not matched:
        widened = any("genişletildi" in r for r in reasons)
        return (f"{sum(1 for i in items if 'verdict' in i)} aday incelendi"
                + (" (arama genişletildi)" if widened else "")
                + ", model hiçbirinde soruya uyan bir durum görmedi. Soruyu farklı ifade etmeyi, saat aralığını "
                  "ya da kapsamı değiştirmeyi deneyin.")
    kinds = Counter(i.get("cls_tr") or "kare" for i in use)
    first = min(use, key=lambda i: i.get("real_t") or str(i["t"]))
    when = _tr_dt(first.get("real_t")) or f"videonun {first['t']:.0f}. saniyesi"
    parts = ", ".join(f"{n} {k}" for k, n in kinds.most_common(4))
    head = "Model doğrulamasıyla" if verified else "Yerel analize göre"
    return f"{head} {len(use)} sonuç bulundu ({parts}). İlk görülme: {when}. Sonuçları tek tek kontrol edip onaylayın."


@jobs.register("query")
def query_job(ctx: jobs.JobContext, params: dict) -> dict:
    qid = params["query_id"]
    q = get(qid)
    case_id = q["case_id"]
    opts = q["options"]
    s = settings.load()["ai"]
    roles = s["roles"]
    mode = opts.get("mode", "dogrula")
    db.update("queries", qid, {"status": "calisiyor"})
    cost = 0.0
    tin = tout = 0
    try:
        ctx.progress(0.05, "Soru çözümleniyor")
        plan, use = planner.plan(q["question"], roles["planner"] if mode != "hizli" else None, case_id, qid)
        cost += use["cost"]
        tin += use["in"]
        tout += use["out"]
        db.update("queries", qid, {"plan": dumps(plan)})

        ctx.progress(0.15, "Yerel adaylar aranıyor")
        limit = int(opts.get("max_candidates") or s["max_candidates"])
        cands, notes = searchmod.find(case_id, plan, opts.get("evidence_ids"), opts.get("roi_id"), limit)
        if plan.get("warning"):
            notes.insert(0, plan["warning"])
        if opts.get("mode_note"):
            notes.insert(0, opts["mode_note"])
        events_mode = False
        if plan.get("intent") == "ozet":
            ev_items, ev_notes = searchmod.case_events(case_id, plan, opts.get("evidence_ids"))
            if ev_items:
                cands = ev_items[:limit]
                events_mode = True  # olay listesi zaten "ne oldu" sorusunun cevabı; kare doğrulaması gerekmez
            notes += ev_notes

        verdicts: dict[str, dict] = {}
        if mode in ("dogrula", "derin") and not events_mode:
            budget = float(opts.get("budget_usd") or s["budget_per_query_usd"])
            spent = 0.0
            if not cands:
                # Yerel analiz bir şey bulamadı: model videolardan düzenli aralıklı kareleri doğrudan incelesin
                cands = searchmod.expand(case_id, plan, opts.get("evidence_ids"), opts.get("roi_id"), min(limit, 24), [])
                if cands:
                    notes.append(f"Yerel analiz aday bulamadı; videolardan {len(cands)} kare doğrudan modele incelettirildi")
            pending = list(cands)
            question = plan.get("verify_question") or q["question"]
            for rnd in (1, 2):
                if not pending:
                    break
                est = verifymod.estimate(roles["verifier"], pending, s["send_context_frame"], int(s["batch_size"]))
                left = budget - spent if budget > 0 else float("inf")
                if est > left and len(pending) > 4:
                    keep = max(4, int(len(pending) * max(0.0, left) / est)) if left > 0 else 0
                    notes.append(f"Bütçe sınırı nedeniyle {len(pending)} adaydan {keep} tanesi incelendi "
                                 f"(bütçe ${budget:.2f}).")
                    pending = pending[:keep]
                if not pending:
                    break
                label = "Model doğruluyor" if rnd == 1 else "Arama genişletildi, model yeni kareleri inceliyor"
                ctx.progress(0.25 if rnd == 1 else 0.55, f"{label} ({len(pending)} aday)")
                v, vu = verifymod.verify(pending, question, roles["verifier"], case_id=case_id, query_id=qid,
                                         batch=int(s["batch_size"]), with_context=bool(s["send_context_frame"]),
                                         progress=lambda x, rnd=rnd: ctx.progress((0.25 if rnd == 1 else 0.55) + 0.28 * x, label))
                verdicts.update(v)
                spent += vu["cost"]
                cost += vu["cost"]
                tin += vu["in"]
                tout += vu["out"]
                notes += [e for e in sorted(set(vu["errors"]))[:3] if e not in notes]
                if rnd == 2 or any(x["match"] for x in v.values()) or vu["errors"]:
                    break
                # 1. turda eşleşme yok: daha önce bakılmayan anlardan yeni karelerle ikinci tur
                extra = searchmod.expand(case_id, plan, opts.get("evidence_ids"), opts.get("roi_id"), 16, cands)
                if not extra:
                    break
                notes.append(f"İlk turda eşleşme çıkmadı; arama genişletildi ({len(extra)} ek kare)")
                pending = extra
                cands = cands + extra
        items = [c.to_dict() for c in cands]
        for it in items:
            if it["id"] in verdicts:
                it["verdict"] = verdicts[it["id"]]
        if not events_mode:
            items.sort(key=lambda i: (bool(i.get("verdict", {}).get("match")), i.get("verdict", {}).get("confidence", 0),
                                      i["score"]), reverse=True)

        video_notes = []
        if mode == "derin" and items:
            top = [i for i in items if i.get("verdict", {}).get("match")][:3] or items[:2]
            by_id = {c.id: c for c in cands}
            for k, it in enumerate(top):
                ctx.progress(0.82 + 0.1 * k / max(1, len(top)), "Video kesiti inceleniyor")
                c = by_id.get(it["id"]) or searchmod.Candidate(**{k2: v for k2, v in it.items() if k2 != "verdict"})
                res, vu = verifymod.analyze_clip(c, q["question"], roles["video"], case_id=case_id, query_id=qid)
                cost += vu["cost"]
                tin += vu["in"]
                tout += vu["out"]
                if res:
                    it["video_analysis"] = res
                    video_notes.append(res)

        ctx.progress(0.94, "Cevap yazılıyor")
        answer, c2 = _summary(q["question"], items, roles["planner"] if mode != "hizli" else None, case_id, qid,
                              notes, events_mode)
        cost += c2
        db.update("queries", qid, {
            "status": "tamamlandi", "results": dumps(items), "answer": answer, "cost": round(cost, 6),
            "tokens_in": tin, "tokens_out": tout, "finished_at": now_iso(),
            "options": dumps({**opts, "notes": notes, "models": {k: roles[k] for k in ("planner", "verifier", "video")}}),
        })
        history.log("soru_soruldu", case_id, soru=q["question"], mod=MODES.get(mode, mode), aday=len(items),
                    eslesen=sum(1 for i in items if i.get("verdict", {}).get("match")), maliyet_usd=round(cost, 4))
        events.publish("query", query_id=qid, case_id=case_id)
        return {"query_id": qid, "results": len(items), "cost": cost}
    except jobs.Cancelled:
        db.update("queries", qid, {"status": "iptal", "finished_at": now_iso()})
        raise
    except Exception as e:
        db.update("queries", qid, {"status": "hata", "error": str(e), "finished_at": now_iso(), "cost": cost})
        events.publish("query", query_id=qid, case_id=case_id)
        raise


# --- bulgular ------------------------------------------------------------------------------

FINDING_STATUS = {"aday": "Aday", "dogrulandi": "Doğrulandı", "reddedildi": "Reddedildi"}


def finding_create(case_id: int, evidence_id: int | None, t: float | None, title: str, note: str = "",
                   source: str = "elle", confidence: float | None = None, box: list[float] | None = None,
                   data: dict | None = None) -> dict:
    image = None
    if evidence_id is not None and t is not None:
        ev = evidence.require(evidence_id)
        src = evidence.evidence_file(ev)
        if src:
            from .media import frames
            got = frames.frame_at(src, t)
            if got:
                img = got[1].copy()
                if box:
                    import cv2
                    H, W = img.shape[:2]
                    x, y, w, h = box
                    cv2.rectangle(img, (int(x * W), int(y * H)), (int((x + w) * W), int((y + h) * H)), (0, 220, 255), 2)
                p = paths.exports_dir(case_id) / "bulgular" / f"bulgu_{now_iso().replace(':', '').replace('+', '_')}_{evidence_id}_{int(t * 1000)}.jpg"
                imwrite(p, img, 92)
                image = p.resolve().relative_to(paths.data_dir().resolve()).as_posix()
    fid = db.insert("findings", {"case_id": case_id, "evidence_id": evidence_id, "t": t, "title": title.strip() or "Bulgu",
                                 "note": note, "source": source, "confidence": confidence, "image": image,
                                 "status": "aday", "data": dumps({**(data or {}), "box": box}), "created_at": now_iso()})
    history.log("bulgu_eklendi", case_id, evidence_id, baslik=title, kaynak=source, t=t)
    return finding_get(fid)


def finding_get(fid: int) -> dict:
    f = db.row("SELECT * FROM findings WHERE id = ?", (fid,))
    if not f:
        raise KeyError("Bulgu bulunamadı")
    f["data"] = loads(f["data"], {})
    f["status_label"] = FINDING_STATUS.get(f["status"], f["status"])
    if f["evidence_id"] and f["t"] is not None:
        m = evidence.get_mapping(f["evidence_id"])
        cam, real = m.to_camera(f["t"]), m.to_real(f["t"])
        f["camera_t"] = cam.isoformat(timespec="seconds") if cam else None
        f["real_t"] = real.isoformat(timespec="seconds") if real else None
    return f


def findings_for(case_id: int) -> list[dict]:
    return [finding_get(r["id"]) for r in db.rows("SELECT id FROM findings WHERE case_id = ? ORDER BY t IS NULL, id", (case_id,))]


def finding_update(fid: int, status: str | None = None, note: str | None = None, title: str | None = None) -> dict:
    f = finding_get(fid)
    data = {}
    if status:
        if status not in FINDING_STATUS:
            raise ValueError("Geçersiz durum")
        data["status"] = status
    if note is not None:
        data["note"] = note
    if title is not None:
        data["title"] = title
    if data:
        db.update("findings", fid, data)
        history.log("bulgu_guncellendi", f["case_id"], f["evidence_id"], bulgu=fid, **data)
    return finding_get(fid)


def finding_delete(fid: int) -> None:
    f = finding_get(fid)
    db.execute("DELETE FROM findings WHERE id = ?", (fid,))
    history.log("bulgu_silindi", f["case_id"], f["evidence_id"], bulgu=fid)
