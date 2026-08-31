import { useEffect, useRef, useState } from "react";
import { playAudioBlob, stopAllAudio } from "./audio";

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const TRANSCRIBE_ENDPOINT = "http://localhost:8080/transcribe";
const MODE_PROMPTS = {
  en: "Would you like to speak with me, or type your answers? Say Speak or Chat, or tap a button below.",
  hi: "क्या आप मुझसे बोलकर बात करना चाहेंगे या अपने जवाब टाइप करना चाहेंगे? बोलकर बात करने के लिए Speak या टाइप करने के लिए Chat कहें, या नीचे दिए बटन को दबाएं।",
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

function ModeSelection({ language, onSelect, onBack }) {
  const prompt = MODE_PROMPTS[language] || MODE_PROMPTS.en;
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timeoutRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    async function speakPrompt() {
      try {
        const response = await fetch(SPEAK_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: MODE_PROMPT }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Mode prompt unavailable");
        if (!cancelled) {
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
        }
      } catch (promptError) {
        if (!cancelled && promptError.name !== "AbortError" && promptError.message !== "Audio playback stopped.") {
          setError("Choose Speak or Chat below. The spoken prompt was unavailable.");
        }
      }
    }
    void speakPrompt();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [language, prompt]);

  useEffect(() => () => {
    window.clearTimeout(timeoutRef.current);
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAllAudio();
  }, []);

  function stopListening() {
    window.clearTimeout(timeoutRef.current);
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsListening(false);
  }

  async function transcribeChoice(blob) {
    try {
      const formData = new FormData();
      formData.append("file", blob, "mode-choice.webm");
      const response = await fetch(TRANSCRIBE_ENDPOINT, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Voice selection failed.");
      const transcript = result.text?.toLowerCase() || "";
      if (transcript.includes("speak")) onSelect("speak");
      else if (transcript.includes("chat")) onSelect("chat");
      else setError("Please say Speak or Chat, then try again.");
    } catch (requestError) {
      setError(requestError.message || "Unable to understand the mode choice.");
    }
  }

  async function startListening() {
    if (isListening) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice selection is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {};
      const recorder = new MediaRecorder(stream, options);
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        if (blob.size > 0) void transcribeChoice(blob);
      };
      recorder.start();
      setError("");
      setIsListening(true);
      timeoutRef.current = window.setTimeout(stopListening, 5000);
    } catch (requestError) {
      setError(requestError.name === "NotAllowedError" ? "Microphone permission is required." : "Unable to access the microphone.");
    }
  }

  return (
    <main className="start-shell">
      <section className="start-card language-card mode-selection-card" aria-label="Interview mode selection">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>How would you like to continue?</h1>
        <p className="start-copy">{prompt}</p>
        <div className="language-buttons">
          <button className="language-button" type="button" onClick={() => onSelect("speak")}>Speak</button>
          <button className="language-button" type="button" onClick={() => onSelect("chat")}>Chat</button>
        </div>
        <button className={`voice-choice-button ${isListening ? "listening" : ""}`} type="button" onClick={isListening ? stopListening : startListening}>
          {isListening ? "Stop listening" : "🎙 Choose by voice"}
        </button>
        {isListening && <p className="recording-status language-recording"><span className="recording-dot" /> Say “Speak” or “Chat”</p>}
        {error && <p className="language-error" role="alert">{error}</p>}
        <button className="secondary-start-button" type="button" onClick={onBack}>Back</button>
      </section>
    </main>
  );
}

export default ModeSelection;
