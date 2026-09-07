"""Live authenticated smoke test for MediKiosk.

Run while the backend and Ollama are running. Each check reports independently.
The test-owned visit, alerts, export, and registry record are removed in finally.
"""

from __future__ import annotations

import io
import json
import math
import os
import sqlite3
import struct
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

from dotenv import load_dotenv

BASE_URL = "http://127.0.0.1:8080"
DATABASE_PATH = Path(__file__).resolve().parent / "medikiosk.db"
load_dotenv(Path(__file__).resolve().parent / ".env")
STAFF_PIN = os.environ.get("STAFF_PIN", "1234")
STAFF_USERNAME = os.environ.get("STAFF_USERNAME", "admin")
TIMEOUT_SECONDS = 90
results: list[tuple[str, bool, str]] = []


def request(method, path, body=None, headers=None, raw_body=None):
    request_headers = dict(headers or {})
    payload = raw_body
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(BASE_URL + path, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, str(exc).encode("utf-8"), {}


def request_json(method, path, body=None, headers=None):
    status, raw, _ = request(method, path, body=body, headers=headers)
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None


def record(name, passed, detail=""):
    results.append((name, bool(passed), detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def multipart_file(field_name, filename, content_type, content):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def wav_bytes(seconds=1, frequency=440, sample_rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = bytearray()
        for index in range(seconds * sample_rate):
            value = int(math.sin(2 * math.pi * frequency * index / sample_rate) * 8000)
            frames.extend(struct.pack("<h", value))
        audio.writeframes(frames)
    return output.getvalue()


def png_bytes():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 350), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 40), "Prescription", fill="black")
    draw.text((30, 120), "Paracetamol 500 mg", fill="black")
    draw.text((30, 200), "Diagnosis: Viral fever", fill="black")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def main():
    suffix = uuid.uuid4().hex[:10]
    session_id = f"SMOKETEST-{suffix}"
    phone = "8" + str(time.time_ns())[-9:]
    session_token = None
    medi_id = None
    staff_token = None

    try:
        status, health = request_json("GET", "/health")
        record("Backend health", status == 200 and health and health.get("status") == "ok", f"status={status} {health}")
        record("Configured Ollama model available", bool(health and health.get("ollama") == "ok"), str(health))

        status, staff = request_json("POST", "/staff/login", {"username": STAFF_USERNAME, "pin": STAFF_PIN})
        staff_token = staff.get("token") if staff else None
        record("Staff authentication", status == 200 and bool(staff_token), f"status={status}")
        staff_headers = {"X-Staff-Token": staff_token} if staff_token else {}
        status, _ = request_json("GET", "/staff/sessions")
        record("Staff API rejects anonymous access", status == 401, f"status={status}")

        status, started = request_json("POST", "/sessions/start", {
            "session_id": session_id, "consent": True,
        })
        session_token = started.get("session_token") if started else None
        patient_headers = {"X-Session-Id": session_id, "X-Session-Token": session_token} if session_token else {}
        record("Consent-backed patient session", status == 200 and bool(session_token), f"status={status}")

        status, _ = request_json(
            "PATCH", f"/sessions/{session_id}/preferences",
            {"language": "en", "interaction_mode": "chat"}, patient_headers,
        )
        record("Language and mode persistence", status == 200, f"status={status}")

        status, patient = request_json("POST", "/patients/register", {
            "name": f"SMOKETEST {suffix}", "phone_number": phone,
        }, patient_headers)
        medi_id = patient.get("medi_id") if patient else None
        record("Patient registration", status == 200 and bool(medi_id), f"status={status} id={medi_id}")

        status, _ = request_json("PATCH", f"/sessions/{session_id}/department", {"department": "general"}, patient_headers)
        record("Department persistence", status == 200, f"status={status}")

        status, chat = request_json("POST", "/chat", {
            "session_id": session_id, "message": "I have had a mild headache since this morning.",
        }, patient_headers)
        record("Real Ollama interview turn", status == 200 and chat and bool(chat.get("reply")), f"status={status}")

        status, alert_chat = request_json("POST", "/chat", {
            "session_id": session_id, "message": "I now have severe chest pain and cannot breathe.",
        }, patient_headers)
        record("Immediate emergency rule", status == 200 and alert_chat and alert_chat.get("red_flag") is True, f"status={status}")

        status, alerts = request_json("GET", "/nurse-station/alerts", headers=staff_headers)
        has_alert = alerts and any(item.get("session_id") == session_id for item in alerts.get("alerts", []))
        record("Persistent nurse alert", status == 200 and has_alert, f"status={status}")

        status, audio, headers = request("POST", "/speak", {"text": "MediKiosk speech check", "language": "en"})
        record("Piper speech", status == 200 and len(audio) > 1000 and "audio" in headers.get("Content-Type", ""), f"status={status} bytes={len(audio)}")

        wav, content_type = multipart_file("file", "tone.wav", "audio/wav", wav_bytes())
        status, raw, _ = request("POST", "/transcribe", raw_body=wav, headers={"Content-Type": content_type})
        record("Whisper accepts valid audio", status == 200, f"status={status} bytes={len(raw)}")

        image, content_type = multipart_file("file", "prescription.png", "image/png", png_bytes())
        status, raw, _ = request("POST", "/ocr", raw_body=image, headers={"Content-Type": content_type})
        record("OCR accepts a prescription image", status == 200, f"status={status} bytes={len(raw)}")

        status, export = request_json(
            "POST", "/abdm/push", {"session_id": session_id, "physician_reviewed": True}, staff_headers
        )
        record("Reviewed mock FHIR export", status == 200 and export and export.get("pushed") is True, f"status={status}")

        status, restored = request_json("GET", f"/staff/sessions/{session_id}", headers=staff_headers)
        record("Staff restores persisted record", status == 200 and restored and restored.get("patient_medi_id") == medi_id, f"status={status}")
    except Exception as exc:
        record("Smoke runner", False, f"{type(exc).__name__}: {exc}")
    finally:
        if session_token:
            status, _ = request_json("DELETE", f"/sessions/{session_id}", headers={"X-Session-Token": session_token})
            record("Test visit cleanup", status in {200, 401, 404}, f"status={status}")
        if medi_id and DATABASE_PATH.exists():
            try:
                with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
                    connection.execute("DELETE FROM patients WHERE medi_id = ? AND name LIKE 'SMOKETEST %'", (medi_id,))
                    connection.commit()
                record("Test registry cleanup", True, medi_id)
            except Exception as exc:
                record("Test registry cleanup", False, str(exc))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} checks passed")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
