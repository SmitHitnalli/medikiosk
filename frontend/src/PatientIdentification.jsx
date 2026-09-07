import { useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { playAudioBlob, stopAllAudio } from "./audio";
import { apiFetch, patientHeaders } from "./api";
import VoiceOrb from "./VoiceOrb";

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

async function speakText(text, language, signal) {
  const response = await apiFetch("/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
    signal,
  });
  if (!response.ok) throw new Error("The spoken prompt was unavailable.");
  const blob = await response.blob();
  try {
    await playAudioBlob(blob);
  } catch {
    if (language === "hi") {
      // Real Hindi Piper voice failed to play - fall back to the browser's own
      // speechSynthesis rather than staying silent.
      await playHindiPlaceholder(text);
    }
  }
}

function normaliseMediId(value) {
  const compact = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return compact.startsWith("MK") ? `MK-${compact.slice(2, 8)}` : compact;
}

function normalisePhone(value) {
  return value.replace(/\D/g, "");
}

function PatientIdentification({ language, interactionMode, sessionId, sessionToken, onComplete, onBack, onClearData }) {
  const isSpeakMode = interactionMode === "speak";
  const isHindi = language === "hi";
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
  const activeRef = useRef(true);
  const transcriptionRef = useRef(null);
  const actionRequestRef = useRef(null);
  const speechRequestRef = useRef(null);

  useEffect(() => {
    if (!isSpeakMode) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    async function speakQuestion() {
      try {
        const text = PROMPTS[language] || PROMPTS.en;
        const response = await apiFetch("/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, language: language || "en" }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Prompt unavailable");
        if (!cancelled) {
          const blob = await response.blob();
          if (language === "hi") {
            // Prefer the real Hindi Piper voice; browser speechSynthesis is now
            // only a last-resort fallback if Piper audio playback itself fails.
            try { await playAudioBlob(blob); } catch (playbackError) {
              if (!cancelled && playbackError.message !== "Audio playback stopped.") await playHindiPlaceholder(text);
            }
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

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      transcriptionRef.current?.abort();
      actionRequestRef.current?.abort();
      speechRequestRef.current?.abort();
      window.clearTimeout(timeoutRef.current);
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.onstop = null;
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      stopAllAudio();
    };
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
    const controller = new AbortController();
    transcriptionRef.current?.abort();
    transcriptionRef.current = controller;
    try {
      const formData = new FormData();
      formData.append("file", blob, `patient-${field}.webm`);
      const response = await apiFetch("/transcribe", { method: "POST", body: formData, signal: controller.signal });
      const result = await response.json();
      if (!activeRef.current || controller.signal.aborted) return;
      if (!response.ok) throw new Error(result.detail || "Voice input failed.");
      const transcript = result.text?.trim() || "";
      if (!transcript) throw new Error("No speech was detected. Please try again.");
      if (field === "name") setName(transcript);
    } catch (requestError) {
      if (activeRef.current && !controller.signal.aborted) setError(requestError.message || "Unable to understand the voice input.");
    } finally {
      if (transcriptionRef.current === controller) transcriptionRef.current = null;
    }
  }

  async function startListening(field) {
    if (recordingField) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice input is not supported in this browser. Please type your answer.");
      return;
    }
    try {
      stopAllAudio();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!activeRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
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

  function speakForScreen(text) {
    const controller = new AbortController();
    speechRequestRef.current?.abort();
    speechRequestRef.current = controller;
    void speakText(text, language || "en", controller.signal).catch(() => {}).finally(() => {
      if (speechRequestRef.current === controller) speechRequestRef.current = null;
    });
  }

  async function registerPatient(event) {
    event.preventDefault();
    if (name.trim().length < 2 || normalisePhone(phoneNumber).length < 10) {
      setError("Please provide your name and a valid 10-digit phone number.");
      return;
    }
    setIsBusy(true);
    setError("");
    const controller = new AbortController();
    actionRequestRef.current?.abort();
    actionRequestRef.current = controller;
    try {
      const response = await apiFetch("/patients/register", {
        method: "POST",
        headers: patientHeaders(sessionId, sessionToken, true),
        body: JSON.stringify({ name: name.trim(), phone_number: normalisePhone(phoneNumber) }),
        signal: controller.signal,
      }, 10000);
      const result = await response.json();
      if (!activeRef.current || controller.signal.aborted) return;
      if (!response.ok) throw new Error(result.detail || "Registration failed.");
      setRegisteredId(result.medi_id);
      setStep("registered");
      if (isSpeakMode) speakForScreen(language === "hi" ? "आपकी मेडी आईडी स्क्रीन पर दिखाई गई है। कृपया इसे अगली बार के लिए सुरक्षित रखें।" : "Your Medi ID is shown on the screen. Please keep it safe for your next visit.");
    } catch (requestError) {
      if (activeRef.current && !controller.signal.aborted) setError(requestError.message || "Unable to register this patient.");
    } finally {
      if (activeRef.current && !controller.signal.aborted) setIsBusy(false);
      if (actionRequestRef.current === controller) actionRequestRef.current = null;
    }
  }

  async function findPatient(event) {
    event.preventDefault();
    if (!mediId.trim()) {
      setError("Please enter your Medi ID.");
      return;
    }
    if (failedAttempts >= 3) return;
    setIsBusy(true);
    setError("");
    const controller = new AbortController();
    actionRequestRef.current?.abort();
    actionRequestRef.current = controller;
    try {
      const response = await apiFetch(`/patients/${encodeURIComponent(normaliseMediId(mediId))}`, {
        headers: patientHeaders(sessionId, sessionToken),
        signal: controller.signal,
      }, 10000);
      const result = await response.json();
      if (!activeRef.current || controller.signal.aborted) return;
      if (!response.ok) {
        if (response.status !== 404) throw new Error(result.detail || "The patient registry is unavailable. Please try again.");
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
      if (isSpeakMode) speakForScreen(language === "hi" ? "फिर से स्वागत है। आपका विवरण मिल गया है।" : "Welcome back. We found your details.");
      setMediId(result.medi_id);
    } catch (requestError) {
      if (activeRef.current && !controller.signal.aborted) setError(requestError.message || "Unable to look up that Medi ID.");
    } finally {
      if (activeRef.current && !controller.signal.aborted) setIsBusy(false);
      if (actionRequestRef.current === controller) actionRequestRef.current = null;
    }
  }

  function continueAsNewPatient() {
    setError("");
    setStep("new");
    setMediId("");
  }

  function finishNewPatient() {
    onComplete({ medi_id: registeredId, name: name.trim(), phone_number: normalisePhone(phoneNumber), prakriti: null, returning_patient: false });
  }

  const prompt = PROMPTS[language] || PROMPTS.en;
  return (
    <main className="start-shell">
      <section className="start-card patient-id-card" aria-label="Patient identification">
        <div className="brand-mark small" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk · {isHindi ? "रोगी की पहचान" : "Patient identification"}</p>
        {isSpeakMode && <VoiceOrb compact state={recordingField ? "listening" : isBusy ? "thinking" : "ready"} label={recordingField ? (isHindi ? "सुन रहा है" : "Listening") : (isHindi ? "तैयार" : "Ready")} />}
        {step === "question" && <>
          <h1>{prompt}</h1>
          <div className="language-buttons patient-choice-buttons">
            <button className="language-button" type="button" onClick={() => chooseVisit(true)}>{isHindi ? "हाँ, मेरे पास मेडी आईडी है" : "Yes, I have a Medi ID"}</button>
            <button className="language-button" type="button" onClick={() => chooseVisit(false)}>{isHindi ? "नहीं, यह मेरी पहली मुलाकात है" : "No, this is my first visit"}</button>
          </div>
        </>}
        {step === "new" && <>
          <h1>{isHindi ? "अपनी मेडी आईडी बनाएँ" : "Let’s create your Medi ID"}</h1>
          <p className="start-copy">{isHindi ? "अपना विवरण भरें।" : "Please enter your details."} {isSpeakMode ? (isHindi ? "आप अपना नाम बोल सकते हैं। गोपनीयता के लिए फ़ोन नंबर टच कीबोर्ड से दर्ज करें।" : "You can say your name. For privacy, enter your phone number with the touch keyboard.") : (isHindi ? "इस मुलाकात को दर्ज करने के लिए इस विवरण का उपयोग होगा।" : "Your details will be used to register this visit.")}</p>
          <form className="patient-form" onSubmit={registerPatient}>
            <label>{isHindi ? "नाम" : "Name"}<input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" /></label>
            {isSpeakMode && <button className="field-voice-button" type="button" onClick={() => recordingField === "name" ? stopListening() : startListening("name")}>{recordingField === "name" ? (isHindi ? "नाम रिकॉर्ड करना बंद करें" : "Stop name recording") : (isHindi ? "🎙 अपना नाम बोलें" : "🎙 Say your name")}</button>}
            <label>{isHindi ? "फ़ोन नंबर" : "Phone number"}<input value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} inputMode="tel" autoComplete="tel" /></label>
            {recordingField && <p className="recording-status patient-recording"><span className="recording-dot" /> {isHindi ? "सुन रहे हैं..." : "Listening..."}</p>}
            <button className="start-button" type="submit" disabled={isBusy}>{isBusy ? (isHindi ? "दर्ज हो रहा है..." : "Registering...") : (isHindi ? "मेडी आईडी बनाएँ" : "Create Medi ID")}</button>
          </form>
        </>}
        {step === "registered" && <>
          <h1>{isHindi ? "आपकी मेडी आईडी है" : "Your Medi ID is"}</h1>
          <p className="medi-id-value">{registeredId}</p>
          <p className="start-copy">{isHindi ? "इस आईडी को याद रखें। अगली बार के लिए यह आपके सारांश पर भी छपेगी।" : "Please remember this ID. It will also be printed on your summary for next time."}</p>
          <button className="start-button" type="button" onClick={finishNewPatient}>{isHindi ? "आगे बढ़ें" : "Continue"}</button>
        </>}
        {step === "returning" && <>
          <h1>{isHindi ? "फिर से स्वागत है" : "Welcome back"}</h1>
          <p className="start-copy">{isHindi ? "गोपनीयता के लिए टच कीबोर्ड से अपनी मेडी आईडी दर्ज करें।" : "For privacy, enter your Medi ID with the touch keyboard."}</p>
          <form className="patient-form" onSubmit={findPatient}>
            <label>Medi ID<input value={mediId} onChange={(event) => setMediId(event.target.value.toUpperCase())} placeholder="MK-ABC123" autoCapitalize="characters" /></label>
            <button className="start-button" type="submit" disabled={isBusy || failedAttempts >= 3}>{isBusy ? (isHindi ? "जाँच हो रही है..." : "Checking...") : failedAttempts >= 3 ? (isHindi ? "खोज बंद है" : "Lookup locked") : (isHindi ? "मेरी मेडी आईडी खोजें" : "Find my Medi ID")}</button>
          </form>
          {failedAttempts >= 3 && <button className="field-voice-button" type="button" onClick={continueAsNewPatient}>{isHindi ? "नए रोगी के रूप में आगे बढ़ें" : "Continue as a new patient"}</button>}
        </>}
        {step === "welcome" && <>
        <h1>{isHindi ? `फिर से स्वागत है, ${welcomeName}` : `Welcome back, ${welcomeName}`}</h1>
          <p className="start-copy">{isHindi ? "आपका विवरण मिल गया है। आगे बढ़ें।" : "Your details have been found. Let’s continue."}</p>
          <button className="start-button" type="button" onClick={() => onComplete(foundPatient)}>{isHindi ? "आगे बढ़ें" : "Continue"}</button>
        </>}
        {error && <p className="language-error" role="alert">{error}</p>}
        {status && <p className="prompt-status">{status}</p>}
        {step !== "question" && <button className="secondary-start-button" type="button" onClick={() => { setError(""); setStep("question"); }}>{isHindi ? "वापस" : "Back"}</button>}
        <button className="secondary-start-button" type="button" onClick={onBack}>{isHindi ? "शुरुआत पर वापस जाएँ" : "Back to start"}</button>
        <ClearDataButton language={language} onClearData={onClearData} />
      </section>
    </main>
  );
}

export default PatientIdentification;
