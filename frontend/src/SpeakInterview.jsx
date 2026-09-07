import { useEffect, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import VoiceOrb from "./VoiceOrb";

// Local model inference can take several seconds; past this threshold the
// orb switches to a "still working" cue so a patient staring at silence
// doesn't think the kiosk has frozen.
const STILL_WORKING_DELAY_MS = 3500;

function SpeakInterview({
  language,
  messages,
  redFlagReason,
  redFlagCategory,
  isSending,
  isSpeaking,
  isRecording,
  interviewComplete,
  readBackSummary,
  readBackConfirmed,
  onConfirmReadBack,
  onDisputeReadBack,
  idleWarning,
  error,
  documentCount,
  message,
  onMessageChange,
  onSend,
  onToggleRecording,
  onSwitchToChat,
  onDocuments,
  onDashboard,
  onClearData,
  onEraseRegistry,
}) {
  const pendingReadBack = interviewComplete && readBackSummary && !readBackConfirmed;
  const isHindi = language === "hi";
  const [showManualInput, setShowManualInput] = useState(false);
  const [stillWorking, setStillWorking] = useState(false);
  useEffect(() => {
    if (!isSending) {
      setStillWorking(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setStillWorking(true), STILL_WORKING_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [isSending]);
  const latestAssistant = [...messages].reverse().find((entry) => entry.role === "assistant")?.content || "";
  const orbState = isRecording ? "listening" : isSending ? "thinking" : isSpeaking ? "speaking" : interviewComplete ? "paused" : "ready";
  const orbLabel = isRecording
    ? (isHindi ? "सुन रहा है" : "Listening")
    : isSending
      ? (stillWorking
          ? (isHindi ? "अभी भी समझ रहा है…" : "Still thinking…")
          : (isHindi ? "समझ रहा है" : "Thinking"))
      : isSpeaking
        ? (isHindi ? "बोल रहा है" : "Speaking")
        : interviewComplete
          ? (isHindi ? "पूरा हुआ" : "Complete")
          : (isHindi ? "आपका जवाब सुनने के लिए तैयार" : "Ready for your answer");

  return (
    <main className="speak-interview-shell">
      <header className="speak-interview-header">
        <div><p className="eyebrow">MediKiosk</p><p className="speak-mode-caption">{isHindi ? "आवाज़ द्वारा स्वास्थ्य इतिहास" : "Voice health history"}</p></div>
        <div className="speak-header-actions">
          <button type="button" onClick={onDocuments}>{isHindi ? `दस्तावेज़ ${documentCount ? `(${documentCount})` : ""}` : `Documents ${documentCount ? `(${documentCount})` : ""}`}</button>
          <ClearDataButton language={language} onClearData={onClearData} onEraseRegistry={onEraseRegistry} />
        </div>
      </header>

      {redFlagReason && (redFlagCategory === "mental_health_crisis" ? (
        <div className="calm-support-alert speak-calm-alert" role="status">
          <div>
            <strong>{isHindi ? "हम आपकी सहायता के लिए यहाँ हैं" : "We're here to help"}</strong>
            <p>{isHindi ? "किसी सदस्य ने आपसे बात करने के लिए संपर्क किया है। कृपया वहीं रहें।" : "A member of our team has been asked to come speak with you. Please stay where you are."}</p>
          </div>
        </div>
      ) : (
        <div className="red-alert speak-red-alert" role="alert"><span className="alert-icon">!</span><div><strong>{isHindi ? "तुरंत सहायता बुलाई गई है" : "Urgent help has been requested"}</strong><p>{redFlagReason}</p></div></div>
      ))}

      <section className="speak-orb-stage" aria-label="Voice interview">
        <button className="orb-touch-target" type="button" onClick={onToggleRecording} disabled={isSending || (interviewComplete && !pendingReadBack)} aria-label={isRecording ? "Stop listening" : "Start listening"}>
          <VoiceOrb state={orbState} label={orbLabel} />
        </button>
        <p className="spoken-caption" aria-live="polite">{latestAssistant}</p>
        {isRecording && <p className="recording-status"><span className="recording-dot" /> {isHindi ? "सुन रहे हैं… बोलना पूरा होने पर रुकें" : "Listening… stop when you have finished"}</p>}
        {isSending && stillWorking && <p className="still-working-note" aria-live="polite">{isHindi ? "बस थोड़ा और समय लगेगा…" : "Still working, this can take a few more seconds…"}</p>}
        {pendingReadBack && (
          <div className="read-back-actions speak-read-back-actions">
            <button type="button" onClick={onConfirmReadBack}>{isHindi ? "हाँ, सही है" : "Yes, that's correct"}</button>
            <button type="button" className="read-back-dispute" onClick={onDisputeReadBack}>{isHindi ? "नहीं, सही नहीं है" : "No, that's not right"}</button>
          </div>
        )}
        {interviewComplete && !pendingReadBack && <p className="speak-complete">{isHindi ? "इतिहास डॉक्टर की समीक्षा के लिए तैयार है।" : "Your history is ready for the doctor to review."}</p>}
        {idleWarning && <p className="idle-warning" role="alert">{isHindi ? "एक मिनट में यह मुलाकात रीसेट होगी। जारी रखने के लिए स्क्रीन छुएँ।" : "This visit will reset in one minute. Touch the screen to continue."}</p>}
        {error && <p className="error-message" role="alert">{error}</p>}
      </section>

      <nav className="speak-controls" aria-label="Voice interview controls">
        <button type="button" onClick={onToggleRecording} disabled={isSending || (interviewComplete && !pendingReadBack)}>{isRecording ? (isHindi ? "रोकें" : "Stop") : (isHindi ? "अभी बोलें" : "Speak now")}</button>
        <button type="button" onClick={() => setShowManualInput((value) => !value)}>{isHindi ? "टाइप करें" : "Type answer"}</button>
        <button type="button" onClick={onSwitchToChat}>{isHindi ? "चैट पर जाएँ" : "Switch to Chat"}</button>
        {interviewComplete && !pendingReadBack && <button type="button" onClick={onDashboard}>{isHindi ? "डॉक्टर सारांश" : "Doctor summary"}</button>}
      </nav>

      {showManualInput && (
        <form className="speak-manual-form" onSubmit={(event) => { event.preventDefault(); onSend(message); }}>
          <input value={message} onChange={(event) => onMessageChange(event.target.value)} placeholder={isHindi ? "अपना जवाब टाइप करें" : "Type your answer"} maxLength={4000} disabled={isSending || (interviewComplete && !pendingReadBack)} />
          <button type="submit" disabled={!message.trim() || isSending || (interviewComplete && !pendingReadBack)}>{isHindi ? "भेजें" : "Send"}</button>
        </form>
      )}

      <p className="disclaimer">{isHindi ? "MediKiosk केवल स्वास्थ्य इतिहास एकत्र करता है। यह निदान या उपचार की सलाह नहीं देता।" : "MediKiosk collects history only. It does not diagnose or recommend treatment."}</p>
    </main>
  );
}

export default SpeakInterview;
