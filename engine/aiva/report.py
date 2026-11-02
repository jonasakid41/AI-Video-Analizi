"""PDF vaka raporu (ReportLab). Türkçe karakterler için Windows yazı tipleri kullanılır."""

from __future__ import annotations

import os
import time
from pathlib import Path

from . import __version__, cases, db, evidence, history, jobs, paths
from .query import findings_for
from .util import fmt_media_time

FONT, FONT_B = "Helvetica", "Helvetica-Bold"


def _fonts() -> tuple[str, str]:
    global FONT, FONT_B
    if FONT != "Helvetica":
        return FONT, FONT_B
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for reg, bold in (("arial.ttf", "arialbd.ttf"), ("segoeui.ttf", "segoeuib.ttf"), ("calibri.ttf", "calibrib.ttf")):
        if (windir / reg).exists() and (windir / bold).exists():
            pdfmetrics.registerFont(TTFont("TR", str(windir / reg)))
            pdfmetrics.registerFont(TTFont("TR-B", str(windir / bold)))
            FONT, FONT_B = "TR", "TR-B"
            break
    return FONT, FONT_B


def _fmt_dt(s: str | None) -> str:
    if not s:
        return "—"
    return s.replace("T", " ")[:19]


def build(case_id: int, include_candidates: bool = False) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    c = cases.get(case_id)
    if not c:
        raise KeyError("Vaka bulunamadı")
    font, bold = _fonts()
    st = {
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=17, leading=21, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=5,
                             textColor=colors.HexColor("#1f3a5f")),
        "p": ParagraphStyle("p", fontName=font, fontSize=9.5, leading=13),
        "small": ParagraphStyle("s", fontName=font, fontSize=7.8, leading=10, textColor=colors.HexColor("#444444")),
        "warn": ParagraphStyle("w", fontName=font, fontSize=8.5, leading=11, textColor=colors.HexColor("#8a4b00")),
    }

    def P(text: str, style: str = "p") -> Paragraph:
        return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), st[style])

    def table(rows: list[list], widths: list[float]) -> Table:
        t = Table([[P(x, "small") if not isinstance(x, (Paragraph, Image)) else x for x in r] for r in rows],
                  colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    out_dir = paths.exports_dir(case_id) / "raporlar"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"rapor_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=f"Vaka raporu — {c['name']}", author="AI Video Analizi")
    story: list = []
    story.append(P(f"Vaka Raporu — {c['name']}", "h1"))
    story.append(P(f"Oluşturma: {time.strftime('%d.%m.%Y %H:%M')} · AI Video Analizi {__version__}", "small"))
    if c["description"]:
        story += [Spacer(1, 4), P(c["description"])]
    story.append(Spacer(1, 6))
    story.append(P("Bu rapordaki yapay zekâ çıktıları soruşturma ipucudur; analist onayı olmadan kesin bulgu sayılmamalıdır. "
                   "AI ile büyütülmüş görüntüler gerçekte olmayan ayrıntı içerebilir ve ayrıca işaretlenmiştir.", "warn"))

    evs = evidence.list_for_case(case_id)
    story.append(P("1. Videolar", "h2"))
    rows = [["Dosya", "Kamera", "Süre / çözünürlük", "SHA-256", "Dönüştürme"]]
    for e in evs:
        res = f"{fmt_media_time(e['duration'] or 0)} · {e['width'] or '?'}×{e['height'] or '?'} · {e['fps'] or 0:.1f} fps"
        rows.append([e["original_name"], e["camera"] or "—", res, e["sha256"] or "—",
                     (e.get("strategy") or {}).get("name", "—")])
    story.append(table(rows, [38 * mm, 22 * mm, 34 * mm, 54 * mm, 30 * mm]))

    story.append(P("2. Saat düzeltmeleri", "h2"))
    rows = [["Dosya", "Kaynak", "Başlangıç (kamera → gerçek)", "Fark / kayma", "Son gerekçe"]]
    for e in evs:
        t = e["time"]
        ver = evidence.mapping_versions(e["id"])
        delta = t.get("duzeltme_farki_sn")
        drift = t.get("gunluk_kayma_sn")
        diff = "—" if delta is None else f"{delta:+.0f} sn" + (f" · {drift:+.1f} sn/gün" if drift else "")
        rows.append([e["original_name"], t.get("kaynak", "—"), f"{_fmt_dt(e['camera_start'])} → {_fmt_dt(e['real_start'])}",
                     diff, ver[0]["reason"] if ver else "—"])
    story.append(table(rows, [38 * mm, 18 * mm, 58 * mm, 28 * mm, 36 * mm]))

    fs = [f for f in findings_for(case_id) if include_candidates or f["status"] == "dogrulandi"]
    story.append(P(f"3. Bulgular ({len(fs)})", "h2"))
    if not fs:
        story.append(P("Onaylanmış bulgu yok." + ("" if include_candidates else " (Yalnızca 'Doğrulandı' durumundaki bulgular raporlanır.)")))
    names = {e["id"]: e for e in evs}
    for i, f in enumerate(fs, 1):
        ev = names.get(f["evidence_id"]) or {}
        img_cell: object = P("—", "small")
        if f.get("image"):
            ip = paths.data_dir() / f["image"]
            if ip.exists():
                img_cell = Image(str(ip), width=62 * mm, height=36 * mm, kind="proportional")
        info = [
            Paragraph(f"<b>{i}. {P(f['title']).text}</b>", st["p"]),
            P(f"Video: {ev.get('original_name', '—')} ({ev.get('camera') or '—'})", "small"),
            P(f"Gerçek saat: {_fmt_dt(f.get('real_t'))} · Kamera saati: {_fmt_dt(f.get('camera_t'))} · "
              f"Video içi: {fmt_media_time(f['t'] or 0)}", "small"),
            P(f"Kaynak: {f['source']} · Güven: {'%' + str(int((f['confidence'] or 0) * 100)) if f['confidence'] is not None else '—'}"
              f" · Durum: {f['status_label']}", "small"),
        ]
        if f["note"]:
            info.append(P(f"Not: {f['note']}", "small"))
        t = Table([[img_cell, info]], colWidths=[66 * mm, 112 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c4d0"))]))
        story += [t, Spacer(1, 4)]

    calls = db.rows("SELECT model, role, COUNT(*) n, SUM(cost) cost, SUM(tokens_in) tin, SUM(tokens_out) tout "
                    "FROM ai_calls WHERE case_id = ? GROUP BY model, role", (case_id,))
    story.append(P("4. Yapay zekâ kullanımı", "h2"))
    if calls:
        rows = [["Model", "Görev", "Çağrı", "Token (girdi/çıktı)", "Maliyet (USD)"]]
        for r in calls:
            rows.append([r["model"], r["role"], r["n"], f"{r['tin'] or 0} / {r['tout'] or 0}", f"{r['cost'] or 0:.4f}"])
        story.append(table(rows, [62 * mm, 26 * mm, 16 * mm, 40 * mm, 30 * mm]))
    else:
        story.append(P("Bu vakada bulut yapay zekâ modeli kullanılmadı; tüm analiz yerelde yapıldı."))
    enh = [h for h in history.list_for_case(case_id) if h["action"] == "iyilestirme"]
    if enh:
        story.append(P(f"İyileştirme işlemi: {len(enh)} (AI büyütme: {sum(1 for h in enh if h['detail'].get('ai'))})", "small"))

    story += [PageBreak(), P("5. İşlem geçmişi", "h2")]
    rows = [["Zaman", "İşlem", "Ayrıntı"]]
    for h in reversed(history.list_for_case(case_id, 300)):
        detail = ", ".join(f"{k}={v}" for k, v in (h["detail"] or {}).items() if k not in ("ozet",))[:220]
        rows.append([_fmt_dt(h["created_at"]), h["action"].replace("_", " "), detail])
    story.append(table(rows, [32 * mm, 38 * mm, 108 * mm]))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(16 * mm, 9 * mm, f"AI Video Analizi · {c['name']}")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Sayfa {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    history.log("rapor_olusturuldu", case_id, dosya=pdf.name, bulgu=len(fs))
    return pdf


@jobs.register("report")
def report_job(ctx: jobs.JobContext, params: dict) -> dict:
    ctx.progress(0.2, "Rapor hazırlanıyor")
    pdf = build(params["case_id"], bool(params.get("include_candidates")))
    return {"pdf": pdf.resolve().relative_to(paths.data_dir().resolve()).as_posix(), "path": str(pdf)}
