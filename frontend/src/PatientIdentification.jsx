import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";

const SPEAK_ENDPOINT = "http://localhost:8080/speak";
const TRANSCRIBE_ENDPOINT = "http://localhost:8080/transcribe";
const REGISTER_ENDPOINT = "http://localhost:8080/patients/register";
const PATIENTS_ENDPOINT = "http://localhost:8080/patients";

const PROMPTS = {
  en: "Have you visited us before?",
  hi: "क्या आप पहले हमारे यहाँ आ चुके हैं?",
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

async function speakText(text, language) {
  const response = await fetch(SPEAK_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
  });
  if (!response.ok) throw new Error("The spoken prompt was unavailable.");
  const blob = await response.blob();
  if (language === "hi") {
    try {
      await playHindiPlaceholder(text);
      return;
    } catch {
      // Fall through to the English Piper voice as a final fallback.
    }
  }
  await playAudioBlob(blob);
}

function PatientIdentification({ language, interactionMode, onComplete, onBack, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const [step, setStep] = useState("question");
  const [name, setName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [mediId, setMediId] = useState("");
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [registeredId, setRegisteredId] = useState("");
  const [welcomeName, setWelcomeName] = useState("");
  const [foundPatient, setFoundPatient] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [recordingField, setRecordingField] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timeoutRef = useRef(null);

  useEffect(() => {
    if (!isSpeakMode) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    async function speakQuestion() {
      try {
        const text = PROMPTS[language] || PROMPTS.en;
        const response = await fetch(SPEAK_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, language: language || "en" }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Prompt unavailable");
        if (!cancelled) {
          const blob = await response.blob();
          if (language === "hi") {
            try { await playHindiPlaceholder(text); } catch { await playAudioBlob(blob); }
          } else {
            await playAudioBlob(blob);
          }
        }
      } catch (promptError) {
        if (!cancelled && promptError.name !== "AbortError" && promptError.message !== "Audio playback stopped.") {
          setStatus("Please choose an option below.");
        }
      }
    }
    void speakQuestion();
    return () => {
      cancelled = true;
      controller.abort();
      stopAllAudio();
    };
  }, [isSpeakMode, language]);

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
    setRecordingField("");
  }

  async function transcribeField(blob, field) {
    try {
      const formData = new FormData();
      formData.append("file", blob, `patient-${field}.webm`);
      const response = await fetch(TRANSCRIBE_ENDPOINT, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Voice input failed.");
      const transcript = result.text?.trim() || "";
      if (!transcript) throw new Error("No speech was detected. Please try again.");
      if (field === "name") setName(transcript);
      if (field === "phone") setPhoneNumber(transcript);
      if (field === "mediId") setMediId(transcript.toUpperCase().replace(/\s+/g, ""));
    } catch (requestError) {
      setError(requestError.message || "Unable to understand the voice input.");
    }
  }

  async function startListening(field) {
    if (recordingField) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice input is not supported in this browser. Please type your answer.");
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
        if (blob.size > 0) void transcribeField(blob, field);
      };
      recorder.start();
      setError("");
      setRecordingField(field);
      timeoutRef.current = window.setTimeout(stopListening, 5000);
    } catch (requestError) {
      setError(requestError.name === "NotAllowedError" ? "Microphone permission is required." : "Unable to access the microphone.");
    }
  }

  function chooseVisit(hasVisited) {
    setError("");
    setStep(hasVisited ? "returning" : "new");
  }

  async function registerPatient(event) {
    event.preventDefault();
    if (!name.trim() || !phoneNumber.trim()) {
      setError("Please provide both your name and phone number.");
      return;
    }
    setIsBusy(true);
    setError("");
    try {
      const response = await fetch(REGISTER_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), phone_number: phoneNumber.trim() }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Registration failed.");
      setRegisteredId(result.medi_id);
      setStep("registered");
      if (isSpeakMode) void speakText(`Your Medi ID is ${result.medi_id}. Please remember it. It will also be printed on your summary for next time.`, language || "en").catch(() => {});
    } catch (requestError) {
      setError(requestError.message || "Unable to register this patient.");
    } finally {
      setIsBusy(false);
    }
  }

  async function findPatient(event) {
    event.preventDefault();
    if (!mediId.trim()) {
      setError("Please enter your Medi ID.");
      return;
    }
    setIsBusy(true);
    setError("");
    try {
      const response = await fetch(`${PATIENTS_ENDPOINT}/${encodeURIComponent(mediId.trim().toUpperCase())}`);
      const result = await response.json();
      if (!response.ok) {
        const attempts = failedAttempts + 1;
        setFailedAttempts(attempts);
        throw new Error(attempts >= 3 ? "We could not find that Medi ID after three attempts. Please ask a staff member for help." : "We could not find that Medi ID. Please check it and try again.");
      }
      setFailedAttempts(0);
      setWelcomeName(result.name);
      setFoundPatient({
        medi_id: result.medi_id,
        name: result.name,
        phone_number: result.phone_number,
        prakriti: result.prakriti,
        returning_patient: true,
      });
      setStep("welcome");
      if (isSpeakMode) void speakText(`Welcome back, ${result.name}.`, language || "en").catch(() => {});
      setMediId(result.medi_id);
    } catch (requestError) {
      setError(requestError.message || "Unable to look up that Medi ID.");
    } finally {
      setIsBusy(false);
    }
  }

  function continueAsNewPatient() {
    setError("");
    setStep("new");
    setMediId("");
  }

  function finishNewPatient() {
    onComplete({ medi_id: registeredId, name: name.trim(), phone_number: phoneNumber.trim(), prakriti: null, returning_patient: false });
  }

  const prompt = PROMPTS[language] || PROMPTS.en;
  return (
    <main className="start-shell">
      <section className="start-card patient-id-card" aria-label="Patient identification">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · Patient identification</p>
        {step === "question" && <>
          <h1>{prompt}</h1>
          <div className="language-buttons patient-choice-buttons">
            <button className="language-button" type="button" onClick={() => chooseVisit(true)}>Yes, I have a Medi ID</button>
            <button className="language-button" type="button" onClick={() => chooseVisit(false)}>No, this is my first visit</button>
          </div>
        </>}
        {step === "new" && <>
          <h1>Let’s create your Medi ID</h1>
          <p className="start-copy">Please enter your details. {isSpeakMode ? "You can use the voice buttons or type instead." : "Your details will be used to register this visit."}</p>
          <form className="patient-form" onSubmit={registerPatient}>
            <label>Name<input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" /></label>
            {isSpeakMode && <button className="field-voice-button" type="button" onClick={() => recordingField === "name" ? stopListening() : startListening("name")}>{recordingField === "name" ? "Stop name recording" : "🎙 Say your name"}</button>}
            <label>Phone number<input value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} inputMode="tel" autoComplete="tel" /></label>
            {isSpeakMode && <button className="field-voice-button" type="button" onClick={() => recordingField === "phone" ? stopListening() : startListening("phone")}>{recordingField === "phone" ? "Stop phone recording" : "🎙 Say your phone number"}</button>}
            {recordingField && <p className="recording-status patient-recording"><span className="recording-dot" /> Listening...</p>}
            <button className="start-button" type="submit" disabled={isBusy}>{isBusy ? "Registering..." : "Create Medi ID"}</button>
          </form>
        </>}
        {step === "registered" && <>
          <h1>Your Medi ID is</h1>
          <p className="medi-id-value">{registeredId}</p>
          <p className="start-copy">Please remember this ID. It will also be printed on your summary for next time.</p>
          <button className="start-button" type="button" onClick={finishNewPatient}>Continue</button>
        </>}
        {step === "returning" && <>
          <h1>Welcome back</h1>
          <p className="start-copy">Enter or say your Medi ID so we can find your details.</p>
          <form className="patient-form" onSubmit={findPatient}>
            <label>Medi ID<input value={mediId} onChange={(event) => setMediId(event.target.value.toUpperCase())} placeholder="MK-ABC123" autoCapitalize="characters" /></label>
            {isSpeakMode && <button className="field-voice-button" type="button" onClick={() => recordingField === "mediId" ? stopListening() : startListening("mediId")}>{recordingField === "mediId" ? "Stop ID recording" : "🎙 Say your Medi ID"}</button>}
            <button className="start-button" type="submit" disabled={isBusy}>{isBusy ? "Checking..." : "Find my Medi ID"}</button>
          </form>
          {failedAttempts >= 3 && <button className="field-voice-button" type="button" onClick={continueAsNewPatient}>Continue as a new patient</button>}
        </>}
        {step === "welcome" && <>
        <h1>Welcome back, {welcomeName}</h1>
          <p className="start-copy">Your details have been found. Let’s continue.</p>
          <button className="start-button" type="button" onClick={() => onComplete(foundPatient)}>Continue</button>
        </>}
        {error && <p className="language-error" role="alert">{error}</p>}
        {status && <p className="prompt-status">{status}</p>}
        {step !== "question" && <button className="secondary-start-button" type="button" onClick={() => { setError(""); setStep("question"); }}>Back</button>}
        <button className="secondary-start-button" type="button" onClick={onBack}>Back to consent</button>
        <ClearDataButton onClearData={onClearData} />
      </section>
    </main>
  );
}

export default PatientIdentification;
