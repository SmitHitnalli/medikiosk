import copy
import difflib
import hashlib
import json
import os
import re
import secrets
import sqlite3
import string
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse
from starlette.responses import Response

from datetime import datetime, timezone
from dotenv import load_dotenv
from PIL import Image

OCR_MAX_IMAGE_PIXELS = 60_000_000  # ~60MP: generous for real photos, rejects decompression-bomb headers
Image.MAX_IMAGE_PIXELS = OCR_MAX_IMAGE_PIXELS
from clinical_pdf import build_clinical_pdf
from abdm_integration import AbdmClient, AbdmConfigurationError, AbdmTransportError, validate_document_bundle
from speech_providers import (
    SpeechProviderError,
    provider_status,
    selected_provider,
    synthesize_ai4bharat,
    synthesize_bhashini,
    transcribe_ai4bharat,
    transcribe_bhashini,
)

load_dotenv()

abdm_client = AbdmClient()

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
DATABASE_PATH = Path(os.environ.get("MEDIKIOSK_DATABASE_PATH") or Path(__file__).resolve().parent / "medikiosk.db")
MEDI_ID_ALPHABET = string.ascii_uppercase + string.digits
PIPER_VOICE_PATH = Path(__file__).resolve().parent / "voices" / "en_US-lessac-medium.onnx"
PIPER_CONFIG_PATH = Path(__file__).resolve().parent / "voices" / "en_US-lessac-medium.onnx.json"
# Real Hindi Piper voice, not yet downloaded into this repo (network-restricted dev
# environment could not fetch it). Drop these two files from
# https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/hi/hi_IN/pratham/medium
# into backend/voices/ and Hindi /speak requests pick it up automatically - no code
# change needed. Until then, /speak falls back to the English voice for Hindi text.
PIPER_HINDI_VOICE_PATH = Path(__file__).resolve().parent / "voices" / "hi_IN-pratham-medium.onnx"
PIPER_HINDI_CONFIG_PATH = Path(__file__).resolve().parent / "voices" / "hi_IN-pratham-medium.onnx.json"
# A single configured administrator keeps first-run setup simple. Hospitals can
# provide STAFF_ACCOUNTS_JSON to provision individually attributable nurse,
# doctor, and administrator accounts without putting credentials in the UI.
STAFF_USERNAME = os.environ.get("STAFF_USERNAME", "admin").strip().lower() or "admin"
STAFF_DISPLAY_NAME = os.environ.get("STAFF_DISPLAY_NAME", "MediKiosk Administrator").strip() or "MediKiosk Administrator"
STAFF_ROLE = os.environ.get("STAFF_ROLE", "admin").strip().lower() or "admin"
STAFF_PIN = os.environ.get("STAFF_PIN", "1234")
STAFF_SESSION_SECONDS = 30 * 60
KIOSK_ID = os.environ.get("KIOSK_ID", "kiosk-local").strip() or "kiosk-local"
APP_VERSION = os.environ.get("MEDIKIOSK_VERSION", "dev").strip() or "dev"
ALERT_ESCALATION_SECONDS = max(30, int(os.environ.get("ALERT_ESCALATION_SECONDS", "120")))
ALLOWED_ORIGINS = [item.strip() for item in os.environ.get(
    "MEDIKIOSK_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if item.strip()]
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
SESSION_COOKIE_NAME = "medikiosk_session_token"
MAX_CHAT_CHARS = 4000
MAX_SPEAK_CHARS = 3000
ALLOWED_DEPARTMENTS = {"general", "Kayachikitsa", "Panchakarma", "Shalya", "Prasuti Tantra"}
UNKNOWN_STRINGS = {"", "unknown", "not known", "not provided", "not recorded", "n/a", "na"}
_whisper_model = None
_piper_voices: dict[str, object] = {}
_easyocr_reader = None
_staff_pin_attempts: dict[str, list[float]] = {}
_staff_pin_lock = threading.Lock()
_audit_lock = threading.Lock()
OCR_PROMPT = """You extract structured information from OCR text from a patient's prescription, lab report, or discharge summary. Return JSON only.

Extract only these fields, matching the digitized_documents.extracted_entities structure in docs/schema.json:
{
  "diagnoses": ["string"],
  "medications": ["string"],
  "lab_values": [
    {
      "name": "string",
      "value": "string",
      "unit": "string",
      "reference_range": "string",
      "flag": "normal | high | low"
    }
  ]
}

Use empty arrays when a field is not present. Do not invent values or add fields outside this structure. For flag, use normal when the report does not indicate high or low."""
DOC_TYPE_KEYWORDS = {
    "prescription": [
        "prescription", "rx", "tablet", "tab.", "cap.", "capsule", "dosage",
        "sig", "refill", "prescribed", "morning", "evening", "twice daily",
        "od", "bd", "tds", "physician", "dr.", "clinic",
    ],
    "lab_report": [
        "lab report", "laboratory", "reference range", "test result",
        "specimen", "pathology", "hemoglobin", "biochemistry", "sample",
        "reported value", "reference interval", "investigation", "normal range",
    ],
    "discharge_summary": [
        "discharge summary", "discharge", "admission", "date of admission",
        "date of discharge", "hospital course", "condition on discharge",
        "ward", "discharged", "final diagnosis",
    ],
}
OCR_CONFIDENT_THRESHOLD = 0.55
OCR_ILLEGIBLE_THRESHOLD = 0.2
DOC_TYPE_CONFIDENT_THRESHOLD = 0.15
CLINICIAN_EDITABLE_FIELDS = {
    "chief_complaint", "hpi.site", "hpi.onset", "hpi.character", "hpi.radiation",
    "hpi.associated_symptoms", "hpi.timing", "hpi.exacerbating_relieving", "hpi.severity",
    "past_medical_history", "past_surgical_history", "drug_allergy_history.current_medications",
    "drug_allergy_history.allergies", "family_history", "personal_history.diet",
    "personal_history.smoking", "personal_history.alcohol", "personal_history.occupation",
    "review_of_systems", "ayush_assessment.vikriti", "ayush_assessment.agni",
    "ayush_assessment.koshtha", "ayush_assessment.nidana", "ayush_assessment.panchakarma_history",
}
# Phone-camera photos routinely come in at 3000-4000px+ on the long side, which
# slows EasyOCR for no accuracy benefit at document-text scale. Cap the long side
# before running OCR.
OCR_MAX_IMAGE_DIMENSION = 1600
FORMULARY_PATH = Path(__file__).resolve().parent / "formulary.json"
SYSTEM_PROMPT = """You are Nurse Anjali, a warm, experienced clinical intake assistant at an AYUSH hospital in India. You are NOT a diagnostic tool - you only gather and organize a patient's history for the physician to review. You never diagnose, suggest treatment, or name a likely condition.

PERSONA AND TONE:
Speak like a caring, competent nurse who has done this a thousand times and genuinely wants to help - not like a form, a chatbot, or a customer service script. Use natural, warm phrasing. Vary your sentence structure - never repeat the same question format twice in a row. Acknowledge what the patient says before moving to the next question (e.g. "I see, that sounds uncomfortable" or "Thank you for sharing that") rather than jumping straight to the next question. Keep questions short and conversational, in plain language a first-time patient would understand - never use clinical jargon when speaking to the patient.

CONTEXT YOU WILL RECEIVE WITH EACH REQUEST:

- department: the department the patient selected (e.g. Kayachikitsa, Panchakarma, Shalya, Prasuti Tantra, or general)
- returning_patient: true/false
- known_prakriti: a prior practitioner-confirmed value. It is context only; do not ask the patient to diagnose or reconfirm their own Prakriti.
- patient_name: use it naturally in conversation, not on every single line

AYUSH QUESTION PRIORITY - FOLLOW THIS FIRST:
When the department is anything other than "general", after the patient has stated their chief complaint, your very next one or two questions MUST ask about Agni (digestion pattern) or Vikriti (current imbalance). Do not continue with generic SOCRATES questions first. Use plain language, such as "How would you describe your digestion - regular, variable, or sluggish?" or ask how their current health feels different from usual. Ask only one of these questions at a time, acknowledge the answer, and then continue naturally with the remaining AYUSH and SOCRATES history.

MODE - AYUSH IS DEFAULT:
Unless the department is explicitly "general", conduct an AYUSH-style interview. This means, in addition to the standard history, naturally weave in these questions using plain language (never raw Sanskrit terms unless the patient uses them first):

- Prakriti is a practitioner assessment. Never infer or assign it from a patient's description.
- Current imbalance (Vikriti) - always ask this fresh, every visit, regardless of returning patient status
- Digestion pattern (Agni): "How would you describe your digestion - regular, variable, or sluggish?"
- Bowel pattern (Koshtha): "What is your bowel movement pattern generally like?"
- Causative factors (Nidana): "Have you noticed anything that seems to trigger or worsen this - stress, certain foods, weather, sleep?"
- If relevant to their complaint, ask about prior Panchakarma treatments: "Have you undergone any Panchakarma therapies before, like Vamana, Virechana, or Basti?"

DASHAVIDHA SEPARATION:
Patient conversation may collect Satmya (adapted foods/habits), Sattva (mental resilience), Ahara Shakti (appetite/intake capacity), Vyayama Shakti (exercise tolerance), and Vaya (age/life stage). Sara, Samhanana, and Pramana require practitioner examination and must remain empty during the kiosk interview. The physician confirms Prakriti and examination-only Dashavidha fields later with their own authenticated account.

If department is "general", skip all AYUSH-specific questions and conduct a standard history only.

CLINICAL QUESTIONING - SOCRATES FRAMEWORK:
For any symptom-based complaint, ensure you naturally cover: Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors, Severity. Ask ONE question at a time. Make questions genuinely useful for clinical assessment, not generic filler - think about what a skilled physician would actually need to know to narrow down what's happening, not just "tell me more."

RED FLAG AWARENESS (secondary check only - a separate deterministic system handles this primarily):
If you notice a pattern suggesting a medical emergency, set red_flag to true in your response and briefly acknowledge urgency in your reply.

INTERVIEW CONTROL:
The server decides which clinical topic is still missing and whether the interview is complete. Follow the ordered gap instructions provided with each turn. Set "asked_field" to the exact field path you ask about. Never skip to a different topic, ask more than one question, or mark the interview complete yourself.

PHYSICAL EXAMINATION NOTE:
Never attempt to assess anything requiring physical examination (pulse, palpation, visual inspection). If relevant, note in your final summary that Nadi Pariksha, Darshana, and Sparshana are to be conducted by the physician directly.

DATA STRUCTURE RULES:
Always nest fields exactly like this in the "data" object, never invent new field names:

- data.chief_complaint (string)
- data.hpi.site, data.hpi.onset, data.hpi.character, data.hpi.radiation, data.hpi.associated_symptoms, data.hpi.timing, data.hpi.exacerbating_relieving, data.hpi.severity
- data.past_medical_history (array), data.past_surgical_history (array)
- data.drug_allergy_history.current_medications (array), data.drug_allergy_history.allergies (array)
- data.ayush_assessment.vikriti, data.ayush_assessment.agni, data.ayush_assessment.koshtha, data.ayush_assessment.nidana, data.ayush_assessment.panchakarma_history
- data.ayush_assessment.dashavidha.patient_reported.satmya, sattva, ahara_shakti, vyayama_shakti, vaya
- Never write prakriti, prakriti provenance, dashavidha.practitioner_exam, confirmation status, confirmed_by, or confirmed_at; these are server/practitioner-controlled.
- For the ayush_assessment fields specifically, use correct Sanskrit terminology in the stored data (this is shown to the doctor, not spoken to the patient)

Always respond in this exact JSON format:
{
"reply": "your natural, warm response to the patient - in plain language",
"interview_complete": false,
"red_flag": false,
"red_flag_reason": "",
"asked_field": "the exact requested field path, or null when no question is asked",
"data": { ...fields matching the structure above, filled in as you learn them... }
}"""


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_CHAT_CHARS)
    session_id: str

    @field_validator("message", "session_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SpeakRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_SPEAK_CHARS)
    language: Literal["en", "hi"] | None = None
    provider: Literal["auto", "local", "bhashini", "ai4bharat"] = "auto"


class PatientRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)
    phone_number: str = Field(min_length=10, max_length=20)
    abha_number: str = Field(default="", max_length=20)
    abha_address: str = Field(default="", max_length=100)


class AbhaLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    abha_number: str = Field(min_length=14, max_length=20)
    abha_address: str = Field(default="", max_length=100)
    verification_method: Literal["qr", "otp", "demographic_match", "sandbox_test"]
    verification_reference: str = Field(min_length=3, max_length=200)


class HiuConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_abha_address: str = Field(min_length=3, max_length=100)
    purpose: str = Field(min_length=3, max_length=200)
    hi_types: list[Literal["OPConsultation", "Prescription", "DiagnosticReport", "DischargeSummary", "HealthDocumentRecord", "WellnessRecord"]] = Field(min_length=1, max_length=10)
    date_from: str
    date_to: str
    expires_at: str


class PractitionerAyushConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prakriti: str = Field(min_length=1, max_length=100)
    sara: str = Field(default="", max_length=200)
    samhanana: str = Field(default="", max_length=200)
    pramana: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class ClinicalRecordEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: dict[str, object] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=3, max_length=500)


class ClinicalSignoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attestation: Literal[True]


class StaffPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=80)
    pin: str = Field(min_length=4, max_length=20)


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=8, max_length=100)
    language: Literal["en", "hi"] | None = None
    interaction_mode: Literal["speak", "chat"] | None = None
    consent: Literal[True]


class SessionPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["en", "hi"]
    interaction_mode: Literal["speak", "chat"]


class SessionDepartmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: Literal["general", "Kayachikitsa", "Panchakarma", "Shalya", "Prasuti Tantra"]


class SessionDocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[dict] = Field(default_factory=list, max_length=20)


class ClinicalHpi(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    site: str = ""
    onset: str = ""
    character: str = ""
    radiation: str = ""
    associated_symptoms: list[str] = Field(default_factory=list)
    timing: str = ""
    exacerbating_relieving: str = ""
    severity: str = ""


class DrugAllergyHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    current_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class PersonalHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    diet: str = ""
    smoking: bool | None = None
    alcohol: bool | None = None
    occupation: str = ""


class DashavidhaPatientReported(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    satmya: str = ""
    sattva: str = ""
    ahara_shakti: str = ""
    vyayama_shakti: str = ""
    vaya: str = ""


class DashavidhaPractitionerExam(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sara: str = ""
    samhanana: str = ""
    pramana: str = ""
    notes: str = ""


class DashavidhaAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    patient_reported: DashavidhaPatientReported = Field(default_factory=DashavidhaPatientReported)
    practitioner_exam: DashavidhaPractitionerExam = Field(default_factory=DashavidhaPractitionerExam)
    status: Literal["patient_reported", "partially_confirmed", "practitioner_confirmed", ""] = ""
    confirmed_by: str = ""
    confirmed_at: str = ""


class AyushAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prakriti: str = ""
    prakriti_source: Literal["prior_practitioner_record", "practitioner_confirmed", ""] = ""
    prakriti_confirmed_by: str = ""
    prakriti_confirmed_at: str = ""
    vikriti: str = ""
    agni: str = ""
    koshtha: str = ""
    nidana: str = ""
    panchakarma_history: str = ""
    dashavidha: DashavidhaAssessment = Field(default_factory=DashavidhaAssessment)


class ClinicalData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    patient_id: str = ""
    session_id: str = ""
    language: Literal["en", "hi"] = "en"
    mode: Literal["general", "ayush"] = "general"
    chief_complaint: str = ""
    hpi: ClinicalHpi = Field(default_factory=ClinicalHpi)
    past_medical_history: list[str] = Field(default_factory=list)
    past_surgical_history: list[str] = Field(default_factory=list)
    drug_allergy_history: DrugAllergyHistory = Field(default_factory=DrugAllergyHistory)
    family_history: list[str] = Field(default_factory=list)
    personal_history: PersonalHistory = Field(default_factory=PersonalHistory)
    review_of_systems: dict[str, str | bool | list[str]] = Field(default_factory=dict)
    ayush_assessment: AyushAssessment = Field(default_factory=AyushAssessment)
    digitized_documents: list[dict] = Field(default_factory=list)
    red_flag: bool = False
    red_flag_reason: str = ""
    consent: dict = Field(default_factory=dict)
    status: Literal["draft", "physician_reviewed", "saved_to_emr"] = "draft"
    interview_complete: bool = False


class ModelChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reply: str = Field(min_length=1, max_length=2000)
    interview_complete: bool = False
    red_flag: bool = False
    red_flag_reason: str = ""
    asked_field: str | None = Field(default=None, max_length=100)
    data: ClinicalData = Field(default_factory=ClinicalData)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _pin_hash(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=2**14, r=8, p=1).hex()


def _configured_staff_accounts() -> list[dict[str, str]]:
    raw = os.environ.get("STAFF_ACCOUNTS_JSON", "").strip()
    accounts = None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                accounts = parsed
        except json.JSONDecodeError as exc:
            raise RuntimeError("STAFF_ACCOUNTS_JSON must be a valid JSON array") from exc
    if accounts is None:
        accounts = [{
            "username": STAFF_USERNAME,
            "display_name": STAFF_DISPLAY_NAME,
            "role": STAFF_ROLE,
            "pin": STAFF_PIN,
        }]

    normalized = []
    seen = set()
    for account in accounts:
        if not isinstance(account, dict):
            raise RuntimeError("Every staff account must be a JSON object")
        username = str(account.get("username", "")).strip().lower()
        display_name = str(account.get("display_name", "")).strip()
        role = str(account.get("role", "")).strip().lower()
        pin = str(account.get("pin", "")).strip()
        if not re.fullmatch(r"[a-z0-9._-]{2,80}", username):
            raise RuntimeError("Staff usernames may contain lowercase letters, numbers, dot, underscore, and hyphen")
        if username in seen:
            raise RuntimeError(f"Duplicate staff username: {username}")
        if not display_name or role not in {"nurse", "doctor", "admin"} or not (4 <= len(pin) <= 20):
            raise RuntimeError(f"Invalid staff account configuration for {username}")
        seen.add(username)
        normalized.append({"username": username, "display_name": display_name, "role": role, "pin": pin})
    return normalized


def _json_load(value: str | None, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed
    except (TypeError, json.JSONDecodeError):
        return copy.deepcopy(fallback)


@contextmanager
def _connect():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _init_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                medi_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                prakriti TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                session_token_hash TEXT NOT NULL,
                language TEXT NOT NULL,
                interaction_mode TEXT NOT NULL,
                consent_given_at TEXT NOT NULL,
                patient_medi_id TEXT,
                patient_name TEXT,
                department TEXT,
                clinical_data TEXT NOT NULL DEFAULT '{}',
                transcript TEXT NOT NULL DEFAULT '[]',
                documents TEXT NOT NULL DEFAULT '[]',
                turn_count INTEGER NOT NULL DEFAULT 0,
                interview_complete INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS nurse_alerts (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                patient_name TEXT,
                department TEXT,
                reason TEXT NOT NULL,
                source TEXT,
                triggered_at TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                acknowledged_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS abdm_pushes (
                session_id TEXT PRIMARY KEY,
                record TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_sessions (
                token_hash TEXT PRIMARY KEY,
                expires_at REAL NOT NULL,
                staff_user_id TEXT,
                created_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                pin_salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT,
                actor_role TEXT,
                session_id TEXT,
                patient_medi_id TEXT,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                previous_hash TEXT,
                event_hash TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clinical_revisions (
                revision_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                actor_user_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                changed_fields TEXT NOT NULL,
                clinical_data TEXT NOT NULL,
                UNIQUE(session_id, version)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clinical_signoffs (
                session_id TEXT PRIMARY KEY,
                revision_id TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                signed_by_user_id TEXT NOT NULL,
                signed_by_name TEXT NOT NULL,
                signature_hash TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS abdm_care_contexts (
                care_context_reference TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE,
                patient_medi_id TEXT NOT NULL, abha_address TEXT, display TEXT NOT NULL,
                created_at TEXT NOT NULL, notified_at TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS abdm_consents (
                consent_id TEXT PRIMARY KEY, direction TEXT NOT NULL, patient_abha_address TEXT NOT NULL,
                status TEXT NOT NULL, artifact TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS abdm_exchanges (
                exchange_id TEXT PRIMARY KEY, consent_id TEXT, direction TEXT NOT NULL, status TEXT NOT NULL,
                payload_metadata TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS security_attempts (
                scope TEXT NOT NULL, subject_key TEXT NOT NULL, occurred_at REAL NOT NULL
            )"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_security_attempts ON security_attempts(scope, subject_key, occurred_at)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS kiosk_heartbeats (
                kiosk_id TEXT PRIMARY KEY, app_version TEXT NOT NULL, status TEXT NOT NULL,
                details TEXT NOT NULL, last_seen TEXT NOT NULL
            )"""
        )
        patient_columns = {row["name"] for row in connection.execute("PRAGMA table_info(patients)")}
        for column in ("abha_number", "abha_address", "abha_status", "abha_verified_at"):
            if column not in patient_columns:
                connection.execute(f"ALTER TABLE patients ADD COLUMN {column} TEXT")
        session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
        if "lookup_failures" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN lookup_failures INTEGER NOT NULL DEFAULT 0")
        if "kiosk_id" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN kiosk_id TEXT")
        staff_session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(staff_sessions)")}
        if "staff_user_id" not in staff_session_columns:
            connection.execute("ALTER TABLE staff_sessions ADD COLUMN staff_user_id TEXT")
        if "created_at" not in staff_session_columns:
            connection.execute("ALTER TABLE staff_sessions ADD COLUMN created_at TEXT")
        alert_columns = {row["name"] for row in connection.execute("PRAGMA table_info(nurse_alerts)")}
        for column, definition in (
            ("severity", "TEXT NOT NULL DEFAULT 'urgent'"), ("kiosk_id", "TEXT"),
            ("escalated", "INTEGER NOT NULL DEFAULT 0"), ("escalated_at", "TEXT"),
        ):
            if column not in alert_columns:
                connection.execute(f"ALTER TABLE nurse_alerts ADD COLUMN {column} {definition}")

        now = datetime.now(timezone.utc).isoformat()
        configured_usernames = []
        for account in _configured_staff_accounts():
            configured_usernames.append(account["username"])
            user_id = "staff-" + hashlib.sha256(account["username"].encode("utf-8")).hexdigest()[:16]
            salt = secrets.token_bytes(16)
            connection.execute(
                """
                INSERT INTO staff_users
                    (user_id, username, display_name, role, pin_salt, pin_hash, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    display_name = excluded.display_name,
                    role = excluded.role,
                    pin_salt = excluded.pin_salt,
                    pin_hash = excluded.pin_hash,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    account["username"],
                    account["display_name"],
                    account["role"],
                    salt.hex(),
                    _pin_hash(account["pin"], salt),
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM staff_sessions WHERE staff_user_id = ?", (user_id,))
        if configured_usernames:
            placeholders = ",".join("?" for _ in configured_usernames)
            connection.execute(
                f"UPDATE staff_users SET active = 0, updated_at = ? WHERE username NOT IN ({placeholders})",
                (now, *configured_usernames),
            )
        connection.commit()


def _write_audit_event(
    action: str,
    outcome: str = "success",
    *,
    actor_type: str,
    actor_id: str | None = None,
    actor_role: str | None = None,
    session_id: str | None = None,
    patient_medi_id: str | None = None,
    details: dict | None = None,
) -> str:
    event_id = "AUD-" + secrets.token_hex(12).upper()
    occurred_at = datetime.now(timezone.utc).isoformat()
    safe_details = details if isinstance(details, dict) else {}
    canonical = json.dumps(
        {
            "event_id": event_id,
            "occurred_at": occurred_at,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "session_id": session_id,
            "patient_medi_id": patient_medi_id,
            "action": action,
            "outcome": outcome,
            "details": safe_details,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with _audit_lock, _connect() as connection:
        previous = connection.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
        previous_hash = previous["event_hash"] if previous else ""
        event_hash = hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()
        connection.execute(
            """
            INSERT INTO audit_events
                (event_id, occurred_at, actor_type, actor_id, actor_role, session_id,
                 patient_medi_id, action, outcome, details, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, occurred_at, actor_type, actor_id, actor_role, session_id,
                patient_medi_id, action, outcome, json.dumps(safe_details), previous_hash or None, event_hash,
            ),
        )
        connection.commit()
    return event_id


def _mask_phone_number(phone_number: str) -> str:
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return "*"
    return "*" * max(len(digits) - 2, 0) + digits[-2:]


def _normalize_abha_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits and len(digits) != 14:
        raise HTTPException(status_code=422, detail="ABHA number must contain 14 digits")
    return digits


def _mask_abha_number(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return f"**-****-****-{digits[-4:]}" if digits else ""


def _safe_kiosk_id(value: str | None) -> str:
    value = (value or KIOSK_ID).strip().lower()
    return value if re.fullmatch(r"[a-z0-9._-]{2,64}", value) else KIOSK_ID


def _patient_response(row: sqlite3.Row) -> dict[str, str | None]:
    response = {
        "medi_id": row["medi_id"],
        "name": row["name"],
        "phone_number": _mask_phone_number(row["phone_number"]),
        "prakriti": row["prakriti"],
        "created_at": row["created_at"],
    }
    if "abha_number" in row.keys():
        response.update({
            "abha_number": _mask_abha_number(row["abha_number"]),
            "abha_address": row["abha_address"] or "",
            "abha_status": row["abha_status"] or "not_linked",
        })
    return response


_init_database()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}):5173$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), payment=(), usb=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
def health(x_kiosk_id: str | None = Header(default=None)) -> dict:
    # Reports the backend process itself (always "ok" if this handler runs) plus a
    # quick, short-timeout reachability probe of Ollama, since "the FastAPI process
    # is alive" and "the AI assistant actually works" are different failure modes a
    # patient can hit (e.g. Ollama not started / crashed while the backend is fine).
    # Frontend uses this distinction for its graceful-failure fallback screens.
    ollama_ok = False
    try:
        probe = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(probe, timeout=1.5) as response:
            tags = json.loads(response.read().decode("utf-8"))
            model_names = {item.get("name") for item in tags.get("models", []) if isinstance(item, dict)}
            ollama_ok = response.status == 200 and any(
                name == OLLAMA_MODEL or str(name).startswith(f"{OLLAMA_MODEL}:") for name in model_names
            )
    except Exception:
        ollama_ok = False
    now = datetime.now(timezone.utc).isoformat()
    reporting_kiosk_id = _safe_kiosk_id(x_kiosk_id)
    deployment = {
        "kiosk_id": reporting_kiosk_id,
        "app_version": APP_VERSION,
        "tls_configured": bool(os.environ.get("TLS_CERT_FILE") and os.environ.get("TLS_KEY_FILE")),
        "database": "central" if os.environ.get("CENTRAL_DATABASE") == "1" else "local",
    }
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO kiosk_heartbeats (kiosk_id, app_version, status, details, last_seen) VALUES (?, ?, 'online', ?, ?)",
            (reporting_kiosk_id, APP_VERSION, json.dumps({"ollama": ollama_ok}), now),
        )
        connection.commit()
    return {
        "status": "ok",
        "ollama": "ok" if ollama_ok else "unreachable",
        "speech": provider_status(),
        "abdm": abdm_client.config.public_status(),
        "deployment": deployment,
    }


@app.post("/staff/login")
def login_staff(payload: StaffPinRequest, request: Request) -> dict:
    username = payload.username.strip().lower()
    remote_address = request.client.host if request.client else "local"
    attempt_keys = (f"user:{username}", f"address:{remote_address}")
    now_epoch = time.time()
    with _connect() as connection:
        connection.execute("DELETE FROM security_attempts WHERE occurred_at < ?", (now_epoch - 300,))
        recent_count = max(connection.execute(
            "SELECT COUNT(*) FROM security_attempts WHERE scope = 'staff_login' AND subject_key = ? AND occurred_at >= ?",
            (attempt_key, now_epoch - 300),
        ).fetchone()[0] for attempt_key in attempt_keys)
        connection.commit()
    if recent_count >= 5:
        _write_audit_event(
            "staff.login", "blocked", actor_type="staff", actor_id=username,
            details={"reason": "rate_limited", "remote_address": remote_address, "kiosk_id": KIOSK_ID},
        )
        raise HTTPException(status_code=429, detail="Too many incorrect PIN attempts. Try again in five minutes.")
    with _connect() as connection:
        staff_user = connection.execute(
            "SELECT * FROM staff_users WHERE username = ?",
            (username,),
        ).fetchone()
    valid_pin = False
    if staff_user is not None and staff_user["active"]:
        salt = bytes.fromhex(staff_user["pin_salt"])
        valid_pin = secrets.compare_digest(staff_user["pin_hash"], _pin_hash(payload.pin.strip(), salt))
    else:
        _pin_hash(payload.pin.strip(), b"medikiosk-login")
    if not valid_pin:
        with _connect() as connection:
            connection.executemany(
                "INSERT INTO security_attempts (scope, subject_key, occurred_at) VALUES ('staff_login', ?, ?)",
                [(attempt_key, now_epoch) for attempt_key in attempt_keys],
            )
            connection.commit()
        _write_audit_event(
            "staff.login", "failure", actor_type="staff", actor_id=username,
            details={"reason": "invalid_credentials", "remote_address": remote_address},
        )
        raise HTTPException(status_code=401, detail="Incorrect staff ID or PIN")
    with _connect() as connection:
        connection.executemany(
            "DELETE FROM security_attempts WHERE scope = 'staff_login' AND subject_key = ?",
            [(attempt_key,) for attempt_key in attempt_keys],
        )
        connection.commit()
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + STAFF_SESSION_SECONDS
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute("DELETE FROM staff_sessions WHERE expires_at <= ?", (time.time(),))
        connection.execute(
            "INSERT INTO staff_sessions (token_hash, expires_at, staff_user_id, created_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), expires_at, staff_user["user_id"], created_at),
        )
        connection.commit()
    _write_audit_event(
        "staff.login", actor_type="staff", actor_id=staff_user["user_id"], actor_role=staff_user["role"],
        details={"remote_address": remote_address},
    )
    return {
        "ok": True,
        "token": token,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(),
        "user": {
            "user_id": staff_user["user_id"],
            "username": staff_user["username"],
            "display_name": staff_user["display_name"],
            "role": staff_user["role"],
        },
    }


def require_staff(x_staff_token: str | None = Header(default=None)) -> dict[str, str]:
    if not x_staff_token:
        raise HTTPException(status_code=401, detail="Staff authentication required")
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT s.expires_at, u.user_id, u.username, u.display_name, u.role, u.active
            FROM staff_sessions s
            JOIN staff_users u ON u.user_id = s.staff_user_id
            WHERE s.token_hash = ?
            """,
            (_token_hash(x_staff_token),),
        ).fetchone()
        if row is None or row["expires_at"] <= time.time() or not row["active"]:
            if row is not None:
                connection.execute("DELETE FROM staff_sessions WHERE token_hash = ?", (_token_hash(x_staff_token),))
                connection.commit()
            raise HTTPException(status_code=401, detail="Staff session expired")
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "token": x_staff_token,
    }


def require_roles(*allowed_roles: str):
    def dependency(staff: dict[str, str] = Depends(require_staff)) -> dict[str, str]:
        if staff["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your staff role cannot perform this action")
        return staff
    return dependency


@app.get("/staff/me")
def get_current_staff(staff: dict[str, str] = Depends(require_staff)) -> dict:
    return {"user": {key: staff[key] for key in ("user_id", "username", "display_name", "role")}}


@app.get("/staff/fleet/status")
def get_fleet_status(_: dict[str, str] = Depends(require_roles("admin"))) -> dict:
    now = datetime.now(timezone.utc)
    with _connect() as connection:
        kiosks = [dict(row) for row in connection.execute("SELECT * FROM kiosk_heartbeats ORDER BY kiosk_id")]
        active_sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        active_alerts = connection.execute("SELECT COUNT(*) FROM nurse_alerts WHERE acknowledged = 0").fetchone()[0]
        pending_reviews = connection.execute("SELECT COUNT(*) FROM sessions WHERE status = 'draft' AND patient_medi_id IS NOT NULL").fetchone()[0]
    for kiosk in kiosks:
        kiosk["details"] = _json_load(kiosk["details"], {})
        age = (now - datetime.fromisoformat(kiosk["last_seen"])).total_seconds()
        kiosk["status"] = "offline" if age > 90 else "online"
        kiosk["seconds_since_seen"] = max(0, round(age))
    return {
        "kiosks": kiosks,
        "metrics": {"sessions": active_sessions, "active_alerts": active_alerts, "pending_reviews": pending_reviews},
    }


@app.post("/staff/logout")
def logout_staff(staff: dict[str, str] = Depends(require_staff)) -> dict:
    with _connect() as connection:
        connection.execute("DELETE FROM staff_sessions WHERE token_hash = ?", (_token_hash(staff["token"]),))
        connection.commit()
    _write_audit_event(
        "staff.logout", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
    )
    return {"ok": True}


def _require_session(session_id: str, token: str | None) -> sqlite3.Row:
    if not token:
        raise HTTPException(status_code=401, detail="Patient session authentication required")
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None or not secrets.compare_digest(row["session_token_hash"], _token_hash(token)):
        raise HTTPException(status_code=401, detail="Invalid patient session")
    return row


def _session_headers(
    x_session_id: str | None = Header(default=None),
    x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> sqlite3.Row:
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Patient session ID required")
    return _require_session(x_session_id, x_session_token)


@app.post("/sessions/start")
def start_session(
    request: SessionStartRequest,
    response: Response,
    x_kiosk_id: str | None = Header(default=None),
) -> dict:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    language = request.language or ""
    interaction_mode = request.interaction_mode or ""
    consent = {
        "abha_id": "",
        "consent_given_at": now,
        "scope": ["history_capture", "document_sharing", "hospital_share"],
    }
    data = ClinicalData(
        session_id=request.session_id,
        # The clinical document requires a valid language value. It is not used
        # until the patient explicitly selects and saves their preference.
        language=language or "en",
        consent=consent,
    ).model_dump()
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, session_token_hash, language, interaction_mode,
                    consent_given_at, clinical_data, updated_at, kiosk_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.session_id,
                    _token_hash(token),
                    language,
                    interaction_mode,
                    now,
                    json.dumps(data),
                    now,
                    _safe_kiosk_id(x_kiosk_id),
                ),
            )
            connection.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Session ID already exists") from exc
    _write_audit_event(
        "patient.consent.accepted",
        actor_type="patient_session",
        actor_id=request.session_id,
        session_id=request.session_id,
        details={"scope": consent["scope"], "kiosk_id": _safe_kiosk_id(x_kiosk_id)},
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=bool(os.environ.get("TLS_CERT_FILE") and os.environ.get("TLS_KEY_FILE")),
        samesite="strict",
        path="/",
    )
    return {"session_id": request.session_id}


@app.patch("/sessions/{session_id}/preferences")
def set_session_preferences(
    session_id: str,
    request: SessionPreferencesRequest,
    x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    row = _require_session(session_id, x_session_token)
    data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
    data["language"] = request.language
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE sessions
            SET language = ?, interaction_mode = ?, clinical_data = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (request.language, request.interaction_mode, json.dumps(data), now, session_id),
        )
        connection.commit()
    _write_audit_event(
        "patient.preferences.selected",
        actor_type="patient_session",
        actor_id=session_id,
        session_id=session_id,
        details={"language": request.language, "interaction_mode": request.interaction_mode},
    )
    return {"language": request.language, "interaction_mode": request.interaction_mode}


@app.delete("/sessions/{session_id}")
def clear_session(
    session_id: str,
    response: Response,
    x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    session = _require_session(session_id, x_session_token)
    with _connect() as connection:
        connection.execute("DELETE FROM nurse_alerts WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM abdm_pushes WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        connection.commit()
    _write_audit_event(
        "patient.session.cleared",
        actor_type="patient_session",
        actor_id=session_id,
        session_id=session_id,
        patient_medi_id=session["patient_medi_id"],
    )
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"cleared": True, "patient_registry_retained": True}


@app.get("/sessions/{session_id}")
def get_patient_session(session_id: str, x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict:
    row = _require_session(session_id, x_session_token)
    data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
    return {
        "session_id": row["session_id"],
        "patient_medi_id": row["patient_medi_id"],
        "patient_name": row["patient_name"],
        "language": row["language"],
        "interaction_mode": row["interaction_mode"],
        "department": row["department"],
        "interview_complete": bool(row["interview_complete"]),
        "coverage": _coverage_state(data, row["department"]),
        "data": data,
        "transcript": _json_load(row["transcript"], []),
        "documents": _validate_documents(_json_load(row["documents"], [])),
    }


@app.patch("/sessions/{session_id}/department")
def set_session_department(
    session_id: str,
    request: SessionDepartmentRequest,
    x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    _require_session(session_id, x_session_token)
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET department = ?, updated_at = ? WHERE session_id = ?",
            (request.department, datetime.now(timezone.utc).isoformat(), session_id),
        )
        connection.commit()
    _write_audit_event(
        "patient.department.selected",
        actor_type="patient_session",
        actor_id=session_id,
        session_id=session_id,
        details={"department": request.department},
    )
    return {"department": request.department}


@app.put("/sessions/{session_id}/documents")
def set_session_documents(
    session_id: str,
    request: SessionDocumentsRequest,
    x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    row = _require_session(session_id, x_session_token)
    documents = _validate_documents(request.documents)
    data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
    data["digitized_documents"] = documents
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET documents = ?, clinical_data = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(documents), json.dumps(data), datetime.now(timezone.utc).isoformat(), session_id),
        )
        connection.commit()
    _write_audit_event(
        "patient.documents.updated",
        actor_type="patient_session",
        actor_id=session_id,
        session_id=session_id,
        patient_medi_id=row["patient_medi_id"],
        details={"document_count": len(documents)},
    )
    return {"documents": documents}


@app.post("/patients/register")
def register_patient(request: PatientRegistration, session: sqlite3.Row = Depends(_session_headers)) -> dict[str, str]:
    name = request.name.strip()
    phone_number = request.phone_number.strip()
    digits = re.sub(r"\D", "", phone_number)
    if not name or len(digits) < 10 or len(digits) > 15:
        raise HTTPException(status_code=400, detail="Enter a valid name and 10-15 digit phone number")
    phone_number = digits
    abha_number = _normalize_abha_number(request.abha_number)
    abha_address = request.abha_address.strip().lower()
    if abha_address and "@" not in abha_address:
        raise HTTPException(status_code=422, detail="Enter a valid ABHA address")

    with _connect() as connection:
        for _ in range(10):
            medi_id = "MK-" + "".join(secrets.choice(MEDI_ID_ALPHABET) for _ in range(6))
            try:
                connection.execute(
                    """INSERT INTO patients
                       (medi_id, name, phone_number, abha_number, abha_address, abha_status, abha_verified_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (medi_id, name, phone_number, abha_number or None, abha_address or None,
                     "patient_provided" if abha_number else "not_linked", None),
                )
                connection.commit()
                data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
                data["patient_id"] = medi_id
                connection.execute(
                    "UPDATE sessions SET patient_medi_id = ?, patient_name = ?, clinical_data = ?, updated_at = ? WHERE session_id = ?",
                    (medi_id, name, json.dumps(data), datetime.now(timezone.utc).isoformat(), session["session_id"]),
                )
                connection.commit()
                _write_audit_event(
                    "patient.registered",
                    actor_type="patient_session",
                    actor_id=session["session_id"],
                    session_id=session["session_id"],
                    patient_medi_id=medi_id,
                )
                return {"medi_id": medi_id, "abha_status": "patient_provided" if abha_number else "not_linked"}
            except sqlite3.IntegrityError:
                continue

    raise HTTPException(status_code=500, detail="Could not generate a unique Medi ID")


@app.get("/patients/{medi_id}")
def get_patient(medi_id: str, session: sqlite3.Row = Depends(_session_headers)) -> dict[str, str | None]:
    now_epoch = time.time()
    with _connect() as connection:
        connection.execute("DELETE FROM security_attempts WHERE occurred_at < ?", (now_epoch - 300,))
        recent_failures = connection.execute(
            "SELECT COUNT(*) FROM security_attempts WHERE scope = 'medi_id_lookup' AND subject_key = ? AND occurred_at >= ?",
            (medi_id, now_epoch - 300),
        ).fetchone()[0]
        connection.commit()
    if recent_failures >= 3:
        raise HTTPException(status_code=429, detail="Medi ID lookup is locked for this visit. Please ask staff for help or continue as a new patient.")
    with _connect() as connection:
        row = connection.execute(
            """SELECT medi_id, name, phone_number, prakriti, created_at,
                      abha_number, abha_address, abha_status, abha_verified_at
               FROM patients WHERE medi_id = ?""",
            (medi_id,),
        ).fetchone()
    if row is None:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO security_attempts (scope, subject_key, occurred_at) VALUES ('medi_id_lookup', ?, ?)",
                (medi_id, now_epoch),
            )
            connection.commit()
        _write_audit_event(
            "patient.lookup", "failure",
            actor_type="patient_session",
            actor_id=session["session_id"],
            session_id=session["session_id"],
            details={"reason": "not_found"},
        )
        raise HTTPException(status_code=404, detail="Patient not found")
    data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
    if row["prakriti"]:
        data["ayush_assessment"]["prakriti"] = row["prakriti"]
        data["ayush_assessment"]["prakriti_source"] = "prior_practitioner_record"
    data["patient_id"] = row["medi_id"]
    with _connect() as connection:
        connection.execute(
            "DELETE FROM security_attempts WHERE scope = 'medi_id_lookup' AND subject_key = ?",
            (medi_id,),
        )
        connection.execute(
            "UPDATE sessions SET patient_medi_id = ?, patient_name = ?, clinical_data = ?, updated_at = ? WHERE session_id = ?",
            (row["medi_id"], row["name"], json.dumps(data), datetime.now(timezone.utc).isoformat(), session["session_id"]),
        )
        connection.commit()
    _write_audit_event(
        "patient.lookup",
        actor_type="patient_session",
        actor_id=session["session_id"],
        session_id=session["session_id"],
        patient_medi_id=row["medi_id"],
    )
    return _patient_response(row)


@app.patch("/patients/{medi_id}/prakriti")
def reject_patient_prakriti_update(
    medi_id: str,
    session: sqlite3.Row = Depends(_session_headers),
) -> dict:
    if session["patient_medi_id"] != medi_id:
        raise HTTPException(status_code=403, detail="This patient is not linked to the active session")
    raise HTTPException(status_code=403, detail="Prakriti must be confirmed by an authenticated practitioner")


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


async def _read_upload(file: UploadFile, allowed_types: set[str]) -> bytes:
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file is too large (maximum 12 MB)")
    return data


def _transcribe_bytes(audio_data: bytes, suffix: str) -> str:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name
        model = _get_whisper_model()
        segments, _ = model.transcribe(temp_path)
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: Literal["en", "hi"] = Form(default="en"),
    provider: Literal["auto", "local", "bhashini", "ai4bharat"] = Form(default="auto"),
) -> dict:
    try:
        audio_data = await _read_upload(
            file,
            {"audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "application/octet-stream"},
        )
        suffix = Path(file.filename or "audio.webm").suffix or ".webm"
        if suffix.lower() not in {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".ogg"}:
            raise HTTPException(status_code=415, detail="Unsupported audio file extension")
        requested_provider = selected_provider(provider)
        used_provider = requested_provider
        fallback_from = None
        try:
            if requested_provider == "bhashini":
                text = await run_in_threadpool(
                    transcribe_bhashini, audio_data, language, suffix.lower().lstrip(".")
                )
            elif requested_provider == "ai4bharat":
                text = await run_in_threadpool(transcribe_ai4bharat, audio_data, language)
            else:
                text = await run_in_threadpool(_transcribe_bytes, audio_data, suffix)
        except SpeechProviderError:
            fallback_from = requested_provider
            used_provider = "local"
            text = await run_in_threadpool(_transcribe_bytes, audio_data, suffix)
        return {"text": text, "provider": used_provider, "fallback_from": fallback_from}
    except HTTPException:
        raise
    except ImportError as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail="faster-whisper is not installed. Install backend requirements and try again.",
        ) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="The audio file could not be decoded") from exc


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr

        _easyocr_reader = easyocr.Reader(["en", "hi"])
    return _easyocr_reader


def _classify_document_type(extracted_text: str) -> tuple[str | None, float]:
    """Fuzzy-match OCR text against known document-type keyword sets (stdlib only)."""
    text_lower = extracted_text.lower()
    words = re.findall(r"[a-z]+", text_lower)
    best_type: str | None = None
    best_score = 0.0
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        hits = 0.0
        for keyword in keywords:
            if keyword in text_lower:
                hits += 1.0
            elif " " not in keyword and difflib.get_close_matches(keyword, words, n=1, cutoff=0.82):
                hits += 0.5
        score = hits / len(keywords)
        if score > best_score:
            best_score = score
            best_type = doc_type
    return (best_type, round(best_score, 2)) if best_score > 0 else (None, 0.0)


def _downscale_image_for_ocr(path: str) -> None:
    """Resize the image in place if its longer side exceeds OCR_MAX_IMAGE_DIMENSION.
    Best-effort: if the file can't be opened as an image, leave it untouched and let
    EasyOCR itself raise/report the problem."""
    try:
        with Image.open(path) as image:
            longer_side = max(image.size)
            if longer_side <= OCR_MAX_IMAGE_DIMENSION:
                return
            scale = OCR_MAX_IMAGE_DIMENSION / longer_side
            new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            resized = image.convert("RGB").resize(new_size, Image.LANCZOS)
            resized.save(path)
    except Exception:
        traceback.print_exc()


def _clean_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value[:100]:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip()[:500])
    return cleaned


def _validate_entities(value) -> dict:
    value = value if isinstance(value, dict) else {}
    labs = []
    if isinstance(value.get("lab_values"), list):
        for item in value["lab_values"][:100]:
            if not isinstance(item, dict):
                continue
            labs.append(
                {
                    "name": str(item.get("name") or "").strip()[:200],
                    "value": str(item.get("value") or "").strip()[:100],
                    "unit": str(item.get("unit") or "").strip()[:100],
                    "reference_range": str(item.get("reference_range") or "").strip()[:100],
                    "flag": item.get("flag") if item.get("flag") in {"normal", "high", "low"} else "normal",
                }
            )
    medications = _clean_string_list(value.get("medications"))
    return {
        "diagnoses": _clean_string_list(value.get("diagnoses")),
        "medications": medications,
        "medication_verification": _match_formulary(medications),
        "lab_values": labs,
    }


def _match_formulary(medications: list[str]) -> list[dict]:
    entries = _json_load(FORMULARY_PATH.read_text(encoding="utf-8") if FORMULARY_PATH.exists() else "[]", [])
    names = {}
    for entry in entries:
        generic = str(entry.get("generic") or "").strip().lower()
        for name in [generic, *(entry.get("aliases") or [])]:
            if str(name).strip():
                names[str(name).strip().lower()] = generic
    results = []
    for raw in medications:
        normalized = re.sub(r"[^a-z ]", " ", raw.lower()).strip()
        tokens = normalized.split()
        exact = next((name for name in names if name in normalized), None)
        close = difflib.get_close_matches(tokens[0] if tokens else normalized, list(names), n=1, cutoff=0.78)
        match = exact or (close[0] if close else None)
        results.append({
            "raw": raw,
            "matched_generic": names.get(match, "") if match else "",
            "status": "exact" if exact else "fuzzy" if match else "unverified",
        })
    return results


def _validate_documents(documents) -> list[dict]:
    if not isinstance(documents, list):
        raise HTTPException(status_code=422, detail="documents must be an array")
    cleaned = []
    for document in documents[:20]:
        if not isinstance(document, dict):
            continue
        doc_type = document.get("doc_type")
        status = document.get("status")
        if doc_type not in {None, "prescription", "lab_report", "discharge_summary"}:
            raise HTTPException(status_code=422, detail="Invalid document type")
        if status not in {"confident", "confirmed", "illegible", "needs_staff_review"}:
            raise HTTPException(status_code=422, detail="Invalid document status")
        cleaned.append(
            {
                "id": str(document.get("id") or secrets.token_hex(8))[:100],
                "doc_type": doc_type,
                "date": str(document.get("date") or "").strip()[:30],
                "status": status,
                "input_style": document.get("input_style") if document.get("input_style") in {"printed", "handwritten", "auto"} else "auto",
                "recognition_route": str(document.get("recognition_route") or "easyocr_printed")[:100],
                "extracted_entities": _validate_entities(document.get("extracted_entities")),
            }
        )
    return cleaned


def _process_ocr(image_data: bytes, suffix: str, doc_type_hint: str | None, document_style: str = "auto") -> dict:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_data)
            temp_path = temp_file.name

        try:
            with Image.open(temp_path) as image:
                if image.width * image.height > OCR_MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="The image dimensions are too large to process")
                image.verify()
        except HTTPException:
            raise
        except Image.DecompressionBombError as exc:
            raise HTTPException(status_code=413, detail="The image dimensions are too large to process") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="The image file could not be decoded") from exc

        _downscale_image_for_ocr(temp_path)
        reader = _get_easyocr_reader()
        ocr_results = reader.readtext(temp_path, detail=1)
        extracted_text = "\n".join(text for _, text, _ in ocr_results).strip()
        ocr_confidence = (
            round(sum(confidence for _, _, confidence in ocr_results) / len(ocr_results), 2)
            if ocr_results
            else 0.0
        )
        if doc_type_hint:
            suggested_doc_type, doc_type_confidence = doc_type_hint, 1.0
        else:
            suggested_doc_type, doc_type_confidence = _classify_document_type(extracted_text)
        if not extracted_text or ocr_confidence < OCR_ILLEGIBLE_THRESHOLD:
            return {
                "extracted_entities": _validate_entities({}),
                "confidence": ocr_confidence,
                "suggested_doc_type": suggested_doc_type,
                "doc_type_confidence": doc_type_confidence,
                "status": "illegible",
                "extracted_text_preview": extracted_text[:200],
            }
        status = (
            "confident"
            if doc_type_hint
            or (ocr_confidence >= OCR_CONFIDENT_THRESHOLD and doc_type_confidence >= DOC_TYPE_CONFIDENT_THRESHOLD)
            else "needs_confirmation"
        )
        ollama_request = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(
                {
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": OCR_PROMPT},
                        {"role": "user", "content": extracted_text},
                    ],
                    "stream": False,
                    "format": "json",
                    "keep_alive": "30m",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        parsed = _parse_model_json(_call_ollama(ollama_request))
        entities = parsed.get("extracted_entities", parsed)
        if document_style == "handwritten":
            status = "needs_staff_review"
        return {
            "extracted_entities": _validate_entities(entities),
            "confidence": ocr_confidence,
            "suggested_doc_type": suggested_doc_type,
            "doc_type_confidence": doc_type_confidence,
            "status": status,
            "input_style": document_style,
            "recognition_route": "easyocr_handwriting_review" if document_style == "handwritten" else "easyocr_printed",
            "extracted_text_preview": extracted_text[:200],
        }
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.post("/ocr")
async def ocr(
    file: UploadFile = File(...),
    doc_type_hint: Literal["prescription", "lab_report", "discharge_summary"] | None = Form(None),
    document_style: Literal["auto", "printed", "handwritten"] = Form("auto"),
) -> dict:
    suffix = Path(file.filename or "document.jpg").suffix or ".jpg"
    try:
        image_data = await _read_upload(file, {"image/jpeg", "image/png", "image/webp", "application/octet-stream"})
        if suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(status_code=415, detail="Unsupported image file extension")
        return await run_in_threadpool(_process_ocr, image_data, suffix, doc_type_hint, document_style)
    except HTTPException:
        raise
    except ImportError as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail="EasyOCR is not installed. Install backend requirements and try again.",
        ) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Document OCR failed") from exc


def _get_piper_voice(language: str | None = None):
    """Load (and cache) the Piper voice for the given language. Falls back to the
    English voice - rather than erroring - when a Hindi voice is requested but its
    files aren't present, since partial/no audio is worse than the wrong accent for
    a kiosk demo."""
    from piper import PiperVoice

    use_hindi = language == "hi" and PIPER_HINDI_VOICE_PATH.exists() and PIPER_HINDI_CONFIG_PATH.exists()
    cache_key = "hi" if use_hindi else "en"

    if cache_key not in _piper_voices:
        if use_hindi:
            _piper_voices[cache_key] = PiperVoice.load(PIPER_HINDI_VOICE_PATH, config_path=PIPER_HINDI_CONFIG_PATH)
        else:
            _piper_voices[cache_key] = PiperVoice.load(PIPER_VOICE_PATH, config_path=PIPER_CONFIG_PATH)
    return _piper_voices[cache_key]


@app.post("/speak")
def speak(request: SpeakRequest) -> FileResponse:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text to synthesize cannot be empty")

    temp_path = None
    try:
        requested_provider = selected_provider(request.provider)
        used_provider = requested_provider
        fallback_from = None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_path = temp_file.name
        try:
            if requested_provider == "bhashini":
                audio_data = synthesize_bhashini(text, request.language or "en")
                Path(temp_path).write_bytes(audio_data)
            elif requested_provider == "ai4bharat":
                audio_data = synthesize_ai4bharat(text, request.language or "en")
                Path(temp_path).write_bytes(audio_data)
            else:
                voice = _get_piper_voice(request.language)
                with wave.open(temp_path, "wb") as wav_file:
                    voice.synthesize_wav(text, wav_file)
        except SpeechProviderError:
            fallback_from = requested_provider
            used_provider = "local"
            voice = _get_piper_voice(request.language)
            with wave.open(temp_path, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        response = FileResponse(
            temp_path,
            media_type="audio/wav",
            filename="medikiosk-summary.wav",
            headers={
                "X-Speech-Provider": used_provider,
                "X-Speech-Fallback": fallback_from or "",
            },
            background=BackgroundTask(os.remove, temp_path),
        )
        temp_path = None
        return response
    except ImportError as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail="piper-tts is not installed. Install backend requirements and try again.",
        ) from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Speech synthesis failed") from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


_NEGATION_CUE_PATTERN = re.compile(
    r"\b(no|never|without|denies|denied|deny|doesn'?t|don'?t|didn'?t|ruled out|no longer)\b"
)
_CLAUSE_SPLIT_PATTERN = re.compile(r"[.,;|]|\b(?:but|however|although)\b")


def _split_clauses(text: str) -> list[str]:
    """
    Split on clause/sentence boundaries so a negation cue attached to one
    symptom mention doesn't accidentally swallow an unrelated, un-negated
    mention elsewhere in the same message (e.g. "no chest pain, but I am
    breathless" should still be able to flag the breathlessness on its own).
    """
    return _CLAUSE_SPLIT_PATTERN.split(text)


def _term_present_and_not_negated(clauses: list[str], term: str) -> bool:
    """
    True if `term` occurs in at least one clause where it is not preceded
    (within that same clause) by a negation cue word - "no", "denies",
    "don't", "without", etc. A clause-local check keeps this simple (no
    real NLP / dependency parsing) while covering the common clinical
    review-of-systems phrasing this safety net actually sees: "no chest
    pain, no breathlessness", "patient denies chest pain and shortness of
    breath", "I had a chest infection last year but no breathing problems
    since".
    """
    for clause in clauses:
        idx = clause.find(term)
        if idx == -1:
            continue
        prefix_words = re.findall(r"[a-z']+", clause[:idx])[-4:]
        suffix = clause[idx + len(term) : idx + len(term) + 30]
        prefix = " ".join(prefix_words)
        is_negated = bool(_NEGATION_CUE_PATTERN.search(prefix)) or (
            "not" in prefix_words and "sure" not in prefix_words
        )
        resolved = bool(re.search(r"\b(?:is|are|feels?|seems?)?\s*(?:fine|normal|okay|ok|clear)\b", suffix))
        if not is_negated and not resolved:
            return True
    return False


def check_red_flags(message: str) -> bool:
    text = message.lower()
    # Common patient-facing Hindi phrases used by the kiosk. These stay
    # deliberately narrow: the AI remains a secondary check, while these rules
    # provide an immediate independent safety net for the highest-risk patterns.
    text = (
        text.replace("सीने में दर्द", "chest pain")
        .replace("छाती में दर्द", "chest pain")
        .replace("सांस लेने में तकलीफ", "breathlessness")
        .replace("साँस लेने में तकलीफ", "breathlessness")
        .replace("सांस लेने में बहुत दिक्कत", "cannot breathe")
        .replace("साँस लेने में बहुत दिक्कत", "cannot breathe")
        .replace("सांस नहीं", "cannot breathe")
        .replace("एक तरफ कमजोरी", "one side weakness")
        .replace("बहुत खून", "heavy bleeding")
        .replace("बहुत ज्यादा खून", "heavy bleeding")
    )
    clauses = _split_clauses(text)

    def present(term: str) -> bool:
        return _term_present_and_not_negated(clauses, term)

    has_chest_pain_or_chest = present("chest pain") or present("chest")
    has_breathing_term = present("breath") or present("breathless") or present("breathing")
    if present("cannot breathe") or present("gasping") or present("choking"):
        return True
    if present("unresponsive") or present("unconscious") or "not responding" in text:
        return True
    if (present("face") and (present("droop") or present("uneven"))) and present("arm") and (present("weak") or present("numb")):
        return True
    if has_chest_pain_or_chest and has_breathing_term:
        return True

    if (
        present("chest pain")
        and (present("sweat") or present("sweating"))
        and (present("dizzy") or present("dizziness"))
    ):
        return True

    if present("headache") and (present("vision") or present("confus")):
        return True

    if present("fever") and (present("stiff neck") or present("drowsy") or present("drowsiness")):
        return True

    if (present("weakness") or present("numbness")) and (
        present("one side") or present("left side") or present("right side")
    ):
        return True

    return present("bleeding") and ("won't stop" in text or "not stopping" in text or present("heavy"))


def _parse_model_json(content: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", content, flags=re.IGNORECASE).strip()
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace == -1 or last_brace < first_brace:
        raise HTTPException(status_code=502, detail="Ollama returned invalid JSON")
    cleaned = cleaned[first_brace : last_brace + 1]

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Ollama returned a non-object JSON response")
    return parsed


def _call_ollama(ollama_request: urllib.request.Request) -> str:
    try:
        with urllib.request.urlopen(ollama_request, timeout=60) as response:
            ollama_response = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Ollama is unavailable. Start Ollama and try again.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Ollama returned invalid JSON") from exc

    content = ollama_response.get("message", {}).get("content")
    if not isinstance(content, str):
        raise HTTPException(status_code=502, detail="Ollama response did not contain message content")
    return content


def _normalise_chat_result(result: dict) -> dict:
    data = result.get("data")
    while isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if data is None and "data" not in result:
        data = {}
    elif not isinstance(data, dict):
        result["data"] = data
        return result

    normalised_data = {}

    def assign_nested(target: dict, parts: list[str], value) -> None:
        current = target
        for part in parts[:-1]:
            if not part:
                continue
            if not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        if parts and parts[-1]:
            current[parts[-1]] = value

    def normalise_fields(source: dict, target: dict) -> None:
        for key, value in source.items():
            if not isinstance(key, str):
                continue
            parts = key.split(".")
            if parts[0] == "data":
                parts = parts[1:]
            if len(parts) > 1:
                assign_nested(target, parts, value)
            else:
                target[parts[0] if key.startswith("data.") else key] = value

    normalise_fields(data, normalised_data)
    for nested_key in ("hpi", "ayush_assessment", "drug_allergy_history", "personal_history", "consent"):
        if isinstance(normalised_data.get(nested_key), dict):
            nested = {}
            normalise_fields(normalised_data[nested_key], nested)
            normalised_data[nested_key] = nested
    result["data"] = normalised_data
    return result


def _validate_chat_result(result: dict) -> dict:
    try:
        return ModelChatResponse.model_validate(_normalise_chat_result(result)).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="Ollama returned data outside the clinical schema") from exc


def _value_is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in UNKNOWN_STRINGS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _merge_accumulated_data(existing: dict, incoming: dict) -> dict:
    negative_values = {"none", "no", "nil", "denies", "no known", "not applicable"}
    for key, value in incoming.items():
        if isinstance(value, dict):
            if not isinstance(existing.get(key), dict):
                existing[key] = {}
            _merge_accumulated_data(existing[key], value)
        elif isinstance(value, list):
            if _value_is_empty(value):
                continue
            incoming_negative = all(isinstance(item, str) and item.strip().lower() in negative_values for item in value)
            if incoming_negative:
                existing[key] = copy.deepcopy(value)
                continue
            if not isinstance(existing.get(key), list) or all(
                isinstance(item, str) and item.strip().lower() in negative_values for item in existing.get(key, [])
            ):
                existing[key] = []
            for item in value:
                if item not in existing[key]:
                    existing[key].append(copy.deepcopy(item))
        elif not _value_is_empty(value):
            existing[key] = copy.deepcopy(value)
    return existing


def _list_has_negative_answer(value) -> bool:
    negative_values = {"none", "no", "nil", "denies", "no known", "not applicable"}
    return bool(value) and all(
        isinstance(item, str) and item.strip().lower() in negative_values for item in value
    )


def _remove_nested_value(data: dict, path: str) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.get(part)
        if not isinstance(current, dict):
            return
    current.pop(parts[-1], None)


def _set_nested_value(data: dict, path: str, value) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _find_clinical_conflict(
    existing: dict,
    incoming: dict,
    latest_message: str,
    pending_field: str | None = None,
) -> tuple[str, object, object] | None:
    correction_words = ("actually", "correction", "i meant", "sorry", "असल", "सुधार", "मतलब")
    explicit_correction = any(word in latest_message.lower() for word in correction_words)
    conflict_paths = (
        "personal_history.smoking",
        "personal_history.alcohol",
        "drug_allergy_history.current_medications",
        "drug_allergy_history.allergies",
    )
    for path in conflict_paths:
        old_value = _get_nested_value(existing, path)
        new_value = _get_nested_value(incoming, path)
        if _value_is_empty(old_value) or _value_is_empty(new_value) or old_value == new_value:
            continue
        is_conflict = (
            isinstance(old_value, bool) and isinstance(new_value, bool)
        ) or (
            isinstance(old_value, list)
            and isinstance(new_value, list)
            and _list_has_negative_answer(old_value) != _list_has_negative_answer(new_value)
        )
        if is_conflict and not explicit_correction and pending_field != path:
            return path, old_value, new_value
    return None


def _conflict_reply(path: str, language: str) -> str:
    topics = {
        "personal_history.smoking": ("tobacco use", "तंबाकू के उपयोग"),
        "personal_history.alcohol": ("alcohol use", "शराब के उपयोग"),
        "drug_allergy_history.current_medications": ("current medicines", "अभी ली जा रही दवाओं"),
        "drug_allergy_history.allergies": ("allergies", "एलर्जी"),
    }
    english_topic, hindi_topic = topics.get(path, ("that answer", "उस उत्तर"))
    return (
        f"मुझे {hindi_topic} के बारे में आपके पहले उत्तर से अलग जानकारी सुनाई दी। कृपया बताएं कि कौन सा उत्तर सही है?"
        if language == "hi"
        else f"I heard something different from your earlier answer about {english_topic}. Which answer is correct?"
    )


FIELD_PROMPTS = {
    "chief_complaint": "the patient's main health concern",
    "hpi.site": "where they feel the symptom",
    "hpi.onset": "when the symptom started",
    "hpi.character": "what the symptom feels like",
    "hpi.radiation": "whether the symptom spreads anywhere else",
    "hpi.associated_symptoms": "any other symptoms happening along with it",
    "hpi.timing": "when and how often the symptom occurs",
    "hpi.exacerbating_relieving": "what makes the symptom worse or better",
    "hpi.severity": "how severe the symptom is",
    "past_medical_history": "past or ongoing health conditions",
    "past_surgical_history": "past operations or procedures",
    "drug_allergy_history.current_medications": "current medicines",
    "drug_allergy_history.allergies": "medicine or other allergies",
    "family_history": "relevant health conditions in close family",
    "personal_history.diet": "their usual diet",
    "personal_history.smoking": "smoking or tobacco use",
    "personal_history.alcohol": "alcohol use",
    "personal_history.occupation": "their occupation",
    "review_of_systems": "any other symptoms not already discussed",
    "ayush_assessment.vikriti": "their current imbalance, or how their health feels different from usual",
    "ayush_assessment.agni": "their digestion pattern - regular, variable, or sluggish",
    "ayush_assessment.koshtha": "their usual bowel movement pattern",
    "ayush_assessment.nidana": "anything that triggers or worsens the problem, such as stress, food, weather, or sleep",
    "ayush_assessment.panchakarma_history": "whether they have undergone Panchakarma therapies before",
    "ayush_assessment.dashavidha.patient_reported.satmya": "foods and routines that suit them well or cause difficulty",
    "ayush_assessment.dashavidha.patient_reported.sattva": "how they usually cope with stress and emotional strain",
    "ayush_assessment.dashavidha.patient_reported.ahara_shakti": "their appetite and ability to comfortably eat a normal meal",
    "ayush_assessment.dashavidha.patient_reported.vyayama_shakti": "their usual exercise tolerance before fatigue",
    "ayush_assessment.dashavidha.patient_reported.vaya": "their age or stage of life",
}

FIELD_QUESTIONS = {
    "en": {
        "chief_complaint": "What brings you in today?",
        "hpi.site": "Where exactly do you feel it?",
        "hpi.onset": "When did it start?",
        "hpi.character": "What does it feel like?",
        "hpi.radiation": "Does it spread anywhere else?",
        "hpi.associated_symptoms": "What other symptoms happen with it? You can say none.",
        "hpi.timing": "Is it constant, or does it come and go?",
        "hpi.exacerbating_relieving": "What makes it better or worse?",
        "hpi.severity": "How severe is it from 0 to 10?",
        "past_medical_history": "Do you have any past or ongoing medical conditions?",
        "past_surgical_history": "Have you had any operations or procedures before?",
        "drug_allergy_history.current_medications": "What medicines are you taking now?",
        "drug_allergy_history.allergies": "Do you have any medicine or other allergies?",
        "family_history": "Do close family members have any relevant health conditions?",
        "personal_history.diet": "How would you describe your usual diet?",
        "personal_history.smoking": "Do you use tobacco or smoke?",
        "personal_history.alcohol": "Do you drink alcohol?",
        "personal_history.occupation": "What work do you do?",
        "review_of_systems": "Is there any other symptom we have not discussed?",
        "ayush_assessment.vikriti": "How does your health feel different from usual right now?",
        "ayush_assessment.agni": "Is your digestion usually regular, variable, or sluggish?",
        "ayush_assessment.koshtha": "What is your usual bowel movement pattern?",
        "ayush_assessment.nidana": "Have you noticed triggers such as stress, food, weather, or sleep?",
        "ayush_assessment.panchakarma_history": "Have you had Panchakarma therapies before?",
        "ayush_assessment.dashavidha.patient_reported.satmya": "Which foods or daily habits usually suit you well, and which do not?",
        "ayush_assessment.dashavidha.patient_reported.sattva": "How do you usually cope when you are under stress?",
        "ayush_assessment.dashavidha.patient_reported.ahara_shakti": "How is your appetite, and can you comfortably finish a normal meal?",
        "ayush_assessment.dashavidha.patient_reported.vyayama_shakti": "How much physical activity can you usually do before feeling tired?",
        "ayush_assessment.dashavidha.patient_reported.vaya": "How old are you?",
    },
    "hi": {
        "chief_complaint": "आज आप किस परेशानी के लिए आए हैं?",
        "hpi.site": "यह परेशानी ठीक कहाँ महसूस होती है?",
        "hpi.onset": "यह कब शुरू हुई?",
        "hpi.character": "यह कैसा महसूस होता है?",
        "hpi.radiation": "क्या यह किसी और जगह फैलती है?",
        "hpi.associated_symptoms": "इसके साथ और कौन से लक्षण होते हैं? नहीं हैं तो 'कोई नहीं' कहें।",
        "hpi.timing": "यह लगातार रहती है या आती-जाती है?",
        "hpi.exacerbating_relieving": "किस चीज़ से यह बेहतर या बदतर होती है?",
        "hpi.severity": "0 से 10 तक इसकी तीव्रता कितनी है?",
        "past_medical_history": "क्या आपको पहले से कोई बीमारी या स्वास्थ्य समस्या है?",
        "past_surgical_history": "क्या पहले कोई ऑपरेशन या प्रक्रिया हुई है?",
        "drug_allergy_history.current_medications": "आप अभी कौन सी दवाएँ ले रहे हैं?",
        "drug_allergy_history.allergies": "क्या आपको किसी दवा या अन्य चीज़ से एलर्जी है?",
        "family_history": "क्या करीबी परिवार में कोई संबंधित बीमारी है?",
        "personal_history.diet": "आपका सामान्य खान-पान कैसा है?",
        "personal_history.smoking": "क्या आप तंबाकू या धूम्रपान करते हैं?",
        "personal_history.alcohol": "क्या आप शराब पीते हैं?",
        "personal_history.occupation": "आप क्या काम करते हैं?",
        "review_of_systems": "क्या कोई और लक्षण है जिसकी हमने बात नहीं की?",
        "ayush_assessment.vikriti": "अभी आपका स्वास्थ्य सामान्य से किस तरह अलग लग रहा है?",
        "ayush_assessment.agni": "आपका पाचन सामान्यतः नियमित, बदलता हुआ या धीमा रहता है?",
        "ayush_assessment.koshtha": "आपका सामान्य मल त्याग कैसा रहता है?",
        "ayush_assessment.nidana": "क्या तनाव, भोजन, मौसम या नींद से यह बढ़ती है?",
        "ayush_assessment.panchakarma_history": "क्या आपने पहले पंचकर्म चिकित्सा कराई है?",
        "ayush_assessment.dashavidha.patient_reported.satmya": "कौन से भोजन या दिनचर्या आपको अनुकूल लगते हैं और कौन से नहीं?",
        "ayush_assessment.dashavidha.patient_reported.sattva": "तनाव के समय आप सामान्यतः कैसे संभालते हैं?",
        "ayush_assessment.dashavidha.patient_reported.ahara_shakti": "आपकी भूख कैसी रहती है, और क्या आप सामान्य भोजन आराम से पूरा कर पाते हैं?",
        "ayush_assessment.dashavidha.patient_reported.vyayama_shakti": "थकान होने से पहले आप सामान्यतः कितना शारीरिक काम कर पाते हैं?",
        "ayush_assessment.dashavidha.patient_reported.vaya": "आपकी उम्र कितनी है?",
    },
}


def _get_nested_value(data: dict, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _required_fields(data: dict, department: str | None) -> list[str]:
    fields = ["chief_complaint"]
    is_ayush = (department or "general").strip().lower() != "general"
    if is_ayush and not _value_is_empty(data.get("chief_complaint")):
        fields.extend(["ayush_assessment.vikriti", "ayush_assessment.agni"])
    fields.extend([
        "drug_allergy_history.current_medications",
        "drug_allergy_history.allergies",
        "hpi.site",
        "hpi.onset",
        "hpi.character",
        "hpi.radiation",
        "hpi.associated_symptoms",
        "hpi.timing",
        "hpi.exacerbating_relieving",
        "hpi.severity",
        "past_medical_history",
    ])
    if not is_ayush:
        fields.extend([
            "past_surgical_history",
            "family_history",
            "personal_history.diet",
            "personal_history.smoking",
            "personal_history.alcohol",
            "personal_history.occupation",
            "review_of_systems",
        ])
    else:
        fields.extend([
            "ayush_assessment.nidana",
            "ayush_assessment.dashavidha.patient_reported.satmya",
            "ayush_assessment.dashavidha.patient_reported.sattva",
            "ayush_assessment.dashavidha.patient_reported.ahara_shakti",
            "ayush_assessment.dashavidha.patient_reported.vyayama_shakti",
            "ayush_assessment.dashavidha.patient_reported.vaya",
        ])

    return fields


def _next_missing_field(data: dict, department: str | None) -> str | None:
    return next((field for field in _required_fields(data, department) if _value_is_empty(_get_nested_value(data, field))), None)


def _coverage_state(data: dict, department: str | None) -> dict:
    required = _required_fields(data, department)
    captured = [field for field in required if not _value_is_empty(_get_nested_value(data, field))]
    next_field = _next_missing_field(data, department)
    return {
        "required_count": len(required),
        "captured_count": len(captured),
        "percent": round((len(captured) / len(required)) * 100) if required else 100,
        "next_field": next_field,
        "missing_fields": [field for field in required if field not in captured],
    }


def _next_field_instruction(data: dict, department: str | None, language: str = "en") -> str:
    gaps = _coverage_state(data, department)["missing_fields"]
    if not gaps:
        return (
            "Extract the patient's latest answer without inventing facts. Set asked_field to null and reply with a brief "
            "acknowledgment. The server will close the interview."
        )
    descriptions = "; ".join(f"{field} = {FIELD_PROMPTS[field]}" for field in gaps)
    language_instruction = "Hindi (Devanagari)" if language == "hi" else "English"
    return (
        "First extract the patient's latest answer into data without inventing facts. Then review this ordered list of "
        f"remaining clinical gaps: {descriptions}. Ask one short, natural question in {language_instruction} about the first "
        "field that is still empty after extraction. Briefly acknowledge the patient's answer before the question when useful. "
        "Set asked_field to that exact field path. If the latest answer creates a conflict with previously recorded information, "
        "ask one clarification question about the conflict and keep asked_field on that field."
    )


def _retry_reply(language: str) -> str:
    return (
        "माफ़ कीजिए, मैं उस उत्तर को भरोसेमंद तरीके से दर्ज नहीं कर पाया। कृपया वही बात एक बार फिर कहें या टाइप करें।"
        if language == "hi"
        else "Sorry, I could not record that answer reliably. Please say or type the same answer once more."
    )


def _is_controlled_question(reply: str, asked_field: str | None, expected_field: str | None) -> bool:
    return bool(expected_field and asked_field == expected_field and "?" in reply.strip())


def _extract_target_value(field: str, latest_answer: str):
    empty_value = _get_nested_value(ClinicalData().model_dump(), field)
    expected_type = (
        "an array of short strings; use [\"none\"] for a clear negative answer"
        if isinstance(empty_value, list)
        else "a JSON boolean"
        if field in {"personal_history.smoking", "personal_history.alcohol"}
        else "a JSON object of symptom names and values"
        if isinstance(empty_value, dict)
        else "a short string"
    )
    prompt = (
        "Extract only the answer to one clinical intake question. Return JSON with exactly two keys: answered and value. "
        f"The question topic is {FIELD_PROMPTS[field]}. The value must be {expected_type}. "
        "Set answered to false when the patient did not answer that topic; otherwise set it to true, including for a clear "
        "negative answer. Do not infer facts or add explanation. "
        f"Patient message: {latest_answer}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        result = _parse_model_json(_call_ollama(request))
    except HTTPException:
        return None
    if not isinstance(result, dict) or result.get("answered") is not True:
        return None
    value = result.get("value")
    if isinstance(empty_value, list):
        return value if isinstance(value, list) and all(isinstance(item, str) for item in value) and value else None
    if field in {"personal_history.smoking", "personal_history.alcohol"}:
        return value if isinstance(value, bool) else None
    if isinstance(empty_value, dict):
        return value if isinstance(value, dict) and value else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _generate_controlled_question(
    field: str,
    language: str,
    latest_answer: str,
    previous_assistant_reply: str = "",
) -> str:
    language_name = "Hindi in Devanagari" if language == "hi" else "English"
    prompt = (
        "You are a warm clinical intake nurse. Return JSON only with one key named reply. "
        f"Ask exactly one short, natural question in {language_name} about {FIELD_PROMPTS[field]}. "
        "You may briefly acknowledge the patient's latest answer, but do not diagnose, suggest treatment, mention a schema, "
        "imply that an answer caused the symptom, lead the patient toward an answer, or ask about a second topic. End with a question mark. "
        f"Patient's latest answer: {latest_answer}\nPrevious nurse reply to avoid repeating: {previous_assistant_reply}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        result = _parse_model_json(_call_ollama(request))
    except HTTPException:
        return ""
    reply = result.get("reply", "") if isinstance(result, dict) else ""
    return reply.strip() if isinstance(reply, str) and 1 <= len(reply.strip()) <= 500 and "?" in reply else ""


def _patient_reply(
    data: dict,
    department: str | None,
    language: str,
    complete: bool,
    red_flag: bool,
    model_reply: str = "",
    asked_field: str | None = None,
) -> str:
    if red_flag:
        return (
            "आपके बताए लक्षणों के लिए तुरंत चिकित्सकीय सहायता चाहिए। कृपया वहीं रहें; स्टाफ को सूचना भेज दी गई है।"
            if language == "hi"
            else "These symptoms need immediate medical attention. Please stay where you are; staff have been alerted."
        )
    if complete:
        return (
            "धन्यवाद। ज़रूरी जानकारी दर्ज हो गई है और डॉक्टर समीक्षा करेंगे।"
            if language == "hi"
            else "Thank you. The required history has been recorded for the doctor to review."
        )
    field = _next_missing_field(data, department)
    candidate = model_reply.strip()
    if _is_controlled_question(candidate, asked_field, field):
        return candidate
    question = FIELD_QUESTIONS.get(language, FIELD_QUESTIONS["en"]).get(field, "Could you tell me a little more?")
    return ("धन्यवाद। " if language == "hi" else "Thank you. ") + question


@app.post("/chat")
def chat(request: ChatRequest, x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict:
    session_id = request.session_id
    session = _require_session(session_id, x_session_token)
    if not session["patient_medi_id"] or not session["department"]:
        raise HTTPException(status_code=409, detail="Complete patient identification and department selection first")
    accumulated_data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
    target_before_turn = _next_missing_field(accumulated_data, session["department"])
    transcript = _json_load(session["transcript"], [])
    recent_patient_text = " | ".join(
        entry.get("content", "") for entry in transcript[-6:] if isinstance(entry, dict) and entry.get("role") == "user"
    )
    keyword_red_flag = check_red_flags(f"{recent_patient_text} | {request.message}")
    if keyword_red_flag:
        accumulated_data["red_flag"] = True
        accumulated_data["red_flag_reason"] = "Emergency symptom pattern detected"
        _record_nurse_station_alert(
            session_id=session_id,
            patient_name=session["patient_name"],
            department=session["department"],
            reason=accumulated_data["red_flag_reason"],
            source="keyword",
        )
        with _connect() as connection:
            connection.execute(
                "UPDATE sessions SET clinical_data = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(accumulated_data), datetime.now(timezone.utc).isoformat(), session_id),
            )
            connection.commit()
    context = (
        "Conversation context for this patient:\n"
        f"department: {session['department']}\n"
        f"known_prakriti: {_get_nested_value(accumulated_data, 'ayush_assessment.prakriti') or ''}\n"
        f"patient_name: {session['patient_name'] or ''}\n"
        f"Current accumulated data: {json.dumps(accumulated_data)}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context},
        {"role": "system", "content": _next_field_instruction(accumulated_data, session["department"], session["language"])},
    ]
    messages.extend(
        {"role": entry["role"], "content": entry["content"]}
        for entry in transcript[-30:]
        if isinstance(entry, dict) and entry.get("role") in {"user", "assistant"} and isinstance(entry.get("content"), str)
    )
    messages.append(
        {
            "role": "user",
            "content": f"Current language: {session['language']}\nPatient's latest message: {request.message}",
        }
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        # Keep the model resident between requests - avoids a multi-second reload
        # on every chat turn (the biggest single latency win available without
        # swapping to a smaller LLM).
        "keep_alive": "30m",
    }
    ollama_request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    first_error = None
    result = None
    try:
        content = _call_ollama(ollama_request)
        try:
            result = _validate_chat_result(_parse_model_json(content))
        except HTTPException as exc:
            first_error = exc
            retry_content = _call_ollama(ollama_request)
            result = _validate_chat_result(_parse_model_json(retry_content))
    except HTTPException:
        if not keyword_red_flag:
            reply = _retry_reply(session["language"])
            transcript.extend([
                {"role": "user", "content": request.message, "timestamp": datetime.now(timezone.utc).isoformat()},
                {"role": "assistant", "content": reply, "timestamp": datetime.now(timezone.utc).isoformat()},
            ])
            with _connect() as connection:
                connection.execute(
                    "UPDATE sessions SET transcript = ?, updated_at = ? WHERE session_id = ?",
                    (json.dumps(transcript), datetime.now(timezone.utc).isoformat(), session_id),
                )
                connection.commit()
            _write_audit_event(
                "clinical.turn.retry_requested",
                actor_type="patient_session",
                actor_id=session_id,
                session_id=session_id,
                patient_medi_id=session["patient_medi_id"],
                details={"reason": "model_unavailable_or_invalid"},
            )
            return {
                "reply": reply,
                "interview_complete": False,
                "red_flag": False,
                "red_flag_reason": "",
                "red_flag_source": None,
                "retry_required": True,
                "clarification_required": False,
                "question_source": "retry",
                "data": accumulated_data,
                "coverage": _coverage_state(accumulated_data, session["department"]),
                "turn_count": int(session["turn_count"]),
            }
        result = ModelChatResponse(
            reply="Emergency detected",
            red_flag=False,
            red_flag_reason="",
            data=ClinicalData.model_validate(accumulated_data),
        ).model_dump()

    existing_red_flag = bool(accumulated_data.get("red_flag"))
    existing_red_flag_reason = accumulated_data.get("red_flag_reason", "")
    incoming_data = copy.deepcopy(result["data"])
    for server_field in (
        "patient_id", "session_id", "language", "mode", "digitized_documents",
        "red_flag", "red_flag_reason", "consent", "status", "interview_complete",
    ):
        incoming_data.pop(server_field, None)
    incoming_ayush = incoming_data.get("ayush_assessment")
    if isinstance(incoming_ayush, dict):
        for controlled_field in (
            "prakriti", "prakriti_source", "prakriti_confirmed_by", "prakriti_confirmed_at"
        ):
            incoming_ayush.pop(controlled_field, None)
        incoming_dashavidha = incoming_ayush.get("dashavidha")
        if isinstance(incoming_dashavidha, dict):
            for controlled_field in ("practitioner_exam", "status", "confirmed_by", "confirmed_at"):
                incoming_dashavidha.pop(controlled_field, None)
    if target_before_turn and _value_is_empty(_get_nested_value(incoming_data, target_before_turn)):
        repaired_value = _extract_target_value(target_before_turn, request.message)
        if repaired_value is not None:
            _set_nested_value(incoming_data, target_before_turn, repaired_value)
    pending_field = (
        transcript[-1].get("clarification_field")
        if transcript and isinstance(transcript[-1], dict) and transcript[-1].get("role") == "assistant"
        else None
    )
    conflict = _find_clinical_conflict(accumulated_data, incoming_data, request.message, pending_field)
    if conflict:
        _remove_nested_value(incoming_data, conflict[0])
    _merge_accumulated_data(accumulated_data, incoming_data)
    dashavidha = accumulated_data.get("ayush_assessment", {}).get("dashavidha", {})
    patient_reported_dashavidha = dashavidha.get("patient_reported", {}) if isinstance(dashavidha, dict) else {}
    if (
        isinstance(patient_reported_dashavidha, dict)
        and any(not _value_is_empty(value) for value in patient_reported_dashavidha.values())
        and dashavidha.get("status") not in {"partially_confirmed", "practitioner_confirmed"}
    ):
        dashavidha["status"] = "patient_reported"
    accumulated_data["patient_id"] = session["patient_medi_id"] or ""
    accumulated_data["session_id"] = session_id
    accumulated_data["language"] = session["language"]
    accumulated_data["mode"] = "general" if session["department"].lower() == "general" else "ayush"
    accumulated_data["consent"] = {
        "abha_id": "",
        "consent_given_at": session["consent_given_at"],
        "scope": ["history_capture", "document_sharing", "hospital_share"],
    }
    accumulated_data["digitized_documents"] = _validate_documents(_json_load(session["documents"], []))
    llm_red_flag = result["red_flag"]
    red_flag = keyword_red_flag or llm_red_flag or existing_red_flag
    red_flag_source = (
        "keyword_and_ai" if keyword_red_flag and llm_red_flag else "keyword" if keyword_red_flag else "ai" if llm_red_flag else None
    )
    if red_flag:
        accumulated_data["red_flag"] = True
        accumulated_data["red_flag_reason"] = (
            result.get("red_flag_reason") or existing_red_flag_reason or "Urgent symptoms detected"
        )
    else:
        accumulated_data["red_flag"] = False
        accumulated_data["red_flag_reason"] = ""
    turn_count = int(session["turn_count"]) + 1
    clarification_required = bool(conflict and not red_flag)
    complete = not clarification_required and (
        turn_count >= 20 or _next_missing_field(accumulated_data, session["department"]) is None
    )
    accumulated_data["interview_complete"] = complete
    model_reply = result.get("reply", "")
    asked_field = result.get("asked_field")
    expected_field = _next_missing_field(accumulated_data, session["department"])
    question_source = "server"
    if not red_flag and not complete and not clarification_required:
        if not _is_controlled_question(model_reply, asked_field, expected_field):
            previous_reply = next(
                (
                    entry.get("content", "")
                    for entry in reversed(transcript)
                    if isinstance(entry, dict) and entry.get("role") == "assistant"
                ),
                "",
            )
            generated_reply = _generate_controlled_question(
                expected_field, session["language"], request.message, previous_reply
            )
            if generated_reply:
                model_reply = generated_reply
                asked_field = expected_field
        question_source = (
            "model" if _is_controlled_question(model_reply, asked_field, expected_field) else "fallback"
        )
    reply = (
        _conflict_reply(conflict[0], session["language"])
        if clarification_required
        else _patient_reply(
            accumulated_data,
            session["department"],
            session["language"],
            complete,
            red_flag,
            model_reply,
            asked_field,
        )
    )
    assistant_entry = {
        "role": "assistant",
        "content": reply,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if clarification_required:
        assistant_entry["clarification_field"] = conflict[0]
    transcript.extend([
        {"role": "user", "content": request.message, "timestamp": datetime.now(timezone.utc).isoformat()},
        assistant_entry,
    ])
    accumulated_data = ClinicalData.model_validate(accumulated_data).model_dump()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE sessions SET clinical_data = ?, transcript = ?, turn_count = ?,
                interview_complete = ?, updated_at = ? WHERE session_id = ?
            """,
            (
                json.dumps(accumulated_data),
                json.dumps(transcript),
                turn_count,
                int(complete),
                datetime.now(timezone.utc).isoformat(),
                session_id,
            ),
        )
        connection.commit()
    _write_audit_event(
        "clinical.turn.recorded",
        actor_type="patient_session",
        actor_id=session_id,
        session_id=session_id,
        patient_medi_id=session["patient_medi_id"],
        details={
            "turn_count": turn_count,
            "interview_complete": complete,
            "red_flag": red_flag,
            "clarification_required": clarification_required,
            "question_source": question_source,
        },
    )
    if llm_red_flag:
        _record_nurse_station_alert(
            session_id=session_id,
            patient_name=session["patient_name"],
            department=session["department"],
            reason=accumulated_data["red_flag_reason"],
            source="ai",
        )
    return {
        "reply": reply,
        "interview_complete": complete,
        "red_flag": red_flag,
        "red_flag_reason": accumulated_data.get("red_flag_reason", ""),
        "red_flag_source": red_flag_source,
        "retry_required": False,
        "clarification_required": clarification_required,
        "question_source": question_source,
        "data": accumulated_data,
        "coverage": _coverage_state(accumulated_data, session["department"]),
        "turn_count": turn_count,
    }


def _record_nurse_station_alert(
    session_id: str,
    patient_name: str | None,
    department: str | None,
    reason: str,
    kind: str = "red_flag",
    source: str | None = None,
) -> None:
    # Keyed by session_id + kind (not session_id alone) so a red-flag alert and a
    # patient-pressed help request for the same session are tracked, shown, and
    # acknowledged independently instead of one silently overwriting the other.
    alert_id = f"{session_id}:{kind}"
    with _connect() as connection:
        existing = connection.execute("SELECT * FROM nurse_alerts WHERE id = ?", (alert_id,)).fetchone()
        session_location = connection.execute("SELECT kiosk_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        still_active = bool(existing and not existing["acknowledged"])
        triggered_at = existing["triggered_at"] if still_active else datetime.now(timezone.utc).isoformat()
        existing_source = existing["source"] if existing else None
        combined_source = (
            "keyword_and_ai" if {source, existing_source} == {"keyword", "ai"} else source or existing_source
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO nurse_alerts
            (id, session_id, kind, patient_name, department, reason, source, triggered_at,
             acknowledged, acknowledged_at, severity, kiosk_id, escalated, escalated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, 0, NULL)
            """,
            (alert_id, session_id, kind, patient_name, department, reason, combined_source, triggered_at,
             "emergency" if kind == "red_flag" else "urgent",
             (session_location["kiosk_id"] if session_location and session_location["kiosk_id"] else KIOSK_ID)),
        )
        connection.commit()
    _write_audit_event(
        "clinical.alert.raised",
        actor_type="system" if kind == "red_flag" else "patient_session",
        actor_id=None if kind == "red_flag" else session_id,
        session_id=session_id,
        details={"kind": kind, "source": combined_source},
    )


@app.get("/nurse-station/alerts")
def get_nurse_station_alerts(_: dict[str, str] = Depends(require_roles("nurse", "doctor", "admin"))) -> dict:
    now = datetime.now(timezone.utc)
    escalated_ids = []
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM nurse_alerts WHERE acknowledged = 0").fetchall()
        for row in rows:
            triggered = datetime.fromisoformat(row["triggered_at"])
            if not row["escalated"] and (now - triggered).total_seconds() >= ALERT_ESCALATION_SECONDS:
                connection.execute(
                    "UPDATE nurse_alerts SET escalated = 1, escalated_at = ? WHERE id = ? AND acknowledged = 0",
                    (now.isoformat(), row["id"]),
                )
                escalated_ids.append(row["id"])
        connection.commit()
        active = [dict(row) for row in connection.execute("SELECT * FROM nurse_alerts WHERE acknowledged = 0")]
    for alert_id in escalated_ids:
        _write_audit_event(
            "clinical.alert.escalated", actor_type="system", actor_id=KIOSK_ID,
            details={"alert_id": alert_id, "threshold_seconds": ALERT_ESCALATION_SECONDS, "kiosk_id": KIOSK_ID},
        )
    active.sort(key=lambda alert: alert["triggered_at"])
    return {"alerts": active, "escalation_threshold_seconds": ALERT_ESCALATION_SECONDS}


@app.post("/nurse-station/alerts/{alert_id}/acknowledge")
def acknowledge_nurse_station_alert(
    alert_id: str,
    staff: dict[str, str] = Depends(require_roles("nurse", "doctor", "admin")),
) -> dict:
    with _connect() as connection:
        alert = connection.execute("SELECT * FROM nurse_alerts WHERE id = ?", (alert_id,)).fetchone()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        acknowledged_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "UPDATE nurse_alerts SET acknowledged = 1, acknowledged_at = ? WHERE id = ?",
            (acknowledged_at, alert_id),
        )
        connection.commit()
        result = dict(alert)
        result.update({"acknowledged": 1, "acknowledged_at": acknowledged_at})
    _write_audit_event(
        "clinical.alert.acknowledged",
        actor_type="staff",
        actor_id=staff["user_id"],
        actor_role=staff["role"],
        session_id=alert["session_id"],
        details={"alert_id": alert_id, "kind": alert["kind"]},
    )
    return result


class HelpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str


@app.post("/nurse-station/help-request")
def request_help(request: HelpRequest, x_session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> dict:
    # Patient-initiated call for staff assistance (the kiosk's "help" button, part
    # of the accessibility baseline) - reuses the same alert feed and acknowledge
    # flow as red-flag alerts rather than standing up a separate notification path.
    session_id = request.session_id.strip()
    session = _require_session(session_id, x_session_token)
    _record_nurse_station_alert(
        session_id=session_id,
        patient_name=session["patient_name"],
        department=session["department"],
        reason="Patient pressed the help button and is waiting for assistance",
        kind="help_request",
    )
    return {"status": "ok"}



# ---------------------------------------------------------------------------
# Mock ABDM/FHIR push
#
# The problem statement calls for the structured history to be "pushed to the
# hospital HIS/EMR and linked to the ABHA Personal Health Record via FHIR
# APIs" once the physician accepts it. No real ABDM sandbox credentials or
# network access exist in this environment, so this simulates that hop: it
# builds a genuine FHIR-shaped Bundle from the session's accumulated history
# and digitized documents, "pushes" it by recording it server-side, and
# returns a mock ABDM reference. The Bundle's shape and content are real -
# only the destination is simulated - so swapping in a real ABDM client later
# is a matter of replacing the SQLite mock store with an actual HTTP call.
# ---------------------------------------------------------------------------
class AbdmPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=8, max_length=100)
    physician_reviewed: Literal[True]


def _build_legacy_fhir_bundle(
    patient_ref: str,
    patient_name: str | None,
    medi_id: str | None,
    department: str | None,
    data: dict,
    documents: list[dict],
) -> dict:
    entries = [
        {
            "resource": {
                "resourceType": "Patient",
                "id": patient_ref,
                "identifier": [{"system": "https://healthid.ndhm.gov.in/mock", "value": medi_id or "unassigned"}],
                "name": [{"text": patient_name or "Unknown patient"}],
            }
        },
        {
            "resource": {
                "resourceType": "Condition",
                "subject": {"reference": f"Patient/{patient_ref}"},
                "code": {"text": data.get("chief_complaint") or "Not recorded"},
                "note": [
                    {
                        "text": json.dumps(
                            {
                                "department": department,
                                "hpi": data.get("hpi", {}),
                                "past_medical_history": data.get("past_medical_history", []),
                                "past_surgical_history": data.get("past_surgical_history", []),
                                "family_history": data.get("family_history", []),
                                "personal_history": data.get("personal_history", {}),
                                "ayush_assessment": data.get("ayush_assessment", {}),
                            }
                        )
                    }
                ],
            }
        },
    ]

    drug_history = data.get("drug_allergy_history") or {}
    for medication in drug_history.get("current_medications") or []:
        entries.append(
            {
                "resource": {
                    "resourceType": "MedicationStatement",
                    "subject": {"reference": f"Patient/{patient_ref}"},
                    "status": "active",
                    "medicationCodeableConcept": {"text": medication},
                }
            }
        )
    for allergy in drug_history.get("allergies") or []:
        entries.append(
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "patient": {"reference": f"Patient/{patient_ref}"},
                    "code": {"text": allergy},
                }
            }
        )

    if data.get("red_flag"):
        entries.append(
            {
                "resource": {
                    "resourceType": "Flag",
                    "status": "active",
                    "subject": {"reference": f"Patient/{patient_ref}"},
                    "code": {"text": data.get("red_flag_reason") or "Urgent symptoms flagged"},
                }
            }
        )

    for document in documents or []:
        extracted = document.get("extracted_entities") or {}
        source_note = f"From digitized {document.get('doc_type') or 'document'}"
        for diagnosis in extracted.get("diagnoses") or []:
            entries.append(
                {
                    "resource": {
                        "resourceType": "Condition",
                        "subject": {"reference": f"Patient/{patient_ref}"},
                        "code": {"text": diagnosis},
                        "note": [{"text": source_note}],
                    }
                }
            )
        for medication in extracted.get("medications") or []:
            entries.append(
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "subject": {"reference": f"Patient/{patient_ref}"},
                        "status": "unknown",
                        "medicationCodeableConcept": {"text": medication},
                        "note": [{"text": source_note}],
                    }
                }
            )
        for lab_value in extracted.get("lab_values") or []:
            value = lab_value.get("value") or ""
            unit = lab_value.get("unit") or ""
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                numeric_value = None
            observation = {
                "resourceType": "Observation",
                "status": "final",
                "subject": {"reference": f"Patient/{patient_ref}"},
                "code": {"text": lab_value.get("name") or "Lab value"},
                "interpretation": [{"text": lab_value.get("flag") or "normal"}],
                "note": [{"text": source_note}],
            }
            if numeric_value is not None:
                observation["valueQuantity"] = {"value": numeric_value, "unit": unit}
            else:
                observation["valueString"] = " ".join(part for part in (str(value), unit) if part).strip()
            if lab_value.get("reference_range"):
                observation["referenceRange"] = [{"text": lab_value["reference_range"]}]
            if document.get("date"):
                observation["effectiveDateTime"] = document["date"]
            entries.append(
                {
                    "resource": observation
                }
            )

    return {"resourceType": "Bundle", "type": "collection", "timestamp": datetime.now(timezone.utc).isoformat(), "entry": entries}


def _build_fhir_bundle(
    patient_ref: str,
    patient_name: str | None,
    medi_id: str | None,
    department: str | None,
    data: dict,
    documents: list[dict],
) -> dict:
    """Build an ABDM R4 document Bundle with an OPConsultRecord Composition."""
    now = datetime.now(timezone.utc).isoformat()
    urls: dict[str, str] = {}

    def full_url(key: str) -> str:
        urls.setdefault(key, "urn:uuid:" + str(uuid.uuid4()))
        return urls[key]

    patient_url, encounter_url = full_url("patient"), full_url("encounter")
    practitioner_url, organization_url = full_url("practitioner"), full_url("organization")
    clinical_entries = []

    def add_clinical(resource: dict, key: str) -> str:
        url = full_url(key)
        clinical_entries.append({"fullUrl": url, "resource": resource})
        return url

    complaint_url = add_clinical({
        "resourceType": "Condition",
        "meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Condition"]},
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        "subject": {"reference": patient_url},
        "encounter": {"reference": encounter_url},
        "code": {"text": data.get("chief_complaint") or "Not recorded"},
        "note": [{"text": json.dumps({"hpi": data.get("hpi", {}), "department": department}, ensure_ascii=False)}],
    }, "chief-complaint")
    medication_urls, allergy_urls, document_urls = [], [], []
    for index, medication in enumerate((data.get("drug_allergy_history") or {}).get("current_medications") or []):
        medication_urls.append(add_clinical({
            "resourceType": "MedicationStatement", "status": "active", "subject": {"reference": patient_url},
            "medicationCodeableConcept": {"text": medication},
        }, f"medication-{index}"))
    for index, allergy in enumerate((data.get("drug_allergy_history") or {}).get("allergies") or []):
        allergy_urls.append(add_clinical({
            "resourceType": "AllergyIntolerance", "patient": {"reference": patient_url},
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
            "code": {"text": allergy},
        }, f"allergy-{index}"))
    if data.get("red_flag"):
        document_urls.append(add_clinical({
            "resourceType": "Flag", "status": "active", "subject": {"reference": patient_url},
            "code": {"text": data.get("red_flag_reason") or "Urgent symptoms flagged"},
        }, "red-flag"))
    for doc_index, document in enumerate(documents or []):
        extracted = document.get("extracted_entities") or {}
        source_note = f"From digitized {document.get('doc_type') or 'document'}; verification={document.get('status')}"
        for item_index, diagnosis in enumerate(extracted.get("diagnoses") or []):
            document_urls.append(add_clinical({
                "resourceType": "Condition", "subject": {"reference": patient_url},
                "code": {"text": diagnosis}, "note": [{"text": source_note}],
            }, f"document-{doc_index}-diagnosis-{item_index}"))
        for item_index, medication in enumerate(extracted.get("medications") or []):
            document_urls.append(add_clinical({
                "resourceType": "MedicationStatement", "status": "unknown", "subject": {"reference": patient_url},
                "medicationCodeableConcept": {"text": medication}, "note": [{"text": source_note}],
            }, f"document-{doc_index}-medication-{item_index}"))
        for item_index, lab in enumerate(extracted.get("lab_values") or []):
            observation = {
                "resourceType": "Observation", "status": "final", "subject": {"reference": patient_url},
                "code": {"text": lab.get("name") or "Lab value"},
                "interpretation": [{"text": lab.get("flag") or "normal"}], "note": [{"text": source_note}],
            }
            try:
                observation["valueQuantity"] = {"value": float(lab.get("value")), "unit": lab.get("unit") or ""}
            except (TypeError, ValueError):
                observation["valueString"] = " ".join(str(part) for part in (lab.get("value"), lab.get("unit")) if part)
            if lab.get("reference_range"): observation["referenceRange"] = [{"text": lab["reference_range"]}]
            if document.get("date"): observation["effectiveDateTime"] = document["date"]
            document_urls.append(add_clinical(observation, f"document-{doc_index}-lab-{item_index}"))

    sections = [{"title": "Chief complaint and history", "entry": [{"reference": complaint_url}]}]
    if medication_urls: sections.append({"title": "Medications", "entry": [{"reference": url} for url in medication_urls]})
    if allergy_urls: sections.append({"title": "Allergies", "entry": [{"reference": url} for url in allergy_urls]})
    if document_urls: sections.append({"title": "Documents and alerts", "entry": [{"reference": url} for url in document_urls]})
    composition = {
        "resourceType": "Composition", "id": str(uuid.uuid4()),
        "meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/OPConsultRecord"]},
        "status": "final", "type": {"coding": [{"system": "http://snomed.info/sct", "code": "371530004", "display": "Clinical consultation report"}]},
        "subject": {"reference": patient_url}, "encounter": {"reference": encounter_url}, "date": now,
        "author": [{"reference": practitioner_url}], "title": "MediKiosk outpatient consultation history", "section": sections,
    }
    entries = [
        {"fullUrl": full_url("composition"), "resource": composition},
        {"fullUrl": patient_url, "resource": {
            "resourceType": "Patient", "id": re.sub(r"[^A-Za-z0-9.-]", "-", patient_ref),
            "meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Patient"]},
            "identifier": [{"system": "https://medikiosk.local/medi-id", "value": medi_id or patient_ref}],
            "name": [{"text": patient_name or "Unknown patient"}],
        }},
        {"fullUrl": practitioner_url, "resource": {"resourceType": "Practitioner", "name": [{"text": "MediKiosk reviewing clinician"}]}},
        {"fullUrl": organization_url, "resource": {"resourceType": "Organization", "identifier": [{"system": "https://facility.ndhm.gov.in", "value": abdm_client.config.facility_id or "UNCONFIGURED"}], "name": abdm_client.config.facility_name}},
        {"fullUrl": encounter_url, "resource": {"resourceType": "Encounter", "status": "finished", "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}, "subject": {"reference": patient_url}, "serviceProvider": {"reference": organization_url}}},
        *clinical_entries,
    ]
    return {
        "resourceType": "Bundle", "id": str(uuid.uuid4()),
        "meta": {"profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/DocumentBundle"]},
        "identifier": {"system": "https://medikiosk.local/fhir/bundle", "value": str(uuid.uuid4())},
        "type": "document", "timestamp": now, "entry": entries,
    }


@app.post("/abdm/push")
def push_to_abdm(
    request: AbdmPushRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    session_id = request.session_id.strip()
    with _connect() as connection:
        session = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        signoff = connection.execute("SELECT * FROM clinical_signoffs WHERE session_id = ?", (session_id,)).fetchone()
    if session is None:
        raise HTTPException(status_code=404, detail="Clinical session not found")
    if not session["consent_given_at"] or not session["patient_medi_id"]:
        raise HTTPException(status_code=409, detail="The session is not ready for physician review")
    if signoff is None:
        raise HTTPException(status_code=409, detail="A clinician must sign off the record before it can be exported")
    data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
    documents = _validate_documents(_json_load(session["documents"], []))
    data["status"] = "physician_reviewed"
    patient_ref = session["patient_medi_id"]
    bundle = _build_fhir_bundle(
        patient_ref,
        session["patient_name"],
        session["patient_medi_id"],
        session["department"],
        data,
        documents,
    )
    validation_errors = validate_document_bundle(bundle)
    if validation_errors:
        raise HTTPException(status_code=422, detail={"message": "FHIR document validation failed", "errors": validation_errors})
    live_delivery = False
    delivery_response = None
    if abdm_client.config.live_ready:
        try:
            delivery_response = abdm_client.notify_care_context({
                "patient": {"referenceNumber": session["patient_medi_id"]},
                "careContexts": [{
                    "referenceNumber": "visit-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20],
                    "display": f"OP consultation {datetime.now(timezone.utc).date().isoformat()}",
                }],
            })
            live_delivery = True
        except (AbdmConfigurationError, AbdmTransportError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    record = {
        "session_id": session_id,
        "pushed": True,
        "mock": not live_delivery,
        "delivery_mode": "sandbox" if live_delivery else "local",
        "abdm_reference": (
            str((delivery_response or {}).get("requestId") or (delivery_response or {}).get("request_id") or "accepted")
            if live_delivery else "LOCAL-ABDM-" + secrets.token_hex(4).upper()
        ),
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "validation": {"profile": "DocumentBundle/OPConsultRecord", "valid": True, "errors": []},
        "bundle": bundle,
    }
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO abdm_pushes (session_id, record) VALUES (?, ?)",
            (session_id, json.dumps(record)),
        )
        connection.execute(
            "UPDATE sessions SET status = 'physician_reviewed', clinical_data = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(data), datetime.now(timezone.utc).isoformat(), session_id),
        )
        connection.commit()
    _write_audit_event(
        "clinical.record.approved_and_exported",
        actor_type="staff",
        actor_id=staff["user_id"],
        actor_role=staff["role"],
        session_id=session_id,
        patient_medi_id=session["patient_medi_id"],
        details={"destination": record["delivery_mode"], "reference": record["abdm_reference"]},
    )
    return record


@app.get("/abdm/push/{session_id}")
def get_abdm_push_status(
    session_id: str,
    _: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT record FROM abdm_pushes WHERE session_id = ?", (session_id,)).fetchone()
    return _json_load(row["record"], {"pushed": False}) if row else {"pushed": False}


@app.get("/staff/abdm/status")
def get_abdm_status(_: dict[str, str] = Depends(require_roles("doctor", "admin"))) -> dict:
    return {
        **abdm_client.config.public_status(),
        "fhir_release": "R4 (4.0.1)",
        "profiles": ["DocumentBundle", "OPConsultRecord"],
        "milestones": {"m1_identity": True, "m2_hip": True, "m3_hiu": True},
    }


@app.patch("/staff/patients/{medi_id}/abha")
def link_patient_abha(
    medi_id: str,
    request: AbhaLinkRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    abha_number = _normalize_abha_number(request.abha_number)
    abha_address = request.abha_address.strip().lower()
    if abha_address and "@" not in abha_address:
        raise HTTPException(status_code=422, detail="Enter a valid ABHA address")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        existing = connection.execute("SELECT * FROM patients WHERE medi_id = ?", (medi_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        duplicate = connection.execute(
            "SELECT medi_id FROM patients WHERE abha_number = ? AND medi_id <> ?", (abha_number, medi_id)
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="This ABHA number is already linked to another Medi ID")
        connection.execute(
            """UPDATE patients SET abha_number = ?, abha_address = ?, abha_status = 'verified', abha_verified_at = ?
               WHERE medi_id = ?""",
            (abha_number, abha_address or None, now, medi_id),
        )
        connection.execute(
            "UPDATE abdm_care_contexts SET abha_address = ? WHERE patient_medi_id = ?",
            (abha_address or None, medi_id),
        )
        connection.commit()
    _write_audit_event(
        "abdm.identity.linked", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
        patient_medi_id=medi_id,
        details={"verification_method": request.verification_method, "verification_reference": request.verification_reference, "has_abha_address": bool(abha_address)},
    )
    return {"medi_id": medi_id, "abha_number": _mask_abha_number(abha_number), "abha_address": abha_address, "abha_status": "verified", "verified_at": now}


@app.get("/staff/patients/{medi_id}/care-contexts")
def list_care_contexts(
    medi_id: str,
    _: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM abdm_care_contexts WHERE patient_medi_id = ? ORDER BY created_at DESC", (medi_id,)
        ).fetchall()
    return {"care_contexts": [dict(row) for row in rows]}


@app.post("/staff/abdm/hiu/consent-requests")
def create_hiu_consent_request(
    request: HiuConsentRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    consent_id = "consent-" + secrets.token_hex(12)
    now = datetime.now(timezone.utc).isoformat()
    artifact = {"request": request.model_dump(), "gateway_response": None}
    status = "locally_staged"
    if abdm_client.config.live_ready:
        try:
            artifact["gateway_response"] = abdm_client.create_hiu_consent_request({
                "requestId": str(uuid.uuid4()), "timestamp": now,
                "consent": {"purpose": {"text": request.purpose}, "patient": {"id": request.patient_abha_address},
                            "hiTypes": request.hi_types, "permission": {"dateRange": {"from": request.date_from, "to": request.date_to}, "dataEraseAt": request.expires_at}},
            })
            status = "requested"
        except (AbdmConfigurationError, AbdmTransportError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    with _connect() as connection:
        connection.execute(
            "INSERT INTO abdm_consents (consent_id, direction, patient_abha_address, status, artifact, created_at, updated_at) VALUES (?, 'outbound_hiu', ?, ?, ?, ?, ?)",
            (consent_id, request.patient_abha_address, status, json.dumps(artifact), now, now),
        )
        connection.commit()
    _write_audit_event(
        "abdm.hiu.consent.requested", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
        details={"consent_id": consent_id, "status": status, "hi_types": request.hi_types},
    )
    return {"consent_id": consent_id, "status": status, "mode": abdm_client.config.mode}


def _require_abdm_callback_secret(x_abdm_callback_secret: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ABDM_CALLBACK_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="ABDM callback authentication is not configured")
    if not x_abdm_callback_secret or not secrets.compare_digest(x_abdm_callback_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid ABDM callback authentication")


@app.post("/abdm/callbacks/consent")
def receive_abdm_consent(payload: dict, _: None = Depends(_require_abdm_callback_secret)) -> dict:
    consent_id = str(payload.get("consentId") or payload.get("consent_id") or "").strip()
    patient_address = str(payload.get("patientAbhaAddress") or payload.get("patient_abha_address") or "").strip()
    status = str(payload.get("status") or "received").strip().lower()
    if not consent_id or not patient_address:
        raise HTTPException(status_code=422, detail="consentId and patientAbhaAddress are required")
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO abdm_consents (consent_id, direction, patient_abha_address, status, artifact, created_at, updated_at)
               VALUES (?, 'inbound_hip', ?, ?, ?, ?, ?)
               ON CONFLICT(consent_id) DO UPDATE SET status = excluded.status, artifact = excluded.artifact, updated_at = excluded.updated_at""",
            (consent_id, patient_address, status, json.dumps(payload), now, now),
        )
        connection.commit()
    _write_audit_event("abdm.hip.consent.received", actor_type="abdm_gateway", actor_id="callback", details={"consent_id": consent_id, "status": status})
    return {"acknowledged": True, "consent_id": consent_id}


@app.post("/abdm/callbacks/health-information")
def receive_health_information_notice(payload: dict, _: None = Depends(_require_abdm_callback_secret)) -> dict:
    exchange_id = str(payload.get("transactionId") or payload.get("transaction_id") or "exchange-" + secrets.token_hex(8))
    consent_id = str(payload.get("consentId") or payload.get("consent_id") or "")
    now = datetime.now(timezone.utc).isoformat()
    metadata = {key: payload.get(key) for key in ("transactionId", "consentId", "status", "checksum", "contentType") if key in payload}
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO abdm_exchanges (exchange_id, consent_id, direction, status, payload_metadata, created_at, updated_at) VALUES (?, ?, 'inbound_hiu', ?, ?, ?, ?)",
            (exchange_id, consent_id or None, str(payload.get("status") or "notified"), json.dumps(metadata), now, now),
        )
        connection.commit()
    _write_audit_event("abdm.hiu.health_information.notified", actor_type="abdm_gateway", actor_id="callback", details={"exchange_id": exchange_id, "consent_id": consent_id})
    return {"acknowledged": True, "exchange_id": exchange_id}


def _staff_session_payload(row: sqlite3.Row, include_record: bool = True) -> dict:
    data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
    payload = {
        "session_id": row["session_id"],
        "patient_medi_id": row["patient_medi_id"],
        "patient_name": row["patient_name"],
        "language": row["language"],
        "interaction_mode": row["interaction_mode"],
        "department": row["department"],
        "turn_count": row["turn_count"],
        "interview_complete": bool(row["interview_complete"]),
        "status": row["status"],
        "updated_at": row["updated_at"],
        "kiosk_id": row["kiosk_id"] if "kiosk_id" in row.keys() else KIOSK_ID,
        "chief_complaint": data.get("chief_complaint", ""),
        "red_flag": data.get("red_flag", False),
    }
    if include_record:
        with _connect() as connection:
            signoff_row = connection.execute(
                "SELECT * FROM clinical_signoffs WHERE session_id = ?", (row["session_id"],)
            ).fetchone()
        payload.update(
            {
                "data": data,
                "transcript": _json_load(row["transcript"], []),
                "documents": _validate_documents(_json_load(row["documents"], [])),
                "signoff": dict(signoff_row) if signoff_row else None,
            }
        )
    return payload


@app.get("/staff/sessions")
def list_staff_sessions(_: dict[str, str] = Depends(require_roles("doctor", "admin"))) -> dict:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM sessions WHERE patient_medi_id IS NOT NULL ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    return {"sessions": [_staff_session_payload(row, include_record=False) for row in rows]}


@app.get("/staff/sessions/{session_id}")
def get_staff_session(
    session_id: str,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clinical session not found")
    _write_audit_event(
        "clinical.record.viewed",
        actor_type="staff",
        actor_id=staff["user_id"],
        actor_role=staff["role"],
        session_id=session_id,
        patient_medi_id=row["patient_medi_id"],
    )
    return _staff_session_payload(row)


def _save_revision(connection, row: sqlite3.Row, data: dict, staff: dict, action: str, reason: str, fields: list[str]) -> dict:
    version = connection.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM clinical_revisions WHERE session_id = ?",
        (row["session_id"],),
    ).fetchone()[0]
    revision = {
        "revision_id": "rev-" + secrets.token_hex(12),
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    connection.execute(
        """INSERT INTO clinical_revisions
           (revision_id, session_id, version, created_at, actor_user_id, actor_name, actor_role,
            action, reason, changed_fields, clinical_data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (revision["revision_id"], row["session_id"], version, revision["created_at"], staff["user_id"],
         staff["display_name"], staff["role"], action, reason, json.dumps(fields), json.dumps(data)),
    )
    return revision


@app.patch("/staff/sessions/{session_id}/record")
def edit_clinical_record(
    session_id: str,
    request: ClinicalRecordEditRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    invalid = sorted(set(request.changes) - CLINICIAN_EDITABLE_FIELDS)
    if invalid:
        raise HTTPException(status_code=422, detail=f"These fields cannot be edited here: {', '.join(invalid)}")
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Clinical session not found")
        data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
        for path, value in request.changes.items():
            _set_nested_value(data, path, value)
        data["status"] = "draft"
        try:
            data = ClinicalData.model_validate(data).model_dump()
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="One or more edited values have the wrong format") from exc
        revision = _save_revision(connection, row, data, staff, "edit", request.reason.strip(), sorted(request.changes))
        now = revision["created_at"]
        connection.execute("DELETE FROM clinical_signoffs WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM abdm_pushes WHERE session_id = ?", (session_id,))
        connection.execute(
            "UPDATE sessions SET clinical_data = ?, status = 'draft', updated_at = ? WHERE session_id = ?",
            (json.dumps(data), now, session_id),
        )
        connection.commit()
    _write_audit_event(
        "clinical.record.edited", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
        session_id=session_id, patient_medi_id=row["patient_medi_id"],
        details={"version": revision["version"], "changed_fields": sorted(request.changes), "reason": request.reason.strip()},
    )
    return {"data": data, "revision": revision, "signoff": None}


@app.get("/staff/sessions/{session_id}/revisions")
def list_clinical_revisions(
    session_id: str,
    _: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        rows = connection.execute(
            """SELECT revision_id, version, created_at, actor_user_id, actor_name, actor_role,
                      action, reason, changed_fields
               FROM clinical_revisions WHERE session_id = ? ORDER BY version DESC""",
            (session_id,),
        ).fetchall()
    return {"revisions": [{**dict(row), "changed_fields": _json_load(row["changed_fields"], [])} for row in rows]}


@app.post("/staff/sessions/{session_id}/signoff")
def sign_off_clinical_record(
    session_id: str,
    request: ClinicalSignoffRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Clinical session not found")
        if not row["patient_medi_id"]:
            raise HTTPException(status_code=409, detail="The session has no registered patient")
        data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
        if not data["chief_complaint"]:
            raise HTTPException(status_code=409, detail="Add a chief complaint before sign-off")
        data["status"] = "physician_reviewed"
        revision = _save_revision(connection, row, data, staff, "sign_off", "Clinician attestation", [])
        signed_at = revision["created_at"]
        signature_material = json.dumps(data, sort_keys=True, separators=(",", ":")) + staff["user_id"] + signed_at
        signature_hash = hashlib.sha256(signature_material.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT OR REPLACE INTO clinical_signoffs
               (session_id, revision_id, signed_at, signed_by_user_id, signed_by_name, signature_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, revision["revision_id"], signed_at, staff["user_id"], staff["display_name"], signature_hash),
        )
        connection.execute(
            "UPDATE sessions SET clinical_data = ?, status = 'physician_reviewed', updated_at = ? WHERE session_id = ?",
            (json.dumps(data), signed_at, session_id),
        )
        patient_identity = connection.execute(
            "SELECT abha_address FROM patients WHERE medi_id = ?", (row["patient_medi_id"],)
        ).fetchone()
        care_context_reference = "visit-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
        connection.execute(
            """INSERT OR REPLACE INTO abdm_care_contexts
               (care_context_reference, session_id, patient_medi_id, abha_address, display, created_at, notified_at)
               VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT notified_at FROM abdm_care_contexts WHERE session_id = ?), NULL))""",
            (care_context_reference, session_id, row["patient_medi_id"],
             patient_identity["abha_address"] if patient_identity else None,
             f"OP consultation {signed_at[:10]}", signed_at, session_id),
        )
        connection.commit()
    signoff = {"revision_id": revision["revision_id"], "signed_at": signed_at, "signed_by_user_id": staff["user_id"],
               "signed_by_name": staff["display_name"], "signature_hash": signature_hash}
    _write_audit_event(
        "clinical.record.signed_off", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
        session_id=session_id, patient_medi_id=row["patient_medi_id"], details={"version": revision["version"], "signature_hash": signature_hash},
    )
    return {"data": data, "revision": revision, "signoff": signoff, "care_context_reference": care_context_reference}


@app.get("/staff/sessions/{session_id}/pdf")
def download_clinical_pdf(
    session_id: str,
    audience: Literal["patient", "clinician"] = "clinician",
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> Response:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        signoff_row = connection.execute("SELECT * FROM clinical_signoffs WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clinical session not found")
    if signoff_row is None:
        raise HTTPException(status_code=409, detail="The clinician must sign off this record before creating a PDF")
    record = _staff_session_payload(row)
    pdf_bytes = build_clinical_pdf(record, audience, dict(signoff_row))
    _write_audit_event(
        "clinical.pdf.generated", actor_type="staff", actor_id=staff["user_id"], actor_role=staff["role"],
        session_id=session_id, patient_medi_id=row["patient_medi_id"], details={"audience": audience},
    )
    filename = f"medikiosk-{session_id[:24]}-{audience}.pdf"
    return Response(pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.patch("/staff/sessions/{session_id}/ayush-confirmation")
def confirm_ayush_assessment(
    session_id: str,
    request: PractitionerAyushConfirmationRequest,
    staff: dict[str, str] = Depends(require_roles("doctor", "admin")),
) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Clinical session not found")
        if (row["department"] or "general").strip().lower() == "general":
            raise HTTPException(status_code=409, detail="AYUSH confirmation is only available for Ayurveda departments")
        data = ClinicalData.model_validate(_json_load(row["clinical_data"], {})).model_dump()
        now = datetime.now(timezone.utc).isoformat()
        ayush = data["ayush_assessment"]
        ayush["prakriti"] = request.prakriti.strip()
        ayush["prakriti_source"] = "practitioner_confirmed"
        ayush["prakriti_confirmed_by"] = staff["display_name"]
        ayush["prakriti_confirmed_at"] = now
        practitioner_exam = ayush["dashavidha"]["practitioner_exam"]
        practitioner_exam.update({
            "sara": request.sara.strip(),
            "samhanana": request.samhanana.strip(),
            "pramana": request.pramana.strip(),
            "notes": request.notes.strip(),
        })
        completed_exam = all(practitioner_exam[field] for field in ("sara", "samhanana", "pramana"))
        patient_reported = ayush["dashavidha"]["patient_reported"]
        complete_dashavidha = (
            completed_exam
            and bool(ayush["prakriti"])
            and bool(ayush["vikriti"])
            and all(patient_reported[field] for field in ("satmya", "sattva", "ahara_shakti", "vyayama_shakti", "vaya"))
        )
        ayush["dashavidha"]["status"] = "practitioner_confirmed" if complete_dashavidha else "partially_confirmed"
        ayush["dashavidha"]["confirmed_by"] = staff["display_name"]
        ayush["dashavidha"]["confirmed_at"] = now
        data = ClinicalData.model_validate(data).model_dump()
        data["status"] = "draft"
        revision = _save_revision(
            connection, row, data, staff, "ayush_confirmation", "Practitioner Ayurveda assessment",
            ["ayush_assessment.prakriti", "ayush_assessment.dashavidha.practitioner_exam"],
        )
        connection.execute("DELETE FROM clinical_signoffs WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM abdm_pushes WHERE session_id = ?", (session_id,))
        connection.execute(
            "UPDATE sessions SET clinical_data = ?, status = 'draft', updated_at = ? WHERE session_id = ?",
            (json.dumps(data), now, session_id),
        )
        connection.execute(
            "UPDATE patients SET prakriti = ? WHERE medi_id = ?",
            (ayush["prakriti"], row["patient_medi_id"]),
        )
        connection.commit()
    _write_audit_event(
        "clinical.ayush.confirmed",
        actor_type="staff",
        actor_id=staff["user_id"],
        actor_role=staff["role"],
        session_id=session_id,
        patient_medi_id=row["patient_medi_id"],
        details={"dashavidha_status": ayush["dashavidha"]["status"]},
    )
    return {
        "data": data,
        "prakriti": ayush["prakriti"],
        "dashavidha_status": ayush["dashavidha"]["status"],
        "confirmed_by": staff["display_name"],
        "confirmed_at": now,
        "revision": revision,
    }


@app.get("/staff/audit")
def list_audit_events(
    limit: int = 100,
    _: dict[str, str] = Depends(require_roles("admin")),
) -> dict:
    safe_limit = max(1, min(limit, 500))
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["details"] = _json_load(event.get("details"), {})
        events.append(event)
    return {"events": events}
