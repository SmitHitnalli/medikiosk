"""Generate the current-state MediKiosk product guide from repository truth."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

from generate_guides_v4 import S, NAVY, TEAL, MINT, AMBER_BG, RED, RED_BG, GREEN, GREEN_BG, INK, MUTED, GRID

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "MediKiosk_Current_Product_Guide.pdf"

S.add(ParagraphStyle(name="GuideHero", parent=S["Cover"], fontSize=31, leading=34, spaceAfter=10))
S.add(ParagraphStyle(name="GuideEyebrow", parent=S["Smallx"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=TEAL, alignment=TA_CENTER, spaceAfter=8))
S.add(ParagraphStyle(name="CardTitle", parent=S["H2x"], fontSize=10.5, leading=13, spaceBefore=0, spaceAfter=3))
S.add(ParagraphStyle(name="CardBody", parent=S["Bodyx"], fontSize=8.2, leading=10.8, spaceAfter=0))
S.add(ParagraphStyle(name="Metric", parent=S["Bodyx"], fontName="Helvetica-Bold", fontSize=17, leading=19, textColor=NAVY, alignment=TA_CENTER, spaceAfter=1))
S.add(ParagraphStyle(name="MetricLabel", parent=S["Smallx"], alignment=TA_CENTER, textColor=MUTED))


def p(text, style="Bodyx"):
    return Paragraph(text, S[style])


def bullets(items):
    return [p("- " + escape(item), "Bulletx") for item in items]


def table(headers, rows, widths=None, tiny=False):
    body = "Tiny" if tiny else "Smallx"
    data = [[p(escape(str(v)), "Smallx") for v in headers]]
    data += [[p(escape(str(v)), body) for v in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .35, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5FAF9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return result


def section(story, number, name, subtitle=None):
    story.append(p(f"{number:02d}  {escape(name)}", "Section"))
    if subtitle:
        story.append(p(escape(subtitle), "Callout"))


def card(title_text, body_text, width=84*mm, background=colors.white, border=GRID):
    content = [[p(escape(title_text), "CardTitle")], [p(escape(body_text), "CardBody")]]
    result = Table(content, colWidths=[width], hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), .6, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return result


def two_cards(left, right):
    grid = Table([[left, right]], colWidths=[87*mm, 87*mm], hAlign="LEFT")
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    return grid


def flow(items):
    cells = []
    widths = []
    for index, item in enumerate(items):
        cells.append(p(escape(item), "Smallx"))
        widths.append(27*mm)
        if index < len(items) - 1:
            cells.append(p("&gt;", "CardTitle"))
            widths.append(7*mm)
    result = Table([cells], colWidths=widths, hAlign="CENTER")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]
    for index in range(0, len(cells), 2):
        style += [("BACKGROUND", (index, 0), (index, 0), MINT), ("BOX", (index, 0), (index, 0), .7, TEAL)]
    result.setStyle(TableStyle(style))
    return result


def metrics(items):
    cells = []
    for value, label in items:
        cells.append([p(value, "Metric"), p(label, "MetricLabel")])
    grid = Table([cells], colWidths=[174*mm/len(cells)]*len(cells), hAlign="LEFT")
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F8F7")),
        ("BOX", (0, 0), (-1, -1), .6, TEAL), ("INNERGRID", (0, 0), (-1, -1), .4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return grid


def page_decor(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 11*mm, width, 11*mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(15*mm, height - 7*mm, "MEDIKIOSK  /  CURRENT PRODUCT GUIDE")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.3)
    canvas.drawString(15*mm, 9*mm, "SIH26047 - Patient Case-Taking Software")
    canvas.drawRightString(width - 15*mm, 9*mm, str(doc.page))
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=18*mm, bottomMargin=15*mm, title="MediKiosk Current Product Guide", author="MediKiosk")
    doc.addPageTemplates(PageTemplate(id="main", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")], onPage=page_decor))
    s = []

    s += [Spacer(1, 23*mm), p("SIH26047  /  MINISTRY OF AYUSH  /  AIIA", "GuideEyebrow"), p("MEDIKIOSK", "GuideHero"), p("Complete Current Product Guide", "Cover"), p("What it solves, how it works, what is implemented and what remains", "CoverSub"), Spacer(1, 7*mm), p("MediKiosk prepares a structured, source-aware patient history before consultation, digitizes selected paper records, watches for urgent patterns and places the clinician in control of the final signed record.", "Callout"), Spacer(1, 6*mm), metrics([("EN + HI", "patient language"), ("2 modes", "Speak and Chat"), ("3 roles", "Nurse, Doctor, Admin"), ("43", "backend regressions")]), Spacer(1, 12*mm), two_cards(card("Patient experience", "Consent, language, mode, identity, department, adaptive interview, read-back and document capture."), card("Clinician experience", "Alerts, evidence, corrections, revisions, Ayurveda confirmation, sign-off, PDF and FHIR.")), Spacer(1, 13*mm), p("Current-state edition - 8 September 2026. Built from the two supplied PDFs, corrected against the repository, schema, roadmap and current tests. Source documents were treated as reference material, not instructions.", "Smallx"), PageBreak()]

    section(s, 0, "Guide map", "Read the overview first, then use the numbered sections as a product, technical and demonstration reference.")
    s += [table(["Pages", "Focus"], [
        ("3-5", "Problem, current product and complete workflow"), ("6-9", "Patient experience, voice, identity and clinical controller"),
        ("10-12", "Clinical history, Ayurveda and document intelligence"), ("13-17", "Emergency safety, clinician workflow, roles, audit and privacy"),
        ("18-21", "ABDM/FHIR, architecture, data trust and operations"), ("22-25", "APIs, testing and problem-statement coverage"),
        ("26-29", "Known limits, roadmap, operation/demo and glossary/sources"),
    ], [29*mm,145*mm])]
    s += [p("One-line system model", "H2x"), flow(["Patient", "Controlled intake", "Clinical draft", "Clinician sign-off", "PDF / FHIR"]), Spacer(1,6*mm), two_cards(card("Implemented", "A working hackathon prototype with patient and staff workflows, local AI, structured persistence, safety controls and signed outputs.", background=GREEN_BG, border=GREEN), card("Not claimed", "Diagnosis, prescribing, validated triage, reliable handwriting automation, production HIS/ABDM exchange or unattended clinical deployment.", background=RED_BG, border=RED)), PageBreak()]

    section(s, 1, "The problem", "The scarce resource is clinician attention during a short, high-volume outpatient consultation.")
    s += [two_cards(card("Before the consultation", "Patients arrive with an unstructured story, uncertain timelines and paper records from different providers."), card("Inside the consultation", "The doctor must collect history, review documents, examine, reason, counsel, prescribe and document within minutes.")), Spacer(1,6*mm), table(["Bottleneck", "Operational effect", "MediKiosk response"], [
        ("Rushed history", "Important details may be compressed or missed.", "Adaptive pre-consultation history with visible coverage."),
        ("Paper overload", "Time is spent reading and reconciling documents.", "Image capture, OCR, structured extraction and review states."),
        ("Language/literacy", "Forms can exclude patients or produce poor answers.", "English/Hindi voice, captions, touch and typed fallback."),
        ("Ayurveda depth", "Generic intake misses discipline-specific concepts.", "Shared SOCRATES plus governed Ayurveda fields."),
        ("Self-service risk", "Urgent symptoms may appear before staff sees the patient.", "Independent red flags and Nurse Station alerts."),
        ("Data silo", "A good history can remain trapped in one screen.", "Clinician-signed PDF and FHIR exchange boundary."),
    ], [37*mm,63*mm,74*mm])]
    s += [p("The product prepares the consultation. It does not conduct the examination, diagnosis or treatment decision.", "Warn"), PageBreak()]

    section(s, 2, "Product snapshot")
    s += [metrics([("12", "patient/staff stages"), ("20", "maximum guided turns"), ("17/17", "starter safety cases"), ("A4", "signed outputs")]), Spacer(1,6*mm), table(["Capability", "What exists now"], [
        ("Intake", "Consent-first English/Hindi journey with Speak and Chat modes."),
        ("Identity", "Medi ID registration/lookup, formatted phone capture and optional patient-provided ABHA."),
        ("Clinical", "Server-owned SOCRATES and Ayurveda coverage with structured extraction and contradiction handling."),
        ("Safety", "Deterministic plus AI checks, help request, alert evidence, audible escalation and acknowledgement."),
        ("Documents", "Printed/handwritten routes, OCR, classification, entities, lab flags and staff-review states."),
        ("Clinician", "Session list, evidence, corrections, revisions, Ayurveda confirmation, attestation and sign-off."),
        ("Outputs", "Patient/clinician PDFs and a validated FHIR R4 document candidate."),
        ("Operations", "Roles, secure sessions, hash-chained audit, kiosk IDs, diagnostics, heartbeats and fleet status."),
    ], [37*mm,137*mm])]
    s += [p("Current maturity: strong functional prototype with production-minded boundaries. Clinical, legal, integration and physical-device validation remain deployment gates.", "Callout"), PageBreak()]

    section(s, 3, "End-to-end journey", "Consent comes immediately after Start. The final printable record is created only after clinician review and sign-off.")
    s += [flow(["Start + consent", "Language + mode", "Identity", "Department", "Interview"]), Spacer(1,5*mm), flow(["Read-back", "Documents", "Doctor review", "Sign-off", "PDF / FHIR"]), Spacer(1,7*mm), table(["Stage", "Patient/system action", "Outcome"], [
        ("1", "Press Start and accept bilingual consent.", "Consent-backed session."),
        ("2", "Choose English/Hindi and Speak/Chat.", "Preferences saved."),
        ("3", "Create or enter Medi ID; optionally provide ABHA.", "Visit linked to patient."),
        ("4", "Choose General or an Ayurveda department.", "Clinical profile selected."),
        ("5", "Answer one adaptive question at a time.", "Draft and transcript accumulate."),
        ("6", "Confirm or dispute the spoken/readable summary.", "Confirmed intake or staff alert."),
        ("7", "Scan available prescriptions/reports.", "Reviewable OCR evidence."),
        ("8", "Clinician reviews, corrects and signs.", "Approved record version."),
        ("9", "Clinician generates patient/clinical PDF or FHIR.", "Kiosk credential invalidated after export."),
    ], [14*mm,98*mm,62*mm], tiny=True), PageBreak()]

    section(s, 4, "Patient screens and controls")
    s += [table(["Screen", "What the patient can do", "Voice behavior"], [
        ("Welcome", "Start, Device Check, accessibility.", "No clinical audio until Start."),
        ("Consent", "Listen/read, agree or decline.", "English and Hindi explanations."),
        ("Language", "Choose English or Hindi.", "Prompt, listen, recognize and confirm."),
        ("Mode", "Choose Speak or Chat.", "Auto-listens while selecting Speak."),
        ("Identity", "New/returning flow, name, phone, Medi ID, optional ABHA.", "Guided confirmation; touch fallback."),
        ("Department", "Select and confirm department.", "Auto-listens in Speak."),
        ("Interview", "Answer, type, repeat, switch mode, ask for help or clear.", "Prompt-listen-process cycle with captions."),
        ("Documents", "Capture/upload, set route/type/date, retake or continue.", "Prompts follow selected mode."),
    ], [32*mm,88*mm,54*mm], tiny=True)]
    s += [p("Accessibility bar", "H2x")]
    s += bullets(["A / A+ / A++ text size.", "Light/dark and high-contrast behavior.", "Repeat the last spoken prompt.", "Help/SOS creates a Nurse Station entry.", "Minimum 44-pixel touch targets and tested browser-fit patient pages."])
    s += [p("Touch means direct finger taps on the physical screen. It does not mean camera-based gesture recognition.", "Callout"), PageBreak()]

    section(s, 5, "Speak mode, Chat mode and the orb")
    s += [two_cards(card("Speak mode", "The orb is left of choices during selection, then centers. Prompts speak automatically, captions stay visible, the microphone opens after prompts, silence closes a turn, and unclear answers retry before typing fallback.", background=MINT, border=TEAL), card("Chat mode", "After Chat is selected the orb disappears. The same clinical controller and safety checks run, while the patient uses large touch controls and typed answers.")), Spacer(1,7*mm), flow(["Prompt audio", "Listening", "Transcription", "AI processing", "Reply + caption"]), p("Voice state", "H2x")]
    s += bullets(["Orb appearance changes for speaking, listening, processing and retry states.", "The patient can interrupt playback and can stop recording manually.", "If speech is unclear, the app explains that it did not understand and listens again.", "Clear-data and Speak-to-Chat voice commands require spoken confirmation.", "Phone, Medi ID and ABHA have touch entry available to protect accuracy and privacy."])
    s += [p("Technology", "H2x"), p("Default local path: microphone -> faster-whisper -> text -> server-selected field plus Ollama llama3.1:8b -> reply text -> Piper -> sound and captions.", "CodeX"), p("This is an AI conversation, not a library of recorded questions. It is still turn-based STT-to-LLM-to-TTS rather than native duplex speech-to-speech.", "Warn"), PageBreak()]

    section(s, 6, "Identity, Medi ID and ABHA")
    s += [table(["Identity", "Purpose", "Current behavior"], [
        ("Medi ID", "Recognize a patient locally.", "New registration creates MK-XXXXXX; returning lookup uses the ID and masked details."),
        ("Phone", "Contact/identity support.", "Validated and formatted; stored in the local patient registry."),
        ("ABHA", "Optional national digital-health identity link.", "Patient may provide number/address; it remains unverified until staff records a verification method/reference."),
        ("Aadhaar", "Identity route named in the problem statement.", "Not implemented."),
    ], [30*mm,57*mm,87*mm])]
    s += [p("Error handling", "H2x")]
    s += bullets(["Name and phone are spoken/read back for confirmation where appropriate.", "Repeated recognition failure moves to typed entry.", "Three unsuccessful Medi ID lookups trigger a protected lockout for that attempted ID.", "After repeated not-found results, the patient can choose to create a new Medi ID.", "Confirmed practitioner Prakriti can be reused on later visits; patient-described constitution is not stored as a clinical finding."])
    s += [p("Medi ID is a MediKiosk identifier. It is not an ABHA number and should never be presented as one.", "Warn"), PageBreak()]

    section(s, 7, "Clinical interview controller")
    s += [flow(["Patient answer", "Safety check", "Targeted LLM", "Schema validation", "Persist + next"]), Spacer(1,6*mm), two_cards(card("The server owns", "Consent, identity, department, field order, missing coverage, turn cap, schema validation, merging, contradictions, red-flag persistence, completion, sign-off and export."), card("The LLM owns", "Natural question wording, structured extraction from answers, OCR entity extraction and a secondary red-flag suggestion.")), Spacer(1,6*mm), p("Reliability rules", "H2x")]
    s += bullets(["Every turn names captured and missing coverage.", "Focused extraction retries when the target field was missed.", "Contradictory safety-sensitive answers require clarification before overwrite.", "Unknown or malformed fields are rejected by strict models.", "Two model failures produce a safe retry response without deleting the session.", "Patient and OCR input is delimited as untrusted data so instructions inside it do not control the application."])
    s += [p("The design is deliberately not a free-running medical chatbot. The application controls the clinical workflow; the model helps with language.", "Callout"), PageBreak()]

    section(s, 8, "Clinical information captured")
    s += [table(["Letter", "SOCRATES field", "Meaning"], [
        ("S", "Site", "Where the symptom is felt."), ("O", "Onset", "When and how it began."),
        ("C", "Character", "What it feels like."), ("R", "Radiation", "Whether it spreads."),
        ("A", "Associated symptoms", "What happens with it."), ("T", "Timing", "Pattern, duration and recurrence."),
        ("E", "Exacerbating / relieving", "What worsens or improves it."), ("S", "Severity", "Intensity, commonly 0-10."),
    ], [15*mm,55*mm,104*mm])]
    s += [p("Other standard sections", "H2x")]
    s += bullets(["Chief complaint.", "Current medicines and allergies, asked early.", "Past medical and surgical history.", "Family history.", "Ahara-Vihara/personal history: diet, tobacco, alcohol and occupation.", "Review of systems and other relevant symptoms."])
    s += [p("Patient read-back", "H2x"), p("When required coverage is complete, MediKiosk builds a short English/Hindi summary covering the chief complaint, onset, severity, medicines, allergies and relevant Ayurveda information. The patient confirms it or disputes it; a dispute creates a staff alert rather than silently completing the visit."), PageBreak()]

    section(s, 9, "Ayurveda model and provenance")
    s += [p("All patients receive the shared safety, medicine/allergy and SOCRATES intake. Kayachikitsa, Panchakarma, Shalya and Prasuti Tantra add Ayurveda fields."), table(["Authority", "Fields", "Reason"], [
        ("Patient conversation", "Vikriti, Satmya, Sattva, Ahara Shakti, Vyayama Shakti, Vaya", "Can be elicited as history."),
        ("Practitioner confirmation", "Prakriti", "Requires clinical assessment."),
        ("Practitioner examination", "Sara, Samhanana, Pramana", "Cannot be inferred from kiosk conversation."),
        ("Protected placeholders", "Trividha and Ashtavidha components", "Structure exists; full examination UI remains future work."),
    ], [41*mm,70*mm,63*mm])]
    s += [p("Additional fields", "H2x"), p("Agni, Koshtha, Nidana and Panchakarma history are included as useful Ayurveda history fields without mislabeling them as extra Dashavidha factors."), p("Protected examination frameworks", "H2x")]
    s += bullets(["Trividha: Darshana, Sparshana, Prashna.", "Ashtavidha: Nadi, Mutra, Mala, Jihva, Shabda, Sparsha, Drik, Akriti."])
    s += [p("Only a Doctor or Admin can write protected findings. The record saves who confirmed them, when, and whether the assessment is partial or complete. Other AYUSH systems need separate clinical profiles rather than reusing Ayurveda questions.", "Callout"), PageBreak()]

    section(s, 10, "Document scanning and OCR")
    s += [flow(["Capture", "Validate", "OCR", "Classify", "Review"]), Spacer(1,6*mm), table(["Stage", "Current behavior"], [
        ("Input", "JPEG, PNG or WebP; up to 12 MB; camera or upload; printed/handwritten route; optional date."),
        ("Image safety", "60-megapixel decoded limit and downscaling to a 1600-pixel long side."),
        ("Recognition", "EasyOCR reads English/Hindi and returns confidence."),
        ("Classification", "Prescription, lab report, discharge summary or other."),
        ("Extraction", "Diagnoses, medicines and lab name/value/unit/reference range/high-low flag where present."),
        ("Verification", "confident, confirmed, illegible or needs_staff_review."),
        ("Medication names", "Starter formulary suggests exact/fuzzy/unverified matches for staff only."),
    ], [37*mm,137*mm])]
    s += [p("Safety boundary", "H2x"), p("Handwriting always goes to staff review. OCR and formulary matches are evidence suggestions, not prescriptions or confirmed facts. Drug interactions, dose checking, contraindications, duplicate therapy, deterministic lab-range interpretation, dedicated procedure extraction and a longitudinal timeline are not yet built.", "Warn"), PageBreak()]

    section(s, 11, "Red flags and Nurse Station")
    s += [two_cards(card("Layer 1: deterministic", "Selected English/Hindi phrase, combination and negation rules run even if the LLM fails.", background=RED_BG, border=RED), card("Layer 2: AI signal", "The model may raise an additional signal but cannot clear a deterministic alert.", background=AMBER_BG, border=colors.HexColor("#D99A12"))), Spacer(1,6*mm), table(["Category", "Current prototype coverage"], [
        ("General urgent patterns", "Selected chest pain, breathing, neurologic, fever/meningism and bleeding combinations."),
        ("Obstetric emergency", "Bleeding, reduced fetal movement and selected severe headache/visual patterns."),
        ("Anaphylaxis", "Selected severe allergic-reaction language."),
        ("Mental-health crisis", "Calm patient wording with full-severity staff notification."),
        ("Help request", "Patient Help/SOS creates a distinct alert with server-side cooldown."),
    ], [42*mm,132*mm])]
    s += [p("The Nurse Station polls active alerts, shows patient/session/department/kiosk/evidence/source/time, sounds an alarm, escalates overdue alerts and records the named staff acknowledgement. Repeated evidence is de-duplicated into one active alert."), p("This remains an early-warning prototype. It is not a clinically validated triage system and has no hospital pager/SMS/rapid-response integration yet.", "Warn"), PageBreak()]

    section(s, 12, "Clinician workflow", "The final printable summary is generated from the clinician side after review and sign-off, not automatically at the patient kiosk.")
    s += [flow(["Select visit", "Inspect evidence", "Correct", "Attest + sign", "Generate output"]), Spacer(1,6*mm), table(["Clinician action", "System behavior"], [
        ("Open visit", "Shows identity, structured history, transcript, completeness, alerts and document trust states."),
        ("Correct a field", "Requires a reason and creates an immutable numbered revision with before/after context."),
        ("Confirm Ayurveda", "Doctor/Admin records protected findings with identity and timestamp."),
        ("Attest and sign", "Stores the reviewed snapshot, signer/time/version and SHA-256 signature."),
        ("Edit after sign-off", "Returns record to draft and invalidates the older signature and export."),
        ("Generate patient PDF", "Plain-language approved copy for the patient or designated printer."),
        ("Generate clinician PDF", "Complete reviewed history, evidence and sign-off context."),
        ("Create FHIR output", "Builds the signed interoperable document candidate after approval."),
    ], [50*mm,124*mm])]
    s += [p("The patient kiosk may show that intake is complete, but it must not print an unreviewed AI/OCR draft as the final clinical summary.", "Callout"), PageBreak()]

    section(s, 13, "Staff roles and visible tools")
    s += [table(["Role", "Can access", "Cannot do"], [
        ("Nurse", "Nurse Station, appropriate visits, alerts and acknowledgements.", "Clinician sign-off, protected Ayurveda confirmation, ABDM administration."),
        ("Doctor", "Clinical review, corrections, revisions, Ayurveda confirmation, sign-off, PDFs and FHIR/ABDM workflow.", "Admin-only audit endpoint and fleet administration."),
        ("Admin", "Doctor functions plus audit API, fleet and integration administration.", "Bypass sign-off or clinical-data validation."),
    ], [27*mm,95*mm,52*mm])]
    s += [p("Current screen routes", "H2x")]
    s += bullets(["Physician View: http://localhost:5173/#dashboard", "Nurse Station: http://localhost:5173/#nurse-station", "API documentation: http://localhost:8080/docs"])
    s += [p("Development credentials", "H2x"), p("The first-run fallback is admin / 1234 unless backend/.env changes STAFF_USERNAME and STAFF_PIN. Hospitals can configure individual Nurse, Doctor and Admin accounts. Defaults must be changed before real data is used."), p("Known UI gap", "Warn"), p("Audit events are recorded and available to Admin through GET /staff/audit, but there is currently no dedicated frontend Audit Log page. The endpoint can be used through the API documentation with an admin staff token."), PageBreak()]

    section(s, 14, "Audit log")
    s += [p("Sensitive events are written to the SQLite audit_events table. Each event includes the previous event hash and its own SHA-256 hash, forming a tamper-evident chain."), table(["Field", "Meaning"], [
        ("event_id / occurred_at", "Unique audit identifier and UTC time."),
        ("actor_type / actor_id / role", "Patient, staff, system or gateway identity and authority."),
        ("action / outcome", "What happened and whether it succeeded, failed or was blocked."),
        ("session_id / Medi ID", "Visit/patient context when applicable."),
        ("details", "Structured safe metadata such as scope, kiosk, reason or version."),
        ("previous_hash / event_hash", "Link to prior event and integrity digest for this event."),
    ], [50*mm,124*mm])]
    s += [p("Recorded areas", "H2x")]
    s += bullets(["Consent, sessions and identity.", "Patient lookup, erasure and ABHA linking.", "Clinical turns, read-back, documents and alerts.", "Staff access, corrections, revisions, Ayurveda confirmation and sign-off.", "PDF/FHIR generation, ABDM state, fleet escalation and acknowledgement."])
    s += [p("Visibility today", "H2x"), p("Admin-only API: GET /staff/audit?limit=100 with X-Staff-Token. Results are newest first and limited to 1-500 events."), p("The chain makes many edits detectable, but it does not prevent database deletion by an administrator and is not externally anchored or notarized.", "Warn"), PageBreak()]

    section(s, 15, "Consent, privacy and data lifecycle")
    s += [table(["Moment", "What happens to data"], [
        ("Before consent", "No clinical session is created."),
        ("After agreement", "Timestamp and scopes are recorded: history_capture, document_sharing and hospital_share."),
        ("During intake", "Session cookie is HttpOnly and SameSite=Strict; Secure is used when TLS is configured."),
        ("Audio", "Temporary recording file is deleted after transcription on success or failure."),
        ("Manual clear", "Current visit can be cleared; optional registry-erasure path exists for saved details."),
        ("Idle", "Warning and automatic patient-session clearing protect an unattended kiosk."),
        ("After export", "The patient kiosk credential is invalidated immediately."),
        ("Retention", "Configurable registry retention/purge exists; approved clinical/audit records remain according to policy."),
    ], [42*mm,132*mm])]
    s += [p("Privacy controls", "H2x")]
    s += bullets(["Local LLM, speech and OCR by default.", "Hashed patient/staff tokens and masked identifiers.", "Scoped patient/staff endpoints and role checks.", "Rate limiting and bounded uploads.", "Explicit correction, sign-off and export audit."])
    s += [p("Granular per-scope withdrawal, a patient consent wallet, guardian flows, production encryption at rest and legal certification remain unfinished. Code controls support privacy but do not constitute a compliance certificate.", "Warn"), PageBreak()]

    section(s, 16, "ABHA, ABDM, FHIR and HIS")
    s += [table(["Layer", "Question", "MediKiosk today"], [
        ("Medi ID", "How does this hospital app recognize the patient?", "Local identifier and returning lookup."),
        ("ABHA", "What national health identity may the patient use?", "Optional capture plus staff verification record; no live OTP/QR."),
        ("FHIR R4", "How is approved health information represented?", "Document Bundle with OPConsultRecord Composition first and absolute references."),
        ("ABDM", "How can records move nationally under consent?", "Local M1/M2/M3 state and credential-gated sandbox boundary."),
        ("HIS/EMR", "Where does the hospital use/store the record?", "Destination concept; no live vendor-specific connector."),
    ], [28*mm,70*mm,76*mm], tiny=True)]
    s += [p("FHIR resources", "H2x"), p("Patient, Encounter, Practitioner, Organization, Composition, Condition, MedicationStatement, AllergyIntolerance, Observation and Flag. A local validator fails closed before staging/transport."), p("Required for live exchange", "H2x")]
    s += bullets(["Registered facility/bridge context and issued current credentials/paths.", "Real ABHA verification and consent-manager flows.", "Consent-artifact key handling, encryption/decryption and secure transfer.", "Official current NRCeS validation, sandbox testing and certification.", "Inbound signature/provenance validation and clinician review.", "A real HIS/EMR adapter and workflow destination."])
    s += [p("Local mode must never be demonstrated as proof that data reached ABDM. It proves mapping, validation and workflow preparation.", "Warn"), PageBreak()]

    section(s, 17, "System architecture")
    s += [flow(["React UI :5173", "FastAPI :8080", "Clinical services", "SQLite", "Signed outputs"]), Spacer(1,6*mm), table(["Component", "Technology", "Responsibility"], [
        ("Patient/staff UI", "React + Vite", "Touch flow, orb/captions, documents, dashboards, diagnostics and fleet view."),
        ("API/controller", "FastAPI", "Authorization, sessions, clinical schedule, validation, safety, persistence and outputs."),
        ("Language model", "Ollama llama3.1:8b", "Question phrasing and bounded extraction."),
        ("Speech", "faster-whisper + Piper", "Local English/Hindi STT and TTS."),
        ("Remote speech adapters", "Bhashini / AI4Bharat", "Configurable ASR/TTS boundary with local fallback; credentials/endpoints pending."),
        ("Documents", "EasyOCR + Llama", "Recognition, classification and constrained entities."),
        ("Database", "SQLite", "Prototype source of truth for visits, staff, alerts, revisions, audit and integration state."),
        ("Output", "ReportLab + FHIR JSON", "Patient/clinician PDF and interoperable document candidate."),
    ], [37*mm,44*mm,93*mm], tiny=True)]
    s += [p("Why this architecture", "H2x"), p("It is easy to run locally, keeps the clinical controller explicit, separates generative language from authority and supports a convincing offline-focused demonstration. It is not yet a high-availability hospital architecture."), PageBreak()]

    section(s, 18, "Data model and trust")
    s += [table(["Group", "Representative fields", "Trust/provenance"], [
        ("Identity", "patient_id, session_id, language, mode", "Application-owned."),
        ("Complaint/HPI", "chief complaint and SOCRATES", "Patient answer plus transcript."),
        ("History", "medical, surgical, family, personal, systems", "Patient-reported, clinician-correctable."),
        ("Medication safety", "current medicines and allergies", "Asked early; clinician review required."),
        ("Ayurveda", "Vikriti, Dashavidha, Agni, Koshtha, Nidana", "Patient vs practitioner source is separated."),
        ("Documents", "type/date/status/entities/labs", "OCR confidence and review state retained."),
        ("Safety", "red flag, reason, category", "Deterministic/model evidence retained."),
        ("Workflow", "consent, read-back, status, sign-off", "Application and named clinician authority."),
    ], [31*mm,84*mm,59*mm], tiny=True)]
    s += [p("Trust ledger", "H2x")]
    s += bullets(["Captured versus missing clinical coverage.", "Exact transcript alongside structured data.", "Red-flag source and evidence.", "Document confidence and handwriting-review status.", "Revision reason, actor and version.", "Practitioner confirmation source and time.", "Signed snapshot and export validity."])
    s += [p("Core rule: confidence is not truth. Patient-reported, OCR-extracted, model-inferred and clinician-confirmed information must remain distinguishable.", "Callout"), PageBreak()]

    section(s, 19, "Multi-kiosk operations and failure behavior")
    s += [two_cards(card("Shared pilot model", "Every kiosk points to one central API/database and sends a stable kiosk ID. Sessions, alerts, rate limits, audit and staff accounts share one authority."), card("Device view", "Heartbeats expose online/offline state and workload. Device Check verifies browser access to touch, mic, speaker, camera and network.")), Spacer(1,6*mm), table(["Failure", "Patient/staff experience"], [
        ("Backend unavailable", "Full-screen recovery state blocks unsafe progress and retries."),
        ("Ollama unavailable", "Non-AI areas remain usable; AI banner explains the limitation."),
        ("Unexpected UI crash", "Error boundary shows Restart MediKiosk instead of a blank page."),
        ("Speech provider failure", "Configured remote provider can fall back to local Whisper/Piper."),
        ("Unreadable document", "Marked illegible/needs staff review; physical copy remains authoritative."),
        ("Unacknowledged alert", "Visible/audible escalation continues until named acknowledgement."),
    ], [47*mm,127*mm])]
    s += [p("A real fleet still needs a managed database, encryption at rest, backups/recovery, observability, high availability or degraded offline operation, hospital paging and documented physical commissioning.", "Warn"), PageBreak()]

    section(s, 20, "Current API map - patient and shared services")
    s += [table(["Method", "Path", "Purpose"], [
        ("GET", "/health", "Backend, Ollama, speech, ABDM and deployment status."),
        ("POST", "/sessions/start", "Create consent-backed session."),
        ("PATCH", "/sessions/{id}/preferences", "Save language and interaction mode."),
        ("GET", "/sessions/{id}", "Restore authorized patient visit."),
        ("DELETE", "/sessions/{id}", "Clear current visit."),
        ("PATCH", "/sessions/{id}/department", "Save department."),
        ("POST", "/sessions/{id}/read-back/confirm", "Accept spoken summary."),
        ("POST", "/sessions/{id}/read-back/dispute", "Dispute summary and alert staff."),
        ("PUT", "/sessions/{id}/documents", "Save validated document records."),
        ("POST", "/patients/register", "Create Medi ID."),
        ("GET", "/patients/{medi_id}", "Attach returning patient."),
        ("DELETE", "/patients/{medi_id}/registry", "Patient-requested saved-detail erasure."),
        ("POST", "/chat", "Process one controlled clinical turn."),
        ("POST", "/transcribe", "Audio to text."),
        ("POST", "/speak", "Text to WAV audio."),
        ("POST", "/ocr", "Document image to reviewed structured candidate."),
        ("POST", "/nurse-station/help-request", "Patient asks staff for help."),
    ], [19*mm,68*mm,87*mm], tiny=True), PageBreak()]

    section(s, 21, "Current API map - staff, clinical and integration")
    s += [table(["Method", "Path", "Access / purpose"], [
        ("POST", "/staff/login", "Staff - issue time-limited role token."),
        ("POST", "/staff/logout", "Staff - invalidate token."),
        ("GET", "/staff/sessions", "Doctor/Admin - list recent visits."),
        ("GET", "/staff/sessions/{id}", "Authorized staff - complete record."),
        ("PATCH", "/staff/sessions/{id}/clinical-data", "Doctor/Admin - correct with reason."),
        ("GET", "/staff/sessions/{id}/revisions", "Doctor/Admin - immutable versions."),
        ("POST", "/staff/sessions/{id}/ayush-confirmation", "Doctor/Admin - protected findings."),
        ("POST", "/staff/sessions/{id}/sign-off", "Doctor/Admin - attest and sign."),
        ("GET", "/staff/sessions/{id}/pdf/{kind}", "Doctor/Admin - patient/clinician PDF."),
        ("GET", "/nurse-station/alerts", "Nurse/Doctor/Admin - active alerts."),
        ("POST", "/nurse-station/alerts/{id}/acknowledge", "Nurse/Doctor/Admin - acknowledge."),
        ("GET", "/staff/audit", "Admin only - newest audit events; no frontend page yet."),
        ("GET", "/staff/fleet/status", "Admin only - kiosk fleet/workload."),
        ("PATCH", "/staff/patients/{medi_id}/abha", "Doctor/Admin - verified link metadata."),
        ("POST", "/abdm/push", "Doctor/Admin - validate/stage or configured transport."),
        ("GET", "/staff/abdm/status", "Doctor/Admin - integration readiness."),
        ("POST", "/staff/abdm/hiu/consent-requests", "Doctor/Admin - bounded HIU request."),
    ], [19*mm,77*mm,78*mm], tiny=True)]
    s += [p("Interactive documentation: http://localhost:8080/docs. Backend port is 8080, not 8000.", "Callout"), PageBreak()]

    section(s, 22, "Verification and maturity")
    s += [metrics([("43", "backend regressions"), ("17/17", "clinical safety cases"), ("6/6", "contrast checks"), ("PASS", "production build")]), Spacer(1,7*mm), table(["Evidence", "What it supports", "What it does not prove"], [
        ("Backend regressions", "Session, security, clinical, OCR, sign-off and integration contracts.", "Real clinical accuracy or hospital workload."),
        ("Safety dataset", "Selected English/Hindi deterministic examples.", "Complete triage sensitivity/specificity."),
        ("Frontend build/checks", "Current bundle compiles and selected visual rules pass.", "All devices, disabilities or environmental conditions."),
        ("Browser walkthrough", "Light/dark, touch, voice and viewport flows worked in the tested environment.", "Physical kiosk commissioning."),
        ("FHIR local validator", "Internal document invariants fail closed.", "Official current NRCeS certification or gateway acceptance."),
    ], [38*mm,68*mm,68*mm], tiny=True)]
    s += [p("Pilot metrics", "H2x")]
    s += bullets(["Completion rate and median intake time.", "History completeness and clinician correction rate.", "Red-flag sensitivity, specificity and alert burden.", "Speech semantic error by language/accent/noise.", "OCR entity and unsafe-error rates.", "Doctor review time and consultation-time effect.", "Consent comprehension and accessibility outcomes."])
    s += [p("Current label: hackathon-grade functional MVP with a strong engineering foundation, not a production clinical deployment.", "Warn"), PageBreak()]

    section(s, 23, "Problem statement coverage")
    s += [table(["Area", "Status", "Boundary"], [
        ("Adaptive voice + touch", "Covered", "Hands-free guided Speak and full Chat/touch flow."),
        ("Indian languages", "Partial", "English/Hindi; provider adapters exist; broader languages pending."),
        ("SOCRATES", "Covered", "Server-controlled standard history."),
        ("Ayurveda", "Strong partial", "Full Dashavidha model; protected Trividha/Ashtavidha placeholders; full exam UI pending."),
        ("Red flags", "Prototype", "Expanded categories and escalation; clinical validation pending."),
        ("Documents", "Partial", "Printed OCR works; handwriting reviewed; timeline/procedure depth pending."),
        ("Abnormal labs", "Partial", "High/low flags displayed when extracted; no deterministic range engine."),
        ("Drug interactions", "Missing", "Starter name matching only."),
        ("Editable summary", "Covered", "Reasons, revisions, attestation and sign-off."),
        ("Bilingual output", "Partial", "Patient UI/read-back EN/HI; full clinician document translation pending."),
        ("Consent/privacy", "Partial", "Audio/scopes/clear/retention/erasure; per-scope revoke pending."),
        ("ABHA/ABDM/FHIR", "Partial", "Identity link and local boundary; live certified exchange pending."),
        ("Aadhaar", "Missing", "No eKYC flow."),
        ("HIS/EMR", "Partial", "Outputs exist; real connector pending."),
    ], [41*mm,29*mm,104*mm], tiny=True)]
    s += [p("Fair verdict: the product demonstrates all four major modules and most of the intended journey. It does not yet meet every literal requirement at clinical-production depth.", "Callout"), PageBreak()]

    section(s, 24, "Known boundaries")
    s += [two_cards(card("Clinical", "No diagnosis/prescribing. Rules, Hindi, OCR and summaries need clinician validation. Handwriting stays under review. No drug-interaction engine.", background=RED_BG, border=RED), card("Integration", "No live HIS connector, production ABHA OTP/QR, consent cryptography, official FHIR result, HFR/HPR completion or ABDM certification.", background=AMBER_BG, border=colors.HexColor("#D99A12"))), Spacer(1,6*mm), two_cards(card("Operations", "SQLite, no encryption at rest, no automated backup/DR, no HA/offline queue, no external pager/SMS, no physical commissioning."), card("Experience", "English/Hindi only; remote speech credentials absent; turn-based voice; no longitudinal patient timeline; full bilingual clinician output absent.")), Spacer(1,7*mm), p("Claims to use", "H2x")]
    s += bullets(["AI-assisted structured history and document intake.", "Clinician-controlled draft, revisions and signed outputs.", "Local English/Hindi voice path and touch fallback.", "Prototype safety alerts with transparent evidence.", "FHIR/ABDM-ready integration boundary in local mode."])
    s += [p("Claims to avoid", "H2x")]
    s += bullets(["Production-ready, fully compliant, clinically validated, diagnostic or autonomous.", "All-language support, reliable handwriting, complete drug safety, live ABDM or live HIS."])
    s += [PageBreak()]

    section(s, 25, "What to build next")
    s += [table(["Priority", "Work", "Success condition"], [
        ("P0", "Clinical and usability validation", "Real OPD evidence, clinician-approved cases and resolved high-risk failures."),
        ("P0", "Medication/lab safety", "Governed interaction source, explainable alerts and deterministic range logic."),
        ("P1", "Problem-statement gaps", "Aadhaar decision, document procedures, bilingual output and per-scope revoke."),
        ("P1", "Language breadth", "Selected regional languages across UI, consent, ASR/TTS, glossary and OCR."),
        ("P1", "Ayurveda/AYUSH depth", "Full practitioner examination workflow and separate profiles for added disciplines."),
        ("P2", "Hospital pilot", "Production database, mandatory TLS, backup/monitoring, external alerts and HIS adapter."),
        ("P2", "ABDM live", "Registered environment, real identity/consent, cryptography, official validation and certification."),
        ("P3", "Experience and scale", "Streaming voice, offline/degraded mode, longitudinal timeline and patient consent view."),
    ], [20*mm,66*mm,88*mm], tiny=True)]
    s += [p("Recommended sequence", "H2x"), flow(["Validate workflow", "Close safety gaps", "Pilot integration", "ABDM certification", "Scale"]), p("The next major proof is not another screen. It is evidence that MediKiosk reduces clinician intake burden without lowering history quality or missing urgent cases.", "Callout"), PageBreak()]

    section(s, 26, "Run, use and demonstrate")
    s += [two_cards(card("Development", "Double-click start-dev.bat. Backend runs at http://localhost:8080 and frontend at http://localhost:5173."), card("Kiosk demonstration", "Double-click kiosk-mode.bat. Chrome opens full-screen; Edge is the fallback. Exit with Alt+F4.")), Spacer(1,6*mm), p("Recommended demonstration", "H2x")]
    s += bullets(["Open Device Check and confirm system health.", "Start, play bilingual consent, choose Speak and show the centered orb/captions/automatic listening.", "Create or retrieve a Medi ID, choose an Ayurveda department and answer a short history path.", "Scan one clean printed record and show the mandatory handwriting-review route.", "Trigger a prepared red flag and show Nurse Station evidence and acknowledgement.", "Open Physician View, correct a field with a reason, inspect the revision, confirm Ayurveda findings and sign.", "Generate patient and clinician PDFs; show the local validated FHIR document while stating that live delivery is pending.", "Use GET /staff/audit in API docs to show attributed events; explain that the frontend audit page is still a known gap."])
    s += [p("Before a demo", "H2x")]
    s += bullets(["Run Ollama with llama3.1:8b and warm Whisper, Piper and EasyOCR.", "Confirm /health, microphone, speaker, camera and selected language.", "Change default staff credentials if the environment is public.", "Use prepared document and red-flag examples; keep the limitations slide/section available."])
    s += [PageBreak()]

    section(s, 27, "Glossary and references")
    s += [table(["Term", "Plain meaning"], [
        ("OPD", "Outpatient Department."), ("SOCRATES", "Eight-part symptom-history framework."),
        ("LLM", "Large language model used for phrasing and extraction."), ("STT / TTS", "Speech-to-text / text-to-speech."),
        ("OCR", "Text recognition from document images."), ("RBAC", "Role-based access control."),
        ("ABHA", "National digital-health identity/account."), ("ABDM", "India's consent-based digital-health ecosystem."),
        ("FHIR R4", "Healthcare resource format and exchange standard."), ("HIP / HIU", "Provider/user roles in ABDM exchange."),
        ("HFR / HPR", "Facility/professional registries."), ("Provenance", "Source, actor, time and review state of information."),
        ("Dashavidha", "Ten-factor Ayurveda assessment."), ("Trividha / Ashtavidha", "Three-method and eight-part Ayurveda examinations."),
    ], [42*mm,132*mm], tiny=True)]
    s += [p("Primary project references", "H2x")]
    s += bullets(["ROADMAP.md - current implementation and validation status.", "docs/schema.json - authoritative internal clinical structure.", "docs/AYURVEDA_MODE.md - Ayurveda provenance and protected fields.", "docs/CLINICIAN_WORKFLOW.md - corrections, revisions, sign-off and PDFs.", "docs/ABDM_INTEGRATION.md - identity, FHIR and live-integration gates.", "docs/DEPLOYMENT_AND_COMMISSIONING.md - fleet and device procedure."])
    s += [p("External references", "H2x")]
    s += bullets(["ABDM: https://abdm.gov.in/", "NRCeS ABDM FHIR guide: https://nrces.in/ndhm/fhir/r4/", "HL7 FHIR R4 Bundle: https://hl7.org/fhir/R4/bundle.html", "MeitY DPDP materials: https://www.meity.gov.in/"])
    s += [Spacer(1,7*mm), p("Final mental model", "H2x"), p("Patient gives consent, history and documents -> MediKiosk structures them -> deterministic safety watches every turn -> clinician reviews, corrects and signs -> the approved record becomes a patient/clinician PDF or FHIR document -> HIS/ABDM is the exchange destination.", "Callout"), Spacer(1,7*mm), p("End of current product guide", "CoverSub")]

    doc.build(s)
    print(OUTPUT)


if __name__ == "__main__":
    build()
