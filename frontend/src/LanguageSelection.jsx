import { useCallback, useEffect, useRef } from "react";
import { resetAccessibilityPreferences } from "./AccessibilityBar";
import { OrbSelectionLayout } from "./VoiceOrb";
import ClearDataButton from "./ClearDataButton";
import { isCancelCommand, normaliseVoiceText, useVoiceFlow, voiceYesNo } from "./voiceFlow";

const ENGLISH_PROMPT = "Choose your language. Say English for English, or Hindi for Hindi.";
const HINDI_PROMPT = "अपनी भाषा चुनें। अंग्रेज़ी के लिए इंग्लिश या हिंदी के लिए हिंदी बोलें।";

function LanguageSelection({ onSelect, onBack, onClearData }) {
  const voice = useVoiceFlow("en");
  const startedRef = useRef(false);

  const confirmCancel = useCallback(async () => {
    await voice.speak("Are you sure you want to cancel and clear your data? Say yes or no.", "en");
    const answer = await voice.listen("en").catch(() => "");
    if (voiceYesNo(answer) === true) onClearData();
    else if (voiceYesNo(answer) === false) await voice.speak("Okay, we will continue.", "en");
  }, [onClearData, voice.listen, voice.speak]);

  const handleAnswer = useCallback((answer) => {
    if (isCancelCommand(answer)) { void confirmCancel(); return; }
    const text = normaliseVoiceText(answer);
    if (text.includes("english") || text.includes("अंग्रेज")) onSelect("en");
    else if (text.includes("hindi") || text.includes("हिंदी") || text.includes("हिन्दी")) onSelect("hi");
    else {
      voice.setError("Please say English or Hindi, or tap a language button.");
      window.setTimeout(() => void voice.listen("en").then(handleAnswer).catch(() => {}), 600);
    }
  }, [confirmCancel, onSelect, voice.listen, voice.setError]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      await voice.speak(ENGLISH_PROMPT, "en");
      const answer = await voice.promptAndListen(HINDI_PROMPT, { spokenLanguage: "hi", listenLanguage: "en", timeoutMs: 7000 });
      handleAnswer(answer);
    })().catch(() => {});
  }, [handleAnswer, voice.promptAndListen, voice.speak]);

  const label = voice.state === "speaking" ? "Speaking · बोल रहा है" : voice.state === "listening" ? "Listening · सुन रहा है" : voice.state === "thinking" ? "Understanding" : "Choose a language";
  return (
    <OrbSelectionLayout state={voice.state} label={label} caption={voice.caption}>
      <section className="start-card language-selection-card orb-popup-card" aria-label="Language selection">
        <p className="step-indicator">Step 1 of 2</p>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>Choose your language</h1>
        <p className="hindi-heading">अपनी भाषा चुनें</p>
        <p className="start-copy">The prompt plays automatically. After it finishes, simply say your choice.</p>
        <div className="language-buttons">
          <button className="language-button" type="button" onClick={() => onSelect("en")}>English</button>
          <button className="language-button" type="button" onClick={() => onSelect("hi")}>हिन्दी <span>Hindi</span></button>
        </div>
        <p className="live-caption" aria-live="polite">{voice.caption}</p>
        {voice.error && <p className="language-error" role="alert">{voice.error}</p>}
        <div className="compact-actions">
          <button className="voice-choice-button" type="button" onClick={() => voice.state === "listening" ? voice.stopListening() : void voice.listen("en").then(handleAnswer).catch(() => {})}>{voice.state === "listening" ? "Stop listening" : "🎙 Listen again"}</button>
          <button className="secondary-start-button" type="button" onClick={resetAccessibilityPreferences}>Reset display</button>
          <button className="secondary-start-button" type="button" onClick={onBack}>Back</button>
        </div>
        <ClearDataButton language="en" onClearData={onClearData} />
      </section>
    </OrbSelectionLayout>
  );
}

export default LanguageSelection;
