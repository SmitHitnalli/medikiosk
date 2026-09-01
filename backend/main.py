from fastapi import FastAPI


import copy
import json
import os
import re
import secrets
import sqlite3
import string
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import FileResponse


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
DATABASE_PATH = Path(__file__).resolve().parent / "medikiosk.db"
MEDI_ID_ALPHABET = string.ascii_uppercase + string.digits
PIPER_VOICE_PATH = Path(__file__).resolve().parent / "voices" / "en_US-lessac-medium.onnx"
PIPER_CONFIG_PATH = Path(__file__).resolve().parent / "voices" / "en_US-lessac-medium.onnx.json"
_whisper_model = None
_piper_voice = None
_easyocr_reader = None
_accumulated_data_by_session: dict[str, dict] = {}
_session_data_lock = threading.Lock()
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
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    session_id: str
    language: Literal["en", "hi"] | None = None
    department: str | None = None
    returning_patient: bool = False
    known_prakriti: str | None = None
    patient_name: str | None = None


class SpeakRequest(BaseModel):
    text: str


class PatientRegistration(BaseModel):
    name: str
    phone_number: str


class PrakritiUpdate(BaseModel):
    prakriti: str | None = None


def _init_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/patients/register")
def register_patient(request: PatientRegistration) -> dict[str, str]:
    name = request.name.strip()
    phone_number = request.phone_number.strip()
    if not name or not phone_number:
        raise HTTPException(status_code=400, detail="Name and phone_number are required")

    with sqlite3.connect(DATABASE_PATH) as connection:
        for _ in range(10):
            medi_id = "MK-" + "".join(secrets.choice(MEDI_ID_ALPHABET) for _ in range(6))
            try:
                connection.execute(
                    "INSERT INTO patients (medi_id, name, phone_number) VALUES (?, ?, ?)",
                    (medi_id, name, phone_number),
                )
                connection.commit()
                return {"medi_id": medi_id}
            except sqlite3.IntegrityError:
                continue

    raise HTTPException(status_code=500, detail="Could not generate a unique Medi ID")


@app.get("/patients/{medi_id}")
def get_patient(medi_id: str) -> dict[str, str | None]:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT medi_id, name, phone_number, prakriti, created_at FROM patients WHERE medi_id = ?",
            (medi_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _patient_response(row)


@app.patch("/patients/{medi_id}/prakriti")
def update_patient_prakriti(medi_id: str, request: PrakritiUpdate) -> dict[str, str | None]:
    prakriti = request.prakriti.strip() if request.prakriti is not None else None
    with sqlite3.connect(DATABASE_PATH) as connection:
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

        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    temp_path = None
    try:
        audio_data = await file.read()
        if not audio_data:
            raise HTTPException(status_code=400, detail="The uploaded audio file is empty")

        suffix = Path(file.filename or "audio.webm").suffix or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name

        model = _get_whisper_model()
        segments, _ = model.transcribe(temp_path)
        text = " ".join(segment.text.strip() for segment in segments).strip()
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
        raise HTTPException(status_code=500, detail="Audio transcription failed") from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr

        _easyocr_reader = easyocr.Reader(["en"])
    return _easyocr_reader


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    image_data = await file.read()
    if not image_data:
        raise HTTPException(status_code=400, detail="The uploaded image file is empty")

    suffix = Path(file.filename or "document.jpg").suffix or ".jpg"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_data)
            temp_path = temp_file.name

        reader = _get_easyocr_reader()
        extracted_text = "\n".join(reader.readtext(temp_path, detail=0)).strip()
        if not extracted_text:
            return {"extracted_entities": {"diagnoses": [], "medications": [], "lab_values": []}}

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
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        parsed = _parse_model_json(_call_ollama(ollama_request))
        entities = parsed.get("extracted_entities", parsed)
        if not isinstance(entities, dict):
            raise HTTPException(status_code=502, detail="Ollama returned an invalid OCR structure")
        return {
            "extracted_entities": {
                "diagnoses": entities.get("diagnoses", []),
                "medications": entities.get("medications", []),
                "lab_values": entities.get("lab_values", []),
            }
        }
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
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _get_piper_voice():
    global _piper_voice
    if _piper_voice is None:
        from piper import PiperVoice

        _piper_voice = PiperVoice.load(PIPER_VOICE_PATH, config_path=PIPER_CONFIG_PATH)
    return _piper_voice


@app.post("/speak")
def speak(request: SpeakRequest) -> FileResponse:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text to synthesize cannot be empty")

    temp_path = None
    try:
        voice = _get_piper_voice()
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


def check_red_flags(message: str) -> bool:
    text = message.lower()

    has_chest_pain_or_chest = "chest pain" in text or "chest" in text
    has_breathing_term = any(term in text for term in ("breath", "breathless", "breathing"))
    if has_chest_pain_or_chest and has_breathing_term:
        return True

    if (
        "chest pain" in text
        and any(term in text for term in ("sweat", "sweating"))
        and any(term in text for term in ("dizzy", "dizziness"))
    ):
        return True

    if "headache" in text and any(term in text for term in ("vision", "confus")):
        return True

    if "fever" in text and any(term in text for term in ("stiff neck", "drowsy", "drowsiness")):
        return True

    if any(term in text for term in ("weakness", "numbness")) and any(
        term in text for term in ("one side", "left side", "right side")
    ):
        return True

    return "bleeding" in text and any(
        term in text for term in ("won't stop", "not stopping", "heavy")
    )


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
    if not isinstance(data, dict):
        data = {}

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


def _value_is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _merge_accumulated_data(existing: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if isinstance(value, dict):
            if not isinstance(existing.get(key), dict):
                existing[key] = {}
            _merge_accumulated_data(existing[key], value)
        elif isinstance(value, list):
            if _value_is_empty(value):
                continue
            if not isinstance(existing.get(key), list):
                existing[key] = []
            for item in value:
                if item not in existing[key]:
                    existing[key].append(copy.deepcopy(item))
        elif not _value_is_empty(value) and _value_is_empty(existing.get(key)):
            existing[key] = copy.deepcopy(value)
    return existing


FIELD_PROMPTS = {
    "chief_complaint": "the patient's main health concern",
    "hpi.site": "where they feel the symptom",
    "hpi.onset": "when the symptom started",
    "hpi.character": "what the symptom feels like",
    "hpi.associated_symptoms": "any other symptoms happening along with it",
    "hpi.timing": "when and how often the symptom occurs",
    "hpi.exacerbating_relieving": "what makes the symptom worse or better",
    "hpi.severity": "how severe the symptom is",
    "ayush_assessment.vikriti": "their current imbalance, or how their health feels different from usual",
    "ayush_assessment.agni": "their digestion pattern - regular, variable, or sluggish",
    "ayush_assessment.koshtha": "their usual bowel movement pattern",
    "ayush_assessment.nidana": "anything that triggers or worsens the problem, such as stress, food, weather, or sleep",
    "ayush_assessment.panchakarma_history": "whether they have undergone Panchakarma therapies before",
}


def _get_nested_value(data: dict, path: str):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _next_field_instruction(data: dict, department: str | None) -> str:
    fields = [
        "chief_complaint",
        "hpi.site",
        "hpi.onset",
        "hpi.character",
        "hpi.associated_symptoms",
        "hpi.timing",
        "hpi.exacerbating_relieving",
        "hpi.severity",
    ]
    if (department or "general").strip().lower() != "general":
        fields.extend([
            "ayush_assessment.vikriti",
            "ayush_assessment.agni",
            "ayush_assessment.koshtha",
            "ayush_assessment.nidana",
        ])
        if (department or "").strip().lower() == "panchakarma":
            fields.append("ayush_assessment.panchakarma_history")

    for field in fields:
        if _value_is_empty(_get_nested_value(data, field)):
            return (
                f"Your next question must specifically ask about {FIELD_PROMPTS[field]}, "
                "phrased warmly and naturally, acknowledging what the patient just said first. "
                "Ask only that one question and do not skip ahead to another field."
            )
    return "The required history fields are sufficiently covered. Ask only a brief clarifying question if needed, or wrap up warmly."


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    session_id = request.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    with _session_data_lock:
        accumulated_data = copy.deepcopy(_accumulated_data_by_session.get(session_id, {}))
    context = (
        "Conversation context for this patient:\n"
        f"department: {request.department or 'general'}\n"
        f"returning_patient: {'true' if request.returning_patient else 'false'}\n"
        f"known_prakriti: {request.known_prakriti or ''}\n"
        f"patient_name: {request.patient_name or ''}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context},
        {"role": "system", "content": _next_field_instruction(accumulated_data, request.department)},
    ]
    messages.extend(request.history)
    messages.append(
        {
            "role": "user",
            "content": f"Current language: {request.language or 'en'}\nPatient's latest message: {request.message}",
        }
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
    }
    ollama_request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    content = _call_ollama(ollama_request)
    try:
        result = _parse_model_json(content)
    except HTTPException as first_error:
        print(f"[chat] Ollama invalid JSON response (attempt 1): {content!r}", flush=True)
        retry_content = _call_ollama(ollama_request)
        try:
            result = _parse_model_json(retry_content)
        except HTTPException:
            print(f"[chat] Ollama invalid JSON response (attempt 2): {retry_content!r}", flush=True)
            raise first_error
    result = _normalise_chat_result(result)
    with _session_data_lock:
        accumulated_data = _accumulated_data_by_session.setdefault(session_id, {})
        _merge_accumulated_data(accumulated_data, result.get("data", {}))
        result["data"] = copy.deepcopy(accumulated_data)
    llm_red_flag = bool(result.get("red_flag", False))
    keyword_red_flag = check_red_flags(request.message)
    if keyword_red_flag or llm_red_flag:
        result["red_flag"] = True
        if keyword_red_flag and not result.get("red_flag_reason"):
            result["red_flag_reason"] = "Emergency symptom pattern detected"
    return result
