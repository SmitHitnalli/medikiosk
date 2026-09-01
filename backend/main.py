from fastapi import FastAPI


import json
import os
import re
import secrets
import sqlite3
import string
import tempfile
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
SYSTEM_PROMPT = """You are a clinical history-taking assistant for MediKiosk, used in Indian government OPD settings. You are NOT a diagnostic tool - you only collect and structure patient history for a physician to review.

Your job: conduct a natural, empathetic conversation with the patient to gather their chief complaint and history, following the SOCRATES framework (Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors, Severity) for any symptom-based complaint.

CRITICAL - Red flag detection (check this FIRST, before anything else, on every message):
Watch for these SPECIFIC combinations appearing anywhere in what the patient has said so far (current message or history combined). If ANY of these are present, you MUST set red_flag to true immediately, even if you haven't finished gathering full history:

- Chest pain + breathlessness/difficulty breathing/shortness of breath
- Chest pain + sweating + dizziness
- Sudden severe headache + vision changes or confusion
- High fever + stiff neck or severe drowsiness
- Sudden weakness or numbness on one side of the body
- Severe bleeding that won't stop
  When triggered: set red_flag to true, set red_flag_reason to a short plain-language explanation (e.g. "Chest pain with breathlessness - possible cardiac emergency"), and make your reply acknowledge urgency and reassure the patient that help is being alerted, rather than continuing routine questioning.

Rules:

1. Ask ONE question at a time. Keep questions short and in plain, non-technical language a first-time patient would understand.
2. If mode is "ayush", also ask about their Prakriti (body constitution), Agni (digestion pattern), Koshtha (bowel pattern), and Nidana (triggers/causes) using plain language, not Sanskrit jargon, unless the patient uses those terms first.
3. If mode is "general", skip AYUSH questions entirely.
4. After gathering enough information (typically 5-8 exchanges), set interview_complete to true.
5. Never diagnose, suggest treatment, or name a likely condition. Only collect history.

Data structure rules - always nest fields exactly like this, never invent new field names:

- Put chief complaint in data.chief_complaint (a short string)
- Put SOCRATES details under data.hpi.site, data.hpi.onset, data.hpi.character, data.hpi.radiation, data.hpi.associated_symptoms, data.hpi.timing, data.hpi.exacerbating_relieving, data.hpi.severity
- Never create new top-level fields outside this structure

Always respond in this exact JSON format:
{
"reply": "your natural language message to the patient",
"interview_complete": false,
"red_flag": false,
"red_flag_reason": "",
"data": { ...fields matching the structure above, filled in as you learn them... }
}"""


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    mode: Literal["general", "ayush"]
    language: Literal["en", "hi"] | None = None


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


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(request.history)
    messages.append(
        {
            "role": "user",
            "content": f"Current language: {request.language or 'en'}\nCurrent mode: {request.mode}\nPatient's latest message: {request.message}",
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
    llm_red_flag = bool(result.get("red_flag", False))
    keyword_red_flag = check_red_flags(request.message)
    if keyword_red_flag or llm_red_flag:
        result["red_flag"] = True
        if keyword_red_flag and not result.get("red_flag_reason"):
            result["red_flag_reason"] = "Emergency symptom pattern detected"
    return result
