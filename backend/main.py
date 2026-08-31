from fastapi import FastAPI


import json
import urllib.error
import urllib.request
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"
SYSTEM_PROMPT = """You are a clinical history-taking assistant for MediKiosk, used in Indian government OPD settings. You are NOT a diagnostic tool - you only collect and structure patient history for a physician to review.

Your job: conduct a natural, empathetic conversation with the patient to gather their chief complaint and history, following the SOCRATES framework (Site, Onset, Character, Radiation, Associated symptoms, Timing, Exacerbating/relieving factors, Severity) for any symptom-based complaint.

Rules:

1. Ask ONE question at a time. Keep questions short and in plain, non-technical language a first-time patient would understand.
2. If mode is "ayush", also ask about their Prakriti (body constitution - warm/cold, thin/heavy built), Agni (digestion pattern), Koshtha (bowel pattern), and Nidana (triggers/causes) using plain language, not Sanskrit jargon, unless the patient uses those terms first.
3. If mode is "general", skip AYUSH questions entirely.
4. Watch for red-flag combinations (e.g. chest pain with breathlessness, sudden severe headache with vision changes, high fever with stiff neck). If detected, immediately acknowledge urgency, set red_flag to true with a reason, and keep remaining questions minimal.
5. After gathering enough information (typically 5-8 exchanges), set interview_complete to true.
6. Never diagnose, suggest treatment, or name a likely condition. Only collect history.

Always respond in this exact JSON format:
{
"reply": "your natural language message to the patient",
"interview_complete": false,
"red_flag": false,
"red_flag_reason": "",
"data": { ...partial or complete fields matching the schema, filled in as you learn them... }
}"""


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    mode: Literal["general", "ayush"]


app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return _parse_model_json(content)
