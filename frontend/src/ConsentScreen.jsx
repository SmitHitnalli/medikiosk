import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const CONSENT_PROMPTS = {
  en: "We will ask you some questions about your health and may look at any documents you share. This is only to help your doctor understand your visit better. Do you agree to continue?",
  hi: "हम आपसे आपके स्वास्थ्य के बारे में कुछ सवाल पूछेंगे और आपके द्वारा साझा किए गए दस्तावेज़ देख सकते हैं। यह केवल आपके डॉक्टर को आपकी मुलाकात को बेहतर समझने में मदद करने के लिए है। क्या आप आगे बढ़ने के लिए सहमत हैं?",
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

function ConsentScreen({ language, interactionMode, onAgree, onDecline, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const [promptStatus, setPromptStatus] = useState(isSpeakMode ? "Playing the consent explanation..." : "Please read the explanation and choose whether you agree to continue.");
  const prompt = CONSENT_PROMPTS[language] || CONSENT_PROMPTS.en;
  const playedPromptRef = useRef("");

  useEffect(() => {
    if (!isSpeakMode) {
      setPromptStatus("Please read the explanation and choose whether you agree to continue.");
      return undefined;
    }
    const promptKey = language || "en";
    if (playedPromptRef.current === promptKey) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    async function speakConsent() {
      try {
        const response = await fetch(SPEAK_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: prompt, language: language || "en" }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Consent prompt unavailable");
        const audioBlob = await response.blob();
        if (language === "hi") {
          try {
            await playHindiPlaceholder(prompt);
          } catch {
            await playAudioBlob(audioBlob);
          }
        } else {
          await playAudioBlob(audioBlob);
        }
        playedPromptRef.current = promptKey;
        if (!cancelled) setPromptStatus("Please choose whether you agree to continue.");
      } catch (error) {
        if (error.name === "AbortError" || error.message === "Audio playback stopped.") return;
        if (!cancelled) setPromptStatus("Please read the explanation and choose whether you agree to continue.");
      }
    }
    void speakConsent();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [isSpeakMode, language, prompt]);

  return (
    <main className="start-shell">
      <section className="start-card consent-card" aria-label="Consent screen">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · Consent</p>
        <h1>Before we begin</h1>
        <p className="consent-copy">{prompt}</p>
        <p className="prompt-status">{promptStatus}</p>
        <div className="consent-actions">
          <button className="start-button" type="button" onClick={onAgree}>I agree, continue</button>
          <button className="decline-button" type="button" onClick={onDecline}>I do not agree</button>
        </div>
        <ClearDataButton onClearData={onClearData} />
      </section>
    </main>
  );
}

export default ConsentScreen;
