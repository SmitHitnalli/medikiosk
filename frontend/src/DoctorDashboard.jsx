import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";
import { apiFetch, staffHeaders } from "./api";

const hpiFields = [
  ["Site", "site"],
  ["Onset", "onset"],
  ["Character", "character"],
  ["Radiation", "radiation"],
  ["Timing", "timing"],
  ["Exacerbating / relieving factors", "exacerbating_relieving"],
  ["Severity", "severity"],
];

const DOC_TYPE_LABELS = {
  prescription: "Prescription",
  lab_report: "Lab report",
  discharge_summary: "Discharge summary",
};

// Mirrors backend FIELD_PROMPTS / _next_field_instruction so the trust ledger's
// completeness meter reflects exactly what the interview engine tracks.
const CORE_FIELDS = [
  ["chief_complaint", "Chief complaint"],
  ["hpi.site", "Symptom site"],
  ["hpi.onset", "Onset"],
  ["hpi.character", "Character"],
  ["hpi.associated_symptoms", "Associated symptoms"],
  ["hpi.timing", "Timing"],
  ["hpi.exacerbating_relieving", "Exacerbating / relieving factors"],
  ["hpi.severity", "Severity"],
  ["past_medical_history", "Past medical history"],
  ["past_surgical_history", "Past surgical history"],
  ["drug_allergy_history.current_medications", "Current medications"],
  ["drug_allergy_history.allergies", "Allergies"],
  ["family_history", "Family history"],
  ["personal_history.diet", "Diet"],
  ["personal_history.smoking", "Tobacco use"],
  ["personal_history.alcohol", "Alcohol use"],
  ["personal_history.occupation", "Occupation"],
  ["review_of_systems", "Other symptoms review"],
];
const AYUSH_FIELDS = [
  ["ayush_assessment.prakriti", "Prakriti (constitution)"],
  ["ayush_assessment.vikriti", "Vikriti (current imbalance)"],
  ["ayush_assessment.agni", "Agni (digestion pattern)"],
  ["ayush_assessment.koshtha", "Koshtha (bowel pattern)"],
  ["ayush_assessment.nidana", "Nidana (causative factors)"],
];
const RED_FLAG_SOURCE_LABELS = {
  keyword: "Deterministic rule",
  ai: "AI model",
  keyword_and_ai: "Deterministic rule + AI model",
};

function getNestedValue(data, path) {
  return path.split(".").reduce((current, part) => (current && typeof current === "object" ? current[part] : undefined), data);
}

function isFieldFilled(value) {
  if (value == null) return false;
  if (typeof value === "string") return !["", "unknown", "not known", "not provided", "not recorded", "n/a"].includes(value.trim().toLowerCase());
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function formatEventTime(isoString) {
  if (!isoString) return "";
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function normaliseItems(value) {
  const values = Array.isArray(value) ? value : value == null ? [] : [value];
  return values
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (typeof item === "object") return Object.keys(item).length ? JSON.stringify(item) : "";
      return String(item);
    })
    .filter(Boolean);
}

function textValue(value, fallback = "not provided") {
  const values = normaliseItems(value);
  return values.length ? values.join(", ") : fallback;
}

function buildSummary(patient) {
  const hpi = patient.hpi || {};
  return `The patient reports ${textValue(patient.chief_complaint)}. The symptom site is ${textValue(hpi.site, "not recorded")}; onset is ${textValue(hpi.onset, "not recorded")}; character is ${textValue(hpi.character, "not recorded")}; radiation is ${textValue(hpi.radiation, "not recorded")}; associated symptoms are ${textValue(hpi.associated_symptoms, "not recorded")}; timing is ${textValue(hpi.timing, "not recorded")}; aggravating or relieving factors are ${textValue(hpi.exacerbating_relieving, "not recorded")}; and severity is ${textValue(hpi.severity, "not recorded")}.`;
}

function SafeValue({ value }) {
  const values = normaliseItems(value);
  if (!values.length) return <span className="muted-value">Not provided</span>;
  if (values.length === 1) return <span>{values[0]}</span>;
  return (
    <ul className="dashboard-list">
      {values.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
    </ul>
  );
}

function ListValue({ items }) {
  return <SafeValue value={items} />;
}

function DoctorDashboard({ patientData, documents, transcript, redFlagEvents, department, sessionId, mediId, patientName, language, staffToken, staffUser, onSessionExpired, onLoadSession, onBack, onClearData, onOpenNurseStation, onLogout }) {
  const patient = patientData || {};
  const hpi = patient.hpi || {};
  const drugHistory = patient.drug_allergy_history || {};
  const ayush = patient.ayush_assessment || {};
  const hasAyushData = Object.values(ayush).some((value) => normaliseItems(value).length > 0);
  const hasPatientData = Boolean(patientData);
  const normalizedDepartment = (department || "general").trim().toLowerCase();
  const trackedFields = normalizedDepartment === "general"
    ? CORE_FIELDS
    : [...CORE_FIELDS, ...AYUSH_FIELDS, ...(normalizedDepartment === "panchakarma" ? [["ayush_assessment.panchakarma_history", "Panchakarma history"]] : [])];
  const filledFields = trackedFields.filter(([path]) => isFieldFilled(getNestedValue(patient, path)));
  const missingFields = trackedFields.filter(([path]) => !isFieldFilled(getNestedValue(patient, path)));
  const completenessPct = trackedFields.length ? Math.round((filledFields.length / trackedFields.length) * 100) : 0;
  const docStatusCounts = (documents || []).reduce(
    (counts, doc) => {
      const key = doc.status === "confident" ? "confident" : doc.status === "confirmed" ? "confirmed" : "illegible";
      counts[key] += 1;
      return counts;
    },
    { confident: 0, confirmed: 0, illegible: 0 }
  );
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechError, setSpeechError] = useState("");
  const [pushState, setPushState] = useState("idle"); // idle | pushing | pushed | error
  const [pushRecord, setPushRecord] = useState(null);
  const [pushError, setPushError] = useState("");
  const [showBundle, setShowBundle] = useState(false);
  const [recentSessions, setRecentSessions] = useState([]);
  const speechRequestRef = useRef(null);

  // Hydrate any prior mock ABDM push for this session, so re-opening the
  // dashboard (or the physician navigating away and back) still shows it was
  // already pushed instead of looking like a fresh, unpushed summary.
  useEffect(() => {
    if (!sessionId || !staffToken) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await apiFetch(`/abdm/push/${encodeURIComponent(sessionId)}`, { headers: staffHeaders(staffToken) }, 10000);
        if (response.status === 401) return onSessionExpired();
        if (!response.ok) return;
        const result = await response.json();
        if (!cancelled && result.pushed) {
          setPushRecord(result);
          setPushState("pushed");
        }
      } catch {
        // Silent - this is just a convenience hydration; the push button still works either way.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, staffToken, onSessionExpired]);

  useEffect(() => {
    if (!staffToken) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await apiFetch("/staff/sessions", { headers: staffHeaders(staffToken) }, 10000);
        if (response.status === 401) return onSessionExpired();
        if (!response.ok) return;
        const result = await response.json();
        if (!cancelled) setRecentSessions(result.sessions || []);
      } catch {
        // The active record remains usable when the recent-session list cannot load.
      }
    })();
    return () => { cancelled = true; };
  }, [staffToken, onSessionExpired]);

  async function handlePush() {
    if (!sessionId) return;
    setPushState("pushing");
    setPushError("");
    try {
      const response = await apiFetch("/abdm/push", {
        method: "POST",
        headers: staffHeaders(staffToken, true),
        body: JSON.stringify({ session_id: sessionId, physician_reviewed: true }),
      }, 15000);
      if (response.status === 401) return onSessionExpired();
      if (!response.ok) throw new Error("Could not push to ABDM/HIS.");
      const result = await response.json();
      setPushRecord(result);
      setPushState("pushed");
    } catch (error) {
      setPushState("error");
      setPushError(error.message || "Unable to push to ABDM/HIS.");
    }
  }

  async function playSummary() {
    const controller = new AbortController();
    speechRequestRef.current?.abort();
    speechRequestRef.current = controller;
    setIsSpeaking(true);
    setSpeechError("");
    try {
      const response = await apiFetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: buildSummary(patient), language: language || "en" }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || "The summary could not be spoken.");
      }
      await playAudioBlob(await response.blob());
      if (!controller.signal.aborted) setIsSpeaking(false);
    } catch (error) {
      if (!controller.signal.aborted) {
        setIsSpeaking(false);
        setSpeechError(error.message || "Unable to play the summary.");
      }
    } finally {
      if (speechRequestRef.current === controller) speechRequestRef.current = null;
    }
  }

  useEffect(() => () => {
    speechRequestRef.current?.abort();
    stopAllAudio();
  }, []);

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">MediKiosk · Physician view</p>
          <h1>Patient summary</h1>
          <p className="subtitle">Review the structured history before the consultation.</p>
          {staffUser && <p className="staff-pin-copy">Signed in as {staffUser.display_name} · {staffUser.role}</p>}
        </div>
        <div className="dashboard-actions">
          {onClearData && <ClearDataButton language={language} onClearData={onClearData} />}
          <button className="nurse-station-link" type="button" onClick={onOpenNurseStation}>Nurse Station →</button>
          <button className="back-link" type="button" onClick={onLogout}>Lock staff view</button>
          <button className="back-link" type="button" onClick={onBack}>← Back to interview</button>
        </div>
      </header>

      {recentSessions.length > 0 && (
        <section className="dashboard-card recent-sessions-card">
          <div className="card-heading"><div><p className="section-kicker">Patient records</p><h2>Recent clinical sessions</h2></div></div>
          <div className="recent-session-list">
            {recentSessions.map((item) => (
              <button
                type="button"
                className={`recent-session-button ${item.session_id === sessionId ? "active" : ""}`}
                key={item.session_id}
                onClick={() => onLoadSession(item.session_id)}
              >
                <strong>{item.patient_name || "Unknown patient"}</strong>
                <span>{item.patient_medi_id} · {item.department || "Department pending"}</span>
                <span>{item.chief_complaint || "History not started"}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="chief-complaint-card">
        <div className="patient-identity-line">
          <strong>{patientName || "No patient selected"}</strong>
          <span>{mediId || "No Medi ID"} · {department || "Department pending"}</span>
        </div>
        <div className="section-kicker">Chief complaint</div>
        <div className="chief-complaint-value"><SafeValue value={patient.chief_complaint} /></div>
        <div className="chief-complaint-actions">
          <span className="sample-badge">{hasPatientData ? (patient.interview_complete ? "Interview complete" : "Live draft") : "No clinical history yet"}</span>
          <button className="play-summary-button" type="button" onClick={playSummary} disabled={isSpeaking || !hasPatientData}>
            {isSpeaking ? "Playing summary..." : "▶ Play summary"}
          </button>
          <button className="secondary-start-button" type="button" onClick={() => window.print()} disabled={!hasPatientData}>Print summary</button>
        </div>
        {speechError && <p className="speech-error" role="alert">{speechError}</p>}
      </section>

      <div className="dashboard-grid">
        <section className="dashboard-card hpi-card">
          <div className="card-heading">
            <div><p className="section-kicker">History of present illness</p><h2>Symptom details</h2></div>
            <span className="framework-badge">SOCRATES</span>
          </div>
          <dl className="detail-grid">
            {hpiFields.map(([label, key]) => (
              <div className="detail-item" key={key}>
                <dt>{label}</dt>
                <dd><SafeValue value={hpi[key]} /></dd>
              </div>
            ))}
            <div className="detail-item detail-item-wide">
              <dt>Associated symptoms</dt>
              <dd><ListValue items={hpi.associated_symptoms} /></dd>
            </div>
          </dl>
        </section>

        <section className="dashboard-card">
          <div className="card-heading"><div><p className="section-kicker">Medication safety</p><h2>Drug & allergy history</h2></div><span className="card-icon">✚</span></div>
          <div className="stacked-detail">
            <div><dt>Current medications</dt><dd><ListValue items={drugHistory.current_medications} /></dd></div>
            <div><dt>Allergies</dt><dd><ListValue items={drugHistory.allergies} /></dd></div>
          </div>
        </section>

        <section className="dashboard-card history-card">
          <div className="card-heading"><div><p className="section-kicker">Background history</p><h2>Medical, family & personal history</h2></div></div>
          <dl className="stacked-detail">
            <div><dt>Past medical history</dt><dd><ListValue items={patient.past_medical_history} /></dd></div>
            <div><dt>Past surgical history</dt><dd><ListValue items={patient.past_surgical_history} /></dd></div>
            <div><dt>Family history</dt><dd><ListValue items={patient.family_history} /></dd></div>
            <div><dt>Diet</dt><dd><SafeValue value={patient.personal_history?.diet} /></dd></div>
            <div><dt>Tobacco / smoking</dt><dd><SafeValue value={patient.personal_history?.smoking == null ? null : patient.personal_history.smoking ? "Yes" : "No"} /></dd></div>
            <div><dt>Alcohol</dt><dd><SafeValue value={patient.personal_history?.alcohol == null ? null : patient.personal_history.alcohol ? "Yes" : "No"} /></dd></div>
            <div><dt>Occupation</dt><dd><SafeValue value={patient.personal_history?.occupation} /></dd></div>
            <div><dt>Other symptoms review</dt><dd><SafeValue value={patient.review_of_systems} /></dd></div>
          </dl>
        </section>

        {hasAyushData && (
          <section className="dashboard-card ayush-card">
            <div className="card-heading"><div><p className="section-kicker">AYUSH assessment</p><h2>Constitution & patterns</h2></div><span className="ayush-badge">AYUSH</span></div>
            <dl className="detail-grid ayush-grid">
              <div className="detail-item"><dt>Prakriti</dt><dd><SafeValue value={ayush.prakriti} /></dd></div>
              <div className="detail-item"><dt>Vikriti</dt><dd><SafeValue value={ayush.vikriti} /></dd></div>
              <div className="detail-item"><dt>Agni</dt><dd><SafeValue value={ayush.agni} /></dd></div>
              <div className="detail-item"><dt>Koshtha</dt><dd><SafeValue value={ayush.koshtha} /></dd></div>
              <div className="detail-item detail-item-wide"><dt>Nidana</dt><dd><SafeValue value={ayush.nidana} /></dd></div>
              <div className="detail-item detail-item-wide"><dt>Panchakarma history</dt><dd><SafeValue value={ayush.panchakarma_history} /></dd></div>
            </dl>
          </section>
        )}

        {documents && documents.length > 0 && (
          <section className="dashboard-card documents-card">
            <div className="card-heading"><div><p className="section-kicker">Digitized documents</p><h2>Scanned by patient</h2></div><span className="card-icon">▣</span></div>
            <ul className="dashboard-doc-list">
              {documents.map((doc) => (
                <li className={`dashboard-doc-item ${doc.status === "illegible" ? "illegible" : ""}`} key={doc.id}>
                  <div className="dashboard-doc-heading">
                    <span className="dashboard-doc-type">
                      {doc.status === "illegible" ? "Unreadable document" : DOC_TYPE_LABELS[doc.doc_type] || "Document"}
                    </span>
                    {doc.status === "confirmed" && <span className="dashboard-doc-flag">Patient-confirmed type</span>}
                  </div>
                  {doc.status === "illegible" ? (
                    <p className="dashboard-doc-note">Could not be digitized - ask the patient for the physical copy.</p>
                  ) : (
                    <dl className="stacked-detail dashboard-doc-detail">
                      <div><dt>Diagnoses</dt><dd><ListValue items={doc.extracted_entities?.diagnoses} /></dd></div>
                      <div><dt>Medications</dt><dd><ListValue items={doc.extracted_entities?.medications} /></dd></div>
                      <div><dt>Lab values</dt><dd><ListValue items={normaliseItems(doc.extracted_entities?.lab_values).map((value) => {
                        const item = typeof value === "string" && value.startsWith("{") ? (() => { try { return JSON.parse(value); } catch { return value; } })() : value;
                        return item && typeof item === "object" ? `${item.name || "Lab value"}: ${[item.value, item.unit].filter(Boolean).join(" ") || "not provided"}${item.reference_range ? ` · range ${item.reference_range}` : ""}${item.flag && item.flag !== "normal" ? ` · ${item.flag}` : ""}` : item;
                      })} /></dd></div>
                    </dl>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="dashboard-card trust-ledger-card">
          <div className="card-heading"><div><p className="section-kicker">Trust ledger</p><h2>How this summary was built</h2></div><span className="card-icon">🛈</span></div>

          <div className="trust-metric">
            <div className="trust-metric-heading">
              <span>History completeness</span>
              <span>{filledFields.length} of {trackedFields.length} fields</span>
            </div>
            <div className="trust-metric-bar"><div className="trust-metric-bar-fill" style={{ width: `${completenessPct}%` }} /></div>
            {missingFields.length > 0 && (
              <p className="trust-metric-note">Not yet captured: {missingFields.map(([, label]) => label).join(", ")}</p>
            )}
          </div>

          <div className="trust-subsection">
            <p className="trust-subsection-heading">Red-flag audit</p>
            {redFlagEvents && redFlagEvents.length > 0 ? (
              <ul className="trust-flag-list">
                {redFlagEvents.map((event, index) => (
                  <li className="trust-flag-item" key={`${event.timestamp}-${index}`}>
                    <span className="trust-flag-reason">{event.reason}</span>
                    <span className="trust-flag-meta">
                      <span className="trust-flag-source">{RED_FLAG_SOURCE_LABELS[event.source] || "AI model"}</span>
                      {formatEventTime(event.timestamp) && <span className="trust-flag-time">{formatEventTime(event.timestamp)}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="trust-metric-note">No red flags raised during this interview.</p>
            )}
          </div>

          {documents && documents.length > 0 && (
            <div className="trust-subsection">
              <p className="trust-subsection-heading">Document verification</p>
              <p className="trust-metric-note">
                {docStatusCounts.confident > 0 && `${docStatusCounts.confident} AI-identified`}
                {docStatusCounts.confident > 0 && (docStatusCounts.confirmed > 0 || docStatusCounts.illegible > 0) && " · "}
                {docStatusCounts.confirmed > 0 && `${docStatusCounts.confirmed} patient-corrected`}
                {docStatusCounts.confirmed > 0 && docStatusCounts.illegible > 0 && " · "}
                {docStatusCounts.illegible > 0 && `${docStatusCounts.illegible} unreadable`}
              </p>
            </div>
          )}
        </section>

        <section className="dashboard-card abdm-push-card">
          <div className="card-heading"><div><p className="section-kicker">ABDM / Hospital HIS</p><h2>Push structured history</h2></div><span className="card-icon">⇪</span></div>
          {!hasPatientData || !sessionId ? (
            <p className="trust-metric-note">Select a patient session before reviewing and pushing its history.</p>
          ) : (
            <>
              <p className="abdm-push-copy">
                Sends this structured history as a FHIR Bundle, linked to the patient's Medi ID, to the hospital
                HIS and the ABHA record. <strong>This is a mock integration</strong> - no real ABDM sandbox is
                reachable from this environment, so the push is simulated and recorded here with the exact
                Bundle that would be sent to a real ABDM endpoint.
              </p>
              <div className="abdm-push-actions">
                <button className="play-summary-button" type="button" onClick={handlePush} disabled={pushState === "pushing"}>
                  {pushState === "pushing" ? "Pushing..." : pushRecord ? "Push again" : "Push to ABDM/HIS"}
                </button>
                {pushRecord && (
                  <button className="secondary-start-button" type="button" onClick={() => setShowBundle((current) => !current)}>
                    {showBundle ? "Hide FHIR bundle" : "View FHIR bundle"}
                  </button>
                )}
              </div>
              {pushRecord && (
                <p className="abdm-push-status">
                  Pushed (mock) at {formatEventTime(pushRecord.pushed_at)} · Reference {pushRecord.abdm_reference}
                </p>
              )}
              {pushError && <p className="speech-error" role="alert">{pushError}</p>}
              {showBundle && pushRecord && <pre className="abdm-bundle-view">{JSON.stringify(pushRecord.bundle, null, 2)}</pre>}
            </>
          )}
        </section>

        <section className="dashboard-card transcript-card">
          <div className="card-heading"><div><p className="section-kicker">Full record</p><h2>Conversation transcript</h2></div><span className="card-icon">≡</span></div>
          {transcript && transcript.length > 0 ? (
            <div className="dashboard-transcript-list">
              {transcript.map((entry, index) => (
                <div className={`dashboard-transcript-row ${entry.role}`} key={`${entry.role}-${index}`}>
                  <span className="dashboard-transcript-author">{entry.role === "user" ? "Patient" : "MediKiosk"}</span>
                  <p className="dashboard-transcript-bubble">{entry.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted-value">No conversation recorded yet.</p>
          )}
        </section>
      </div>
      <p className="dashboard-footnote">This summary is collected history, not a diagnosis. Confirm details with the patient.</p>
    </main>
  );
}

export default DoctorDashboard;
