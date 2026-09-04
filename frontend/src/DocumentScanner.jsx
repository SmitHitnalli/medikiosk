import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";

const OCR_ENDPOINT = "http://localhost:8080/ocr";
const SPEAK_ENDPOINT = "http://localhost:8080/speak";

const SCAN_PROMPTS = {
  en: "You can scan any prescriptions, lab reports, or discharge summaries you have. Tap Scan a document to begin, or Done if you have none.",
  hi: "अगर आपके पास कोई नुस्खा, लैब रिपोर्ट, या डिस्चार्ज समरी है, तो उसे स्कैन करें। शुरू करने के लिए 'दस्तावेज़ स्कैन करें' दबाएं, या यदि नहीं है तो 'हो गया' दबाएं।",
};

const DOC_TYPE_LABELS = {
  prescription: "Prescription",
  lab_report: "Lab report",
  discharge_summary: "Discharge summary",
};

function playHindiPlaceholder(text) {
  if (!window.speechSynthesis) return Promise.reject(new Error("Hindi voice fallback is unavailable."));
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "hi-IN";
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

function createDocId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `doc-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function summariseEntities(entities) {
  const diagnoses = entities?.diagnoses || [];
  const medications = entities?.medications || [];
  const labValues = entities?.lab_values || [];
  const parts = [];
  if (diagnoses.length) parts.push(`${diagnoses.length} diagnosis note${diagnoses.length === 1 ? "" : "s"}`);
  if (medications.length) parts.push(`${medications.length} medication${medications.length === 1 ? "" : "s"}`);
  if (labValues.length) parts.push(`${labValues.length} lab value${labValues.length === 1 ? "" : "s"}`);
  return parts.length ? parts.join(" · ") : "No structured fields found";
}

// Guided multi-document scanning with a confidence-based fallback chain:
// fuzzy match (backend) -> ask patient to confirm -> mark illegible.
function DocumentScanner({ language, interactionMode, initialDocuments, onDone, onBack, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const prompt = SCAN_PROMPTS[language] || SCAN_PROMPTS.en;
  const [documents, setDocuments] = useState(initialDocuments || []);
  const [stage, setStage] = useState("idle"); // idle | uploading | review
  const [pendingResult, setPendingResult] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!isSpeakMode) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    async function speakPrompt() {
      try {
        const response = await fetch(SPEAK_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: prompt, language: language || "en" }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Scan prompt unavailable");
        if (!cancelled) {
          const audioBlob = await response.blob();
          if (language === "hi") {
            // Prefer the real Hindi Piper voice; browser speechSynthesis is now
            // only a last-resort fallback if Piper audio playback itself fails.
            try { await playAudioBlob(audioBlob); } catch { await playHindiPlaceholder(prompt); }
          } else {
            await playAudioBlob(audioBlob);
          }
        }
      } catch (speakError) {
        if (!cancelled && speakError.name !== "AbortError" && speakError.message !== "Audio playback stopped.") return;
      }
    }
    void speakPrompt();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [isSpeakMode, language, prompt]);

  async function uploadFile(file) {
    setStage("uploading");
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(OCR_ENDPOINT, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "The document could not be processed.");
      setPendingResult(result);
      setStage("review");
    } catch (requestError) {
      setError(requestError.message || "Unable to process the document.");
      setStage("idle");
    }
  }

  function handleFileSelected(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    void uploadFile(file);
  }

  function addDocument(docType, status) {
    setDocuments((current) => [
      ...current,
      {
        id: createDocId(),
        doc_type: docType,
        status,
        extracted_entities: pendingResult?.extracted_entities || { diagnoses: [], medications: [], lab_values: [] },
      },
    ]);
    setPendingResult(null);
    setStage("idle");
  }

  function markIllegible() {
    setDocuments((current) => [
      ...current,
      {
        id: createDocId(),
        doc_type: null,
        status: "illegible",
        extracted_entities: { diagnoses: [], medications: [], lab_values: [] },
      },
    ]);
    setPendingResult(null);
    setStage("idle");
  }

  function retakePhoto() {
    setPendingResult(null);
    setStage("idle");
    fileInputRef.current?.click();
  }

  function removeDocument(id) {
    setDocuments((current) => current.filter((doc) => doc.id !== id));
  }

  return (
    <main className="start-shell">
      <section className="start-card scanner-card" aria-label="Document scanning">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · Documents</p>
        <h1>{prompt}</h1>

        {documents.length > 0 && (
          <ul className="scanner-doc-list" aria-label="Scanned documents">
            {documents.map((doc) => (
              <li className={`scanner-doc-chip ${doc.status === "illegible" ? "illegible" : ""}`} key={doc.id}>
                <span className="scanner-doc-type">
                  {doc.status === "illegible" ? "Unreadable" : DOC_TYPE_LABELS[doc.doc_type] || "Document"}
                </span>
                <span className="scanner-doc-summary">
                  {doc.status === "illegible" ? "Please show this to the nurse" : summariseEntities(doc.extracted_entities)}
                </span>
                <button type="button" className="scanner-doc-remove" onClick={() => removeDocument(doc.id)} aria-label="Remove this document">✕</button>
              </li>
            ))}
          </ul>
        )}

        {stage === "idle" && (
          <div className="scanner-actions">
            <input ref={fileInputRef} className="visually-hidden" type="file" accept="image/*" capture="environment" onChange={handleFileSelected} />
            <button className="start-button scanner-scan-button" type="button" onClick={() => fileInputRef.current?.click()}>
              Scan a document
            </button>
          </div>
        )}

        {stage === "uploading" && <p className="scanner-status">Reading your document...</p>}

        {stage === "review" && pendingResult && (
          <div className="scanner-review">
            {pendingResult.status === "confident" && (
              <>
                <p className="scanner-review-heading">
                  This looks like a <strong>{DOC_TYPE_LABELS[pendingResult.suggested_doc_type] || "document"}</strong>.
                </p>
                <p className="scanner-review-detail">{summariseEntities(pendingResult.extracted_entities)}</p>
                <div className="scanner-type-buttons">
                  <button className="voice-choice-button" type="button" onClick={() => addDocument(pendingResult.suggested_doc_type, "confident")}>
                    Add this document
                  </button>
                  <button className="secondary-start-button" type="button" onClick={() => setPendingResult({ ...pendingResult, status: "needs_confirmation" })}>
                    That's not right
                  </button>
                </div>
              </>
            )}

            {pendingResult.status === "needs_confirmation" && (
              <>
                <p className="scanner-review-heading">We couldn't confidently tell what kind of document this is.</p>
                <p className="scanner-review-detail">What kind of document did you scan?</p>
                <div className="scanner-type-buttons">
                  {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => (
                    <button className="voice-choice-button" type="button" key={value} onClick={() => addDocument(value, "confirmed")}>
                      {label}
                    </button>
                  ))}
                </div>
                <button className="secondary-start-button" type="button" onClick={markIllegible}>
                  This document is unreadable
                </button>
              </>
            )}

            {pendingResult.status === "illegible" && (
              <>
                <p className="scanner-review-heading">We couldn't read this document clearly.</p>
                <p className="scanner-review-detail">You can try a clearer photo, or mark it as unreadable and continue - the nurse can review the physical copy.</p>
                <div className="scanner-type-buttons">
                  <button className="voice-choice-button" type="button" onClick={retakePhoto}>Try a clearer photo</button>
                  <button className="secondary-start-button" type="button" onClick={markIllegible}>Mark as unreadable and continue</button>
                </div>
              </>
            )}
          </div>
        )}

        {error && <p className="language-error" role="alert">{error}</p>}

        <div className="scanner-footer">
          <button className="start-button" type="button" onClick={() => onDone(documents)}>
            {documents.length > 0 ? `Done (${documents.length} scanned)` : "Done · no documents to scan"}
          </button>
          <button className="secondary-start-button" type="button" onClick={onBack}>Back to interview</button>
        </div>
        <ClearDataButton onClearData={onClearData} />
      </section>
    </main>
  );
}

export default DocumentScanner;
