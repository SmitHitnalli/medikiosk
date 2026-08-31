import { useEffect, useRef, useState } from "react";
import { playAudioBlob, stopAllAudio } from "./audio";

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const TRANSCRIBE_ENDPOINT = "http://localhost:8080/transcribe";
const ENGLISH_PROMPT = "If you want to continue this conversation in English, say English or tap the English button below";
const HINDI_PROMPT = "Agar aapko baat cheet Hindi mein karni hai to Hindi boliye ya neeche Hindi button dabaiye";

async function requestSpeech(text) {
  const response = await fetch(SPEAK_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!response.ok) throw new Error("Unable to play the language prompt.");
  return response.blob();
}

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

function LanguageSelection({ onSelect, onBack }) {
  const [promptStatus, setPromptStatus] = useState("Playing language prompts...");
  const [isListening, setIsListening] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    let cancelled = false;
    async function playPrompts() {
      try {
        const englishAudio = await requestSpeech(ENGLISH_PROMPT);
        if (!cancelled) await playAudioBlob(englishAudio);
      } catch {
        if (!cancelled) setPromptStatus("Choose a language below; the spoken English prompt was unavailable.");
      }
      if (cancelled) return;
      try {
        const hindiAudio = await requestSpeech(HINDI_PROMPT);
        if (!cancelled) {
          try {
            await playHindiPlaceholder(HINDI_PROMPT);
          } catch {
            await playAudioBlob(hindiAudio);
          }
        }
        if (!cancelled) setPromptStatus("Select English or Hindi, or use the voice button.");
      } catch {
        if (!cancelled) setPromptStatus("Select English or Hindi, or use the voice button. Hindi voice is a known gap.");
      }
    }
    void playPrompts();
    return () => {
      cancelled = true;
      stopAllAudio();
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function stopListening() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsListening(false);
  }

  async function handleRecording(blob) {
    try {
      const formData = new FormData();
      formData.append("file", blob, "language-choice.webm");
      const response = await fetch(TRANSCRIBE_ENDPOINT, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Voice selection failed.");
      const transcript = result.text?.toLowerCase() || "";
      if (transcript.includes("english")) onSelect("en");
      else if (transcript.includes("hindi")) onSelect("hi");
      else setVoiceError("Please say English or Hindi, then try again.");
    } catch (error) {
      setVoiceError(error.message || "Unable to understand the language choice.");
    }
  }

  async function startListening() {
    if (isListening) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError("Voice selection is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {};
      const recorder = new MediaRecorder(stream, options);
      chunksRef.current = [];
      streamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        chunksRef.current = [];
        if (blob.size > 0) void handleRecording(blob);
      };
      recorder.start();
      setVoiceError("");
      setIsListening(true);
    } catch (error) {
      setVoiceError(error.name === "NotAllowedError" ? "Microphone permission is required." : "Unable to access the microphone.");
    }
  }

  return (
    <main className="start-shell">
      <section className="start-card language-selection-card" aria-label="Language selection">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>Choose your language</h1>
        <p className="start-copy">{promptStatus}</p>
        <div className="language-buttons">
          <button className="language-button" type="button" onClick={() => onSelect("en")}>English</button>
          <button className="language-button" type="button" onClick={() => onSelect("hi")}>हिन्दी <span>Hindi</span></button>
        </div>
        <button className={`voice-choice-button ${isListening ? "listening" : ""}`} type="button" onClick={isListening ? stopListening : startListening}>
          {isListening ? "Stop listening" : "🎙 Choose by voice"}
        </button>
        {isListening && <p className="recording-status language-recording"><span className="recording-dot" /> Say “English” or “Hindi”</p>}
        {voiceError && <p className="language-error" role="alert">{voiceError}</p>}
        <p className="known-gap">Hindi voice playback uses a browser placeholder until a Hindi Piper voice is available.</p>
        <button className="secondary-start-button" type="button" onClick={onBack}>Back</button>
      </section>
    </main>
  );
}

export default LanguageSelection;
