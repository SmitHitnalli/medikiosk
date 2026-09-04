import { useEffect, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";

const samplePatient = {
  chief_complaint: "Chest discomfort, worse on exertion",
  hpi: {
    site: "Central chest",
    onset: "3 days ago",
    character: "Dull ache",
    radiation: "None",
    associated_symptoms: ["Mild breathlessness on exertion"],
    timing: "Intermittent",
    exacerbating_relieving: "Worse climbing stairs, better with rest",
    severity: "4 out of 10",
  },
  drug_allergy_history: {
    current_medications: ["Amlodipine 5mg"],
    allergies: ["Sulfa drugs"],
  },
  ayush_assessment: {
    prakriti: "Vata-Pitta",
    agni: "Irregular",
    koshtha: "Medium",
    nidana: "Stress, irregular meals",
  },
};

const hpiFields = [
  ["Site", "site"],
  ["Onset", "onset"],
  ["Character", "character"],
  ["Radiation", "radiation"],
  ["Timing", "timing"],
  ["Exacerbating / relieving factors", "exacerbating_relieving"],
  ["Severity", "severity"],
];

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const ABDM_PUSH_ENDPOINT = "http://localhost:8080/abdm/push";
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
];
const AYUSH_FIELDS = [
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
  if (typeof value === "string") return value.trim().length > 0;
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
      if (typeof item === "object") return JSON.stringify(item);
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
  return `The patient reports ${textValue(patient.chief_complaint)}. The symptom is located at ${textValue(hpi.site)}, started ${textValue(hpi.onset)}, and is described as ${textValue(hpi.character)}. It ${textValue(hpi.radiation, "does not radiate")}, with ${textValue(hpi.associated_symptoms, "no associated symptoms")}. It is ${textValue(hpi.timing)}, ${textValue(hpi.exacerbating_relieving, "with no aggravating or relieving factors noted")}, and has a severity of ${textValue(hpi.severity)}.`;
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

function DoctorDashboard({ patientData, documents, transcript, redFlagEvents, department, sessionId, mediId, patientName, onBack, onClearData, onOpenNurseStation }) {
  const patient = patientData || samplePatient;
  const hpi = patient.hpi || {};
  const drugHistory = patient.drug_allergy_history || {};
  const ayush = patient.ayush_assessment || {};
  const hasAyushData = Object.values(ayush).some((value) => normaliseItems(value).length > 0);
  const isSample = !patientData;
  const trackedFields = (department || "").trim().toLowerCase() === "general" ? CORE_FIELDS : [...CORE_FIELDS, ...AYUSH_FIELDS];
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

  // Hydrate any prior mock ABDM push for this session, so re-opening the
  // dashboard (or the physician navigating away and back) still shows it was
  // already pushed instead of looking like a fresh, unpushed summary.
  useEffect(() => {
    if (isSample || !sessionId) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${ABDM_PUSH_ENDPOINT}/${sessionId}`);
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
  }, [sessionId, isSample]);

  async function handlePush() {
    if (!sessionId) return;
    setPushState("pushing");
    setPushError("");
    try {
      const response = await fetch(ABDM_PUSH_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          medi_id: mediId || null,
          patient_name: patientName || null,
          department: department || null,
          documents: documents || [],
        }),
      });
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
    setIsSpeaking(true);
    setSpeechError("");
    try {
      const response = await fetch(SPEAK_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: buildSummary(patient) }),
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || "The summary could not be spoken.");
      }
      await playAudioBlob(await response.blob());
      setIsSpeaking(false);
    } catch (error) {
      setIsSpeaking(false);
      setSpeechError(error.message || "Unable to play the summary.");
    }
  }

  useEffect(() => () => stopAllAudio(), []);

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">MediKiosk · Physician view</p>
          <h1>Patient summary</h1>
          <p className="subtitle">Review the structured history before the consultation.</p>
        </div>
        <div className="dashboard-actions">
          <ClearDataButton onClearData={onClearData} />
          <button className="nurse-station-link" type="button" onClick={onOpenNurseStation}>Nurse Station →</button>
          <button className="back-link" type="button" onClick={onBack}>← Back to interview</button>
        </div>
      </header>

      <section className="chief-complaint-card">
        <div className="section-kicker">Chief complaint</div>
        <div className="chief-complaint-value"><SafeValue value={patient.chief_complaint} /></div>
        <div className="chief-complaint-actions">
          <span className="sample-badge">{isSample ? "Sample patient · Draft" : "Live conversation · Ready for review"}</span>
          <button className="play-summary-button" type="button" onClick={playSummary} disabled={isSpeaking}>
            {isSpeaking ? "Playing summary..." : "▶ Play summary"}
          </button>
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

        {hasAyushData && (
          <section className="dashboard-card ayush-card">
            <div className="card-heading"><div><p className="section-kicker">AYUSH assessment</p><h2>Constitution & patterns</h2></div><span className="ayush-badge">AYUSH</span></div>
            <dl className="detail-grid ayush-grid">
              <div className="detail-item"><dt>Prakriti</dt><dd><SafeValue value={ayush.prakriti} /></dd></div>
              <div className="detail-item"><dt>Agni</dt><dd><SafeValue value={ayush.agni} /></dd></div>
              <div className="detail-item"><dt>Koshtha</dt><dd><SafeValue value={ayush.koshtha} /></dd></div>
              <div className="detail-item detail-item-wide"><dt>Nidana</dt><dd><SafeValue value={ayush.nidana} /></dd></div>
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
                      <div><dt>Lab values</dt><dd><ListValue items={(doc.extracted_entities?.lab_values || []).map((value) => (value && typeof value === "object" ? `${value.name || "Lab value"}: ${[value.value, value.unit].filter(Boolean).join(" ") || "not provided"}${value.flag && value.flag !== "normal" ? ` · ${value.flag}` : ""}` : value))} /></dd></div>
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
          {isSample ? (
            <p className="trust-metric-note">Open a real patient's interview to push their history - this is disabled for the sample patient.</p>
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
