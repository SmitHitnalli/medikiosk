"""Generate the complete MediKiosk product, usage, and handoff guide."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "MediKiosk_Complete_Product_Guide.pdf"
NAVY = colors.HexColor("#103B4C")
TEAL = colors.HexColor("#17A6A1")
PALE = colors.HexColor("#EAF7F5")
INK = colors.HexColor("#17313B")
MUTED = colors.HexColor("#5B7078")
AMBER = colors.HexColor("#F4B942")
RED = colors.HexColor("#B42318")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=31, textColor=NAVY, alignment=TA_CENTER, spaceAfter=10))
styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontSize=12, leading=17, textColor=MUTED, alignment=TA_CENTER, spaceAfter=8))
styles.add(ParagraphStyle(name="Section", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=NAVY, spaceAfter=8))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=TEAL, spaceBefore=8, spaceAfter=4))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=9.2, leading=13, textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name="Bulletx", parent=styles["BodyText"], fontSize=9, leading=12.5, textColor=INK, leftIndent=12, firstLineIndent=-7, bulletIndent=3, spaceAfter=3))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontSize=7.7, leading=10.2, textColor=MUTED))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9.3, leading=13, textColor=NAVY, backColor=PALE, borderColor=TEAL, borderWidth=0.6, borderPadding=7, spaceBefore=6, spaceAfter=8))
styles.add(ParagraphStyle(name="Codex", parent=styles["BodyText"], fontName="Courier", fontSize=7.7, leading=10, textColor=INK, backColor=colors.HexColor("#F2F5F6"), borderPadding=6, spaceAfter=5))


def p(text, style="Bodyx"):
    return Paragraph(text, styles[style])


def bullets(items):
    return [p("- " + escape(item), "Bulletx") for item in items]


def table(headers, rows, widths=None, small=False):
    data = [[p(escape(str(x)), "Smallx") for x in headers]]
    data += [[p(escape(str(x)), "Smallx" if small else "Bodyx") for x in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B9C9CE")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5FAFA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def section(story, number, title, intro=None):
    story += [p(f"{number:02d}  {escape(title)}", "Section")]
    if intro:
        story += [p(escape(intro), "Callout")]


def page_decor(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 11 * mm, w, 11 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(16 * mm, h - 7 * mm, "MEDIKIOSK  /  SIH26047")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(16 * mm, 9 * mm, "MediKiosk - Complete Product and Problem Statement Guide")
    canvas.drawRightString(w - 16 * mm, 9 * mm, f"{doc.page}")
    canvas.restoreState()


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=18 * mm, bottomMargin=16 * mm, title="MediKiosk Complete Product and Problem Statement Guide", author="MediKiosk")
    doc.addPageTemplates(PageTemplate(id="main", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")], onPage=page_decor))
    s = []

    s += [Spacer(1, 26 * mm), p("MEDIKIOSK", "CoverTitle"), p("Complete Product and Problem Statement Guide", "CoverTitle"), p("SIH26047 | Patient Case-Taking Software", "CoverSub"), p("Ministry of Ayush / All India Institute of Ayurveda", "CoverSub"), Spacer(1, 8 * mm), p("MediKiosk gathers a consent-backed patient history before consultation, structures it for clinical review, digitizes selected records, raises safety alerts, and prepares a signed interoperable handoff.", "Callout"), Spacer(1, 6 * mm)]
    s.append(table(["Patient", "Clinical staff", "Safety boundary"], [["Consent, identify, speak or type, scan records", "Review, correct, sign, export and respond to alerts", "History collection only - no diagnosis or treatment advice"]], [56 * mm, 56 * mm, 56 * mm]))
    s += [Spacer(1, 18 * mm), p("Current repository state: all eight redesign phases completed. Verified on 8 September 2026 with 23 backend regressions, 8 clinical safety cases, a production frontend build, and a live patient/staff browser walkthrough.", "Smallx"), PageBreak()]

    section(s, 1, "The problem and the intended outcome", "The consultation is too valuable to spend on repeatedly converting an unstructured story into basic history fields.")
    s += bullets([
        "Patients describe symptoms naturally, while clinicians need consistent fields and follow-up answers.",
        "Short consultations combine history, examination, reasoning, counselling, prescribing, and documentation.",
        "Paper prescriptions, laboratory reports, and discharge records are fragmented and difficult to reuse.",
        "AYUSH case-taking needs both shared clinical history and discipline-specific concepts.",
        "Digital health exchange only helps after useful, consented, structured information exists.",
    ])
    s += [p("What SIH26047 expects", "H2x"), p("A patient-facing software system for guided voice and touch history-taking, medical-document digitization, physician-ready summaries, urgent-pattern escalation, and integration with hospital and national digital-health systems."), p("Product boundary", "H2x")]
    s += bullets(["MediKiosk prepares the consultation.", "It does not diagnose, prescribe, replace examination, or guarantee emergency detection.", "A clinician verifies the record and remains responsible for decisions."])
    s += [p("Core outcome: patient input -> structured history -> evidence and alerts -> clinician review -> signed handoff.", "Callout"), PageBreak()]

    section(s, 2, "What the product can do today")
    rows = [
        ("Intake", "Consent-first English/Hindi patient journey with Speak and Chat modes."),
        ("Identity", "New/returning Medi ID, masked lookup, optional ABHA capture, staff-verified ABHA link."),
        ("Clinical", "Server-controlled SOCRATES and AYUSH coverage with structured extraction."),
        ("Safety", "Deterministic and AI-assisted red flags, persistent Nurse Station alerts, escalation."),
        ("Documents", "Printed/handwritten routes, OCR, entity extraction, confidence and review states."),
        ("Clinician", "Edit with reason, revision history, Ayurveda confirmation, attestation, PDFs."),
        ("Exchange", "Validated FHIR R4 document bundle and credential-gated ABDM boundary."),
        ("Operations", "Audit trail, role-based staff access, device checks, kiosk identity, fleet view."),
    ]
    s += [table(["Area", "Current capability"], rows, [35 * mm, 133 * mm]), p("The current voice path is speech-to-text -> Llama text reasoning -> text-to-speech. It is conversational and not a hardcoded question recording, but it is not native real-time speech-to-speech.", "Callout"), PageBreak()]

    section(s, 3, "Complete patient journey")
    journey = [
        ("1", "Start", "Press Start. The consent screen appears before a clinical session is created."),
        ("2", "Consent", "Agree to start securely, or decline and return without continuing."),
        ("3", "Language", "Choose English or Hindi."),
        ("4", "Mode", "Choose Speak or Chat."),
        ("5", "Identity", "Register a new patient or enter a returning Medi ID; ABHA is optional."),
        ("6", "Department", "Select General consultation or one of the supported AYUSH disciplines."),
        ("7", "Interview", "Answer one adaptive history question at a time."),
        ("8", "Documents", "Photograph prior records, confirm their type, and resolve unclear scans."),
        ("9", "Review", "A clinician opens the protected dashboard, verifies, corrects, and signs."),
        ("10", "Finish", "Clear the visit or allow the patient inactivity reset to protect privacy."),
    ]
    s += [table(["Step", "Screen", "Action"], journey, [12 * mm, 32 * mm, 124 * mm]), PageBreak()]

    section(s, 4, "Speak, Chat, orb, and touch behavior")
    s += [table(["Behavior", "Speak mode", "Chat mode"], [
        ("Selection screens", "Orb left, choices right", "Orb left until Chat is selected"),
        ("After selection", "Orb centers", "Orb disappears"),
        ("Answering", "Tap orb to record; typed fallback remains", "Type and use large touch controls"),
        ("Replies", "Captioned and spoken", "Displayed without automatic speech"),
        ("Switching", "Can switch to Chat in the interview", "Can use the available microphone control"),
    ], [42 * mm, 63 * mm, 63 * mm])]
    s += [p("Touch implementation", "H2x")]
    s += bullets(["Touch means direct finger taps on the physical kiosk screen.", "Large controls have a minimum 44-pixel target.", "Phone numbers, Medi IDs, ABHA details, and sensitive identifiers are touch-keyboard only and are never spoken aloud.", "The product does not currently use camera-based hand gestures."])
    s += [p("Voice interaction", "H2x")]
    s += bullets(["Tap the orb or microphone to start and stop.", "Silence can stop recording after about 2.5 seconds.", "Captions always show what the system heard and said.", "Repeat replays the last prompt; typing remains a fallback.", "Local voice uses faster-whisper for recognition and Piper for English/Hindi output."])
    s += [PageBreak()]

    section(s, 5, "Identity, Medi ID, ABHA, and consent")
    s += [p("Medi ID", "H2x")]
    s += bullets(["New registration records basic identity and a validated phone number, then creates an internal ID such as MK-A1B2C3.", "Returning lookup shows a masked phone number.", "Three missing-ID attempts lock lookup for that visit.", "A Medi ID is an internal prototype identifier and is not an ABHA number."])
    s += [p("ABHA", "H2x")]
    s += bullets(["The patient may enter an ABHA number or address during registration.", "The value remains unverified until a doctor/admin records a verification method and reference.", "Verified links support care-context creation after clinician sign-off.", "Real ABHA discovery, OTP, QR, and gateway verification require issued ABDM access and approved flows."])
    s += [p("Consent and privacy", "H2x")]
    s += bullets(["Consent occurs immediately after Start and before conversation setup.", "Consent, identity attachment, access, corrections, sign-off, and export are audited.", "Clearing removes visit data while retaining the reusable registry entry.", "Patient state can recover after refresh; inactivity warns at four minutes and clears at five."])
    s += [PageBreak()]

    section(s, 6, "Departments and AYUSH mode")
    s += [p("The current department selector offers General consultation and AYUSH pathways including Ayurveda, Siddha, Unani, Homeopathy, and Sowa-Rigpa. The chosen department controls additional fields; it never removes shared medication, allergy, safety, and SOCRATES history."), p("Shared clinical intake", "H2x")]
    s += bullets(["Chief complaint and SOCRATES symptom history.", "Current medicines and allergies collected early.", "Past medical/surgical and family history.", "Diet, tobacco, alcohol, occupation, and other symptoms.", "Red-flag monitoring for every department."])
    s += [p("Ayurveda-specific intake", "H2x")]
    s += bullets(["Patient conversation may capture Vikriti, Agni, Nidana, and five conversational Dashavidha factors.", "Prakriti, Sara, Samhanana, and Pramana are protected clinician findings.", "Only a doctor/admin can confirm protected findings, with staff identity, time, and partial/full status.", "Confirmed Prakriti may be reused on later visits.", "Pulse, inspection, palpation, and other physical findings remain clinician work."])
    s += [PageBreak()]

    section(s, 7, "Clinical information and SOCRATES")
    s += [table(["Letter", "Field", "Purpose"], [
        ("S", "Site", "Where the symptom is felt"), ("O", "Onset", "When and how it began"),
        ("C", "Character", "What it feels like"), ("R", "Radiation", "Whether it spreads"),
        ("A", "Associated symptoms", "What occurs with it"), ("T", "Timing", "Pattern and duration"),
        ("E", "Exacerbating/relieving", "What worsens or improves it"), ("S", "Severity", "Intensity, usually 0-10"),
    ], [16 * mm, 48 * mm, 104 * mm])]
    s += [p("The server owns the coverage list and chooses the next missing target. The model phrases that question naturally and extracts the answer into docs/schema.json. This prevents the conversation from becoming a free-form chatbot."), p("Important behavior", "H2x")]
    s += bullets(["Every response reports captured and missing coverage.", "A focused extractor repairs a missed target field.", "Conflicting safety-sensitive answers require clarification before replacement.", "Two invalid or unavailable model responses produce a safe retry prompt.", "The interview ends when required coverage is complete or the 20-turn cap is reached."])
    s += [PageBreak()]

    section(s, 8, "AI architecture and safety controller")
    s += [table(["Component", "Responsibility"], [
        ("FastAPI", "Identity, authorization, field order, validation, merging, alerts, persistence, export."),
        ("Ollama llama3.1:8b", "Natural-language interpretation, question phrasing, structured extraction, OCR entity extraction."),
        ("Pydantic/schema", "Reject unknown or malformed clinical structures."),
        ("SQLite", "Patients, visits, transcripts, documents, alerts, staff sessions, audit, revisions, ABDM state."),
        ("React/Vite", "Patient/staff touchscreen interface and device workflows."),
    ], [44 * mm, 124 * mm])]
    s += [p("The LLM does not own identity, consent, department, interview completion, clinician sign-off, emergency persistence, or FHIR construction.", "Callout"), p("Failure behavior", "H2x")]
    s += bullets(["Ollama loss shows a non-blocking AI-unavailable banner where possible.", "Backend loss shows a recovery screen and continues checking.", "Unexpected React errors show a restart screen instead of a blank page.", "Network, audio, and recording work is canceled on navigation and session reset."])
    s += [PageBreak()]

    section(s, 9, "Red flags, Nurse Station, and escalation")
    s += bullets(["Deterministic rules run before the LLM so selected urgent patterns persist even if AI fails.", "Rules cover selected combinations such as chest pain with breathlessness, chest pain with sweating/dizziness, headache with vision/confusion, fever with stiff neck/drowsiness, unilateral weakness/numbness, and heavy bleeding.", "Common English negations and a focused Hindi safety vocabulary are handled.", "The LLM supplies a secondary signal; it does not replace deterministic checks.", "Patients can also press Call for staff help, which creates a distinct amber alert."])
    s += [p("Nurse Station", "H2x")]
    s += bullets(["Shows patient, department, kiosk, reason, source, and elapsed time.", "Refreshes live and allows acknowledgement by authorized staff.", "Unacknowledged alerts escalate after 120 seconds by default and the escalation is audited.", "There is no SMS, pager, or hospital rapid-response integration yet."])
    s += [p("This is an early-warning prototype and requires clinician validation before safety-critical use.", "Callout"), PageBreak()]

    section(s, 10, "Documents, OCR, handwriting, and formulary")
    s += [table(["Stage", "Behavior"], [
        ("Capture", "Camera or image upload; printed or handwritten route; optional date."),
        ("Validation", "JPEG/PNG/WebP, up to 12 MB; large images reduced to a 1600-pixel long side."),
        ("OCR", "EasyOCR reads English/Hindi text and reports confidence."),
        ("Classification", "Keyword/fuzzy matching suggests prescription, lab report, discharge summary, or other."),
        ("Extraction", "Diagnoses, medicines, lab values, units, ranges, flags, and source notes where available."),
        ("Review", "Confirm type, choose another, retake, or mark unreadable."),
    ], [35 * mm, 133 * mm])]
    s += [p("Handwriting is always marked needs_staff_review; MediKiosk does not claim dependable handwritten recognition. Medicine names are compared with a small starter formulary using exact/fuzzy/unverified suggestions. Suggestions require staff confirmation and are not prescriptions."), PageBreak()]

    section(s, 11, "Staff roles and protected access")
    s += [table(["Role", "Primary access"], [
        ("Nurse", "Nurse Station, alerts, acknowledgement, appropriate visit access."),
        ("Doctor", "Clinical review, corrections, revisions, Ayurveda confirmation, sign-off, PDF, exchange."),
        ("Admin", "Doctor capabilities plus audit, fleet, and integration administration."),
    ], [35 * mm, 133 * mm])]
    s += bullets(["Staff sign in with an individual ID and PIN when accounts are configured.", "The development fallback is admin / 1234 and must be changed.", "Login attempts are rate-limited by username and address in SQLite.", "Staff tokens expire and explicit logout locks the view.", "Every protected operation checks the server-issued staff token and role."])
    s += [p("For a demonstration: open Doctor dashboard from the interview, sign in, choose a recent clinical session, review it, and open Nurse Station from the header."), PageBreak()]

    section(s, 12, "Clinician review, corrections, revisions, and sign-off")
    s += bullets(["The dashboard shows structured history, transcript, missing fields, red-flag evidence, document confidence, ABHA/FHIR status, and recent sessions.", "A clinician can correct the structured record only with a required reason.", "Each correction creates an immutable numbered clinical revision with before/after context and staff attribution.", "Ayurveda protected findings are confirmed separately by a doctor/admin.", "Sign-off requires an explicit attestation and stores a SHA-256 signature of the reviewed snapshot.", "Any later correction or Ayurveda confirmation invalidates the signature and earlier export.", "The clinician must review and sign the new version again.", "Patient and clinician A4 PDFs are generated from the persisted signed record."])
    s += [p("The signature is a workflow-integrity hash and attestation, not a regulated digital signature certificate."), PageBreak()]

    section(s, 13, "ABDM, ABHA, care contexts, and FHIR")
    s += [table(["Term", "Meaning here"], [
        ("ABHA", "Patient health account identifier; capture is optional and linking requires staff verification."),
        ("ABDM", "National digital-health exchange boundary used for identity, consent, and record sharing."),
        ("FHIR R4", "Typed standard used to construct the clinical document bundle."),
        ("Care context", "Signed visit linked to a verified identity for later consented discovery/exchange."),
    ], [34 * mm, 134 * mm])]
    s += [p("Current FHIR output", "H2x")]
    s += bullets(["Bundle.type is document.", "The first resource is an OPConsultRecord Composition.", "Absolute urn:uuid fullUrl references connect Patient, Encounter, Practitioner, Organization, Conditions, MedicationStatements, AllergyIntolerance, Observations, and Flags.", "A local validator fails closed before staging or transport.", "M2 consent callbacks and M3 HIU request/health-information notification metadata are persisted and audited."])
    s += [p("Current limitation", "H2x"), p("ABDM_MODE is local by default. Live Sandbox transport still needs issued bridge credentials, HFR registration, assigned versioned paths, consent-artifact encryption/decryption, an official validator, and certification. The interface must never claim a live push while in local mode.")]
    s += [PageBreak()]

    section(s, 14, "Audit log and accountability")
    s += bullets(["Audit events are append-only database records.", "Events include actor type and identity, action, target, timestamp, kiosk/session context, and structured metadata.", "Each event stores the previous event hash and its own SHA-256 hash, creating a tamper-evident chain.", "Covered actions include consent, identity, clinical turns, alerts, access, edits, Ayurveda confirmation, sign-off, PDF generation, ABHA linking, FHIR/ABDM activity, and fleet escalation.", "Only authorized administrative access can read the audit endpoint."])
    s += [p("The chain reveals changes inside the database history, but it is not externally anchored. Production needs protected centralized storage, restricted database administration, retention rules, monitoring, backups, and periodic external anchoring or signing."), PageBreak()]

    section(s, 15, "Multi-kiosk deployment and device checks")
    s += bullets(["Each frontend sends a stable VITE_KIOSK_ID in X-Kiosk-ID.", "Sessions, help requests, and alerts retain their kiosk origin.", "Health requests update kiosk heartbeats.", "The admin fleet view reports online/offline state, active sessions, alerts, and pending reviews.", "A kiosk is considered offline after roughly 90 seconds without a heartbeat.", "The production launcher supports TLS certificate/key validation and forwarded-proxy settings.", "Security headers block MIME sniffing, framing, unnecessary referrers/permissions, and enable HSTS on HTTPS."])
    s += [p("Device check tests touch, backend connection, microphone, speaker, and camera. Software diagnostics cannot certify the physical kiosk; every deployment still needs the documented privacy, audio, camera, touch, network, and alert drills."), PageBreak()]

    section(s, 16, "How to run and operate the app")
    s += [p("Fastest local start", "H2x"), p("Double-click kiosk-mode.bat for full-screen mode, or start-dev.bat for ordinary development. Open http://localhost:5173. The API uses port 8080 and Ollama uses port 11434.", "Codex"), p("Required local components", "H2x")]
    s += bullets(["Python virtual environment and backend requirements.", "Node/npm dependencies in frontend.", "Ollama with llama3.1:8b.", "Piper English and Hindi voice model files under backend/voices.", "faster-whisper and EasyOCR model caches."])
    s += [p("Operational sequence", "H2x")]
    s += bullets(["Run Device check.", "Confirm /health reports backend and Ollama OK.", "Warm voice, transcription, OCR, and LLM before an offline demo.", "Use Alt+F4 to exit full-screen kiosk mode.", "Run run_smoke_test.bat for live component verification when Ollama and models are available."])
    s += [PageBreak()]

    section(s, 17, "API inventory")
    endpoints = [
        ("GET", "/health", "System, speech, ABDM, deployment health"), ("POST", "/staff/login", "Staff authentication"),
        ("GET", "/staff/me", "Current staff identity"), ("GET", "/staff/fleet/status", "Admin fleet metrics"), ("POST", "/staff/logout", "End staff session"),
        ("POST", "/sessions/start", "Consent-backed visit"), ("PATCH", "/sessions/{id}/preferences", "Language/mode"), ("GET", "/sessions/{id}", "Restore visit"), ("DELETE", "/sessions/{id}", "Clear visit"),
        ("PATCH", "/sessions/{id}/department", "Department"), ("PUT", "/sessions/{id}/documents", "Documents"),
        ("POST", "/patients/register", "New Medi ID"), ("GET", "/patients/{medi_id}", "Returning lookup"), ("PATCH", "/patients/{medi_id}/prakriti", "Reject patient-side protected update"),
        ("POST", "/transcribe", "Speech recognition"), ("POST", "/speak", "Speech output"), ("POST", "/ocr", "Document OCR"), ("POST", "/chat", "Clinical turn"),
        ("GET", "/nurse-station/alerts", "Active alerts"), ("POST", "/nurse-station/alerts/{id}/acknowledge", "Acknowledge"), ("POST", "/nurse-station/help-request", "Patient help"),
        ("GET", "/staff/sessions", "Recent visits"), ("GET", "/staff/sessions/{id}", "Full record"), ("PATCH", "/staff/sessions/{id}/record", "Clinical correction"),
        ("GET", "/staff/sessions/{id}/revisions", "Revision history"), ("POST", "/staff/sessions/{id}/signoff", "Attestation/signature"), ("GET", "/staff/sessions/{id}/pdf", "Patient/clinician PDF"),
        ("PATCH", "/staff/sessions/{id}/ayush-confirmation", "Protected AYUSH findings"), ("GET", "/staff/audit", "Audit log"),
        ("POST", "/abdm/push", "Validate/stage or transport FHIR"), ("GET", "/abdm/push/{id}", "Export state"), ("GET", "/staff/abdm/status", "ABDM readiness"),
        ("PATCH", "/staff/patients/{medi_id}/abha", "Verify ABHA link"), ("GET", "/staff/patients/{medi_id}/care-contexts", "Care contexts"),
        ("POST", "/staff/abdm/hiu/consent-requests", "HIU consent request"), ("POST", "/abdm/callbacks/consent", "Consent callback"), ("POST", "/abdm/callbacks/health-information", "HI notification callback"),
    ]
    s += [table(["Method", "Endpoint", "Purpose"], endpoints, [18 * mm, 85 * mm, 65 * mm], small=True), PageBreak()]

    section(s, 18, "Security, privacy, reliability, and data limits")
    s += [p("Implemented controls", "H2x")]
    s += bullets(["Hashed patient/staff tokens, scoped API authorization, role checks, rate limiting, masked phone display, size/type bounds, strict schemas, consent gating, session recovery, explicit clearing, security headers, TLS configuration, and hash-chained audit events."])
    s += [p("Production requirements", "H2x")]
    s += bullets(["Managed multi-user database instead of SQLite.", "Encryption at rest, managed keys/secrets, TLS everywhere, backup/restore tests, high availability, central monitoring, and incident response.", "Hospital identity integration, strong patient verification, retention and deletion policy, guardian/minor flows, legal review, and penetration testing.", "Clinician-approved safety datasets, real-document benchmarks, device accessibility testing, and model monitoring."])
    s += [p("Never present the prototype as ready for unsupervised clinical deployment."), PageBreak()]

    section(s, 19, "Verification status and the fixed runtime error")
    s += [table(["Check", "Result on 8 Sep 2026"], [
        ("Backend regression suite", "23/23 passed"), ("Bilingual clinical safety dataset", "8/8 passed"),
        ("Frontend production build", "Passed, 47 modules"), ("Live patient onboarding", "Start, consent, English, Chat, patient identification passed"),
        ("Live staff workflow", "Protected admin login and clinician dashboard passed"), ("Browser console", "No errors or warnings"),
    ], [62 * mm, 106 * mm])]
    s += [p("The observed failure was a stale development auto-reload process holding port 8080 while serving nothing. The stuck process was replaced and start-dev.bat now uses the stable run_server.py launcher, matching kiosk mode. The backend and UI recovered."), p("Tests reduce risk but do not replace physical kiosk, hospital-network, clinical, accessibility, or ABDM certification testing.", "Callout"), PageBreak()]

    section(s, 20, "Honest limitations")
    s += bullets(["Only English and Hindi interfaces are implemented.", "Voice is turn-based STT -> LLM -> TTS, not native speech-to-speech or provider-native partial streaming.", "Bhashini and AI4Bharat need credentials/service URLs and real microphone benchmarks.", "Red-flag rules and Hindi clinical language require clinician validation.", "Handwriting always needs staff review; OCR needs representative hospital documents.", "The starter formulary is deliberately small and has no drug-interaction checker.", "ABDM live exchange, encryption, official validation, HFR registration, and certification are unfinished external gates.", "No production HIS/EMR connector, SMS/pager escalation, managed database, or disaster-recovery deployment exists.", "Physical kiosk hardware has not been commissioned by software tests.", "Audit hashes are not externally anchored."])
    s += [PageBreak()]

    section(s, 21, "Demonstration and judge preparation")
    s += [p("Recommended demo", "H2x")]
    s += bullets(["Run Device check and health first.", "Start, consent, choose Hindi/English and Speak; show the centered orb and captions.", "Register or retrieve a patient and select an AYUSH department.", "Show adaptive shared history plus Agni/Vikriti/Nidana questions.", "Scan one clean printed report and show the handwriting review route.", "Open clinician view, correct a field with a reason, show the revision, confirm Ayurveda findings, and sign.", "Generate a PDF and show the validated local FHIR bundle without claiming a live network push.", "Trigger a prepared red-flag example and show the Nurse Station alert/escalation."])
    s += [p("Answers to memorize", "H2x")]
    s += bullets(["Why more than a chatbot? It combines consent, identity, structured coverage, documents, safety, clinician governance, and exchange.", "How are hallucinations limited? Server-owned flow, strict schema, focused extraction, evidence transcript, revisions, and clinician sign-off.", "Does it diagnose? No; it prepares history for verification.", "Why local AI? It reduces cloud dependency and supports an offline-focused demo.", "Is ABDM live? Local validation is complete; live Sandbox and certification remain external gates."])
    s += [PageBreak()]

    section(s, 22, "Future plan")
    s += [table(["Priority", "Next outcome"], [
        ("1", "Clinical review of question coverage, red flags, Hindi language, PDFs, and safety dataset."),
        ("2", "Real kiosk commissioning: microphones, speaker, camera, touch, privacy, cleaning, network, alert drills."),
        ("3", "Replace demo credentials; deploy TLS, managed database, encryption, backups, monitoring, and paging."),
        ("4", "Connect selected Bhashini or AI4Bharat services and measure latency/accuracy; later evaluate native speech-to-speech."),
        ("5", "Expand hospital-owned formulary, document datasets, timeline, coding, and HIS/EMR integration."),
        ("6", "Complete ABDM credentials, HFR registration, encryption, official validation, Sandbox testing, and certification."),
        ("7", "Add languages only after clinical wording, voice quality, and safety cases are approved."),
    ], [20 * mm, 148 * mm]), PageBreak()]

    section(s, 23, "Claude handoff - copy this context")
    handoff = (
        "Repository: https://github.com/SmitHitnalli/medikiosk (master). MediKiosk is a solo-built AI clinical history-taking prototype for SIH26047. "
        "Stack: React/Vite frontend on 5173; FastAPI backend on 8080; SQLite; Ollama llama3.1:8b; faster-whisper; Piper; EasyOCR. "
        "The flow is Start -> consent -> English/Hindi -> Speak/Chat -> new/returning Medi ID with optional ABHA -> General/AYUSH department -> server-controlled SOCRATES/AYUSH interview -> document scan -> protected clinician review. "
        "Speak mode centers the orb; Chat removes it. Touch means finger taps on kiosk controls. Phone/Medi ID/ABHA stay touch-only. "
        "The backend owns coverage, schema validation, contradictions, completion, safety persistence, sign-off, and FHIR. The LLM phrases questions and extracts structured facts. "
        "All departments share medication/allergy/red-flag/SOCRATES intake. AYUSH adds Vikriti, Agni, Nidana and conversational Dashavidha; protected examination fields require doctor/admin confirmation. "
        "Documents have printed/handwritten routes; handwriting always needs staff review. Staff roles are nurse/doctor/admin. Clinician edits require reasons and create immutable revisions; sign-off hashes the snapshot; edits invalidate sign-off/export. "
        "ABHA linking is staff-verified. FHIR R4 DocumentBundle export and M2/M3 persistence exist; ABDM runs local unless real credentials and certification are supplied. Audit events are append-only and hash-chained. Multi-kiosk IDs, heartbeats, fleet status, TLS settings, alert escalation, and device diagnostics exist. "
        "Current limits: two languages, turn-based STT-LLM-TTS, no live Bhashini/AI4Bharat credentials, small formulary, no reliable handwriting, SQLite, no hospital pager/HIS, no live ABDM certification, and no physical commissioning. "
        "On 8 Sep 2026, 23 backend regressions, 8 clinical cases, frontend build, and live browser patient/staff flows passed. A stale uvicorn reload process caused port 8080 outage; it was stopped and start-dev.bat was changed to run_server.py. Follow AGENTS.md, ROADMAP.md, docs/schema.json, and the workflow docs before changing code."
    )
    s += [p(escape(handoff), "Codex"), p("Key files", "H2x")]
    s += bullets(["ROADMAP.md - current progress and limits.", "docs/schema.json - required clinical structure.", "docs/AYURVEDA_MODE.md - protected and conversational Ayurveda data.", "docs/SPEECH_PROVIDERS.md - local/Bhashini/AI4Bharat boundary.", "docs/CLINICIAN_WORKFLOW.md - revisions, sign-off, and PDFs.", "docs/ABDM_INTEGRATION.md - identity, consent, FHIR, and external gates.", "docs/DEPLOYMENT_AND_COMMISSIONING.md - fleet and hardware procedure."])
    s += [PageBreak()]

    section(s, 24, "Sources and final reference")
    source_rows = [
        ("Official SIH catalog", "https://sih.gov.in/sih2026PS", "Problem catalog entry point"),
        ("ABDM FAQ", "https://abdm.gov.in/FAQ", "ABHA and ABDM concepts"),
        ("ABDM FHIR Implementation Guide", "https://nrces.in/ndhm/fhir/r4/", "FHIR R4 profiles"),
        ("ABDM Health Data Management Policy", "https://abdm.gov.in/", "Consent, privacy, and security"),
        ("HL7 FHIR R4 Bundle", "https://hl7.org/fhir/R4/bundle.html", "General Bundle rules"),
        ("Repository schema", "docs/schema.json", "Authoritative MediKiosk clinical shape"),
        ("Repository roadmap", "ROADMAP.md", "Implemented scope and known gates"),
    ]
    s += [table(["Source", "Location", "Use"], source_rows, [48 * mm, 72 * mm, 48 * mm], small=True), p("Use the current repository behavior, schema, tests, and workflow documents as the authority for product claims. Recheck external policies and integration guides before any real deployment."), Spacer(1, 18 * mm), p("End of guide", "CoverSub")]

    doc.build(s)
    print(OUTPUT)


if __name__ == "__main__":
    build()
