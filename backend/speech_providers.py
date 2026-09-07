"""Small HTTP adapters for optional Indian-language speech services.

The patient endpoints keep local Whisper/Piper as the dependable fallback. These
adapters only translate MediKiosk's stable inputs into provider-specific payloads.
"""

import base64
import json
import os
import urllib.error
import urllib.request


class SpeechProviderError(RuntimeError):
    pass


SUPPORTED_PROVIDERS = {"local", "bhashini", "ai4bharat"}


def selected_provider(requested: str | None = None) -> str:
    value = (requested or "auto").strip().lower()
    if value == "auto":
        value = os.environ.get("SPEECH_PROVIDER", "local").strip().lower()
    return value if value in SUPPORTED_PROVIDERS else "local"


def provider_status() -> dict:
    bhashini_ready = all(
        os.environ.get(name, "").strip()
        for name in (
            "BHASHINI_COMPUTE_URL",
            "BHASHINI_AUTH_NAME",
            "BHASHINI_AUTH_VALUE",
            "BHASHINI_ASR_SERVICE_ID",
            "BHASHINI_TTS_SERVICE_ID",
        )
    )
    ai4bharat_ready = bool(os.environ.get("AI4BHARAT_ASR_URL", "").strip())
    return {
        "selected": selected_provider(),
        "providers": {
            "local": {"configured": True, "asr": True, "tts": True},
            "bhashini": {"configured": bhashini_ready, "asr": bhashini_ready, "tts": bhashini_ready},
            "ai4bharat": {
                "configured": ai4bharat_ready,
                "asr": ai4bharat_ready,
                "tts": bool(os.environ.get("AI4BHARAT_TTS_URL", "").strip()),
            },
        },
    }


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise SpeechProviderError("Speech provider request failed") from exc
    if not isinstance(result, dict):
        raise SpeechProviderError("Speech provider returned an invalid response")
    return result


def _bhashini_headers() -> dict[str, str]:
    auth_name = os.environ.get("BHASHINI_AUTH_NAME", "").strip()
    auth_value = os.environ.get("BHASHINI_AUTH_VALUE", "").strip()
    if not auth_name or not auth_value:
        raise SpeechProviderError("Bhashini authentication is not configured")
    return {auth_name: auth_value}


def transcribe_bhashini(audio_data: bytes, language: str, audio_format: str = "webm") -> str:
    url = os.environ.get("BHASHINI_COMPUTE_URL", "").strip()
    service_id = os.environ.get("BHASHINI_ASR_SERVICE_ID", "").strip()
    if not url or not service_id:
        raise SpeechProviderError("Bhashini ASR is not configured")
    payload = {
        "pipelineTasks": [{
            "taskType": "asr",
            "config": {
                "language": {"sourceLanguage": language},
                "serviceId": service_id,
                "audioFormat": audio_format,
                "samplingRate": 16000,
            },
        }],
        "inputData": {"audio": [{"audioContent": base64.b64encode(audio_data).decode("ascii")}]},
    }
    result = _post_json(url, payload, _bhashini_headers())
    try:
        text = result["pipelineResponse"][0]["output"][0]["source"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SpeechProviderError("Bhashini ASR response did not contain text") from exc
    return str(text).strip()


def synthesize_bhashini(text: str, language: str) -> bytes:
    url = os.environ.get("BHASHINI_COMPUTE_URL", "").strip()
    service_id = os.environ.get("BHASHINI_TTS_SERVICE_ID", "").strip()
    if not url or not service_id:
        raise SpeechProviderError("Bhashini TTS is not configured")
    payload = {
        "pipelineTasks": [{
            "taskType": "tts",
            "config": {
                "language": {"sourceLanguage": language},
                "serviceId": service_id,
                "gender": "female",
                "samplingRate": 22050,
            },
        }],
        "inputData": {"input": [{"source": text}]},
    }
    result = _post_json(url, payload, _bhashini_headers())
    try:
        content = result["pipelineResponse"][0]["audio"][0]["audioContent"]
        return base64.b64decode(content, validate=True)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SpeechProviderError("Bhashini TTS response did not contain audio") from exc


def transcribe_ai4bharat(audio_data: bytes, language: str) -> str:
    base_url = os.environ.get("AI4BHARAT_ASR_URL", "").strip().rstrip("/")
    if not base_url:
        raise SpeechProviderError("AI4Bharat ASR is not configured")
    payload = {
        "config": {
            "language": {"sourceLanguage": language},
            "transcriptionFormat": {"value": "transcript"},
            "audioFormat": "wav",
            "samplingRate": "16000",
            "postProcessors": None,
        },
        "audio": [{"audioContent": base64.b64encode(audio_data).decode("ascii")}],
    }
    headers = {}
    if os.environ.get("AI4BHARAT_API_KEY", "").strip():
        headers["Authorization"] = f"Bearer {os.environ['AI4BHARAT_API_KEY'].strip()}"
    result = _post_json(f"{base_url}/recognize/{language}", payload, headers)
    try:
        return str(result["output"][0]["source"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise SpeechProviderError("AI4Bharat ASR response did not contain text") from exc


def synthesize_ai4bharat(text: str, language: str) -> bytes:
    url = os.environ.get("AI4BHARAT_TTS_URL", "").strip()
    if not url:
        raise SpeechProviderError("AI4Bharat TTS is not configured")
    headers = {}
    if os.environ.get("AI4BHARAT_API_KEY", "").strip():
        headers["Authorization"] = f"Bearer {os.environ['AI4BHARAT_API_KEY'].strip()}"
    result = _post_json(url, {"text": text, "language": language, "format": "wav"}, headers)
    content = result.get("audio") or result.get("audioContent")
    try:
        return base64.b64decode(content, validate=True)
    except (TypeError, ValueError) as exc:
        raise SpeechProviderError("AI4Bharat TTS response did not contain audio") from exc

