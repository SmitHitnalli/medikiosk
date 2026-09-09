import { useCallback, useEffect, useRef } from "react";
import { OrbSelectionLayout } from "./VoiceOrb";
import ClearDataButton from "./ClearDataButton";
import { isCancelCommand, normaliseVoiceText, useVoiceFlow, voiceYesNo } from "./voiceFlow";

const PROMPTS = {
  en: "How would you like to continue? Say Speak for a hands-free voice conversation, or Chat to type and use buttons.",
  hi: "आप कैसे आगे बढ़ना चाहेंगे? आवाज़ से बात करने के लिए बोलकर कहें, या टाइप करने के लिए चैट कहें।",
};

function ModeSelection({ language, onSelect, onBack, onClearData }) {
  const isHindi = language === "hi";
  const voice = useVoiceFlow(language);
  const startedRef = useRef(false);

  const confirmCancel = useCallback(async () => {
    let answer = await voice.promptAndListen(isHindi ? "क्या आप वाकई रद्द करके अपना डेटा मिटाना चाहते हैं? हाँ या नहीं कहें।" : "Are you sure you want to cancel and clear your data? Say yes or no.").catch(() => "");
    if (voiceYesNo(answer) === null) answer = await voice.promptAndListen(isHindi ? "मैं समझ नहीं पाया। हाँ या नहीं कहें।" : "I did not understand. Please say yes or no.", { retries: 0 }).catch(() => "");
    if (voiceYesNo(answer) === true) onClearData();
    else if (voiceYesNo(answer) === false) await voice.speak(isHindi ? "ठीक है, हम जारी रखेंगे।" : "Okay, we will continue.");
  }, [isHindi, onClearData, voice.promptAndListen, voice.speak]);

  const handleAnswer = useCallback(async (answer, attempt = 0) => {
    if (isCancelCommand(answer)) { void confirmCancel(); return; }
    const text = normaliseVoiceText(answer);
    if (["speak", "voice", "bol", "awaaz", "aawaz", "बोल", "आवाज़"].some((word) => text.includes(word))) onSelect("speak");
    else if (["chat", "type", "likh", "टाइप", "लिख"].some((word) => text.includes(word))) onSelect("chat");
    else {
      if (attempt >= 2) {
        voice.setError(isHindi ? "कृपया स्क्रीन से बोलकर या चैट चुनें।" : "Please choose Speak or Chat on the screen.");
        return;
      }
      const retryPrompt = isHindi ? "मैं समझ नहीं पाया। कृपया बोलकर या चैट कहें।" : "I did not understand. Please say Speak or Chat.";
      const retry = await voice.promptAndListen(retryPrompt).catch(() => "");
      if (retry) await handleAnswer(retry, attempt + 1);
    }
  }, [confirmCancel, isHindi, onSelect, voice.promptAndListen, voice.setError]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void voice.promptAndListen(PROMPTS[language] || PROMPTS.en).then(handleAnswer).catch(() => {});
  }, [handleAnswer, language, voice.promptAndListen]);

  const label = voice.state === "speaking" ? (isHindi ? "बोल रहा है" : "Speaking") : voice.state === "listening" ? (isHindi ? "सुन रहा है" : "Listening") : voice.state === "thinking" ? (isHindi ? "समझ रहा है" : "Understanding") : (isHindi ? "अपना तरीका चुनें" : "Choose your mode");
  return (
    <OrbSelectionLayout state={voice.state} label={label} caption={voice.caption}>
      <section className="start-card language-card mode-selection-card orb-popup-card" aria-label="Interview mode selection">
        <p className="step-indicator">{isHindi ? "चरण 2 में से 2" : "Step 2 of 2"}</p>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>{isHindi ? "आप कैसे आगे बढ़ना चाहेंगे?" : "How would you like to continue?"}</h1>
        <p className="start-copy">{PROMPTS[language] || PROMPTS.en}</p>
        <div className="mode-choice-grid">
          <button className="mode-choice-card" type="button" onClick={() => onSelect("speak")}><span className="mode-icon">◉</span><strong>{isHindi ? "बोलकर" : "Speak"}</strong><small>{isHindi ? "स्वचालित आवाज़ बातचीत" : "Automatic voice conversation"}</small></button>
          <button className="mode-choice-card" type="button" onClick={() => onSelect("chat")}><span className="mode-icon">⌨</span><strong>{isHindi ? "चैट" : "Chat"}</strong><small>{isHindi ? "टाइप और टच करें" : "Type and use touch controls"}</small></button>
        </div>
        <p className="live-caption" aria-live="polite">{voice.caption}</p>
        {voice.error && <p className="language-error" role="alert">{voice.error}</p>}
        <button className="voice-choice-button" type="button" onClick={() => voice.state === "listening" ? voice.stopListening() : void voice.promptAndListen(PROMPTS[language] || PROMPTS.en).then(handleAnswer).catch(() => {})}>{voice.state === "listening" ? (isHindi ? "सुनना बंद करें" : "Stop listening") : (isHindi ? "🎙 फिर से सुनें" : "🎙 Listen again")}</button>
        <button className="secondary-start-button" type="button" onClick={onBack}>{isHindi ? "वापस" : "Back"}</button>
        <ClearDataButton language={language} onClearData={onClearData} />
      </section>
    </OrbSelectionLayout>
  );
}

export default ModeSelection;
