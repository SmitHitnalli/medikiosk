"""Focused regression checks for the engineering audit fixes.

Runs against a temporary SQLite database and stubs only Ollama responses, so it
never reads or changes the real patient registry and remains fast enough to run
after every code change.
"""

import json
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

_temp_dir = tempfile.TemporaryDirectory(prefix="medikiosk-regression-")
os.environ["MEDIKIOSK_DATABASE_PATH"] = os.path.join(_temp_dir.name, "test.db")
os.environ["STAFF_ACCOUNTS_JSON"] = json.dumps([
    {"username": "nurse1", "display_name": "Test Nurse", "role": "nurse", "pin": "1357"},
    {"username": "doctor1", "display_name": "Test Doctor", "role": "doctor", "pin": "2468"},
    {"username": "admin1", "display_name": "Test Admin", "role": "admin", "pin": "9876"},
])

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class MediKioskRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app, raise_server_exceptions=False)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        _temp_dir.cleanup()

    def setUp(self):
        main._staff_pin_attempts.clear()

    def start_session(self, language="en", mode="chat"):
        session_id = f"audit-{uuid.uuid4().hex}"
        response = self.client.post(
            "/sessions/start",
            json={"session_id": session_id, "language": language, "interaction_mode": mode, "consent": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["session_token"]
        return session_id, token, {"X-Session-Id": session_id, "X-Session-Token": token}

    def active_session(self, department="general"):
        session_id, token, headers = self.start_session()
        response = self.client.post(
            "/patients/register",
            headers=headers,
            json={"name": "Regression Patient", "phone_number": "9876543210"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        medi_id = response.json()["medi_id"]
        response = self.client.patch(
            f"/sessions/{session_id}/department",
            headers=headers,
            json={"department": department},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return session_id, token, headers, medi_id

    def staff_headers(self, username="doctor1", pin="2468"):
        response = self.client.post("/staff/login", json={"username": username, "pin": pin})
        self.assertEqual(response.status_code, 200, response.text)
        return {"X-Staff-Token": response.json()["token"]}

    def test_staff_endpoints_require_a_valid_token(self):
        self.assertEqual(self.client.get("/nurse-station/alerts").status_code, 401)
        self.assertEqual(self.client.get("/staff/sessions").status_code, 401)
        self.assertEqual(self.client.get("/abdm/push/unknown").status_code, 401)
        self.assertEqual(self.client.get("/nurse-station/alerts", headers=self.staff_headers()).status_code, 200)

        nurse = self.staff_headers("nurse1", "1357")
        self.assertEqual(self.client.get("/nurse-station/alerts", headers=nurse).status_code, 200)
        self.assertEqual(self.client.get("/staff/sessions", headers=nurse).status_code, 403)

    def test_staff_pin_is_rate_limited(self):
        for _ in range(5):
            self.assertEqual(self.client.post("/staff/login", json={"username": "doctor1", "pin": "0000"}).status_code, 401)
        self.assertEqual(self.client.post("/staff/login", json={"username": "doctor1", "pin": "2468"}).status_code, 429)

    def test_consent_first_session_accepts_preferences_afterward(self):
        session_id = f"consent-{uuid.uuid4().hex}"
        response = self.client.post("/sessions/start", json={"session_id": session_id, "consent": True})
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["session_token"]
        headers = {"X-Session-Token": token}
        record = self.client.get(f"/sessions/{session_id}", headers=headers).json()
        self.assertEqual(record["language"], "")
        self.assertEqual(record["interaction_mode"], "")
        response = self.client.patch(
            f"/sessions/{session_id}/preferences",
            headers=headers,
            json={"language": "hi", "interaction_mode": "speak"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        record = self.client.get(f"/sessions/{session_id}", headers=headers).json()
        self.assertEqual(record["language"], "hi")
        self.assertEqual(record["interaction_mode"], "speak")

    def test_audit_events_are_attributed_and_hash_chained(self):
        session_id, _, _, _ = self.active_session()
        doctor = self.staff_headers()
        self.assertEqual(self.client.get(f"/staff/sessions/{session_id}", headers=doctor).status_code, 200)
        self.assertEqual(self.client.get("/staff/audit", headers=doctor).status_code, 403)
        admin = self.staff_headers("admin1", "9876")
        response = self.client.get("/staff/audit?limit=50", headers=admin)
        self.assertEqual(response.status_code, 200, response.text)
        events = list(reversed(response.json()["events"]))
        self.assertTrue(any(event["action"] == "patient.consent.accepted" for event in events))
        self.assertTrue(any(event["action"] == "clinical.record.viewed" for event in events))
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current["previous_hash"], previous["event_hash"])

    def test_patient_flow_requires_consent_identity_and_department(self):
        self.assertEqual(
            self.client.post("/chat", json={"session_id": "missing", "message": "hello"}).status_code,
            401,
        )
        session_id, token, headers = self.start_session()
        response = self.client.post(
            "/chat",
            headers=headers,
            json={"session_id": session_id, "message": "hello"},
        )
        self.assertEqual(response.status_code, 409)

    def test_registration_validates_phone(self):
        _, _, headers = self.start_session()
        response = self.client.post(
            "/patients/register",
            headers=headers,
            json={"name": "Valid Name", "phone_number": "not-a-phone"},
        )
        self.assertIn(response.status_code, {400, 422})

    def test_medi_id_lookup_locks_after_three_missing_ids(self):
        _, _, _, known_id = self.active_session()
        _, _, headers = self.start_session()
        for _ in range(3):
            self.assertEqual(self.client.get("/patients/MK-NOTREAL", headers=headers).status_code, 404)
        self.assertEqual(self.client.get(f"/patients/{known_id}", headers=headers).status_code, 429)

    def test_model_data_is_strictly_schema_validated(self):
        session_id, _, headers, _ = self.active_session()
        malformed = json.dumps(
            {"reply": "Next", "interview_complete": False, "red_flag": False, "data": {"hpi": {"severity": {"bad": "type"}}}}
        )
        with patch.object(main, "_call_ollama", return_value=malformed):
            response = self.client.post("/chat", headers=headers, json={"session_id": session_id, "message": "hello"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["retry_required"])

        string_boolean = json.dumps(
            {"reply": "Next", "interview_complete": "false", "red_flag": "false", "data": {}}
        )
        with patch.object(main, "_call_ollama", return_value=string_boolean):
            response = self.client.post("/chat", headers=headers, json={"session_id": session_id, "message": "hello"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["retry_required"])

        wrong_data_shape = json.dumps(
            {"reply": "Next", "interview_complete": False, "red_flag": False, "data": "not-an-object"}
        )
        with patch.object(main, "_call_ollama", return_value=wrong_data_shape):
            response = self.client.post("/chat", headers=headers, json={"session_id": session_id, "message": "hello"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["retry_required"])

    def test_model_phrases_the_server_selected_question_naturally(self):
        session_id, _, headers, _ = self.active_session()
        natural_reply = "That sounds uncomfortable. Are you taking any medicines at the moment?"
        valid = json.dumps({
            "reply": natural_reply,
            "interview_complete": False,
            "red_flag": False,
            "red_flag_reason": "",
            "asked_field": "drug_allergy_history.current_medications",
            "data": {"chief_complaint": "headache"},
        })
        with patch.object(main, "_call_ollama", return_value=valid):
            response = self.client.post(
                "/chat", headers=headers, json={"session_id": session_id, "message": "I have a headache"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["reply"], natural_reply)
        self.assertEqual(response.json()["question_source"], "model")
        self.assertEqual(response.json()["coverage"]["next_field"], "drug_allergy_history.current_medications")
        self.assertFalse(response.json()["retry_required"])

    def test_focused_extractor_repairs_a_missing_target_field(self):
        with patch.object(main, "_call_ollama", return_value='{"answered": true, "value": "headache"}'):
            self.assertEqual(main._extract_target_value("chief_complaint", "I have a headache"), "headache")
        with patch.object(main, "_call_ollama", return_value='{"answered": true, "value": false}'):
            self.assertIs(main._extract_target_value("personal_history.smoking", "I do not smoke"), False)

    def test_emergency_alert_survives_ollama_outage_and_restart_store(self):
        session_id, _, headers, _ = self.active_session()
        with patch.object(main, "_call_ollama", side_effect=HTTPException(status_code=503, detail="offline")):
            response = self.client.post(
                "/chat",
                headers=headers,
                json={"session_id": session_id, "message": "I have chest pain and cannot breathe"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["red_flag"])
        self.assertEqual(response.json()["red_flag_source"], "keyword")
        alert_response = self.client.get("/nurse-station/alerts", headers=self.staff_headers())
        self.assertTrue(any(item["session_id"] == session_id for item in alert_response.json()["alerts"]))
        restored = self.client.get(f"/sessions/{session_id}", headers=headers)
        self.assertTrue(restored.json()["data"]["red_flag"])

    def test_interview_cap_is_enforced_by_server(self):
        session_id, _, headers, _ = self.active_session()
        valid = json.dumps(
            {"reply": "Recorded", "interview_complete": False, "red_flag": False, "data": {"chief_complaint": "headache"}}
        )
        with patch.object(main, "_call_ollama", return_value=valid):
            for turn in range(20):
                response = self.client.post(
                    "/chat", headers=headers, json={"session_id": session_id, "message": f"answer {turn}"}
                )
                self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["interview_complete"])
        restored = self.client.get(f"/sessions/{session_id}", headers=headers).json()
        self.assertTrue(restored["interview_complete"])

    def test_merge_supports_corrections_and_resolves_negative_lists(self):
        value = main._merge_accumulated_data(
            {"hpi": {"onset": "unknown", "severity": "2/10"}, "drug_allergy_history": {"allergies": ["none"]}},
            {"hpi": {"onset": "yesterday", "severity": "8/10"}, "drug_allergy_history": {"allergies": ["penicillin"]}},
        )
        self.assertEqual(value["hpi"], {"onset": "yesterday", "severity": "8/10"})
        self.assertEqual(value["drug_allergy_history"]["allergies"], ["penicillin"])

    def test_contradictions_require_clarification_before_overwrite(self):
        existing = main.ClinicalData(personal_history={"smoking": False}).model_dump()
        incoming = main.ClinicalData(personal_history={"smoking": True}).model_dump()
        conflict = main._find_clinical_conflict(existing, incoming, "Yes, I smoke")
        self.assertEqual(conflict[0], "personal_history.smoking")
        self.assertIsNone(
            main._find_clinical_conflict(
                existing, incoming, "Yes, I smoke", pending_field="personal_history.smoking"
            )
        )
        self.assertIsNone(main._find_clinical_conflict(existing, incoming, "Actually, I do smoke"))

    def test_ayush_priority_and_hindi_emergency_rules(self):
        data = main.ClinicalData(chief_complaint="stomach pain").model_dump()
        self.assertEqual(main._next_missing_field(data, "Kayachikitsa"), "ayush_assessment.vikriti")
        self.assertEqual(main._next_missing_field(data, "general"), "drug_allergy_history.current_medications")
        self.assertTrue(main.check_red_flags("मुझे सीने में दर्द और सांस लेने में तकलीफ है"))
        self.assertFalse(main.check_red_flags("My chest is fine and my breathing is normal."))
        self.assertTrue(main.check_red_flags("I am not sure why I have chest pain and breathlessness."))

    def test_export_rejects_missing_session_and_keeps_lab_metadata(self):
        staff = self.staff_headers()
        self.assertEqual(
            self.client.post(
                "/abdm/push",
                headers=staff,
                json={"session_id": "missing-session", "physician_reviewed": True},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/abdm/push", headers=staff, json={"session_id": "missing-session"}).status_code,
            422,
        )
        bundle = main._build_fhir_bundle(
            "patient", "Test", "MK-TEST01", "general", main.ClinicalData().model_dump(),
            [{
                "id": "doc", "doc_type": "lab_report", "date": "2026-09-05", "status": "confirmed",
                "extracted_entities": {"diagnoses": [], "medications": [], "lab_values": [{
                    "name": "Glucose", "value": "180", "unit": "mg/dL", "reference_range": "70-140", "flag": "high",
                }]},
            }],
        )
        observation = bundle["entry"][-1]["resource"]
        self.assertEqual(observation["valueQuantity"]["unit"], "mg/dL")
        self.assertEqual(observation["referenceRange"][0]["text"], "70-140")
        self.assertEqual(observation["effectiveDateTime"], "2026-09-05")

    def test_session_clear_removes_visit_but_retains_registry(self):
        session_id, token, headers, medi_id = self.active_session()
        response = self.client.delete(
            f"/sessions/{session_id}", headers={"X-Session-Token": token}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(f"/sessions/{session_id}", headers=headers).status_code, 401)
        with main._connect() as connection:
            self.assertIsNotNone(connection.execute("SELECT 1 FROM patients WHERE medi_id = ?", (medi_id,)).fetchone())


if __name__ == "__main__":
    unittest.main(verbosity=2)
