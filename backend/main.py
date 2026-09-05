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
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from datetime import datetime, timezone
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

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
# Hackathon-simple shared staff PIN, not per-user auth. Set STAFF_PIN in backend/.env to change it.
STAFF_PIN = os.environ.get("STAFF_PIN", "1234")
STAFF_SESSION_SECONDS = 30 * 60
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_CHAT_CHARS = 4000
MAX_SPEAK_CHARS = 3000
ALLOWED_DEPARTMENTS = {"general", "Kayachikitsa", "Panchakarma", "Shalya", "Prasuti Tantra"}
UNKNOWN_STRINGS = {"", "unknown", "not known", "not provided", "not recorded", "n/a", "na"}
_whisper_model = None
_piper_voices: dict[str, object] = {}
_easyocr_reader = None
_staff_pin_attempts: dict[str, list[float]] = {}
_staff_pin_lock = threading.Lock()
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
# Phone-camera photos routinely come in at 3000-4000px+ on the long side, which
# slows EasyOCR for no accuracy benefit at document-text scale. Cap the long side
# before running OCR.
OCR_MAX_IMAGE_DIMENSION = 1600
SYSTEM_PROMPT = """You are Nurse Anjali, a warm, experienced clinical intake assistant at an AYUSH hospital in India. You are NOT a diagnostic tool - you only gather and organize a patient's history for the physician to review. You never diagnose, suggest treatment, or name a likely condition.

PERSONA AND TONE:
Speak like a caring, competent nurse who has done this a thousand times and genuinely wants to help - not like a form, a chatbot, or a customer service script. Use natural, warm phrasing. Vary your sentence structure - never repeat the same question format twice in a row. Acknowledge what the patient says before moving to the next question (e.g. "I see, that sounds uncomfortable" or "Thank you for sharing that") rather than jumping straight to the next question. Keep questions short and conversational, in plain language a first-time patient would understand - never use clinical jargon when speaking to the patient.

CONTEXT YOU WILL RECEIVE WITH EACH REQUEST:

- department: the department the patient selected (e.g. Kayachikitsa, Panchakarma, Shalya, Prasuti Tantra, or general)
- returning_patient: true/false
- known_prakriti: if returning_patient is true and this is filled in, DO NOT ask Prakriti questions again - acknowledge it naturally instead (e.g. "I see from your last visit that you have a Vata-Pitta constitution")
- patient_name: use it naturally in conversation, not on every single line

AYUSH QUESTION PRIORITY - FOLLOW THIS FIRST:
When the department is anything other than "general", after the patient has stated their chief complaint, your very next one or two questions MUST ask about Agni (digestion pattern) or Vikriti (current imbalance). Do not continue with generic SOCRATES questions first. Use plain language, such as "How would you describe your digestion - regular, variable, or sluggish?" or ask how their current health feels different from usual. Ask only one of these questions at a time, acknowledge the answer, and then continue naturally with the remaining AYUSH and SOCRATES history.

MODE - AYUSH IS DEFAULT:
Unless the department is explicitly "general", conduct an AYUSH-style interview. This means, in addition to the standard history, naturally weave in these questions using plain language (never raw Sanskrit terms unless the patient uses them first):

- Body constitution (Prakriti) - ONLY if known_prakriti is not already provided: "How would you describe your body type generally - do you run warm or cold, are you naturally thin, medium, or heavier built?"
- Current imbalance (Vikriti) - always ask this fresh, every visit, regardless of returning patient status
- Digestion pattern (Agni): "How would you describe your digestion - regular, variable, or sluggish?"
- Bowel pattern (Koshtha): "What is your bowel movement pattern generally like?"
- Causative factors (Nidana): "Have you noticed anything that seems to trigger or worsen this - stress, certain foods, weather, sleep?"
- If relevant to their complaint, ask about prior Panchakarma treatments: "Have you undergone any Panchakarma therapies before, like Vamana, Virechana, or Basti?"

If department is "general", skip all AYUSH-specific questions and conduct a standard history only.

CLINICAL QUESTIONING - SOCRATES FRAMEWORK:
For any symptom-based complaint, ensure you naturally cover: Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors, Severity. Ask ONE question at a time. Make questions genuinely useful for clinical assessment, not generic filler - think about what a skilled physician would actually need to know to narrow down what's happening, not just "tell me more."

RED FLAG AWARENESS (secondary check only - a separate deterministic system handles this primarily):
If you notice a pattern suggesting a medical emergency, set red_flag to true in your response and briefly acknowledge urgency in your reply.

HARD CAP:
After a maximum of 15-20 total exchanges, regardless of how complete the picture feels, set interview_complete to true and wrap up warmly (e.g. "Thank you, I think I have a good picture now - the doctor will take it from here").

PHYSICAL EXAMINATION NOTE:
Never attempt to assess anything requiring physical examination (pulse, palpation, visual inspection). If relevant, note in your final summary that Nadi Pariksha, Darshana, and Sparshana are to be conducted by the physician directly.

DATA STRUCTURE RULES:
Always nest fields exactly like this in the "data" object, never invent new field names:

- data.chief_complaint (string)
- data.hpi.site, data.hpi.onset, data.hpi.character, data.hpi.radiation, data.hpi.associated_symptoms, data.hpi.timing, data.hpi.exacerbating_relieving, data.hpi.severity
- data.past_medical_history (array), data.past_surgical_history (array)
- data.drug_allergy_history.current_medications (array), data.drug_allergy_history.allergies (array)
- data.ayush_assessment.prakriti, data.ayush_assessment.vikriti, data.ayush_assessment.agni, data.ayush_assessment.koshtha, data.ayush_assessment.nidana, data.ayush_assessment.panchakarma_history
- For the ayush_assessment fields specifically, use correct Sanskrit terminology in the stored data (this is shown to the doctor, not spoken to the patient)

Always respond in this exact JSON format:
{
"reply": "your natural, warm response to the patient - in plain language",
"interview_complete": false,
"red_flag": false,
"red_flag_reason": "",
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


class PatientRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)
    phone_number: str = Field(min_length=10, max_length=20)


class PrakritiUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prakriti: str | None = Field(default=None, max_length=100)


class StaffPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: str = Field(min_length=4, max_length=20)


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=8, max_length=100)
    language: Literal["en", "hi"]
    interaction_mode: Literal["speak", "chat"]
    consent: Literal[True]


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


class AyushAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prakriti: str = ""
    vikriti: str = ""
    agni: str = ""
    koshtha: str = ""
    nidana: str = ""
    panchakarma_history: str = ""


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
    data: ClinicalData = Field(default_factory=ClinicalData)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
                expires_at REAL NOT NULL
            )
            """
        )
        session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
        if "lookup_failures" not in session_columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN lookup_failures INTEGER NOT NULL DEFAULT 0")
        connection.commit()


def _mask_phone_number(phone_number: str) -> str:
    digits = re.sub(r"\D", "", phone_number)
    if not digits:
        return "*"
    return "*" * max(len(digits) - 2, 0) + digits[-2:]


def _patient_response(row: sqlite3.Row) -> dict[str, str | None]:
    return {
        "medi_id": row["medi_id"],
        "name": row["name"],
        "phone_number": _mask_phone_number(row["phone_number"]),
        "prakriti": row["prakriti"],
        "created_at": row["created_at"],
    }


_init_database()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^https?://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}):5173$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
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
    return {"status": "ok", "ollama": "ok" if ollama_ok else "unreachable"}


@app.post("/staff/verify-pin")
def verify_staff_pin(payload: StaffPinRequest, request: Request) -> dict:
    client_key = request.client.host if request.client else "local"
    now_epoch = time.time()
    with _staff_pin_lock:
        recent = [value for value in _staff_pin_attempts.get(client_key, []) if now_epoch - value < 300]
        _staff_pin_attempts[client_key] = recent
        if len(recent) >= 5:
            raise HTTPException(status_code=429, detail="Too many incorrect PIN attempts. Try again in five minutes.")
    if payload.pin.strip() != STAFF_PIN:
        with _staff_pin_lock:
            _staff_pin_attempts.setdefault(client_key, []).append(now_epoch)
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    with _staff_pin_lock:
        _staff_pin_attempts.pop(client_key, None)
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + STAFF_SESSION_SECONDS
    with _connect() as connection:
        connection.execute("DELETE FROM staff_sessions WHERE expires_at <= ?", (time.time(),))
        connection.execute(
            "INSERT INTO staff_sessions (token_hash, expires_at) VALUES (?, ?)",
            (_token_hash(token), expires_at),
        )
        connection.commit()
    return {"ok": True, "token": token, "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat()}


def require_staff(x_staff_token: str | None = Header(default=None)) -> str:
    if not x_staff_token:
        raise HTTPException(status_code=401, detail="Staff authentication required")
    with _connect() as connection:
        row = connection.execute(
            "SELECT expires_at FROM staff_sessions WHERE token_hash = ?",
            (_token_hash(x_staff_token),),
        ).fetchone()
        if row is None or row["expires_at"] <= time.time():
            if row is not None:
                connection.execute("DELETE FROM staff_sessions WHERE token_hash = ?", (_token_hash(x_staff_token),))
                connection.commit()
            raise HTTPException(status_code=401, detail="Staff session expired")
    return x_staff_token


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
    x_session_token: str | None = Header(default=None),
) -> sqlite3.Row:
    if not x_session_id:
        raise HTTPException(status_code=401, detail="Patient session ID required")
    return _require_session(x_session_id, x_session_token)


@app.post("/sessions/start")
def start_session(request: SessionStartRequest) -> dict:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    consent = {
        "abha_id": "",
        "consent_given_at": now,
        "scope": ["history_capture", "document_sharing", "hospital_share"],
    }
    data = ClinicalData(
        session_id=request.session_id,
        language=request.language,
        consent=consent,
    ).model_dump()
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, session_token_hash, language, interaction_mode,
                    consent_given_at, clinical_data, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.session_id,
                    _token_hash(token),
                    request.language,
                    request.interaction_mode,
                    now,
                    json.dumps(data),
                    now,
                ),
            )
            connection.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Session ID already exists") from exc
    return {"session_id": request.session_id, "session_token": token}


@app.delete("/sessions/{session_id}")
def clear_session(session_id: str, x_session_token: str | None = Header(default=None)) -> dict:
    _require_session(session_id, x_session_token)
    with _connect() as connection:
        connection.execute("DELETE FROM nurse_alerts WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM abdm_pushes WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        connection.commit()
    return {"cleared": True, "patient_registry_retained": True}


@app.get("/sessions/{session_id}")
def get_patient_session(session_id: str, x_session_token: str | None = Header(default=None)) -> dict:
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
        "data": data,
        "transcript": _json_load(row["transcript"], []),
        "documents": _validate_documents(_json_load(row["documents"], [])),
    }


@app.patch("/sessions/{session_id}/department")
def set_session_department(
    session_id: str,
    request: SessionDepartmentRequest,
    x_session_token: str | None = Header(default=None),
) -> dict:
    _require_session(session_id, x_session_token)
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET department = ?, updated_at = ? WHERE session_id = ?",
            (request.department, datetime.now(timezone.utc).isoformat(), session_id),
        )
        connection.commit()
    return {"department": request.department}


@app.put("/sessions/{session_id}/documents")
def set_session_documents(
    session_id: str,
    request: SessionDocumentsRequest,
    x_session_token: str | None = Header(default=None),
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
    return {"documents": documents}


@app.post("/patients/register")
def register_patient(request: PatientRegistration, session: sqlite3.Row = Depends(_session_headers)) -> dict[str, str]:
    name = request.name.strip()
    phone_number = request.phone_number.strip()
    digits = re.sub(r"\D", "", phone_number)
    if not name or len(digits) < 10 or len(digits) > 15:
        raise HTTPException(status_code=400, detail="Enter a valid name and 10-15 digit phone number")
    phone_number = digits

    with _connect() as connection:
        for _ in range(10):
            medi_id = "MK-" + "".join(secrets.choice(MEDI_ID_ALPHABET) for _ in range(6))
            try:
                connection.execute(
                    "INSERT INTO patients (medi_id, name, phone_number) VALUES (?, ?, ?)",
                    (medi_id, name, phone_number),
                )
                connection.commit()
                data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
                data["patient_id"] = medi_id
                connection.execute(
                    "UPDATE sessions SET patient_medi_id = ?, patient_name = ?, clinical_data = ?, updated_at = ? WHERE session_id = ?",
                    (medi_id, name, json.dumps(data), datetime.now(timezone.utc).isoformat(), session["session_id"]),
                )
                connection.commit()
                return {"medi_id": medi_id}
            except sqlite3.IntegrityError:
                continue

    raise HTTPException(status_code=500, detail="Could not generate a unique Medi ID")


@app.get("/patients/{medi_id}")
def get_patient(medi_id: str, session: sqlite3.Row = Depends(_session_headers)) -> dict[str, str | None]:
    if int(session["lookup_failures"] or 0) >= 3:
        raise HTTPException(status_code=429, detail="Medi ID lookup is locked for this visit. Please ask staff for help or continue as a new patient.")
    with _connect() as connection:
        row = connection.execute(
            "SELECT medi_id, name, phone_number, prakriti, created_at FROM patients WHERE medi_id = ?",
            (medi_id,),
        ).fetchone()
    if row is None:
        with _connect() as connection:
            connection.execute(
                "UPDATE sessions SET lookup_failures = lookup_failures + 1, updated_at = ? WHERE session_id = ?",
                (datetime.now(timezone.utc).isoformat(), session["session_id"]),
            )
            connection.commit()
        raise HTTPException(status_code=404, detail="Patient not found")
    data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
    if row["prakriti"]:
        data["ayush_assessment"]["prakriti"] = row["prakriti"]
    data["patient_id"] = row["medi_id"]
    with _connect() as connection:
        connection.execute(
            "UPDATE sessions SET patient_medi_id = ?, patient_name = ?, clinical_data = ?, lookup_failures = 0, updated_at = ? WHERE session_id = ?",
            (row["medi_id"], row["name"], json.dumps(data), datetime.now(timezone.utc).isoformat(), session["session_id"]),
        )
        connection.commit()
    return _patient_response(row)


@app.patch("/patients/{medi_id}/prakriti")
def update_patient_prakriti(
    medi_id: str,
    request: PrakritiUpdate,
    session: sqlite3.Row = Depends(_session_headers),
) -> dict[str, str | None]:
    if session["patient_medi_id"] != medi_id:
        raise HTTPException(status_code=403, detail="This patient is not linked to the active session")
    prakriti = request.prakriti.strip() if request.prakriti is not None else None
    with _connect() as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            "UPDATE patients SET prakriti = ? WHERE medi_id = ?",
            (prakriti or None, medi_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Patient not found")
        connection.commit()
        row = connection.execute(
            "SELECT medi_id, name, phone_number, prakriti, created_at FROM patients WHERE medi_id = ?",
            (medi_id,),
        ).fetchone()
    return _patient_response(row)


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
async def transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    try:
        audio_data = await _read_upload(
            file,
            {"audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "application/octet-stream"},
        )
        suffix = Path(file.filename or "audio.webm").suffix or ".webm"
        if suffix.lower() not in {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".ogg"}:
            raise HTTPException(status_code=415, detail="Unsupported audio file extension")
        text = await run_in_threadpool(_transcribe_bytes, audio_data, suffix)
        return {"text": text}
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
    return {
        "diagnoses": _clean_string_list(value.get("diagnoses")),
        "medications": _clean_string_list(value.get("medications")),
        "lab_values": labs,
    }


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
        if status not in {"confident", "confirmed", "illegible"}:
            raise HTTPException(status_code=422, detail="Invalid document status")
        cleaned.append(
            {
                "id": str(document.get("id") or secrets.token_hex(8))[:100],
                "doc_type": doc_type,
                "date": str(document.get("date") or "").strip()[:30],
                "status": status,
                "extracted_entities": _validate_entities(document.get("extracted_entities")),
            }
        )
    return cleaned


def _process_ocr(image_data: bytes, suffix: str, doc_type_hint: str | None) -> dict:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_data)
            temp_path = temp_file.name

        try:
            with Image.open(temp_path) as image:
                image.verify()
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
        return {
            "extracted_entities": _validate_entities(entities),
            "confidence": ocr_confidence,
            "suggested_doc_type": suggested_doc_type,
            "doc_type_confidence": doc_type_confidence,
            "status": status,
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
) -> dict:
    suffix = Path(file.filename or "document.jpg").suffix or ".jpg"
    try:
        image_data = await _read_upload(file, {"image/jpeg", "image/png", "image/webp", "application/octet-stream"})
        if suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise HTTPException(status_code=415, detail="Unsupported image file extension")
        return await run_in_threadpool(_process_ocr, image_data, suffix, doc_type_hint)
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
        voice = _get_piper_voice(request.language)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_path = temp_file.name
        with wave.open(temp_path, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        response = FileResponse(
            temp_path,
            media_type="audio/wav",
            filename="medikiosk-summary.wav",
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
        .replace("सांस नहीं", "cannot breathe")
        .replace("एक तरफ कमजोरी", "one side weakness")
        .replace("बहुत खून", "heavy bleeding")
    )
    clauses = _split_clauses(text)

    def present(term: str) -> bool:
        return _term_present_and_not_negated(clauses, term)

    has_chest_pain_or_chest = present("chest pain") or present("chest")
    has_breathing_term = present("breath") or present("breathless") or present("breathing")
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
    "ayush_assessment.prakriti": "their usual body constitution",
    "ayush_assessment.vikriti": "their current imbalance, or how their health feels different from usual",
    "ayush_assessment.agni": "their digestion pattern - regular, variable, or sluggish",
    "ayush_assessment.koshtha": "their usual bowel movement pattern",
    "ayush_assessment.nidana": "anything that triggers or worsens the problem, such as stress, food, weather, or sleep",
    "ayush_assessment.panchakarma_history": "whether they have undergone Panchakarma therapies before",
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
        "ayush_assessment.prakriti": "Are you usually warm or cold, and naturally thin, medium, or heavier built?",
        "ayush_assessment.vikriti": "How does your health feel different from usual right now?",
        "ayush_assessment.agni": "Is your digestion usually regular, variable, or sluggish?",
        "ayush_assessment.koshtha": "What is your usual bowel movement pattern?",
        "ayush_assessment.nidana": "Have you noticed triggers such as stress, food, weather, or sleep?",
        "ayush_assessment.panchakarma_history": "Have you had Panchakarma therapies before?",
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
        "ayush_assessment.prakriti": "आपको सामान्यतः गर्मी या ठंड अधिक लगती है, और शरीर दुबला, मध्यम या भारी है?",
        "ayush_assessment.vikriti": "अभी आपका स्वास्थ्य सामान्य से किस तरह अलग लग रहा है?",
        "ayush_assessment.agni": "आपका पाचन सामान्यतः नियमित, बदलता हुआ या धीमा रहता है?",
        "ayush_assessment.koshtha": "आपका सामान्य मल त्याग कैसा रहता है?",
        "ayush_assessment.nidana": "क्या तनाव, भोजन, मौसम या नींद से यह बढ़ती है?",
        "ayush_assessment.panchakarma_history": "क्या आपने पहले पंचकर्म चिकित्सा कराई है?",
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
        "hpi.site",
        "hpi.onset",
        "hpi.character",
        "hpi.radiation",
        "hpi.associated_symptoms",
        "hpi.timing",
        "hpi.exacerbating_relieving",
        "hpi.severity",
        "past_medical_history",
        "past_surgical_history",
        "drug_allergy_history.current_medications",
        "drug_allergy_history.allergies",
        "family_history",
        "personal_history.diet",
        "personal_history.smoking",
        "personal_history.alcohol",
        "personal_history.occupation",
        "review_of_systems",
    ])
    if is_ayush:
        if _value_is_empty(_get_nested_value(data, "ayush_assessment.prakriti")):
            fields.append("ayush_assessment.prakriti")
        fields.extend([
            "ayush_assessment.koshtha",
            "ayush_assessment.nidana",
        ])
        if (department or "").strip().lower() == "panchakarma":
            fields.append("ayush_assessment.panchakarma_history")

    return fields


def _next_missing_field(data: dict, department: str | None) -> str | None:
    return next((field for field in _required_fields(data, department) if _value_is_empty(_get_nested_value(data, field))), None)


def _next_field_instruction(data: dict, department: str | None) -> str:
    field = _next_missing_field(data, department)
    if field:
        return (
            "First extract the patient's latest answer into the data object. Do not invent facts. "
            f"After incorporating that answer, the server is currently tracking {FIELD_PROMPTS[field]} as the next gap. "
            "Your reply should only acknowledge the answer briefly; do not ask a question because the server adds it."
        )
    return "Extract the latest answer. Reply with only a brief acknowledgment; the server will close the interview."


def _patient_reply(data: dict, department: str | None, language: str, complete: bool, red_flag: bool) -> str:
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
    question = FIELD_QUESTIONS.get(language, FIELD_QUESTIONS["en"]).get(field, "Could you tell me a little more?")
    return ("धन्यवाद। " if language == "hi" else "Thank you. ") + question


@app.post("/chat")
def chat(request: ChatRequest, x_session_token: str | None = Header(default=None)) -> dict:
    session_id = request.session_id
    session = _require_session(session_id, x_session_token)
    if not session["patient_medi_id"] or not session["department"]:
        raise HTTPException(status_code=409, detail="Complete patient identification and department selection first")
    accumulated_data = ClinicalData.model_validate(_json_load(session["clinical_data"], {})).model_dump()
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
        {"role": "system", "content": _next_field_instruction(accumulated_data, session["department"])},
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
            raise first_error or HTTPException(status_code=503, detail="The AI assistant is unavailable")
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
    _merge_accumulated_data(accumulated_data, incoming_data)
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
    complete = turn_count >= 20 or _next_missing_field(accumulated_data, session["department"]) is None
    accumulated_data["interview_complete"] = complete
    reply = _patient_reply(accumulated_data, session["department"], session["language"], complete, red_flag)
    transcript.extend([
        {"role": "user", "content": request.message, "timestamp": datetime.now(timezone.utc).isoformat()},
        {"role": "assistant", "content": reply, "timestamp": datetime.now(timezone.utc).isoformat()},
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
        "data": accumulated_data,
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
        still_active = bool(existing and not existing["acknowledged"])
        triggered_at = existing["triggered_at"] if still_active else datetime.now(timezone.utc).isoformat()
        existing_source = existing["source"] if existing else None
        combined_source = (
            "keyword_and_ai" if {source, existing_source} == {"keyword", "ai"} else source or existing_source
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO nurse_alerts
            (id, session_id, kind, patient_name, department, reason, source, triggered_at, acknowledged, acknowledged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (alert_id, session_id, kind, patient_name, department, reason, combined_source, triggered_at),
        )
        connection.commit()


@app.get("/nurse-station/alerts")
def get_nurse_station_alerts(_: str = Depends(require_staff)) -> dict:
    with _connect() as connection:
        active = [dict(row) for row in connection.execute("SELECT * FROM nurse_alerts WHERE acknowledged = 0")]
    active.sort(key=lambda alert: alert["triggered_at"])
    return {"alerts": active}


@app.post("/nurse-station/alerts/{alert_id}/acknowledge")
def acknowledge_nurse_station_alert(alert_id: str, _: str = Depends(require_staff)) -> dict:
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
        return result


class HelpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str


@app.post("/nurse-station/help-request")
def request_help(request: HelpRequest, x_session_token: str | None = Header(default=None)) -> dict:
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


def _build_fhir_bundle(
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


@app.post("/abdm/push")
def push_to_abdm(request: AbdmPushRequest, _: str = Depends(require_staff)) -> dict:
    session_id = request.session_id.strip()
    with _connect() as connection:
        session = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if session is None:
        raise HTTPException(status_code=404, detail="Clinical session not found")
    if not session["consent_given_at"] or not session["patient_medi_id"]:
        raise HTTPException(status_code=409, detail="The session is not ready for physician review")
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
    record = {
        "session_id": session_id,
        "pushed": True,
        "mock": True,
        "abdm_reference": "MOCK-ABDM-" + secrets.token_hex(4).upper(),
        "pushed_at": datetime.now(timezone.utc).isoformat(),
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
    return record


@app.get("/abdm/push/{session_id}")
def get_abdm_push_status(session_id: str, _: str = Depends(require_staff)) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT record FROM abdm_pushes WHERE session_id = ?", (session_id,)).fetchone()
    return _json_load(row["record"], {"pushed": False}) if row else {"pushed": False}


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
        "chief_complaint": data.get("chief_complaint", ""),
        "red_flag": data.get("red_flag", False),
    }
    if include_record:
        payload.update(
            {
                "data": data,
                "transcript": _json_load(row["transcript"], []),
                "documents": _validate_documents(_json_load(row["documents"], [])),
            }
        )
    return payload


@app.get("/staff/sessions")
def list_staff_sessions(_: str = Depends(require_staff)) -> dict:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM sessions WHERE patient_medi_id IS NOT NULL ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    return {"sessions": [_staff_session_payload(row, include_record=False) for row in rows]}


@app.get("/staff/sessions/{session_id}")
def get_staff_session(session_id: str, _: str = Depends(require_staff)) -> dict:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clinical session not found")
    return _staff_session_payload(row)
