import { useEffect } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const DEPARTMENT_PROMPTS = {
  en: "Which department are you visiting today?",
  hi: "आप आज किस विभाग में आए हैं?",
};
const DEPARTMENTS = [
  ["Kayachikitsa", "Kayachikitsa"],
  ["Panchakarma", "Panchakarma"],
  ["Shalya", "Shalya"],
  ["Prasuti Tantra", "Prasuti Tantra"],
  ["Not sure / General consultation", "general"],
];

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

function DepartmentSelection({ language, interactionMode, onSelect, onBack, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const prompt = DEPARTMENT_PROMPTS[language] || DEPARTMENT_PROMPTS.en;

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
        if (!response.ok) throw new Error("Department prompt unavailable");
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
      } catch (error) {
        if (!cancelled && error.name !== "AbortError" && error.message !== "Audio playback stopped.") return;
      }
    }
    void speakPrompt();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [isSpeakMode, language, prompt]);

  return (
    <main className="start-shell">
      <section className="start-card department-card" aria-label="Department selection">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · Department</p>
        <h1>{prompt}</h1>
        <div className="department-grid">
          {DEPARTMENTS.map(([label, value]) => (
            <button className="department-button" type="button" key={value} onClick={() => onSelect(value)}>{label}</button>
          ))}
        </div>
        <button className="secondary-start-button" type="button" onClick={onBack}>Back to patient identification</button>
        <ClearDataButton onClearData={onClearData} />
      </section>
    </main>
  );
}

export default DepartmentSelection;
