import { useState } from "react";
import ClearDataButton from "./ClearDataButton";

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

function DoctorDashboard({ patientData, onBack, onClearData }) {
  const patient = patientData || samplePatient;
  const hpi = patient.hpi || {};
  const drugHistory = patient.drug_allergy_history || {};
  const ayush = patient.ayush_assessment || {};
  const hasAyushData = Object.values(ayush).some((value) => normaliseItems(value).length > 0);
  const isSample = !patientData;
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechError, setSpeechError] = useState("");

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
      const audio = new Audio(URL.createObjectURL(await response.blob()));
      audio.onended = () => setIsSpeaking(false);
      audio.onerror = () => {
        setIsSpeaking(false);
        setSpeechError("The audio could not be played.");
      };
      await audio.play();
    } catch (error) {
      setIsSpeaking(false);
      setSpeechError(error.message || "Unable to play the summary.");
    }
  }

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
      </div>
      <p className="dashboard-footnote">This summary is collected history, not a diagnosis. Confirm details with the patient.</p>
    </main>
  );
}

export default DoctorDashboard;
