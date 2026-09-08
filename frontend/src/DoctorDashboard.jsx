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
  ["hpi.radiation", "Radiation"],
  ["hpi.associated_symptoms", "Associated symptoms"],
  ["hpi.timing", "Timing"],
  ["hpi.exacerbating_relieving", "Exacerbating / relieving factors"],
  ["hpi.severity", "Severity"],
  ["past_medical_history", "Past medical history"],
  ["past_surgical_history", "Past surgical history"],
  ["drug_allergy_history.current_medications", "Current medications"],
  ["drug_allergy_history.allergies", "Allergies"],
  ["family_history", "Family history"],
  ["personal_history.diet", "Ahara-Vihara: Diet"],
  ["personal_history.smoking", "Ahara-Vihara: Tobacco use"],
  ["personal_history.alcohol", "Ahara-Vihara: Alcohol use"],
  ["personal_history.occupation", "Ahara-Vihara: Occupation"],
  ["review_of_systems", "Other symptoms review"],
];
const AYUSH_FIELDS = [
  ["ayush_assessment.vikriti", "Vikriti (current imbalance)"],
  ["ayush_assessment.agni", "Agni (digestion pattern)"],
  ["ayush_assessment.nidana", "Nidana (causative factors)"],
  ["ayush_assessment.dashavidha.patient_reported.satmya", "Satmya"],
  ["ayush_assessment.dashavidha.patient_reported.sattva", "Sattva"],
  ["ayush_assessment.dashavidha.patient_reported.ahara_shakti", "Ahara Shakti"],
  ["ayush_assessment.dashavidha.patient_reported.vyayama_shakti", "Vyayama Shakti"],
  ["ayush_assessment.dashavidha.patient_reported.vaya", "Vaya"],
];
const TRIVIDHA_PARIKSHA_FIELDS = [["darshana", "Darshana"], ["sparshana", "Sparshana"], ["prashna", "Prashna"]];
const ASHTAVIDHA_PARIKSHA_FIELDS = [
  ["nadi", "Nadi"], ["mutra", "Mutra"], ["mala", "Mala"], ["jihva", "Jihva"],
  ["shabda", "Shabda"], ["sparsha", "Sparsha"], ["drik", "Drik"], ["akriti", "Akriti"],
];
const DASHAVIDHA_EXAM_FIELDS = [
  ["sara", "Sara"], ["samhanana", "Samhanana"], ["pramana", "Pramana"],
  ...TRIVIDHA_PARIKSHA_FIELDS, ...ASHTAVIDHA_PARIKSHA_FIELDS,
];
const AYURVEDA_OPTIONAL_CORE = new Set([
  "past_surgical_history", "family_history", "personal_history.diet", "personal_history.smoking",
  "personal_history.alcohol", "personal_history.occupation", "review_of_systems",
]);
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
  const dashavidha = ayush.dashavidha || {};
  const patientDashavidha = dashavidha.patient_reported || {};
  const practitionerDashavidha = dashavidha.practitioner_exam || {};
  const hasPatientData = Boolean(patientData);
  const normalizedDepartment = (department || "general").trim().toLowerCase();
  const hasAyushData = normalizedDepartment !== "general";
  const trackedFields = normalizedDepartment === "general"
    ? CORE_FIELDS
    : [...CORE_FIELDS.filter(([path]) => !AYURVEDA_OPTIONAL_CORE.has(path)), ...AYUSH_FIELDS];
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
  const [ayushConfirmation, setAyushConfirmation] = useState(() => ({
    prakriti: "", notes: "", ...Object.fromEntries(DASHAVIDHA_EXAM_FIELDS.map(([key]) => [key, ""])),
  }));
  const [ayushSaveState, setAyushSaveState] = useState("idle");
  const [ayushSaveMessage, setAyushSaveMessage] = useState("");
  const [editValues, setEditValues] = useState({ chief_complaint: "", medications: "", allergies: "", past_medical_history: "", past_surgical_history: "" });
  const [editReason, setEditReason] = useState("");
  const [workflowState, setWorkflowState] = useState({ saving: false, signing: false, message: "", error: "" });
  const [signoff, setSignoff] = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [attested, setAttested] = useState(false);
  const [abhaLink, setAbhaLink] = useState({ number: "", address: "", method: "qr", reference: "" });
  const [abhaMessage, setAbhaMessage] = useState("");
  const [abdmStatus, setAbdmStatus] = useState(null);
  const [activeSection, setActiveSection] = useState("overview");
  const [showSessions, setShowSessions] = useState(false);
  const speechRequestRef = useRef(null);

  useEffect(() => {
    setActiveSection("overview");
    setShowSessions(false);
  }, [sessionId]);

  useEffect(() => {
    setAyushConfirmation({
      prakriti: ayush.prakriti || "",
      notes: practitionerDashavidha.notes || "",
      ...Object.fromEntries(DASHAVIDHA_EXAM_FIELDS.map(([key]) => [key, practitionerDashavidha[key] || ""])),
    });
    setAyushSaveState("idle");
    setAyushSaveMessage("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, ayush.prakriti, practitionerDashavidha.notes, ...DASHAVIDHA_EXAM_FIELDS.map(([key]) => practitionerDashavidha[key])]);

  useEffect(() => {
    setEditValues({
      chief_complaint: patient.chief_complaint || "",
      medications: (drugHistory.current_medications || []).join(", "),
      allergies: (drugHistory.allergies || []).join(", "),
      past_medical_history: (patient.past_medical_history || []).join(", "),
      past_surgical_history: (patient.past_surgical_history || []).join(", "),
    });
  }, [sessionId, patient.chief_complaint, drugHistory.current_medications, drugHistory.allergies, patient.past_medical_history, patient.past_surgical_history]);

  useEffect(() => {
    if (!sessionId || !staffToken) return;
    (async () => {
      try {
        const [sessionResponse, revisionsResponse] = await Promise.all([
          apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}`, { headers: staffHeaders(staffToken) }, 10000),
          apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/revisions`, { headers: staffHeaders(staffToken) }, 10000),
        ]);
        if (sessionResponse.status === 401 || revisionsResponse.status === 401) return onSessionExpired();
        if (sessionResponse.ok) setSignoff((await sessionResponse.json()).signoff || null);
        if (revisionsResponse.ok) setRevisions((await revisionsResponse.json()).revisions || []);
      } catch {
        setWorkflowState((current) => ({ ...current, error: "Could not load review history." }));
      }
    })();
  }, [sessionId, staffToken, onSessionExpired]);

  useEffect(() => {
    if (!staffToken) return;
    apiFetch("/staff/abdm/status", { headers: staffHeaders(staffToken) }, 10000)
      .then(async (response) => { if (response.ok) setAbdmStatus(await response.json()); })
      .catch(() => {});
  }, [staffToken]);

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
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Could not push to ABDM/HIS.");
      const result = body;
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

  const splitItems = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

  async function saveStructuredEdits(event) {
    event.preventDefault();
    setWorkflowState({ saving: true, signing: false, message: "", error: "" });
    try {
      const response = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/record`, {
        method: "PATCH", headers: staffHeaders(staffToken, true),
        body: JSON.stringify({
          reason: editReason,
          changes: {
            chief_complaint: editValues.chief_complaint,
            "drug_allergy_history.current_medications": splitItems(editValues.medications),
            "drug_allergy_history.allergies": splitItems(editValues.allergies),
            past_medical_history: splitItems(editValues.past_medical_history),
            past_surgical_history: splitItems(editValues.past_surgical_history),
          },
        }),
      }, 10000);
      if (response.status === 401) return onSessionExpired();
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not save the clinical edits.");
      setSignoff(null); setEditReason(""); setPushRecord(null); setPushState("idle");
      setWorkflowState({ saving: false, signing: false, message: `Saved version ${result.revision.version}. Previous sign-off was cleared.`, error: "" });
      await onLoadSession(sessionId);
      const history = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/revisions`, { headers: staffHeaders(staffToken) });
      if (history.ok) setRevisions((await history.json()).revisions || []);
    } catch (error) {
      setWorkflowState({ saving: false, signing: false, message: "", error: error.message || "Could not save the clinical edits." });
    }
  }

  async function signOffRecord() {
    setWorkflowState({ saving: false, signing: true, message: "", error: "" });
    try {
      const response = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/signoff`, {
        method: "POST", headers: staffHeaders(staffToken, true), body: JSON.stringify({ attestation: true }),
      }, 10000);
      if (response.status === 401) return onSessionExpired();
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not sign off this record.");
      setSignoff(result.signoff); setAttested(false);
      setWorkflowState({ saving: false, signing: false, message: `Signed as version ${result.revision.version}.`, error: "" });
      await onLoadSession(sessionId);
      const history = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/revisions`, { headers: staffHeaders(staffToken) });
      if (history.ok) setRevisions((await history.json()).revisions || []);
    } catch (error) {
      setWorkflowState({ saving: false, signing: false, message: "", error: error.message || "Could not sign off this record." });
    }
  }

  async function downloadPdf(audience) {
    setWorkflowState((current) => ({ ...current, error: "" }));
    try {
      const response = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/pdf?audience=${audience}`, { headers: staffHeaders(staffToken) }, 15000);
      if (response.status === 401) return onSessionExpired();
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail || "Could not create the PDF."); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `medikiosk-${sessionId}-${audience}.pdf`; link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setWorkflowState((current) => ({ ...current, error: error.message || "Could not create the PDF." }));
    }
  }

  async function saveAbhaLink(event) {
    event.preventDefault(); setAbhaMessage("");
    try {
      const response = await apiFetch(`/staff/patients/${encodeURIComponent(mediId)}/abha`, {
        method: "PATCH", headers: staffHeaders(staffToken, true), body: JSON.stringify({
          abha_number: abhaLink.number.replace(/\D/g, ""), abha_address: abhaLink.address.trim(),
          verification_method: abhaLink.method, verification_reference: abhaLink.reference.trim(),
        }),
      }, 10000);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not link this ABHA identity.");
      setAbhaMessage(`Verified ${result.abha_number}${result.abha_address ? ` · ${result.abha_address}` : ""}`);
      setAbhaLink((current) => ({ ...current, number: "", reference: "" }));
    } catch (error) { setAbhaMessage(error.message || "Could not link this ABHA identity."); }
  }

  async function saveAyushConfirmation(event) {
    event.preventDefault();
    if (!sessionId || !ayushConfirmation.prakriti.trim()) return;
    setAyushSaveState("saving");
    setAyushSaveMessage("");
    try {
      const response = await apiFetch(`/staff/sessions/${encodeURIComponent(sessionId)}/ayush-confirmation`, {
        method: "PATCH",
        headers: staffHeaders(staffToken, true),
        body: JSON.stringify(ayushConfirmation),
      }, 10000);
      if (response.status === 401) return onSessionExpired();
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not save the Ayurveda assessment.");
      setAyushSaveState("saved");
      setAyushSaveMessage(`Saved as ${result.dashavidha_status.replaceAll("_", " ")} by ${result.confirmed_by}.`);
      await onLoadSession(sessionId);
    } catch (error) {
      setAyushSaveState("error");
      setAyushSaveMessage(error.message || "Could not save the Ayurveda assessment.");
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

      <nav className="dashboard-section-nav" aria-label="Patient summary sections">
        {[
          ["overview", "Overview"],
          ["review", "Review & sign"],
          ...(hasAyushData ? [["ayurveda", "Ayurveda"]] : []),
          ...((documents || []).length ? [["documents", `Documents (${documents.length})`]] : []),
          ["integration", "ABHA / FHIR"],
          ["transcript", "Transcript"],
        ].map(([value, label]) => (
          <button className={activeSection === value ? "active" : ""} type="button" key={value} onClick={() => setActiveSection(value)}>{label}</button>
        ))}
        {recentSessions.length > 0 && <button className={showSessions ? "active" : ""} type="button" onClick={() => setShowSessions((current) => !current)}>Patients ({recentSessions.length})</button>}
      </nav>

      {recentSessions.length > 0 && showSessions && (
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

      {activeSection === "review" && hasPatientData && sessionId && (
        <section className="dashboard-card clinical-review-card">
          <div className="card-heading"><div><p className="section-kicker">Clinician review</p><h2>Edit, sign and issue the record</h2></div><span className="card-icon">✓</span></div>
          <form className="clinical-edit-form" onSubmit={saveStructuredEdits}>
            <label className="wide-field">Chief complaint<textarea rows="2" value={editValues.chief_complaint} onChange={(event) => setEditValues((current) => ({ ...current, chief_complaint: event.target.value }))} required /></label>
            <label>Current medicines<input value={editValues.medications} onChange={(event) => setEditValues((current) => ({ ...current, medications: event.target.value }))} placeholder="Comma separated" /></label>
            <label>Allergies<input value={editValues.allergies} onChange={(event) => setEditValues((current) => ({ ...current, allergies: event.target.value }))} placeholder="Comma separated" /></label>
            <label>Past medical history<input value={editValues.past_medical_history} onChange={(event) => setEditValues((current) => ({ ...current, past_medical_history: event.target.value }))} placeholder="Comma separated" /></label>
            <label>Past surgical history<input value={editValues.past_surgical_history} onChange={(event) => setEditValues((current) => ({ ...current, past_surgical_history: event.target.value }))} placeholder="Comma separated" /></label>
            <label className="wide-field">Reason for change<input value={editReason} minLength="3" required onChange={(event) => setEditReason(event.target.value)} placeholder="Example: confirmed medicines with patient" /></label>
            <button className="secondary-start-button" type="submit" disabled={workflowState.saving}>{workflowState.saving ? "Saving..." : "Save new version"}</button>
          </form>
          <div className="signoff-panel">
            {signoff ? (
              <><p className="abdm-push-status">Signed by {signoff.signed_by_name} at {new Date(signoff.signed_at).toLocaleString()}</p><div className="abdm-push-actions"><button className="play-summary-button" type="button" onClick={() => downloadPdf("patient")}>Patient PDF</button><button className="secondary-start-button" type="button" onClick={() => downloadPdf("clinician")}>Clinician PDF</button></div></>
            ) : (
              <><label className="attestation-check"><input type="checkbox" checked={attested} onChange={(event) => setAttested(event.target.checked)} /> I reviewed this history and confirmed it with the patient.</label><button className="play-summary-button" type="button" disabled={!attested || workflowState.signing} onClick={signOffRecord}>{workflowState.signing ? "Signing..." : "Sign off record"}</button></>
            )}
          </div>
          {workflowState.message && <p className="abdm-push-status">{workflowState.message}</p>}
          {workflowState.error && <p className="speech-error" role="alert">{workflowState.error}</p>}
          {revisions.length > 0 && <details className="revision-history"><summary>Version history ({revisions.length})</summary><ol>{revisions.map((revision) => <li key={revision.revision_id}><strong>v{revision.version} · {revision.action.replaceAll("_", " ")}</strong> by {revision.actor_name} · {new Date(revision.created_at).toLocaleString()}<br /><span>{revision.reason}{revision.changed_fields.length ? ` · ${revision.changed_fields.join(", ")}` : ""}</span></li>)}</ol></details>}
        </section>
      )}

      <div className="dashboard-grid">
        {activeSection === "overview" && <section className="dashboard-card hpi-card">
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
        </section>}

        {activeSection === "overview" && <section className="dashboard-card">
          <div className="card-heading"><div><p className="section-kicker">Medication safety</p><h2>Drug & allergy history</h2></div><span className="card-icon">✚</span></div>
          <div className="stacked-detail">
            <div><dt>Current medications</dt><dd><ListValue items={drugHistory.current_medications} /></dd></div>
            <div><dt>Allergies</dt><dd><ListValue items={drugHistory.allergies} /></dd></div>
          </div>
        </section>}

        {activeSection === "overview" && <section className="dashboard-card history-card">
          <div className="card-heading"><div><p className="section-kicker">Background history</p><h2>Medical, family & personal history</h2></div></div>
          <dl className="stacked-detail">
            <div><dt>Past medical history</dt><dd><ListValue items={patient.past_medical_history} /></dd></div>
            <div><dt>Past surgical history</dt><dd><ListValue items={patient.past_surgical_history} /></dd></div>
            <div><dt>Family history</dt><dd><ListValue items={patient.family_history} /></dd></div>
            <div><dt>Ahara-Vihara: Diet</dt><dd><SafeValue value={patient.personal_history?.diet} /></dd></div>
            <div><dt>Ahara-Vihara: Tobacco / smoking</dt><dd><SafeValue value={patient.personal_history?.smoking == null ? null : patient.personal_history.smoking ? "Yes" : "No"} /></dd></div>
            <div><dt>Ahara-Vihara: Alcohol</dt><dd><SafeValue value={patient.personal_history?.alcohol == null ? null : patient.personal_history.alcohol ? "Yes" : "No"} /></dd></div>
            <div><dt>Ahara-Vihara: Occupation</dt><dd><SafeValue value={patient.personal_history?.occupation} /></dd></div>
            <div><dt>Other symptoms review</dt><dd><SafeValue value={patient.review_of_systems} /></dd></div>
          </dl>
        </section>}

        {activeSection === "ayurveda" && hasAyushData && (
          <section className="dashboard-card ayush-card">
            <div className="card-heading"><div><p className="section-kicker">Ayurveda assessment</p><h2>Patient history and practitioner examination</h2></div><span className="ayush-badge">AYURVEDA</span></div>
            <dl className="detail-grid ayush-grid">
              <div className="detail-item"><dt>Prakriti</dt><dd><SafeValue value={ayush.prakriti} /><small>{ayush.prakriti_source ? `Source: ${ayush.prakriti_source.replaceAll("_", " ")}` : "Awaiting practitioner confirmation"}</small></dd></div>
              <div className="detail-item"><dt>Vikriti</dt><dd><SafeValue value={ayush.vikriti} /></dd></div>
              <div className="detail-item"><dt>Agni</dt><dd><SafeValue value={ayush.agni} /></dd></div>
              <div className="detail-item"><dt>Koshtha</dt><dd><SafeValue value={ayush.koshtha} /></dd></div>
              <div className="detail-item detail-item-wide"><dt>Nidana</dt><dd><SafeValue value={ayush.nidana} /></dd></div>
              <div className="detail-item detail-item-wide"><dt>Panchakarma history</dt><dd><SafeValue value={ayush.panchakarma_history} /></dd></div>
            </dl>
            <h3 className="ayush-subheading">Dashavidha: patient-reported factors</h3>
            <dl className="detail-grid ayush-grid">
              <div className="detail-item"><dt>Satmya</dt><dd><SafeValue value={patientDashavidha.satmya} /></dd></div>
              <div className="detail-item"><dt>Sattva</dt><dd><SafeValue value={patientDashavidha.sattva} /></dd></div>
              <div className="detail-item"><dt>Ahara Shakti</dt><dd><SafeValue value={patientDashavidha.ahara_shakti} /></dd></div>
              <div className="detail-item"><dt>Vyayama Shakti</dt><dd><SafeValue value={patientDashavidha.vyayama_shakti} /></dd></div>
              <div className="detail-item"><dt>Vaya</dt><dd><SafeValue value={patientDashavidha.vaya} /></dd></div>
            </dl>
            <form className="ayush-confirmation-form" onSubmit={saveAyushConfirmation}>
              <div>
                <p className="section-kicker">Practitioner-only confirmation</p>
                <h3>Confirm Prakriti and examination factors</h3>
                <p className="trust-metric-note">Sara, Samhanana, and Pramana require direct examination. The kiosk never fills them from patient speech.</p>
              </div>
              <label>Confirmed Prakriti<input value={ayushConfirmation.prakriti} onChange={(event) => setAyushConfirmation((current) => ({ ...current, prakriti: event.target.value }))} required /></label>
              <label>Sara<input value={ayushConfirmation.sara} onChange={(event) => setAyushConfirmation((current) => ({ ...current, sara: event.target.value }))} /></label>
              <label>Samhanana<input value={ayushConfirmation.samhanana} onChange={(event) => setAyushConfirmation((current) => ({ ...current, samhanana: event.target.value }))} /></label>
              <label>Pramana<input value={ayushConfirmation.pramana} onChange={(event) => setAyushConfirmation((current) => ({ ...current, pramana: event.target.value }))} /></label>
              <p className="section-kicker">Trividha Pariksha</p>
              {TRIVIDHA_PARIKSHA_FIELDS.map(([key, label]) => (
                <label key={key}>{label}<input value={ayushConfirmation[key]} onChange={(event) => setAyushConfirmation((current) => ({ ...current, [key]: event.target.value }))} /></label>
              ))}
              <p className="section-kicker">Ashtavidha Pariksha</p>
              {ASHTAVIDHA_PARIKSHA_FIELDS.map(([key, label]) => (
                <label key={key}>{label}<input value={ayushConfirmation[key]} onChange={(event) => setAyushConfirmation((current) => ({ ...current, [key]: event.target.value }))} /></label>
              ))}
              <label className="ayush-notes-field">Examination notes<textarea value={ayushConfirmation.notes} onChange={(event) => setAyushConfirmation((current) => ({ ...current, notes: event.target.value }))} rows="3" /></label>
              <button className="play-summary-button" type="submit" disabled={ayushSaveState === "saving" || !ayushConfirmation.prakriti.trim()}>{ayushSaveState === "saving" ? "Saving..." : "Save practitioner confirmation"}</button>
              {ayushSaveMessage && <p className={ayushSaveState === "error" ? "speech-error" : "abdm-push-status"} role={ayushSaveState === "error" ? "alert" : undefined}>{ayushSaveMessage}</p>}
              {dashavidha.confirmed_by && <p className="trust-metric-note">Last confirmed by {dashavidha.confirmed_by} · {formatEventTime(dashavidha.confirmed_at)}</p>}
            </form>
          </section>
        )}

        {activeSection === "documents" && documents && documents.length > 0 && (
          <section className="dashboard-card documents-card">
            <div className="card-heading"><div><p className="section-kicker">Digitized documents</p><h2>Scanned by patient</h2></div><span className="card-icon">▣</span></div>
            <ul className="dashboard-doc-list">
              {documents.map((doc) => (
                <li className={`dashboard-doc-item ${["illegible", "needs_staff_review"].includes(doc.status) ? "illegible" : ""}`} key={doc.id}>
                  <div className="dashboard-doc-heading">
                    <span className="dashboard-doc-type">
                      {doc.status === "illegible" ? "Unreadable document" : DOC_TYPE_LABELS[doc.doc_type] || "Document"}
                    </span>
                    {doc.status === "confirmed" && <span className="dashboard-doc-flag">Patient-confirmed type</span>}
                    {doc.status === "needs_staff_review" && <span className="dashboard-doc-flag">Handwriting: staff confirmation required</span>}
                  </div>
                  {doc.status === "illegible" ? (
                    <p className="dashboard-doc-note">Could not be digitized - ask the patient for the physical copy.</p>
                  ) : (
                    <dl className="stacked-detail dashboard-doc-detail">
                      <div><dt>Diagnoses</dt><dd><ListValue items={doc.extracted_entities?.diagnoses} /></dd></div>
                      <div><dt>Medications</dt><dd><ListValue items={doc.extracted_entities?.medications} /></dd></div>
                      {doc.extracted_entities?.medication_verification?.length > 0 && <div><dt>Formulary suggestions</dt><dd><ListValue items={doc.extracted_entities.medication_verification.map((item) => item.matched_generic ? `${item.raw} → ${item.matched_generic} (${item.status})` : `${item.raw} → not matched; verify manually`)} /></dd></div>}
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

        {activeSection === "overview" && <section className="dashboard-card trust-ledger-card">
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
        </section>}

        {activeSection === "integration" && <section className="dashboard-card abdm-push-card">
          <div className="card-heading"><div><p className="section-kicker">ABDM / Hospital HIS</p><h2>Push structured history</h2></div><span className="card-icon">⇪</span></div>
          {!hasPatientData || !sessionId ? (
            <p className="trust-metric-note">Select a patient session before reviewing and pushing its history.</p>
          ) : (
            <>
              <p className="trust-metric-note">Integration: {abdmStatus?.live_ready ? "ABDM sandbox configured" : "local contract mode"} · FHIR R4 DocumentBundle / OPConsultRecord</p>
              <form className="clinical-edit-form abha-link-form" onSubmit={saveAbhaLink}>
                <label>ABHA number<input inputMode="numeric" maxLength="14" value={abhaLink.number} onChange={(event) => setAbhaLink((current) => ({ ...current, number: event.target.value.replace(/\D/g, "") }))} required /></label>
                <label>ABHA address<input value={abhaLink.address} onChange={(event) => setAbhaLink((current) => ({ ...current, address: event.target.value.toLowerCase() }))} placeholder="name@abdm" /></label>
                <label>Verification method<select value={abhaLink.method} onChange={(event) => setAbhaLink((current) => ({ ...current, method: event.target.value }))}><option value="qr">ABHA QR</option><option value="otp">OTP flow</option><option value="demographic_match">Demographic match</option><option value="sandbox_test">Sandbox test</option></select></label>
                <label>Verification reference<input value={abhaLink.reference} onChange={(event) => setAbhaLink((current) => ({ ...current, reference: event.target.value }))} placeholder="Gateway request or staff reference" required minLength="3" /></label>
                <button className="secondary-start-button" type="submit">Verify and link ABHA</button>
              </form>
              {abhaMessage && <p className="abdm-push-status">{abhaMessage}</p>}
              <p className="abdm-push-copy">
                Validates this signed history as an ABDM FHIR document and stages its care context. With sandbox
                credentials and assigned API paths configured, the same action sends the care-context notification
                through the ABDM gateway. Local mode keeps the validated bundle on this device for integration testing.
              </p>
              <div className="abdm-push-actions">
                <button className="play-summary-button" type="button" onClick={handlePush} disabled={pushState === "pushing" || !signoff}>
                  {!signoff ? "Sign off before export" : pushState === "pushing" ? "Pushing..." : pushRecord ? "Push again" : "Push to ABDM/HIS"}
                </button>
                {pushRecord && (
                  <button className="secondary-start-button" type="button" onClick={() => setShowBundle((current) => !current)}>
                    {showBundle ? "Hide FHIR bundle" : "View FHIR bundle"}
                  </button>
                )}
              </div>
              {pushRecord && (
                <p className="abdm-push-status">
                  {pushRecord.delivery_mode === "sandbox" ? "Sent to sandbox" : "Validated locally"} at {formatEventTime(pushRecord.pushed_at)} · Reference {pushRecord.abdm_reference}
                </p>
              )}
              {pushError && <p className="speech-error" role="alert">{pushError}</p>}
              {showBundle && pushRecord && <pre className="abdm-bundle-view">{JSON.stringify(pushRecord.bundle, null, 2)}</pre>}
            </>
          )}
        </section>}

        {activeSection === "transcript" && <section className="dashboard-card transcript-card">
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
        </section>}
      </div>
      <p className="dashboard-footnote">This summary is collected history, not a diagnosis. Confirm details with the patient.</p>
    </main>
  );
}

export default DoctorDashboard;
