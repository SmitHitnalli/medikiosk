import { useEffect, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";
import { apiFetch } from "./api";
import VoiceOrb from "./VoiceOrb";
const DEPARTMENT_PROMPTS = {
  en: "Which department are you visiting today?",
  hi: "आप आज किस विभाग में आए हैं?",
};
const DEPARTMENTS = [
  ["Kayachikitsa", "कायचिकित्सा", "Kayachikitsa"],
  ["Panchakarma", "पंचकर्म", "Panchakarma"],
  ["Shalya", "शल्य", "Shalya"],
  ["Prasuti Tantra", "प्रसूति तंत्र", "Prasuti Tantra"],
  ["Not sure / General consultation", "निश्चित नहीं / सामान्य परामर्श", "general"],
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
  const isHindi = language === "hi";
  const prompt = DEPARTMENT_PROMPTS[language] || DEPARTMENT_PROMPTS.en;
  const [promptStatus, setPromptStatus] = useState("");

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
        if (!response.ok) throw new Error("Department prompt unavailable");
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
      } catch (error) {
        if (!cancelled && error.name !== "AbortError" && error.message !== "Audio playback stopped.") {
          setPromptStatus("Please choose your department below.");
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

  return (
    <main className="start-shell">
      <section className="start-card department-card" aria-label="Department selection">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · {isHindi ? "विभाग" : "Department"}</p>
        {isSpeakMode && <VoiceOrb compact state="ready" label={isHindi ? "विभाग चुनें" : "Choose a department"} />}
        <h1>{prompt}</h1>
        {promptStatus && <p className="language-error" role="status">{promptStatus}</p>}
        <div className="department-grid">
          {DEPARTMENTS.map(([label, hindiLabel, value]) => (
            <button className="department-button" type="button" key={value} onClick={() => onSelect(value)}>{isHindi ? hindiLabel : label}</button>
          ))}
        </div>
        <button className="secondary-start-button" type="button" onClick={onBack}>{isHindi ? "रोगी की पहचान पर वापस जाएँ" : "Back to patient identification"}</button>
        <ClearDataButton language={language} onClearData={onClearData} />
      </section>
    </main>
  );
}

export default DepartmentSelection;
