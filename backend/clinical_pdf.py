"""Small, deterministic PDF summaries for reviewed MediKiosk records."""

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


_BUNDLED_DEVANAGARI_FONT = Path(__file__).resolve().parent / "fonts" / "NotoSansDevanagari-Regular.ttf"


def _font_name() -> str:
    # Bundle a Devanagari-capable font rather than depending on whatever the
    # host kiosk happens to have installed (Windows' Nirmala.ttf may be
    # missing on a machine without a Hindi language pack).
    for path in (_BUNDLED_DEVANAGARI_FONT, Path("C:/Windows/Fonts/Nirmala.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("MediKioskUnicode", str(path)))
                return "MediKioskUnicode"
            except Exception:
                pass
    return "Helvetica"


def _text(value, fallback="Not recorded") -> str:
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, dict):
        value = "; ".join(f"{key}: {_text(item, '')}" for key, item in value.items() if _text(item, ""))
    return str(value).strip() or fallback


def build_clinical_pdf(record: dict, audience: str, signoff: dict) -> bytes:
    """Return a patient-friendly or clinician-detail PDF from a signed snapshot."""
    data = record["data"]
    hpi = data.get("hpi") or {}
    drugs = data.get("drug_allergy_history") or {}
    font = _font_name()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font
    styles.add(ParagraphStyle("Centered", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17473d")))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story = [Paragraph("MediKiosk Clinical History", styles["Centered"]), Spacer(1, 4 * mm)]
    meta = [
        ["Patient", _text(record.get("patient_name"))],
        ["Medi ID", _text(record.get("patient_medi_id"))],
        ["Department", _text(record.get("department"))],
        ["Reviewed by", _text(signoff.get("signed_by_name"))],
        ["Reviewed at", _text(signoff.get("signed_at"))],
    ]
    table = Table(meta, colWidths=[38 * mm, 125 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f3ef")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b7ccc5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 5 * mm)]

    sections = [
        ("Main concern", data.get("chief_complaint")),
        ("Symptom history", hpi),
        ("Current medicines", drugs.get("current_medications")),
        ("Allergies", drugs.get("allergies")),
        ("Past medical history", data.get("past_medical_history")),
        ("Past surgical history", data.get("past_surgical_history")),
        ("Family history", data.get("family_history")),
        ("Personal history", data.get("personal_history")),
    ]
    if data.get("mode") == "ayush":
        sections.append(("Ayurveda assessment", data.get("ayush_assessment")))
    if audience == "clinician":
        sections.extend([
            ("Review of systems", data.get("review_of_systems")),
            ("Digitized documents", data.get("digitized_documents")),
            ("Red-flag status", data.get("red_flag_reason") if data.get("red_flag") else "No red flag recorded"),
            ("Record signature", signoff.get("signature_hash")),
        ])
    for heading, value in sections:
        story.append(Paragraph(heading, styles["Heading2"]))
        story.append(Paragraph(_text(value), styles["BodyText"]))
        story.append(Spacer(1, 3 * mm))
    if audience == "patient":
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("This is a reviewed history summary. It is not a diagnosis or prescription. Seek urgent care if symptoms worsen or an emergency develops.", styles["Italic"]))
    doc.build(story)
    return buffer.getvalue()
