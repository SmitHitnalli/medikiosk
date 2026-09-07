import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";
import { apiFetch } from "./api";

const CONSENT_PROMPTS = {
  en: "We will ask you questions about your health and may process documents you choose to share. Your answers will be prepared for a healthcare professional to review. MediKiosk does not diagnose or prescribe treatment. Do you agree to continue?",
  hi: "हम आपसे आपके स्वास्थ्य के बारे में प्रश्न पूछेंगे और आपके द्वारा साझा किए गए दस्तावेज़ों को संसाधित कर सकते हैं। आपके उत्तर स्वास्थ्यकर्मी की समीक्षा के लिए तैयार किए जाएंगे। MediKiosk निदान या उपचार निर्धारित नहीं करता। क्या आप आगे बढ़ने के लिए सहमत हैं?",
};

function playBrowserHindi(text) {
  if (!window.speechSynthesis) return Promise.reject(new Error("Hindi audio is unavailable."));
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "hi-IN";
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

function ConsentScreen({ onAgree, onDecline, onClearData, actionError, isSubmitting }) {
  const [playingLanguage, setPlayingLanguage] = useState(null);
  const requestRef = useRef(null);

  useEffect(() => () => {
    requestRef.current?.abort();
    stopAllAudio();
  }, []);

  async function playConsent(language) {
    requestRef.current?.abort();
    stopAllAudio();
    const controller = new AbortController();
    requestRef.current = controller;
    setPlayingLanguage(language);
    try {
      const response = await apiFetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: CONSENT_PROMPTS[language], language }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Consent audio unavailable");
      const audioBlob = await response.blob();
      try {
        await playAudioBlob(audioBlob);
      } catch (playbackError) {
        if (language === "hi" && playbackError.message !== "Audio playback stopped.") {
          await playBrowserHindi(CONSENT_PROMPTS.hi);
        } else {
          throw playbackError;
        }
      }
    } catch (error) {
      if (error.name !== "AbortError" && error.message !== "Audio playback stopped.") {
        setPlayingLanguage("unavailable");
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setPlayingLanguage(null);
      }
    }
  }

  return (
    <main className="start-shell">
      <section className="start-card consent-card" aria-label="Consent screen">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · Consent / सहमति</p>
        <h1>Before we begin / शुरू करने से पहले</h1>
        <div className="consent-language-block" lang="en">
          <p className="consent-copy">{CONSENT_PROMPTS.en}</p>
          <button className="consent-listen-button" type="button" onClick={() => void playConsent("en")} disabled={Boolean(playingLanguage)}>
            {playingLanguage === "en" ? "Playing…" : "Listen in English"}
          </button>
        </div>
        <div className="consent-language-block" lang="hi">
          <p className="consent-copy">{CONSENT_PROMPTS.hi}</p>
          <button className="consent-listen-button" type="button" onClick={() => void playConsent("hi")} disabled={Boolean(playingLanguage)}>
            {playingLanguage === "hi" ? "सुनाया जा रहा है…" : "हिन्दी में सुनें"}
          </button>
        </div>
        <p className="prompt-status">The microphone remains off until you agree. / आपकी सहमति तक माइक्रोफ़ोन बंद रहेगा।</p>
        <div className="consent-actions">
          <button className="start-button" type="button" onClick={onAgree} disabled={isSubmitting}>
            {isSubmitting ? "Starting securely…" : "I agree, continue / मैं सहमत हूँ"}
          </button>
          <button className="decline-button" type="button" onClick={onDecline}>I do not agree / मैं सहमत नहीं हूँ</button>
        </div>
        {actionError && <p className="language-error" role="alert">{actionError}</p>}
        <ClearDataButton language="en" onClearData={onClearData} />
      </section>
    </main>
  );
}

export default ConsentScreen;
