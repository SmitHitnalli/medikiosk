from fastapi import FastAPI


import json
import urllib.error
import urllib.request
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
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
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

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


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(request.history)
    messages.append(
        {
            "role": "user",
            "content": f"Current mode: {request.mode}\nPatient's latest message: {request.message}",
        }
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    ollama_request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

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
    result = _parse_model_json(content)
    llm_red_flag = bool(result.get("red_flag", False))
    keyword_red_flag = check_red_flags(request.message)
    if keyword_red_flag or llm_red_flag:
        result["red_flag"] = True
        if keyword_red_flag and not result.get("red_flag_reason"):
            result["red_flag_reason"] = "Emergency symptom pattern detected"
    return result
