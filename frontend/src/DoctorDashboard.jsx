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

function DoctorDashboard({ patientData, onBack }) {
  const patient = patientData || samplePatient;
  const hpi = patient.hpi || {};
  const drugHistory = patient.drug_allergy_history || {};
  const ayush = patient.ayush_assessment || {};
  const hasAyushData = Object.values(ayush).some((value) => normaliseItems(value).length > 0);
  const isSample = !patientData;

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">MediKiosk · Physician view</p>
          <h1>Patient summary</h1>
          <p className="subtitle">Review the structured history before the consultation.</p>
        </div>
        <button className="back-link" type="button" onClick={onBack}>← Back to interview</button>
      </header>

      <section className="chief-complaint-card">
        <div className="section-kicker">Chief complaint</div>
        <div className="chief-complaint-value"><SafeValue value={patient.chief_complaint} /></div>
        <span className="sample-badge">{isSample ? "Sample patient · Draft" : "Live conversation · Ready for review"}</span>
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
