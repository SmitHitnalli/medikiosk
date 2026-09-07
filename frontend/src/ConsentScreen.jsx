import { useEffect, useRef } from "react";
import ClearDataButton from "./ClearDataButton";
import VoiceOrb from "./VoiceOrb";
import { useVoiceFlow } from "./voiceFlow";

const CONSENT_PROMPTS = {
  en: "MediKiosk will ask about your health and process only the documents you choose to share. Your answers are prepared for a healthcare professional. It does not diagnose or prescribe. Do you agree to continue?",
  hi: "मेडीकियोस्क आपसे आपके स्वास्थ्य के बारे में प्रश्न पूछेगा और केवल आपके चुने हुए दस्तावेज़ों को पढ़ेगा। आपके उत्तर स्वास्थ्यकर्मी की समीक्षा के लिए तैयार किए जाएंगे। यह निदान या दवा नहीं देता। क्या आप आगे बढ़ने के लिए सहमत हैं?",
};

function ConsentScreen({ onAgree, onDecline, onClearData, actionError, isSubmitting }) {
  const voice = useVoiceFlow("en");
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      await voice.speak(CONSENT_PROMPTS.en, "en");
      await voice.speak(CONSENT_PROMPTS.hi, "hi");
    })().catch(() => {});
  }, [voice.speak]);

  return (
    <main className="start-shell consent-shell">
      <section className="start-card consent-card" aria-label="Consent screen">
        <div className="consent-hero">
          <VoiceOrb compact state={voice.state} label={voice.state === "speaking" ? "Speaking · बोल रहा है" : "Privacy first · गोपनीयता पहले"} />
          <div>
            <p className="start-eyebrow">MediKiosk · Consent / सहमति</p>
            <h1>Your information stays under your control.</h1>
            <p className="consent-hindi-title">आपकी जानकारी पर आपका नियंत्रण रहता है।</p>
          </div>
        </div>
        <div className="consent-summary-grid">
          <article><span>01</span><strong>Health history</strong><p>We prepare a structured summary for clinical review.</p></article>
          <article><span>02</span><strong>Your choice</strong><p>You may cancel and clear this visit at any time.</p></article>
          <article><span>03</span><strong>Clinical boundary</strong><p>MediKiosk does not diagnose or prescribe treatment.</p></article>
        </div>
        <div className="consent-bilingual-copy">
          <p lang="en">{CONSENT_PROMPTS.en}</p>
          <p lang="hi">{CONSENT_PROMPTS.hi}</p>
        </div>
        <p className="live-caption" aria-live="polite">{voice.caption || "The explanation will play automatically in English and Hindi."}</p>
        <p className="prompt-status">The microphone remains off until you agree. / आपकी सहमति तक माइक्रोफ़ोन बंद रहेगा।</p>
        <div className="consent-actions">
          <button className="start-button" type="button" onClick={onAgree} disabled={isSubmitting}>{isSubmitting ? "Starting securely…" : "I agree, continue / मैं सहमत हूँ"}</button>
          <button className="decline-button" type="button" onClick={onDecline}>I do not agree / मैं सहमत नहीं हूँ</button>
          <button className="consent-listen-button" type="button" onClick={() => void voice.speak(CONSENT_PROMPTS.en, "en")} disabled={voice.state === "speaking"}>Replay English</button>
          <button className="consent-listen-button" type="button" onClick={() => void voice.speak(CONSENT_PROMPTS.hi, "hi")} disabled={voice.state === "speaking"}>हिन्दी दोहराएँ</button>
        </div>
        {(actionError || voice.error) && <p className="language-error" role="alert">{actionError || voice.error}</p>}
        <ClearDataButton language="en" onClearData={onClearData} />
      </section>
    </main>
  );
}

export default ConsentScreen;
