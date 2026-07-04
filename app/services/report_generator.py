"""
PDF Rapor Üretici (İP-5: n8n üzerinden PDF raporlama)
------------------------------------------------------
Son 24 saatin anomali/İSG özetini PDF olarak üretir.
n8n workflow'u arıza anında GET /report/anomali-pdf çağırarak raporu alır
ve e-posta ekinde gönderir; dashboard'dan da indirilebilir.
"""

from datetime import datetime, timedelta, timezone
from fpdf import FPDF

# fpdf2 core fontları latin-1'dir; Türkçe karakterleri güvenli forma indirger.
_TR = str.maketrans("ğĞışİŞçÇöÖüÜ", "gGisIScCoOuU")


def _s(text: str) -> str:
    t = str(text).translate(_TR)
    for a, b in [("—", "-"), ("–", "-"), ("·", "."), ("’", "'"), ("‘", "'"),
                 ("“", '"'), ("”", '"'), ("⚠", "!"), ("₄", "4"), ("°", " ")]:
        t = t.replace(a, b)
    # latin-1 dışı kalan her karakteri güvenli forma indir
    return t.encode("latin-1", "replace").decode("latin-1")


class _Report(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 58, 95)
        self.cell(0, 8, _s("Maden Dijital İkiz — Anomali ve İSG Raporu"), ln=1)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, _s(f"CankaYazılım · Teknofest 2026 · Üretim: "
                           f"{datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"), ln=1)
        self.ln(3)
        self.set_draw_color(37, 99, 235)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, _s(f"Sayfa {self.page_no()} · Otomatik rapor (n8n/FastAPI)"), align="C")


def build_anomaly_report(summary: dict, anomalies: list, rul_rows: list) -> bytes:
    """
    summary  : {"toplam_okuma", "anomali_24h", "anomali_1h"}
    anomalies: [{"time","equipment_id","anomaly_score","description"}...]
    rul_rows : [{"equipment_id","rul_saat","saglik_yuzde","durum"}...]
    """
    pdf = _Report()
    pdf.add_page()

    # ── KPI özeti ──
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, _s("1. Genel Durum (Son 24 Saat)"), ln=1)
    pdf.set_font("Helvetica", "", 10)
    for label, val in [
        ("Toplam sensör okuması", f"{summary.get('toplam_okuma', 0):,}".replace(",", ".")),
        ("Anomali (24 saat)", summary.get("anomali_24h", 0)),
        ("Anomali (son 1 saat)", summary.get("anomali_1h", 0)),
    ]:
        pdf.cell(70, 6, _s(f"  {label}"), border=0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, _s(str(val)), ln=1)
        pdf.set_font("Helvetica", "", 10)
    pdf.ln(3)

    # ── RUL / sağlık ──
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _s("2. Ekipman Sağlığı — LSTM Kalan Faydalı Ömür (RUL)"), ln=1)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(226, 232, 240)
    for w, h in [(50, "Ekipman"), (35, "Sağlık (%)"), (40, "RUL (saat)"), (35, "Durum")]:
        pdf.cell(w, 6, _s(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for r in rul_rows:
        durum = r.get("durum", "-")
        pdf.set_text_color(*(185, 28, 28) if durum == "KRİTİK" else
                            (180, 83, 9) if durum == "UYARI" else (21, 128, 61))
        pdf.cell(50, 6, _s(r.get("equipment_id", "-")), border=1)
        pdf.cell(35, 6, _s(f"{r.get('saglik_yuzde', '-')}"), border=1)
        pdf.cell(40, 6, _s(f"{r.get('rul_saat', '-')}"), border=1)
        pdf.cell(35, 6, _s(durum), border=1, ln=1)
    pdf.set_text_color(15, 23, 42)
    pdf.ln(3)

    # ── Anomali listesi ──
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _s(f"3. Anomali Kayıtları ({len(anomalies)} adet)"), ln=1)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(226, 232, 240)
    for w, h in [(32, "Zaman (UTC)"), (28, "Ekipman"), (18, "Skor"), (112, "Açıklama")]:
        pdf.cell(w, 6, _s(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for a in anomalies[:40]:
        t = a.get("time", "")[:16].replace("T", " ")
        desc = _s(a.get("description") or "-")[:78]
        isg = "METAN" in (a.get("description") or "")
        pdf.set_text_color(*(194, 65, 12) if isg else (15, 23, 42))
        pdf.cell(32, 5.5, _s(t), border=1)
        pdf.cell(28, 5.5, _s(a.get("equipment_id", "-")), border=1)
        pdf.cell(18, 5.5, _s(f"{a.get('anomaly_score', 0):.2f}"), border=1)
        pdf.cell(112, 5.5, desc, border=1, ln=1)
    pdf.set_text_color(15, 23, 42)

    return bytes(pdf.output())
