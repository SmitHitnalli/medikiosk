import { useEffect, useRef } from "react";
import VoiceOrb from "./VoiceOrb";
import { useVoiceFlow } from "./voiceFlow";

const CONSENT_PROMPTS = {
  en: "Before we begin: MediKiosk will record the health answers you give and read only the documents you choose to share. It prepares a summary for authorised hospital staff and keeps an audit trail of access. ABHA sharing is optional. MediKiosk does not diagnose or prescribe. You may cancel and clear this visit at any time. Do you agree to continue?",
  hi: "शुरू करने से पहले: मेडीकियोस्क आपके दिए हुए स्वास्थ्य उत्तर दर्ज करेगा और केवल आपके चुने हुए दस्तावेज़ पढ़ेगा। यह अधिकृत अस्पताल कर्मचारियों के लिए सारांश बनाता है और जानकारी तक पहुँच का रिकॉर्ड रखता है। आभा साझा करना वैकल्पिक है। मेडीकियोस्क निदान या दवा नहीं देता। आप किसी भी समय यह मुलाकात रद्द करके डेटा मिटा सकते हैं। क्या आप आगे बढ़ने के लिए सहमत हैं?",
};

function ConsentScreen({ onAgree, onDecline, actionError, isSubmitting }) {
  const voice = useVoiceFlow("en");
  const startedRef = useRef(false);

  async function playBothLanguages() {
    await voice.speak(CONSENT_PROMPTS.en, "en");
    await voice.speak(CONSENT_PROMPTS.hi, "hi");
  }

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void playBothLanguages().catch(() => {});
    // This is intentionally a once-per-screen announcement.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="start-shell consent-shell">
      <section className="start-card consent-card" aria-label="Consent screen">
        <div className="consent-title-row">
          <VoiceOrb compact state={voice.state} label={voice.state === "speaking" ? "Speaking · बोल रहा है" : "Privacy · गोपनीयता"} />
          <div>
            <p className="start-eyebrow">Your permission / आपकी सहमति</p>
            <h1>Before we begin</h1>
            <p className="consent-hindi-title" lang="hi">शुरू करने से पहले</p>
          </div>
        </div>

        <div className="consent-essential">
          <p className="consent-lead">If you continue, you allow MediKiosk to:</p>
          <ul>
            <li><strong>Use what you share</strong><span>Health answers and documents you choose to provide.</span></li>
            <li><strong>Prepare a clinical summary</strong><span>Visible to authorised hospital staff, with access recorded.</span></li>
            <li><strong>Store this visit securely</strong><span>You can cancel and clear the active visit at any time.</span></li>
          </ul>
          <p className="consent-boundary"><strong>ABHA is optional.</strong> MediKiosk collects history; it does not diagnose or prescribe.</p>
          <p className="consent-hindi-summary" lang="hi">आपके उत्तर और चुने हुए दस्तावेज़ अधिकृत अस्पताल कर्मचारियों के लिए सुरक्षित क्लिनिकल सारांश बनाने में उपयोग होंगे। पहुँच दर्ज की जाती है। आभा वैकल्पिक है। यह निदान या दवा नहीं देता।</p>
        </div>

        <p className="live-caption consent-caption" aria-live="polite">{voice.caption || "This explanation will play in English and Hindi."}</p>
        <div className="consent-actions">
          <button className="start-button" type="button" onClick={onAgree} disabled={isSubmitting}>{isSubmitting ? "Starting securely…" : "I agree · मैं सहमत हूँ"}</button>
          <button className="decline-button" type="button" onClick={onDecline}>I do not agree · मैं सहमत नहीं हूँ</button>
          <button className="consent-listen-button" type="button" onClick={() => void playBothLanguages()} disabled={voice.state === "speaking"}>↻ Replay both languages</button>
        </div>
        <p className="prompt-status">The microphone stays off until you agree. / आपकी सहमति तक माइक्रोफ़ोन बंद रहेगा।</p>
        {(actionError || voice.error) && <p className="language-error" role="alert">{actionError || voice.error}</p>}
      </section>
    </main>
  );
}

export default ConsentScreen;
