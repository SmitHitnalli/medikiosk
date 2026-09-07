"""Generate the current MediKiosk complete guide and concise handbook."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf"
COMPLETE = OUT / "MediKiosk_Complete_Guide_v4.pdf"
HANDBOOK = OUT / "MediKiosk_Handbook_v4.pdf"

NAVY = colors.HexColor("#0B3442")
TEAL = colors.HexColor("#078C86")
MINT = colors.HexColor("#E7F5F2")
BLUE = colors.HexColor("#E9F0FB")
AMBER = colors.HexColor("#F5B940")
AMBER_BG = colors.HexColor("#FFF6DE")
RED = colors.HexColor("#B42318")
RED_BG = colors.HexColor("#FDECEA")
GREEN = colors.HexColor("#207A4A")
GREEN_BG = colors.HexColor("#E9F6EE")
INK = colors.HexColor("#17313B")
MUTED = colors.HexColor("#536A73")
GRID = colors.HexColor("#B8C9CE")

S = getSampleStyleSheet()
S.add(ParagraphStyle(name="Cover", parent=S["Title"], fontName="Helvetica-Bold", fontSize=27, leading=31, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8))
S.add(ParagraphStyle(name="CoverSub", parent=S["Normal"], fontSize=11.5, leading=16, textColor=MUTED, alignment=TA_CENTER, spaceAfter=6))
S.add(ParagraphStyle(name="Section", parent=S["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=8))
S.add(ParagraphStyle(name="H2x", parent=S["Heading2"], fontName="Helvetica-Bold", fontSize=11.4, leading=14, textColor=TEAL, spaceBefore=7, spaceAfter=4))
S.add(ParagraphStyle(name="Bodyx", parent=S["BodyText"], fontSize=9.1, leading=12.6, textColor=INK, spaceAfter=4.5))
S.add(ParagraphStyle(name="Bulletx", parent=S["BodyText"], fontSize=8.9, leading=12.2, textColor=INK, leftIndent=12, firstLineIndent=-7, bulletIndent=3, spaceAfter=2.6))
S.add(ParagraphStyle(name="Smallx", parent=S["BodyText"], fontSize=7.5, leading=9.8, textColor=MUTED, spaceAfter=2))
S.add(ParagraphStyle(name="Tiny", parent=S["BodyText"], fontSize=6.8, leading=8.7, textColor=INK))
S.add(ParagraphStyle(name="Callout", parent=S["BodyText"], fontName="Helvetica-Bold", fontSize=9.3, leading=13, textColor=NAVY, backColor=MINT, borderColor=TEAL, borderWidth=.7, borderPadding=7, spaceBefore=5, spaceAfter=7))
S.add(ParagraphStyle(name="Warn", parent=S["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=12.5, textColor=RED, backColor=RED_BG, borderColor=RED, borderWidth=.6, borderPadding=7, spaceBefore=5, spaceAfter=7))
S.add(ParagraphStyle(name="CodeX", parent=S["BodyText"], fontName="Courier", fontSize=7.4, leading=9.6, textColor=INK, backColor=colors.HexColor("#F2F5F6"), borderPadding=6, spaceAfter=5))


def p(text, style="Bodyx"):
    return Paragraph(text, S[style])


def bullets(items):
    return [p("- " + escape(item), "Bulletx") for item in items]


def tbl(headers, rows, widths=None, tiny=False):
    body_style = "Tiny" if tiny else "Smallx"
    data = [[p(escape(str(value)), "Smallx") for value in headers]]
    data += [[p(escape(str(value)), body_style) for value in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), .35, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6FAFA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def title(story, number, name, note=None):
    story.append(p(f"{number:02d}  {escape(name)}", "Section"))
    if note:
        story.append(p(escape(note), "Callout"))


def new_page(story):
    story.append(PageBreak())


def decor(label):
    def draw(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 11 * mm, width, 11 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(15 * mm, height - 7 * mm, "MEDIKIOSK  /  SIH26047")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.3)
        canvas.drawString(15 * mm, 9 * mm, label)
        canvas.drawRightString(width - 15 * mm, 9 * mm, str(doc.page))
        canvas.restoreState()
    return draw


def doc_for(path, label):
    doc = BaseDocTemplate(str(path), pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=18 * mm, bottomMargin=15 * mm, title=label, author="MediKiosk")
    doc.addPageTemplates(PageTemplate(id="main", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")], onPage=decor(label)))
    return doc


def coverage_rows():
    return [
        ("Adaptive voice and touch history", "COVERED", "Speak and Chat flows; server-selected questions; automatic prompt-listen-confirm voice flow; touch controls and typed fallback."),
        ("Indian-language ASR", "PARTIAL", "English and Hindi work locally. Bhashini and AI4Bharat adapters exist, but other regional languages and live provider credentials are pending."),
        ("SOCRATES", "COVERED", "Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors, Severity."),
        ("AYUSH / Ayurveda", "PARTIAL", "All ten Dashavidha factors are modeled with provenance. Trividha and Ashtavidha placeholders exist, but full practitioner examination workflows and non-Ayurveda AYUSH profiles do not."),
        ("Red-flag alerts", "COVERED AS PROTOTYPE", "Deterministic plus AI checks, Nurse Station, audible alarm, evidence, cooldown, escalation, acknowledgement. Clinical validation is still required."),
        ("Printed and handwritten OCR", "PARTIAL", "English/Hindi EasyOCR, classification, confidence and review states. Handwriting always goes to staff review; hospital-dataset accuracy is unvalidated."),
        ("Diagnoses, medicines, labs", "MOSTLY COVERED", "OCR extracts diagnoses, medicines and lab values/ranges/flags. Procedure/surgery extraction from documents is not a dedicated structured field."),
        ("Chronology", "PARTIAL", "Documents can carry dates and appear with visit context. A reconciled longitudinal patient timeline is not built."),
        ("Abnormal values", "PARTIAL", "The extractor can store high/low flags and the dashboard shows them. There is no deterministic numeric/reference-range engine."),
        ("Drug interactions", "NOT BUILT", "A small formulary performs name matching only. It does not check interactions, dose safety, contraindications or duplicate therapy."),
        ("Structured editable summary", "COVERED", "Standard history sections, transcript/evidence, corrections with reasons, revisions, clinician attestation and sign-off."),
        ("Bilingual output", "PARTIAL", "Patient UI, prompts, captions and spoken read-back support English/Hindi. The full clinician record/PDF is not automatically translated into two languages."),
        ("Consent and privacy", "PARTIAL", "Consent-first flow, English/Hindi audio, scopes, audit, secure cookie, idle/manual clear, retention and erasure paths. Per-scope withdrawal and a patient consent wallet are pending."),
        ("ABHA / ABDM / FHIR", "PARTIAL", "Optional ABHA capture, staff verification boundary, care contexts, FHIR R4 document construction and local M1/M2/M3 workflow state. Live certified exchange is pending."),
        ("Aadhaar identification", "NOT BUILT", "The product uses new registration, Medi ID and optional ABHA; no Aadhaar eKYC flow exists."),
        ("HIS / EMR routing", "PARTIAL", "Signed FHIR/PDF output exists. A real hospital-specific connector and automatic routing are not implemented."),
        ("Immediate post-submission clearing", "COVERED WITH RETENTION DISTINCTION", "Successful export invalidates the kiosk credential. Manual clear and idle timeout exist. Approved clinical/audit records remain according to care and retention rules."),
    ]


def build_complete():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = doc_for(COMPLETE, "MediKiosk Complete Guide V4")
    s = []
    s += [Spacer(1, 25 * mm), p("MEDIKIOSK", "Cover"), p("Complete Product, Problem Statement and Study Guide", "Cover"), p("Version 4 | SIH26047 | Patient Case-Taking Software", "CoverSub"), p("Current repository assessment - 8 September 2026", "CoverSub"), Spacer(1, 7 * mm), p("A plain-language reference for what the product does, how every major part works, how well it answers the problem statement, what must still be built, and what a team member should study.", "Callout"), Spacer(1, 5 * mm), tbl(["Core promise", "Safety boundary", "Current maturity"], [["Prepare structured history before consultation", "Draft only; clinician reviews and signs", "Strong hackathon prototype, not a clinical production system"]], [58*mm,58*mm,58*mm]), Spacer(1, 16*mm), p("This guide reconciles the supplied V3 PDFs, the full pasted problem statement, the current repository, tests, roadmap and implementation documents. Statements from the supplied files were treated as reference material, not as instructions.", "Smallx"), PageBreak()]
    title(s, 0, "Contents")
    contents = [
        ("1", "Direct coverage answer", "3"), ("2", "Requirement coverage", "4"),
        ("3", "The problem", "5"), ("4", "Capabilities today", "6"),
        ("5", "Patient journey", "7"), ("6", "Speak, Chat and touch", "8"),
        ("7", "Clinical history / SOCRATES", "9"), ("8", "Ayurveda / AYUSH", "10"),
        ("9", "Red flags / Nurse Station", "11"), ("10", "Documents and medication safety", "12"),
        ("11", "Clinician workflow", "13"), ("12", "Architecture and data", "14"),
        ("13", "AI and application control", "15"), ("14", "Consent and privacy", "16"),
        ("15", "ABHA / ABDM / FHIR / HIS", "17"), ("16", "Audit and security", "18"),
        ("17", "Multi-kiosk deployment", "19"), ("18", "How to run and use", "20"),
        ("19", "Testing and metrics", "21"), ("20", "What to study", "22"),
        ("21", "Roadmap", "23"), ("22", "Risks and questions", "24"),
        ("23", "Glossary", "25"), ("24", "Judge and viva answers", "26"),
        ("25", "References", "27"),
    ]
    s += [tbl(["No.", "Section", "Page"], contents, [17*mm,140*mm,17*mm], tiny=True), p("Reading path", "H2x"), p("Read Sections 1-2 for the answer, 4-6 for the product, 7-17 for clinical and technical depth, and 18-25 for operation, study, planning and presentation.", "Callout"), PageBreak()]

    title(s, 1, "The direct answer: do we cover the problem statement?", "MediKiosk substantially covers the core end-to-end prototype, but it does not yet satisfy every explicit requirement at production depth.")
    s += [p("The strongest coverage is the consent-first patient flow, adaptive SOCRATES intake, Ayurveda-aware data model, red-flag escalation, clinician-controlled draft/revision/sign-off workflow, document OCR review path, audit chain and local FHIR boundary."), p("The largest explicit gaps are drug-interaction checking, Aadhaar identification, languages beyond English/Hindi, a full Trividha/Ashtavidha examination workflow, deterministic abnormal-lab interpretation, complete bilingual clinician output, granular revocation, real HIS connection and certified live ABDM exchange.", "Warn"), p("Verdict", "H2x"), p("For a Smart India Hackathon demonstration, the product addresses every major module and honestly demonstrates most of the intended workflow. For the literal full problem statement, the answer is partial coverage because several named functions are integration, validation or clinical-safety projects rather than finished features.")]
    new_page(s)

    title(s, 2, "Requirement-by-requirement coverage")
    s += [tbl(["Requirement", "Status", "Evidence and boundary"], coverage_rows(), [43*mm,31*mm,100*mm], tiny=True)]
    new_page(s)

    title(s, 3, "The problem MediKiosk solves")
    s += bullets([
        "High-volume OPDs give clinicians very little time for history, examination, reasoning, counselling and documentation.",
        "Patients speak in natural stories; clinicians need consistent, reviewable fields.",
        "Paper prescriptions, reports and discharge summaries are fragmented and slow to reconcile.",
        "Ayurveda intake adds detailed history and examination concepts that a generic registration form misses.",
        "ABDM exchange is useful only after identity, consent, structure, provenance and clinician approval exist.",
    ])
    s += [p("MediKiosk moves information gathering before the consultation. It aims to reduce repetitive questioning and document reading while preserving clinician authority. Its value must eventually be measured in time saved, history completeness, correction burden, patient completion, safety performance and clinician adoption."), p("Product boundary", "H2x")]
    s += bullets(["No diagnosis.", "No prescription or treatment recommendation.", "No replacement for physical examination or formal triage.", "No unreviewed AI export.", "No claim of production ABDM or hospital deployment."])
    new_page(s)

    title(s, 4, "What the app can do today")
    s += [tbl(["Area", "Current capability"], [
        ("Patient intake", "Start, bilingual consent, English/Hindi, Speak/Chat, new/returning patient, department, adaptive interview, document scan, read-back and completion."),
        ("Voice", "Automatic prompt, listening, transcription, confirmation and retry states; captions; refined orb; interruption; silence stop; typed fallback."),
        ("Identity", "Internal Medi ID, validated phone format, masked returning lookup, optional ABHA capture, staff-verified ABHA linkage."),
        ("Clinical", "Structured SOCRATES, medicines/allergies early, past/family/personal history, review of systems, Ayurveda extensions and contradiction handling."),
        ("Safety", "Deterministic and LLM red flags, calm mental-health handling, help request, Nurse Station, sound, escalation and acknowledgement."),
        ("Documents", "Camera/upload, printed/handwritten route, OCR, document type, date, confidence, entities, lab flags and medicine-name suggestions."),
        ("Clinician", "Protected dashboard, completeness/evidence, corrections with reasons, immutable revisions, Ayurveda confirmation, attestation, sign-off and PDFs."),
        ("Exchange", "Signed FHIR R4 document Bundle, local validation, care contexts, staged ABDM consent/exchange state and credential-gated transport boundary."),
        ("Operations", "Roles, staff sessions, rate limits, hash-chained audit, kiosk ID, device checks, heartbeats, fleet status, TLS configuration and graceful failures."),
    ], [38*mm,136*mm])]
    new_page(s)

    title(s, 5, "Complete patient journey")
    s += [tbl(["Step", "What happens", "Result"], [
        ("1. Welcome", "Patient presses Start; accessibility, help and Device Check are available.", "No clinical session yet."),
        ("2. Consent", "Short consent explains collection, use, review and sharing in English and Hindi audio/text.", "Accept creates a consent-backed session; decline returns to welcome."),
        ("3. Language", "Choose English or Hindi. Speak mode can auto-listen and confirm the answer.", "Language saved."),
        ("4. Mode", "Choose Speak or Chat. In Speak, the orb centers and automatic listening continues. In Chat, the orb disappears.", "Interaction mode saved."),
        ("5. Identity", "New patient gives name and phone, may add ABHA; returning patient enters Medi ID. Voice answers are confirmed and repeated before touch fallback.", "Visit linked to a local patient."),
        ("6. Department", "Choose General or Ayurveda department and confirm.", "Clinical profile selected."),
        ("7. Interview", "One question at a time; voice auto-listens after prompts; Chat uses touch/typing. Captions remain visible.", "Structured record and transcript grow together."),
        ("8. Safety", "Every answer is checked. Urgent patterns or Help create a Nurse Station alert.", "Staff can respond while intake continues appropriately."),
        ("9. Read-back", "The system speaks and displays a short summary. Patient confirms or disputes it.", "Confirmation completes intake; dispute alerts staff."),
        ("10. Documents", "Scan any prescription, lab report or discharge paper and resolve uncertainty.", "OCR evidence attaches to the visit."),
        ("11. Clinician", "Doctor reviews, edits with reasons, confirms protected Ayurveda fields and signs.", "Approved version created."),
        ("12. Output", "Create patient/clinician PDF or stage/send FHIR if configured.", "Kiosk credential is invalidated after successful export."),
    ], [25*mm,101*mm,48*mm], tiny=True)]
    new_page(s)

    title(s, 6, "Speak, Chat and touch")
    s += [p("Speak mode is a guided conversational loop: the app plays a prompt, shows captions, changes the orb to speaking/listening/processing, opens the microphone automatically, stops after detected silence, transcribes, asks for confirmation where needed and retries unclear answers. The patient can interrupt, type instead, repeat a prompt, switch to Chat after confirmation, or cancel and clear data after confirmation."), p("Chat mode uses the same backend controller and clinical safety logic. The patient taps large controls and types answers. Once Chat is selected, the orb disappears."), p("Touch", "H2x")]
    s += bullets(["Touch means ordinary finger taps on the kiosk touchscreen, not camera gestures.", "Controls target at least 44 pixels and support text-size and contrast settings.", "Phone, Medi ID and ABHA entry use touch/keyboard to protect privacy and accuracy.", "Each patient page is designed to fit the browser viewport without body scrolling at the tested kiosk-like size."])
    s += [p("Current voice architecture", "H2x"), p("Microphone audio -> faster-whisper or configured remote ASR -> text -> server-controlled clinical field selection plus local Llama 3.1:8b -> reply text -> Piper or configured remote TTS -> audio and captions.", "CodeX"), p("It is conversational AI rather than recorded hardcoded questions, but it remains a turn-based STT-to-LLM-to-TTS system. Native duplex speech-to-speech and provider-native partial streaming are future work.", "Callout")]
    new_page(s)

    title(s, 7, "Clinical history and SOCRATES")
    s += [tbl(["Letter", "Field", "Question answered"], [
        ("S", "Site", "Where is the symptom?"), ("O", "Onset", "When and how did it start?"),
        ("C", "Character", "What does it feel like?"), ("R", "Radiation", "Does it move or spread?"),
        ("A", "Associated symptoms", "What else happens with it?"), ("T", "Timing", "How long, how often, what pattern?"),
        ("E", "Exacerbating / relieving", "What worsens or improves it?"), ("S", "Severity", "How intense is it, commonly 0-10?"),
    ], [16*mm,52*mm,106*mm])]
    s += [p("The shared record also includes chief complaint, current medicines, allergies, past medical and surgical history, family history, Ahara-Vihara/personal history and review of systems. The backend owns the ordered coverage list, selects the next missing field, validates the returned structure and merges only allowed data."), p("Why this matters", "H2x")]
    s += bullets(["The LLM can phrase a natural question without deciding which safety-critical section to skip.", "Focused extraction retries a missed target field.", "Contradictory sensitive answers require clarification before replacement.", "Malformed model replies are retried and then produce a safe prompt instead of invented data.", "The interview has a bounded turn cap and visible captured/missing coverage."])
    new_page(s)

    title(s, 8, "Ayurveda and AYUSH mode")
    s += [p("The present specialist pathways are Ayurveda departments: Kayachikitsa, Panchakarma, Shalya and Prasuti Tantra, plus General consultation. The shared safety, medicines, allergies and SOCRATES intake always runs first."), p("Dashavidha with provenance", "H2x"), tbl(["Source", "Factors", "Why"], [
        ("Patient conversation", "Vikriti, Satmya, Sattva, Ahara Shakti, Vyayama Shakti, Vaya", "These can be described or elicited in history."),
        ("Practitioner confirmation", "Prakriti", "A patient description is not treated as a confirmed constitution assessment."),
        ("Practitioner examination", "Sara, Samhanana, Pramana", "These require trained clinical observation/examination."),
    ], [42*mm,70*mm,62*mm])]
    s += [p("Additional Ayurveda fields include Agni, Koshtha, Nidana and Panchakarma history. They are useful history fields but are not mislabeled as extra Dashavidha factors."), p("Trividha and Ashtavidha", "H2x"), p("The schema includes protected placeholders for Trividha - Darshana, Sparshana, Prashna - and Ashtavidha - Nadi, Mutra, Mala, Jihva, Shabda, Sparsha, Drik, Akriti. A complete clinician capture and examination workflow is still pending."), p("AYUSH boundary", "Warn"), p("Ayurveda cannot stand in for all AYUSH systems. Yoga/Naturopathy, Unani, Siddha, Homoeopathy and other disciplines require separately governed profiles and terminology.")]
    new_page(s)

    title(s, 9, "Red flags and Nurse Station")
    s += bullets(["Deterministic phrase and combination rules run independently of the model.", "An LLM secondary signal can add an alert but cannot erase a deterministic one.", "Covered starter categories include selected chest-pain/neurologic/bleeding patterns, obstetric emergencies, anaphylaxis and mental-health crisis in English and Hindi.", "Negation handling reduces obvious false alerts such as denying a symptom.", "Mental-health crisis uses calm patient wording while still notifying staff at full severity.", "Repeated evidence appends to one active alert; the help button has a cooldown.", "The Nurse Station polls for alerts, sounds an alarm, shows kiosk and evidence, escalates overdue items and records acknowledgement." ])
    s += [p("This is an early-warning layer, not a validated triage protocol. Before clinical use it needs clinician-authored datasets, sensitivity/specificity measurement, vulnerable-population cases, local-language variants, alert-burden testing and an external paging/rapid-response path.", "Warn")]
    new_page(s)

    title(s, 10, "Documents, OCR and medication safety")
    s += [tbl(["Stage", "Implementation"], [
        ("Capture", "Camera or upload; JPEG, PNG or WebP; printed/handwritten selection; optional document date."),
        ("Safety", "File/type/size limits, 60-megapixel decoded cap and downscaling before OCR."),
        ("Recognition", "EasyOCR uses English/Hindi models and returns text/confidence."),
        ("Classification", "Suggests prescription, lab report, discharge summary or other."),
        ("Extraction", "LLM receives delimited untrusted text and returns allowed diagnoses, medicines and lab values/ranges/flags."),
        ("Verification", "Confident, confirmed, illegible or needs_staff_review; handwritten input always requires staff review."),
        ("Medicine matching", "Small starter formulary offers exact/fuzzy/unverified generic-name suggestions."),
    ], [39*mm,135*mm])]
    s += [p("What is missing", "H2x")]
    s += bullets(["A governed hospital formulary and terminology service.", "A drug-interaction, allergy-interaction, contraindication, dose-range or duplicate-therapy engine.", "Deterministic numeric comparison of lab values against age/sex/method-specific ranges.", "Dedicated structured extraction of procedures/surgeries from scanned documents.", "Validated multilingual handwriting accuracy and a longitudinal reconciliation timeline."])
    new_page(s)

    title(s, 11, "Clinician workflow and summaries")
    s += bullets(["Nurse, Doctor and Admin roles receive scoped access.", "The dashboard shows current structured history, transcript, missing coverage, red-flag evidence and document-review state.", "Corrections require a reason and create immutable numbered revisions with actor and time.", "Protected Ayurveda findings can be confirmed only by a doctor/admin.", "The clinician attests to the reviewed snapshot; the server stores its canonical hash and signer context.", "Any later edit invalidates the old sign-off and export, requiring a new review.", "Patient and clinician PDF outputs are available only after valid sign-off.", "A disputed patient read-back creates an alert instead of silently treating the draft as accepted."])
    s += [p("Bilingual limitation", "H2x"), p("The supported patient experience and read-back are English/Hindi. The clinician dashboard and complete exported record are not yet automatically translated into parallel bilingual clinical documents. Translation of clinical content must use a clinician-approved glossary and preserve the original source text.")]
    new_page(s)

    title(s, 12, "Architecture and data flow")
    s += [tbl(["Layer", "Technology", "Responsibility"], [
        ("Patient/staff UI", "React + Vite", "Touchscreen pages, voice states, captions, dashboards, diagnostics and fleet view."),
        ("API/controller", "FastAPI on port 8080", "Authentication, sessions, coverage, validation, safety, OCR/speech routing, sign-off and export."),
        ("Language model", "Ollama llama3.1:8b", "Natural phrasing and bounded structured extraction; never workflow authority."),
        ("Speech", "faster-whisper + Piper", "Local English/Hindi ASR and TTS, with Bhashini/AI4Bharat provider adapters and local fallback."),
        ("Documents", "EasyOCR + Llama", "Recognition, classification and constrained entity extraction."),
        ("Storage", "SQLite", "Patients, sessions, clinical data, documents, staff, alerts, revisions, sign-offs, audit and ABDM state."),
        ("Outputs", "ReportLab + FHIR JSON", "Signed PDFs and interoperable document candidate."),
    ], [33*mm,45*mm,96*mm])]
    s += [Spacer(1,5*mm), p("Patient -> consent session -> identity/preferences -> controlled clinical turns -> schema validation -> persisted draft -> clinician revision/sign-off -> PDF or validated FHIR document -> local staging or configured external transport", "CodeX"), p("The schema in docs/schema.json is the product's internal clinical contract. FHIR is the exchange representation at the boundary; it does not replace the internal database model.", "Callout")]
    new_page(s)

    title(s, 13, "What AI controls and what code controls")
    s += [tbl(["AI may", "Application/server must"], [
        ("Phrase the selected question naturally.", "Choose required coverage and the next field."),
        ("Extract facts from a patient's answer.", "Validate types, allowed keys and merge rules."),
        ("Structure printed OCR text.", "Preserve source, confidence and review status."),
        ("Provide a secondary red-flag suggestion.", "Keep deterministic red flags authoritative."),
        ("Draft patient-friendly wording.", "Enforce no diagnosis, clinician review and sign-off."),
    ], [87*mm,87*mm])]
    s += [p("Threat model", "H2x")]
    s += bullets(["Patient and OCR text are untrusted and can contain prompt-injection instructions.", "Inputs are explicitly delimited as data; deterministic safety runs outside the model.", "React renders patient text as escaped content; no raw HTML rendering is used.", "A decompression-bomb limit protects OCR decoding.", "Model failure cannot authorize export, change identity or sign a record."])
    new_page(s)

    title(s, 14, "Consent, privacy and data lifecycle")
    s += [tbl(["Control", "Current behavior", "Remaining work"], [
        ("Notice/audio", "Short English/Hindi consent text and speech before session creation.", "Usability testing with low-literacy patients and approved wording."),
        ("Scopes", "history_capture, document_sharing and hospital_share stored with time.", "Separate opt-in/withdrawal per scope and visible consent receipts."),
        ("Session", "HttpOnly SameSite=Strict cookie; Secure with TLS; idle/manual clearing.", "Production browser/device policy and enforced TLS."),
        ("After export", "Patient kiosk credential becomes unusable immediately.", "Document exact hospital retention/legal basis and downstream deletion handling."),
        ("Registry", "Configurable retention purge; patient/staff erasure endpoints.", "Operational scheduler, request verification and legal hold policy."),
        ("Audit", "Hash-chained append-only events with actor/action/target/time/context.", "External anchoring, monitoring and formal retention policy."),
    ], [35*mm,70*mm,69*mm], tiny=True)]
    s += [p("Clearing a kiosk session and deleting every healthcare record are different actions. The kiosk must stop exposing the patient's session immediately, while a clinician-approved record and audit evidence may need lawful retention. This must be explained precisely in consent and hospital policy."), p("Compliance statement", "Warn"), p("The code contains privacy and security controls, but it has not been legally certified as compliant with the DPDP Act/Rules, ABDM policy, hospital policy or any medical-device regime.")]
    new_page(s)

    title(s, 15, "ABHA, ABDM, FHIR and HIS")
    s += [tbl(["Term", "Meaning", "MediKiosk today"], [
        ("Medi ID", "Local returning-patient identifier.", "Built and independent of ABHA."),
        ("ABHA", "National health account identity/address.", "Optional capture; staff records verification reference; no live OTP/QR eKYC."),
        ("ABDM", "Consent-based national digital-health ecosystem.", "Local M1/M2/M3 workflow state and credential-gated transport boundary."),
        ("FHIR R4", "Standard resource format for exchange.", "Document Bundle with OPConsultRecord Composition and referenced resources."),
        ("HIS/EMR", "Hospital operational/clinical record system.", "Target destination; no vendor-specific live connector."),
    ], [28*mm,65*mm,81*mm])]
    s += [p("The export includes resources such as Patient, Encounter, Practitioner, Organization, Condition, MedicationStatement, AllergyIntolerance, Observation and Flag. The first resource is the Composition, references use absolute urn:uuid values, and a local validator fails closed."), p("Still required for a real ABDM pilot", "H2x")]
    s += bullets(["Facility HFR and professional HPR registration where applicable.", "Issued bridge credentials and assigned current M1/M2/M3 paths.", "Official current NRCeS implementation-guide validation.", "Real ABHA discovery/OTP/QR flows.", "Consent-artifact key handling, encryption/decryption, signatures and secure transfer.", "Sandbox exit/certification, security testing and operational monitoring.", "A clinician review/provenance workflow for inbound records."])
    new_page(s)

    title(s, 16, "Audit log, security and access")
    s += [p("Every audit event stores the previous event hash and a SHA-256 hash of the current event, creating a tamper-evident chain. The event records actor type/identity/role, action, target, outcome, time, kiosk/session context and structured metadata. Admin access can inspect the trail."), p("Audited areas", "H2x")]
    s += bullets(["Consent, session and identity activity.", "Patient lookup, registry erasure and ABHA linking.", "Clinical turns, read-back, documents and alerts.", "Staff access, corrections, revisions, Ayurveda confirmation and sign-off.", "PDF/FHIR generation and ABDM workflow events.", "Fleet, escalation and acknowledgement events."])
    s += [p("Other controls", "H2x")]
    s += bullets(["Individual role-based staff sessions and server-side authorization.", "Hashed tokens, masked identifiers, bounded uploads and strict models.", "Rate limits for staff login, Medi ID lookup and Help requests.", "Security headers, controlled CORS and optional TLS launcher validation.", "Temporary voice files deleted on success and failure."])
    s += [p("A hash chain reveals many database edits but does not prevent deletion by a database administrator and is not externally notarized. Production needs database encryption at rest, secrets management, backups, monitoring, incident response and tested recovery.", "Callout")]
    new_page(s)

    title(s, 17, "Multi-kiosk and physical deployment")
    s += bullets(["One central API/database is the source of truth; each frontend has a stable kiosk ID.", "Heartbeats report online/offline state and pending workload to the fleet view.", "Shared rate limits and alerts work across kiosks.", "SystemStatusGate blocks safely when the backend is absent and degrades when Ollama alone is down.", "Kiosk mode removes ordinary browser navigation; OS lockdown remains a separate installation task.", "Device Check covers browser access to touch, microphone, speaker, camera and network." ])
    s += [p("Every real installation still needs human commissioning for touch corners, gloves/wet fingers, noisy microphones, speaker privacy, camera glare/rotation, network loss, power recovery, accessibility, cleaning, shoulder surfing and an end-to-end alert drill."), p("Production architecture gap", "H2x"), p("SQLite and one central API are suitable for a hackathon or supervised pilot. A real fleet needs a managed relational database, high availability, encryption at rest, backups, observability, a degraded/offline strategy and hospital-owned notification integration.", "Warn")]
    new_page(s)

    title(s, 18, "How to run and use the current app")
    s += [p("Prerequisites", "H2x")]
    s += bullets(["Python environment with backend requirements.", "Node/npm frontend dependencies.", "Ollama running llama3.1:8b at localhost:11434.", "Whisper/EasyOCR model caches and Piper English/Hindi voice files."])
    s += [p("Start", "H2x"), p("From the repository root, use the included Windows launchers. The backend uses port 8080; the Vite frontend normally uses port 5173. run_server.py avoids the Windows reload/port issue. kiosk-mode.bat opens a locked full-screen browser for demonstration."), p("Patient", "H2x")]
    s += bullets(["Press Start, review/accept consent, choose language and mode.", "Create or enter a Medi ID, select department, answer the interview and confirm the read-back.", "Scan documents if available, use Repeat/Help/accessibility as needed, then finish.", "Use Cancel and clear my data for the current visit; select permanent registry deletion only when intended."])
    s += [p("Staff", "H2x")]
    s += bullets(["Open Nurse Station for active alerts and acknowledgement.", "Open Physician View, sign in, select a real session and review all captured evidence.", "Correct fields with a reason, confirm practitioner-only Ayurveda findings, attest and sign.", "Generate the right PDF or use the ABDM/HIS card while clearly identifying local/staged mode."])
    new_page(s)

    title(s, 19, "Testing evidence and what it proves")
    s += [tbl(["Check", "Latest recorded result", "Meaning"], [
        ("Backend regression suite", "43 passing", "Engineering contracts and fixed bugs remain covered."),
        ("Clinical safety dataset", "17/17 passing", "Starter English/Hindi deterministic cases pass."),
        ("Frontend production build", "Passed", "The current React bundle compiles."),
        ("Contrast checks", "6/6 passed", "Selected theme text pairs meet the scripted threshold."),
        ("Browser walkthrough", "Passed", "Light/dark, touch, voice and viewport behavior were manually checked."),
    ], [42*mm,40*mm,92*mm])]
    s += [p("These tests prove implementation behavior in the tested environment. They do not prove diagnostic accuracy, clinical safety, Hindi quality across accents, OCR accuracy on hospital documents, legal compliance, physical kiosk fitness or ABDM certification."), p("Metrics required for a serious pilot", "H2x")]
    s += bullets(["Intake completion rate and median time.", "History-field completeness and clinician correction rate.", "Red-flag sensitivity, specificity and alerts per 100 visits.", "ASR word/semantic error rate by language, noise and demographic group.", "OCR entity accuracy, unsafe-error rate and review-routing accuracy.", "Doctor review time, adoption and measured consultation-time effect.", "Consent comprehension, abandonment and accessibility outcomes."])
    new_page(s)

    title(s, 20, "What the team must study")
    s += [tbl(["Priority", "Topics", "Practical goal"], [
        ("Must know", "SIH26047 scope; OPD workflow; history sections; SOCRATES; red flags; Ayurveda provenance; consent; Medi ID/ABHA/ABDM; FHIR document mental model; clinician sign-off.", "Explain why every module exists and demonstrate it honestly."),
        ("Should know", "DPDP concepts; HIP/HIU; HFR/HPR; FHIR profiles; SNOMED CT; LOINC; audit/provenance; RBAC; retention; threat modeling; human factors.", "Design a safe pilot and communicate with hospital/ABDM teams."),
        ("Learn during pilot", "Clinical validation, Hindi/Indic speech evaluation, OCR datasets, workflow observation, usability/accessibility, alarm fatigue, data-quality governance.", "Replace assumptions with measured evidence."),
        ("Later", "Production databases, HA/offline sync, terminology service, DICOM/PACS, advanced analytics, regulatory classification and formal security certification.", "Scale only when the clinical workflow is proven."),
    ], [28*mm,98*mm,48*mm], tiny=True)]
    s += [p("Key distinctions", "H2x")]
    s += bullets(["ABHA is identity; ABDM is the ecosystem; FHIR is the data-exchange standard; HIS/EMR is the hospital system.", "A schema validates shape; terminology coding standardizes meaning; provenance explains where a fact came from.", "Confidence is not clinical truth. Patient-reported, OCR-extracted, model-inferred and practitioner-confirmed data must remain distinguishable.", "A draft summary supports a clinician; a diagnosis or treatment recommendation crosses the product boundary."])
    new_page(s)

    title(s, 21, "Gap-closing roadmap")
    s += [tbl(["Priority", "Work", "Definition of done"], [
        ("P0", "Drug-interaction and medication safety", "Hospital-governed source, clinician-facing alerts, allergy/duplicate/dose rules, explainable evidence and clinical validation."),
        ("P0", "Clinical and usability validation", "Clinician-approved cases, real OPD testing, red-flag metrics, ASR/OCR benchmarks and resolved high-risk failures."),
        ("P1", "Full PS compliance", "Aadhaar decision/flow, deterministic lab flags, document procedures, bilingual clinical output, granular consent withdrawal."),
        ("P1", "Language breadth", "At least selected regional languages across UI, consent, ASR/TTS, clinical glossary and OCR with measured quality."),
        ("P1", "Ayurveda/AYUSH depth", "Practitioner UI for Trividha/Ashtavidha and separate governed profiles for added AYUSH disciplines."),
        ("P2", "Hospital pilot", "Production DB, mandatory TLS, backups, monitoring, external alerting, real queue/HIS adapter and commissioning."),
        ("P2", "ABDM live integration", "Registered facility/bridge, real ABHA and consent flows, cryptographic exchange, official validation and certification."),
        ("P3", "Experience/scale", "Streaming voice, offline/degraded kiosk, longitudinal timeline, vitals, consent wallet and deidentified analytics after validation."),
    ], [20*mm,65*mm,89*mm], tiny=True)]
    new_page(s)

    title(s, 22, "Key risks and questions")
    s += [tbl(["Risk", "Why it matters", "Question to answer"], [
        ("Patient independence", "Noise, literacy, disability or unfamiliarity can make self-service slower.", "Can target patients finish without repeated help?"),
        ("Clinical usefulness", "More text can increase rather than reduce clinician burden.", "Does the summary save time and reduce missed history?"),
        ("Safety alerts", "False negatives harm; false positives cause alarm fatigue.", "What are sensitivity, specificity and alert burden?"),
        ("Speech", "Lab performance may fail in a noisy OPD.", "What is semantic error and completion by language/accent/noise?"),
        ("OCR", "Wrong medicine or lab values can mislead clinicians.", "Does uncertainty reliably reach staff review?"),
        ("Consent", "A checkbox can be legally present yet poorly understood.", "Can patients explain and withdraw what they agreed to?"),
        ("Integration", "A FHIR file alone may never enter the doctor's actual workflow.", "Where and when should the approved record appear?"),
    ], [39*mm,67*mm,68*mm], tiny=True)]
    new_page(s)

    title(s, 23, "Glossary")
    s += [tbl(["Term", "Plain meaning"], [
        ("ABDM", "Ayushman Bharat Digital Mission, India's digital-health ecosystem."),
        ("ABHA", "Ayushman Bharat Health Account identity/address used in ABDM."),
        ("FHIR R4", "HL7 standard for representing and exchanging healthcare information as resources."),
        ("HIS / EMR / EHR", "Hospital information system / electronic medical record / broader longitudinal electronic health record."),
        ("HIP / HIU", "Health Information Provider / Health Information User in consented ABDM exchange."),
        ("HFR / HPR", "Health Facility Registry / Healthcare Professional Registry."),
        ("SOCRATES", "Eight-part symptom-history mnemonic used by the interview controller."),
        ("ASR / STT / TTS", "Automatic speech recognition / speech-to-text / text-to-speech."),
        ("OCR", "Optical character recognition from document images."),
        ("LLM", "Large language model used here for phrasing and structured extraction."),
        ("RBAC", "Role-based access control for Nurse, Doctor and Admin permissions."),
        ("Provenance", "Who or what supplied a fact, when and with what confidence/review state."),
        ("SNOMED CT", "Clinical terminology for consistent concept meaning."),
        ("LOINC", "Terminology for lab/clinical observations and documents."),
        ("DPDP", "India's Digital Personal Data Protection law and related rules."),
        ("Dashavidha", "Ten-factor Ayurveda assessment separated by patient and practitioner provenance."),
        ("Trividha / Ashtavidha", "Three-method and eight-part Ayurveda examination frameworks."),
    ], [42*mm,132*mm], tiny=True)]
    new_page(s)

    title(s, 24, "Judge and viva answers")
    s += [tbl(["Question", "Strong short answer"], [
        ("What is the product?", "A consent-first, AI-assisted pre-consultation history and document system that produces a clinician-reviewed structured record."),
        ("Why AI?", "To understand natural language and phrase adaptive questions; code still owns coverage, safety, validation and sign-off."),
        ("Does it diagnose?", "No. It produces a draft history and early-warning alerts; clinicians examine, correct and decide."),
        ("Why more than a chatbot?", "It adds identity, consent, schema-controlled coverage, OCR provenance, deterministic alerts, revisions, sign-off, audit and interoperability."),
        ("Is voice hardcoded?", "No. Speech becomes text, a local LLM interprets it under a server-selected clinical target, and TTS speaks the answer. It is turn-based, not native speech-to-speech."),
        ("Is ABDM live?", "The FHIR and consent workflow boundary is implemented locally; production credentials, cryptography, validation and certification are still external gates."),
        ("Does it cover the PS?", "It strongly covers the prototype's core modules. Named gaps remain in drug interactions, Aadhaar, language breadth, full exam workflows, granular revocation and live integrations."),
        ("Biggest strength?", "Clinician authority is enforced: every AI record is a draft, edits are versioned, and export requires current sign-off."),
        ("Biggest next step?", "Clinical/usability validation plus the missing medication-safety and integration requirements."),
    ], [48*mm,126*mm], tiny=True)]
    new_page(s)

    title(s, 25, "Reference map and source discipline")
    s += [p("Product claims were checked against the current repository, ROADMAP.md, docs/schema.json, AYURVEDA_MODE.md, SPEECH_PROVIDERS.md, CLINICIAN_WORKFLOW.md, ABDM_INTEGRATION.md, DEPLOYMENT_AND_COMMISSIONING.md, the current test records, the supplied V3 PDFs and the user's pasted SIH26047 problem statement."), p("External standards", "H2x"), tbl(["Source", "Location", "Use"], [
        ("NRCeS ABDM FHIR Implementation Guide", "https://nrces.in/ndhm/fhir/r4/", "Current ABDM FHIR profiles; recheck version before integration."),
        ("HL7 FHIR R4 Bundle", "https://hl7.org/fhir/R4/bundle.html", "Base document Bundle rules."),
        ("ABDM portal/policies", "https://abdm.gov.in/", "ABHA, policy and ecosystem context."),
        ("MeitY DPDP materials", "https://www.meity.gov.in/", "Current Act/rules and official notices."),
        ("SNOMED International", "https://www.snomed.org/", "Clinical terminology context."),
        ("LOINC", "https://loinc.org/", "Laboratory/observation terminology context."),
    ], [49*mm,72*mm,53*mm], tiny=True)]
    s += [p("Current official pages should be rechecked before a real integration or legal claim. As of this guide, NRCeS publishes an ABDM FHIR R4 implementation guide and DocumentBundle profile; HL7 requires a document Bundle to place a Composition first. These references support architecture, not a certification claim."), Spacer(1, 12*mm), p("End of complete guide", "CoverSub")]
    doc.build(s)


def build_handbook():
    doc = doc_for(HANDBOOK, "MediKiosk Project Handbook V4")
    s = []
    s += [Spacer(1, 26*mm), p("MEDIKIOSK", "Cover"), p("Project Handbook", "Cover"), p("Key product, clinical and architecture facts", "CoverSub"), p("Version 4 | 8 September 2026", "CoverSub"), Spacer(1, 8*mm), p("Use this shorter guide for demos, revision, team onboarding and judge questions. It contains the important facts without the full study detail.", "Callout"), Spacer(1, 7*mm), tbl(["Problem", "Solution", "Boundary"], [["OPD time is consumed by basic history and paper records", "Collect and structure information before consultation", "AI drafts; clinician verifies, signs and decides"]], [58*mm,58*mm,58*mm]), PageBreak()]

    title(s, 1, "The project in one page")
    s += [p("10 seconds", "H2x"), p("MediKiosk is a patient-facing pre-consultation kiosk that gathers structured history, digitizes paper records, flags urgent patterns and prepares a clinician-reviewable summary."), p("30 seconds", "H2x"), p("Patients use English or Hindi in Speak or Chat mode. A server-controlled interview follows SOCRATES and Ayurveda-specific fields while a local LLM phrases questions and extracts answers. Deterministic safety rules can alert the Nurse Station. The doctor reviews, corrects, signs and only then creates a PDF or FHIR export."), p("Architecture in one line", "H2x"), p("React/Vite -> FastAPI:8080 -> SQLite + Ollama llama3.1:8b + faster-whisper/Piper + EasyOCR -> clinician sign-off -> ReportLab PDF / FHIR R4 document", "CodeX"), p("Maturity", "H2x"), p("Strong functional hackathon prototype with production-minded controls. It is not a deployed clinical system, certified ABDM connection, diagnostic device or autonomous doctor.", "Warn")]
    new_page(s)

    title(s, 2, "Problem statement coverage")
    s += [tbl(["Status", "Covered areas"], [
        ("Covered", "Consent-first flow; adaptive voice/touch; SOCRATES; structured summary; clinician edits/revisions/sign-off; red flags; audit; FHIR document generation."),
        ("Partial", "English/Hindi only; Ayurveda strong but other AYUSH profiles and full physical-exam workflow pending; OCR handwriting always reviewed; abnormal lab and chronology limited; consent revocation and bilingual clinician output incomplete; ABDM/HIS staged."),
        ("Missing", "Drug-interaction engine; Aadhaar flow; production HIS connector; certified live ABDM exchange."),
    ], [31*mm,143*mm])]
    s += [p("Answer to judges", "H2x"), p("We cover the complete prototype journey and all four major modules, with strong clinician governance. We do not claim literal production completion: drug interactions, Aadhaar, broader languages, granular revocation, full Ayurveda examination workflows and live integrations remain planned.", "Callout")]
    new_page(s)

    title(s, 3, "End-to-end workflow")
    s += [tbl(["Stage", "Result"], [
        ("Start -> consent", "Bilingual explanation; accepted scopes and timestamp create the session."),
        ("Language -> mode", "English/Hindi and Speak/Chat; orb centers only in Speak."),
        ("Identity", "New Medi ID or returning lookup; optional ABHA; sensitive numbers use touch."),
        ("Department", "General or Ayurveda department selects the clinical profile."),
        ("Interview", "Automatic prompt/listen/confirm in Speak; typed touch flow in Chat; captions in speech."),
        ("Safety", "Deterministic/AI checks can create a live Nurse Station alert."),
        ("Read-back", "Patient confirms a short spoken summary or dispute alerts staff."),
        ("Documents", "OCR extracts reviewable diagnoses, medicines and lab values from images."),
        ("Clinician", "Review, correction reason, revision, Ayurveda confirmation, attestation and sign-off."),
        ("Output", "Patient/clinician PDF or validated FHIR candidate; kiosk credential invalidated after export."),
    ], [44*mm,130*mm])]
    new_page(s)

    title(s, 4, "Clinical and Ayurveda essentials")
    s += [p("SOCRATES", "H2x"), p("Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors and Severity. Medicines and allergies are deliberately collected early, followed by past medical/surgical, family, Ahara-Vihara/personal and systems history."), p("Ayurveda", "H2x"), tbl(["Provenance", "Fields"], [
        ("Patient-reported", "Vikriti, Satmya, Sattva, Ahara Shakti, Vyayama Shakti, Vaya; plus Agni, Koshtha, Nidana and Panchakarma history."),
        ("Practitioner-confirmed", "Prakriti."),
        ("Practitioner examination", "Sara, Samhanana, Pramana."),
        ("Protected placeholders", "Trividha: Darshana, Sparshana, Prashna. Ashtavidha: Nadi, Mutra, Mala, Jihva, Shabda, Sparsha, Drik, Akriti."),
    ], [51*mm,123*mm])]
    s += [p("The product currently supports Ayurveda departments, not every AYUSH discipline. It never asks the LLM to invent examination findings.", "Callout")]
    new_page(s)

    title(s, 5, "Architecture and safety decisions")
    s += [tbl(["Owner", "Responsibilities"], [
        ("Frontend", "Touch UI, voice/orb state, captions, accessibility, dashboard and device/fleet views."),
        ("FastAPI", "Identity, cookies, roles, field schedule, validation, merging, alerts, persistence, sign-off and export."),
        ("LLM", "Natural question phrasing and constrained extraction only."),
        ("Speech", "faster-whisper ASR and Piper TTS; Bhashini/AI4Bharat adapters with local fallback."),
        ("OCR", "EasyOCR plus constrained entity extraction and mandatory uncertainty review."),
        ("SQLite", "Prototype authority for patients, visits, evidence, staff, alerts, audit, revisions and integration state."),
    ], [40*mm,134*mm])]
    s += [p("Safety spine", "H2x")]
    s += bullets(["Server chooses coverage; model cannot skip requirements.", "Deterministic red flags survive model failure or prompt injection.", "Patient/OCR text is treated as untrusted data.", "Unknown data stays unknown; handwriting needs staff review.", "Every AI summary remains a draft until current clinician sign-off.", "Later edits invalidate old sign-off and export."])
    new_page(s)

    title(s, 6, "ABDM, FHIR and consent")
    s += [tbl(["Term", "Remember this"], [
        ("Medi ID", "Local patient identifier; works without ABHA."),
        ("ABHA", "Optional national health identity link; real OTP/QR is pending."),
        ("ABDM", "Consent-based national exchange ecosystem; local/staged today."),
        ("FHIR R4", "Exchange format. MediKiosk creates a document Bundle with an OPConsultRecord Composition first."),
        ("HIS/EMR", "Hospital system that should receive the approved record; real connector pending."),
    ], [36*mm,138*mm])]
    s += [p("Production ABDM still needs registered facility/bridge context, issued credentials and paths, real ABHA verification, consent-artifact cryptography, official validation, certification and secure inbound provenance review."), p("Consent today", "H2x"), p("Bilingual audio/text notice, stored scopes/time, HttpOnly cookie, idle/manual clear, post-export credential invalidation, registry retention/purge and erasure endpoints. Granular per-scope withdrawal and a visible consent wallet are not built.")]
    new_page(s)

    title(s, 7, "Security, audit and operations")
    s += bullets(["Nurse, Doctor and Admin roles with server-side authorization.", "Hashed patient/staff tokens; HttpOnly SameSite=Strict patient cookie; Secure when TLS is configured.", "Masked identifiers, strict schemas, upload limits and OCR pixel cap.", "Rate limits for staff login, Medi ID lookup and Help.", "Temporary voice recordings deleted after transcription.", "Append-only audit events linked by previous hash and SHA-256 current hash.", "Kiosk IDs, heartbeats, fleet status, alert escalation and device diagnostics.", "Graceful backend/Ollama failure screens and full-screen kiosk launcher."])
    s += [p("Before deployment", "H2x"), p("Replace SQLite, require TLS, encrypt data at rest, add secrets management, backups/recovery, monitoring, high availability or degraded mode, external staff paging, formal retention policy, physical commissioning, clinical validation and legal/security review.", "Warn")]
    new_page(s)

    title(s, 8, "What works, what remains")
    s += [tbl(["Strong now", "Next critical work"], [
        ("Consent-to-sign-off patient and clinician workflow", "Clinical/usability study with real OPD users and clinicians"),
        ("Deterministic clinical orchestration + bounded LLM", "Drug-interaction and deterministic lab-safety engine"),
        ("Two-layer red flags + Nurse Station", "Validated safety dataset and external escalation"),
        ("Ayurveda provenance model", "Full Trividha/Ashtavidha workflow and separate AYUSH profiles"),
        ("OCR review states", "Hospital document benchmarks and dedicated procedure extraction"),
        ("FHIR document and ABDM boundary", "Live HIS/ABDM, cryptography and certification"),
        ("English/Hindi voice/chat", "Regional languages and streaming conversational voice"),
        ("Security/audit foundation", "Production infrastructure, governance and operations"),
    ], [87*mm,87*mm])]
    s += [p("Explicit missing requirements", "H2x")]
    s += bullets(["Aadhaar identification.", "Drug interactions.", "Full bilingual clinician output.", "Per-scope consent revocation.", "Production HIS and ABDM exchange."])
    new_page(s)

    title(s, 9, "Terms to know")
    s += [tbl(["Term", "Meaning"], [
        ("OPD", "Outpatient Department."), ("SOCRATES", "Eight-part symptom-history framework."),
        ("LLM", "Large language model."), ("ASR/STT/TTS", "Speech recognition / speech-to-text / text-to-speech."),
        ("OCR", "Text recognition from document images."), ("RBAC", "Role-based access control."),
        ("Provenance", "Source, actor, time and verification state of a fact."), ("ABHA", "National digital-health identity/account."),
        ("ABDM", "India's digital-health ecosystem."), ("FHIR R4", "Healthcare exchange standard/resource model."),
        ("HIP/HIU", "Provider/user roles in ABDM exchange."), ("HFR/HPR", "Facility/professional registries."),
        ("SNOMED CT", "Clinical terminology."), ("LOINC", "Lab/observation terminology."),
        ("DPDP", "India's personal-data protection law/rules."), ("Dashavidha", "Ten-factor Ayurveda assessment."),
    ], [38*mm,136*mm], tiny=True)]
    new_page(s)

    title(s, 10, "Demo and viva cheat sheet")
    s += [p("Recommended demo", "H2x")]
    s += bullets(["Run Device Check and health status.", "Start, hear bilingual consent, choose Hindi/English and Speak, show orb/captions/automatic listening.", "Register or retrieve a patient, choose an Ayurveda department and answer a short SOCRATES/Ayurveda path.", "Show a printed scan and the mandatory handwriting-review route.", "Trigger a prepared red flag and acknowledge it at Nurse Station.", "Open Physician View, correct a field with a reason, show revision, confirm Ayurveda fields and sign.", "Generate PDFs and show the local validated FHIR Bundle without claiming live delivery."])
    s += [p("Five answers to memorize", "H2x")]
    s += bullets(["AI helps conversation and extraction; application code owns safety and workflow.", "The product prepares history; it does not diagnose or prescribe.", "ABHA is optional identity; Medi ID keeps the local workflow usable.", "FHIR is the exchange format; ABDM/HIS are destinations and workflows.", "Core PS prototype coverage is strong, but named production and clinical gaps remain."])
    s += [p("Current evidence", "H2x"), p("Latest recorded verification: 43 backend regressions, 17/17 clinical safety cases, production frontend build, 6/6 contrast checks and a live light/dark/touch/voice/viewport walkthrough."), Spacer(1,7*mm), p("Reference: the Complete Guide V4 contains the full coverage matrix, operating instructions, study map, risks and sources.", "Callout")]
    new_page(s)

    title(s, 11, "Reference links")
    s += [tbl(["Reference", "Location"], [
        ("MediKiosk current scope", "ROADMAP.md and docs/ in the repository"),
        ("Clinical schema", "docs/schema.json"),
        ("ABDM FHIR profiles", "https://nrces.in/ndhm/fhir/r4/"),
        ("HL7 FHIR R4 Bundle", "https://hl7.org/fhir/R4/bundle.html"),
        ("ABDM", "https://abdm.gov.in/"),
        ("MeitY DPDP material", "https://www.meity.gov.in/"),
    ], [60*mm,114*mm])]
    s += [Spacer(1,9*mm), p("Final mental model", "H2x"), p("Patient gives consent, history and documents -> MediKiosk structures them -> deterministic safety watches continuously -> clinician verifies and signs -> approved data becomes a PDF or FHIR document -> HIS/ABDM is the integration destination.", "Callout"), Spacer(1,15*mm), p("End of handbook", "CoverSub")]
    doc.build(s)


if __name__ == "__main__":
    build_complete()
    build_handbook()
    print(COMPLETE)
    print(HANDBOOK)

