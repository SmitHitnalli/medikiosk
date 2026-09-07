import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";
import { apiFetch } from "./api";

const SCAN_PROMPTS = {
  en: "You can scan any prescriptions, lab reports, or discharge summaries you have. Tap Scan a document to begin, or Done if you have none.",
  hi: "अगर आपके पास कोई नुस्खा, लैब रिपोर्ट, या डिस्चार्ज समरी है, तो उसे स्कैन करें। शुरू करने के लिए 'दस्तावेज़ स्कैन करें' दबाएं, या यदि नहीं है तो 'हो गया' दबाएं।",
};

const DOC_TYPE_LABELS = {
  prescription: "Prescription",
  lab_report: "Lab report",
  discharge_summary: "Discharge summary",
};
const DOC_TYPE_LABELS_HI = {
  prescription: "नुस्खा",
  lab_report: "लैब रिपोर्ट",
  discharge_summary: "डिस्चार्ज समरी",
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
function DocumentScanner({ language, interactionMode, initialDocuments, onDocumentsChange, onDone, onBack, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const isHindi = language === "hi";
  const docLabels = isHindi ? DOC_TYPE_LABELS_HI : DOC_TYPE_LABELS;
  const prompt = SCAN_PROMPTS[language] || SCAN_PROMPTS.en;
  const [documents, setDocuments] = useState(initialDocuments || []);
  const [stage, setStage] = useState("idle"); // idle | uploading | review
  const [pendingResult, setPendingResult] = useState(null);
  const [documentDate, setDocumentDate] = useState("");
  const [documentStyle, setDocumentStyle] = useState("printed");
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const activeRef = useRef(true);
  const uploadRequestRef = useRef(null);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      uploadRequestRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!isSpeakMode) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    async function speakPrompt() {
      try {
        const response = await apiFetch("/speak", {
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
            try { await playAudioBlob(audioBlob); } catch (playbackError) {
              if (!cancelled && playbackError.message !== "Audio playback stopped.") await playHindiPlaceholder(prompt);
            }
          } else {
            await playAudioBlob(audioBlob);
          }
        }
      } catch (speakError) {
        if (!cancelled && speakError.name !== "AbortError" && speakError.message !== "Audio playback stopped.") {
          setError("Please choose an option below.");
        }
      }
    }
    void speakPrompt();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [isSpeakMode, language, prompt]);

  useEffect(() => {
    onDocumentsChange?.(documents);
  }, [documents, onDocumentsChange]);

  async function uploadFile(file) {
    const controller = new AbortController();
    uploadRequestRef.current?.abort();
    uploadRequestRef.current = controller;
    setStage("uploading");
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("document_style", documentStyle);
      const response = await apiFetch("/ocr", { method: "POST", body: formData, signal: controller.signal });
      const result = await response.json();
      if (!activeRef.current || controller.signal.aborted) return;
      if (!response.ok) throw new Error(result.detail || "The document could not be processed.");
      setPendingResult(result);
      setStage("review");
    } catch (requestError) {
      if (activeRef.current && !controller.signal.aborted) {
        setError(requestError.message || "Unable to process the document.");
        setStage("idle");
      }
    } finally {
      if (uploadRequestRef.current === controller) uploadRequestRef.current = null;
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
        date: documentDate,
        status,
        input_style: pendingResult?.input_style || documentStyle,
        recognition_route: pendingResult?.recognition_route || "easyocr_printed",
        extracted_entities: pendingResult?.extracted_entities || { diagnoses: [], medications: [], lab_values: [] },
      },
    ]);
    setPendingResult(null);
    setDocumentDate("");
    setStage("idle");
  }

  function markIllegible() {
    setDocuments((current) => [
      ...current,
      {
        id: createDocId(),
        doc_type: null,
        date: documentDate,
        status: "illegible",
        input_style: documentStyle,
        recognition_route: pendingResult?.recognition_route || "manual_review",
        extracted_entities: { diagnoses: [], medications: [], lab_values: [] },
      },
    ]);
    setPendingResult(null);
    setDocumentDate("");
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
        <p className="start-eyebrow">MediKiosk · {isHindi ? "दस्तावेज़" : "Documents"}</p>
        <h1>{prompt}</h1>

        {documents.length > 0 && (
          <ul className="scanner-doc-list" aria-label="Scanned documents">
            {documents.map((doc) => (
              <li className={`scanner-doc-chip ${doc.status === "illegible" ? "illegible" : ""}`} key={doc.id}>
                <span className="scanner-doc-type">
                  {doc.status === "illegible" ? (isHindi ? "पढ़ने योग्य नहीं" : "Unreadable") : docLabels[doc.doc_type] || (isHindi ? "दस्तावेज़" : "Document")}
                </span>
                <span className="scanner-doc-summary">
                  {doc.status === "illegible" ? (isHindi ? "इसे नर्स को दिखाएँ" : "Please show this to the nurse") : summariseEntities(doc.extracted_entities)}
                </span>
                <button type="button" className="scanner-doc-remove" onClick={() => removeDocument(doc.id)} aria-label="Remove this document">✕</button>
              </li>
            ))}
          </ul>
        )}

        <input ref={fileInputRef} className="visually-hidden" type="file" accept="image/*" capture="environment" onChange={handleFileSelected} />
        {stage === "idle" && (
          <div className="scanner-actions">
            <div className="scanner-style-choice" role="group" aria-label="Document writing style">
              <button className={documentStyle === "printed" ? "voice-choice-button selected" : "secondary-start-button"} type="button" onClick={() => setDocumentStyle("printed")}>{isHindi ? "मुद्रित" : "Printed"}</button>
              <button className={documentStyle === "handwritten" ? "voice-choice-button selected" : "secondary-start-button"} type="button" onClick={() => setDocumentStyle("handwritten")}>{isHindi ? "हस्तलिखित" : "Handwritten"}</button>
            </div>
            <p className="scanner-review-detail">{documentStyle === "handwritten" ? (isHindi ? "हस्तलिखित सामग्री को कर्मचारी पुष्टि के लिए भेजा जाएगा।" : "Handwriting will always be routed to staff for confirmation.") : (isHindi ? "मुद्रित दस्तावेज़ स्वचालित रूप से पढ़े जाते हैं।" : "Printed documents are read automatically.")}</p>
            <button className="start-button scanner-scan-button" type="button" onClick={() => fileInputRef.current?.click()}>
              {isHindi ? "दस्तावेज़ स्कैन करें" : "Scan a document"}
            </button>
          </div>
        )}

        {stage === "uploading" && <p className="scanner-status">{isHindi ? "दस्तावेज़ पढ़ा जा रहा है..." : "Reading your document..."}</p>}

        {stage === "review" && pendingResult && (
          <div className="scanner-review">
            <label className="scanner-date-label">
              {isHindi ? "दस्तावेज़ की तारीख (यदि लिखी हो)" : "Document date (if shown)"}
              <input type="date" value={documentDate} onChange={(event) => setDocumentDate(event.target.value)} />
            </label>
            {pendingResult.status === "confident" && (
              <>
                <p className="scanner-review-heading">
                  {isHindi ? "यह " : "This looks like a "}<strong>{docLabels[pendingResult.suggested_doc_type] || (isHindi ? "दस्तावेज़" : "document")}</strong>{isHindi ? " लगता है।" : "."}
                </p>
                <p className="scanner-review-detail">{summariseEntities(pendingResult.extracted_entities)}</p>
                <div className="scanner-type-buttons">
                  <button className="voice-choice-button" type="button" onClick={() => addDocument(pendingResult.suggested_doc_type, "confident")}>
                    {isHindi ? "यह दस्तावेज़ जोड़ें" : "Add this document"}
                  </button>
                  <button className="secondary-start-button" type="button" onClick={() => setPendingResult({ ...pendingResult, status: "needs_confirmation" })}>
                    {isHindi ? "यह सही नहीं है" : "That's not right"}
                  </button>
                </div>
              </>
            )}

            {pendingResult.status === "needs_confirmation" && (
              <>
                <p className="scanner-review-heading">{isHindi ? "हम दस्तावेज़ का प्रकार निश्चित रूप से नहीं पहचान सके।" : "We couldn't confidently tell what kind of document this is."}</p>
                <p className="scanner-review-detail">{isHindi ? "आपने किस प्रकार का दस्तावेज़ स्कैन किया?" : "What kind of document did you scan?"}</p>
                <div className="scanner-type-buttons">
                  {Object.entries(docLabels).map(([value, label]) => (
                    <button className="voice-choice-button" type="button" key={value} onClick={() => addDocument(value, "confirmed")}>
                      {label}
                    </button>
                  ))}
                </div>
                <button className="secondary-start-button" type="button" onClick={markIllegible}>
                  {isHindi ? "यह दस्तावेज़ पढ़ने योग्य नहीं है" : "This document is unreadable"}
                </button>
              </>
            )}

            {pendingResult.status === "needs_staff_review" && (
              <>
                <p className="scanner-review-heading">{isHindi ? "यह हस्तलिखित दस्तावेज़ कर्मचारी द्वारा जाँचा जाएगा।" : "This handwritten document needs staff confirmation."}</p>
                <p className="scanner-review-detail">{summariseEntities(pendingResult.extracted_entities)}. {isHindi ? "संभावित दवाओं को डॉक्टर से पुष्टि कराएँ।" : "Any medicine matches are suggestions for the clinician, not confirmed prescriptions."}</p>
                <div className="scanner-type-buttons">
                  {Object.entries(docLabels).map(([value, label]) => <button className="voice-choice-button" type="button" key={value} onClick={() => addDocument(value, "needs_staff_review")}>{label}</button>)}
                </div>
                <button className="secondary-start-button" type="button" onClick={retakePhoto}>{isHindi ? "फिर से फोटो लें" : "Try a clearer photo"}</button>
              </>
            )}

            {pendingResult.status === "illegible" && (
              <>
                <p className="scanner-review-heading">{isHindi ? "हम इस दस्तावेज़ को साफ़ नहीं पढ़ सके।" : "We couldn't read this document clearly."}</p>
                <p className="scanner-review-detail">{isHindi ? "अधिक साफ़ फोटो लें, या इसे पढ़ने योग्य नहीं मानकर आगे बढ़ें। नर्स मूल प्रति देख सकती है।" : "You can try a clearer photo, or mark it as unreadable and continue - the nurse can review the physical copy."}</p>
                <div className="scanner-type-buttons">
                  <button className="voice-choice-button" type="button" onClick={retakePhoto}>{isHindi ? "अधिक साफ़ फोटो लें" : "Try a clearer photo"}</button>
                  <button className="secondary-start-button" type="button" onClick={markIllegible}>{isHindi ? "पढ़ने योग्य नहीं मानकर आगे बढ़ें" : "Mark as unreadable and continue"}</button>
                </div>
              </>
            )}
          </div>
        )}

        {error && <p className="language-error" role="alert">{error}</p>}

        <div className="scanner-footer">
          <button className="start-button" type="button" disabled={stage !== "idle"} onClick={() => onDone(documents)}>
            {documents.length > 0 ? (isHindi ? `हो गया (${documents.length} स्कैन किए)` : `Done (${documents.length} scanned)`) : (isHindi ? "हो गया · कोई दस्तावेज़ नहीं" : "Done · no documents to scan")}
          </button>
          <button className="secondary-start-button" type="button" disabled={stage === "uploading"} onClick={onBack}>{isHindi ? "साक्षात्कार पर वापस जाएँ" : "Back to interview"}</button>
        </div>
        <ClearDataButton language={language} onClearData={onClearData} />
      </section>
    </main>
  );
}

export default DocumentScanner;
