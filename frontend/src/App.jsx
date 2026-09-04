import { useCallback, useEffect, useRef, useState } from "react";
import AccessibilityBar from "./AccessibilityBar";
import SystemStatusGate from "./SystemStatusGate";
import ClearDataButton from "./ClearDataButton";
import ConsentScreen from "./ConsentScreen";
import DoctorDashboard from "./DoctorDashboard";
import DocumentScanner from "./DocumentScanner";
import LanguageSelection from "./LanguageSelection";
import NurseStation from "./NurseStation";
import ModeSelection from "./ModeSelection";
import PatientIdentification from "./PatientIdentification";
import DepartmentSelection from "./DepartmentSelection";
import StaffPinGate from "./StaffPinGate";
import { stopAllAudio } from "./audio";

const CHAT_ENDPOINT = "http://localhost:8080/chat";
const TRANSCRIBE_ENDPOINT = "http://localhost:8080/transcribe";
const IDLE_TIMEOUT_MS = 90 * 1000;

function createSessionId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function StartScreen({ onStart }) {
  return (
    <main className="start-shell">
      <section className="start-card" aria-label="MediKiosk welcome screen">
        <div className="brand-mark" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>Patient history, made simple.</h1>
        <p className="start-copy">A guided conversation to help your physician understand how you are feeling.</p>
        <button className="start-button" type="button" onClick={onStart}>Start</button>
        <p className="start-note">Tap Start when you are ready.</p>
      </section>
    </main>
  );
}

function App() {
  const [page, setPage] = useState(() => {
    if (window.location.hash === "#dashboard") return "dashboard";
    if (window.location.hash === "#nurse-station") return "nurse-station";
    if (window.location.hash === "#chat") return "chat";
    if (window.location.hash === "#documents") return "documents";
    if (window.location.hash === "#language") return "language";
    if (window.location.hash === "#consent") return "consent";
    if (window.location.hash === "#mode") return "mode";
    if (window.location.hash === "#patient") return "patient";
    if (window.location.hash === "#department") return "department";
    return "idle";
  });
  const [interviewData, setInterviewData] = useState(null);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const [language, setLanguage] = useState(null);
  const [interactionMode, setInteractionMode] = useState(null);
  const [patientInfo, setPatientInfo] = useState(null);
  const [department, setDepartment] = useState(null);
  const [sessionId, setSessionId] = useState(createSessionId);
  const [clearConfirmation, setClearConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello. I’m here to understand what brings you in today.",
    },
  ]);
  const [redFlagReason, setRedFlagReason] = useState("");
  const [redFlagEvents, setRedFlagEvents] = useState([]);
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [scannedDocuments, setScannedDocuments] = useState([]);
  const [staffAuthenticated, setStaffAuthenticated] = useState(false);
  const [error, setError] = useState("");
  const messageListRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const silenceStartedAtRef = useRef(null);
  const recordingStartedAtRef = useRef(null);
  const silenceAnimationRef = useRef(null);

  const clearSession = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (silenceAnimationRef.current) cancelAnimationFrame(silenceAnimationRef.current);
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    audioContextRef.current = null;
    analyserRef.current = null;
    silenceStartedAtRef.current = null;
    recordingStartedAtRef.current = null;
    setMessages([{ role: "assistant", content: "Hello. I’m here to understand what brings you in today." }]);
    setInterviewData(null);
    setInterviewComplete(false);
    setLanguage(null);
    setInteractionMode(null);
    setPatientInfo(null);
    setDepartment(null);
    setSessionId(createSessionId());
    setMessage("");
    setRedFlagReason("");
    setRedFlagEvents([]);
    setScannedDocuments([]);
    setError("");
    setIsSending(false);
    setIsRecording(false);
  }, []);

  function returnToStart(showConfirmation = false) {
    clearSession();
    if (showConfirmation) setClearConfirmation("Your data has been cleared");
    window.location.hash = "";
    setPage("idle");
  }

  useEffect(() => {
    const handleHashChange = () => {
      stopAllAudio();
      const hash = window.location.hash;
      setPage(hash === "#dashboard" ? "dashboard" : hash === "#nurse-station" ? "nurse-station" : hash === "#documents" ? "documents" : hash === "#language" ? "language" : hash === "#consent" ? "consent" : hash === "#mode" ? "mode" : hash === "#patient" ? "patient" : hash === "#department" ? "department" : hash === "#chat" ? "chat" : "idle");
    };
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function navigate(nextPage) {
    stopAllAudio();
    window.location.hash = nextPage === "dashboard" ? "dashboard" : nextPage === "nurse-station" ? "nurse-station" : nextPage === "documents" ? "documents" : nextPage === "language" ? "language" : nextPage === "consent" ? "consent" : nextPage === "mode" ? "mode" : nextPage === "patient" ? "patient" : nextPage === "department" ? "department" : nextPage === "chat" ? "chat" : "";
    setPage(nextPage);
  }

  useEffect(() => {
    if (page === "idle") clearSession();
  }, [page, clearSession]);

  useEffect(() => {
    if (!clearConfirmation) return undefined;
    const timeoutId = window.setTimeout(() => setClearConfirmation(""), 3000);
    return () => window.clearTimeout(timeoutId);
  }, [clearConfirmation]);

  useEffect(() => {
    if (page === "idle") return undefined;
    let timeoutId;
    const resetIdleTimeout = () => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => {
        clearSession();
        window.location.hash = "";
        setPage("idle");
      }, IDLE_TIMEOUT_MS);
    };
    const activityEvents = ["pointerdown", "keydown", "touchstart"];
    activityEvents.forEach((eventName) => window.addEventListener(eventName, resetIdleTimeout));
    resetIdleTimeout();
    return () => {
      window.clearTimeout(timeoutId);
      activityEvents.forEach((eventName) => window.removeEventListener(eventName, resetIdleTimeout));
    };
  }, [page, clearSession]);

  useEffect(() => {
    const list = messageListRef.current;
    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, isSending]);

  async function sendTextMessage(text, { alreadySending = false } = {}) {
    const trimmedMessage = text.trim();
    if (!trimmedMessage) return;
    const patientMessage = { role: "user", content: trimmedMessage };
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((currentMessages) => [...currentMessages, patientMessage]);
    setMessage("");
    setError("");
    if (!alreadySending) setIsSending(true);

    try {
      const response = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmedMessage,
          history,
          session_id: sessionId,
          language,
          department,
          returning_patient: Boolean(patientInfo?.returning_patient),
          known_prakriti: patientInfo?.prakriti || null,
          patient_name: patientInfo?.name || null,
        }),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.detail || "The assistant could not respond.");
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        { role: "assistant", content: result.reply },
      ]);
      if (result.interview_complete) {
        setInterviewComplete(true);
        setInterviewData(result.data);
      }
      if (result.red_flag) {
        const reason = result.red_flag_reason || "Urgent symptoms detected";
        setRedFlagReason(reason);
        setRedFlagEvents((currentEvents) => [
          ...currentEvents,
          { reason, source: result.red_flag_source || "ai", timestamp: new Date().toISOString() },
        ]);
      }
    } catch (requestError) {
      setError(requestError.message || "Unable to reach the backend.");
    } finally {
      if (!alreadySending) setIsSending(false);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (!message.trim() || isSending || isRecording) return;
    await sendTextMessage(message);
  }

  async function transcribeRecording(audioBlob) {
    setIsSending(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "patient-recording.webm");
      const response = await fetch(TRANSCRIBE_ENDPOINT, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "The audio could not be transcribed.");
      if (!result.text?.trim()) throw new Error("No speech was detected. Please try again.");
      await sendTextMessage(result.text, { alreadySending: true });
    } catch (requestError) {
      setError(requestError.message || "Unable to transcribe the recording.");
    } finally {
      setIsSending(false);
    }
  }

  function stopSilenceMonitor() {
    if (silenceAnimationRef.current) cancelAnimationFrame(silenceAnimationRef.current);
    silenceAnimationRef.current = null;
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    silenceStartedAtRef.current = null;
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    mediaRecorderRef.current = null;
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    stopSilenceMonitor();
    setIsRecording(false);
  }

  function monitorSilence() {
    const analyser = analyserRef.current;
    if (!analyser || !mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") return;

    const samples = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(samples);
    const rms = Math.sqrt(samples.reduce((sum, sample) => sum + ((sample - 128) / 128) ** 2, 0) / samples.length);
    const now = Date.now();
    if (now - recordingStartedAtRef.current > 1000 && rms < 0.018) {
      silenceStartedAtRef.current ??= now;
      if (now - silenceStartedAtRef.current >= 2500) {
        stopRecording();
        return;
      }
    } else {
      silenceStartedAtRef.current = null;
    }
    silenceAnimationRef.current = requestAnimationFrame(monitorSilence);
  }

  async function startRecording() {
    if (isSending || isRecording) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Audio recording is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {};
      const recorder = new MediaRecorder(stream, options);
      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];
        if (audioBlob.size > 0) void transcribeRecording(audioBlob);
      };
      recorder.start();
      recordingStartedAtRef.current = Date.now();
      setError("");
      setIsRecording(true);

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        const audioContext = new AudioContextClass();
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 2048;
        audioContext.createMediaStreamSource(stream).connect(analyser);
        audioContextRef.current = audioContext;
        analyserRef.current = analyser;
        void audioContext.resume();
        silenceAnimationRef.current = requestAnimationFrame(monitorSilence);
      }
    } catch (requestError) {
      setError(requestError.name === "NotAllowedError" ? "Microphone permission is required to record." : "Unable to access the microphone.");
    }
  }

  let pageContent = null;

  if (page === "dashboard" || page === "nurse-station") {
    if (!staffAuthenticated) {
      pageContent = <StaffPinGate onSuccess={() => setStaffAuthenticated(true)} onBack={() => navigate("chat")} />;
    } else if (page === "nurse-station") {
      pageContent = <NurseStation onBack={() => navigate("dashboard")} />;
    } else {
      pageContent = <DoctorDashboard patientData={interviewData} documents={scannedDocuments} transcript={messages} redFlagEvents={redFlagEvents} department={department} onBack={() => navigate("chat")} onClearData={() => returnToStart(true)} onOpenNurseStation={() => navigate("nurse-station")} />;
    }
  } else if (page === "idle") {
    pageContent = <><StartScreen onStart={() => { setClearConfirmation(""); clearSession(); navigate("language"); }} />{clearConfirmation && <div className="clear-confirmation" role="status">{clearConfirmation}</div>}</>;
  } else if (page === "language") {
    pageContent = <LanguageSelection onSelect={(selectedLanguage) => { setLanguage(selectedLanguage); navigate("mode"); }} onBack={() => navigate("idle")} />;
  } else if (page === "mode") {
    pageContent = <ModeSelection language={language} onSelect={(selectedMode) => { setInteractionMode(selectedMode); navigate("consent"); }} onBack={() => navigate("language")} />;
  } else if (page === "consent") {
    pageContent = <ConsentScreen language={language} interactionMode={interactionMode} onAgree={() => navigate("patient")} onDecline={() => returnToStart(false)} onClearData={() => returnToStart(true)} />;
  } else if (page === "patient") {
    pageContent = <PatientIdentification language={language} interactionMode={interactionMode} onComplete={(patient) => { setPatientInfo(patient); navigate("department"); }} onBack={() => navigate("consent")} onClearData={() => returnToStart(true)} />;
  } else if (page === "department") {
    pageContent = <DepartmentSelection language={language} interactionMode={interactionMode} onSelect={(selectedDepartment) => { setDepartment(selectedDepartment); navigate("chat"); }} onBack={() => navigate("patient")} onClearData={() => returnToStart(true)} />;
  } else if (page === "documents") {
    pageContent = (
      <DocumentScanner
        language={language}
        interactionMode={interactionMode}
        initialDocuments={scannedDocuments}
        onDone={(documents) => { setScannedDocuments(documents); navigate("chat"); }}
        onBack={() => navigate("chat")}
        onClearData={() => returnToStart(true)}
      />
    );
  } else {
    pageContent = (
    <main className="app-shell">
      <section className="chat-card" aria-label="MediKiosk patient interview">
        <header className="app-header">
          <div>
            <p className="eyebrow">MediKiosk</p>
            <h1>Patient interview</h1>
            <p className="subtitle">A structured history for your physician to review.</p>
          </div>
          <div className="header-actions">
            <ClearDataButton onClearData={() => returnToStart(true)} />
            <a className="dashboard-link" href="#documents" onClick={(event) => { event.preventDefault(); navigate("documents"); }}>{scannedDocuments.length > 0 ? `Documents (${scannedDocuments.length}) →` : "Scan documents →"}</a>
            <a className="dashboard-link" href="#dashboard" onClick={(event) => { event.preventDefault(); navigate("dashboard"); }}>{interviewData ? "View live summary →" : "Doctor dashboard →"}</a>
          </div>
        </header>

        {redFlagReason && (
          <div className="red-alert" role="alert">
            <span className="alert-icon">!</span>
            <div>
              <strong>Urgent attention needed</strong>
              <p>{redFlagReason}</p>
            </div>
          </div>
        )}

        <div className="message-list" ref={messageListRef} aria-live="polite">
          {messages.map((chatMessage, index) => (
            <div className={`message-row ${chatMessage.role}`} key={`${chatMessage.role}-${index}`}>
              <div className="message-bubble">
                <span className="message-author">{chatMessage.role === "user" ? "You" : "MediKiosk"}</span>
                <p>{chatMessage.content}</p>
              </div>
            </div>
          ))}
          {isSending && (
            <div className="message-row assistant">
              <div className="message-bubble typing" aria-label="MediKiosk is typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}
        </div>

        {interviewComplete && interviewData && (
          <div className="completion-card">
            <div>
              <strong>Interview complete</strong>
              <p>The structured summary is ready for physician review.</p>
            </div>
            <button type="button" onClick={() => navigate("dashboard")}>View doctor summary →</button>
          </div>
        )}

        {error && <p className="error-message" role="alert">{error}</p>}

        <form className="composer" onSubmit={sendMessage}>
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Tell me what brings you in today..."
            aria-label="Your message"
            disabled={isSending}
          />
          <button
            className={`mic-button ${isRecording ? "recording" : ""}`}
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isSending && !isRecording}
            aria-label={isRecording ? "Stop recording" : "Start recording"}
          >
            <span className="mic-icon">●</span>
            {isRecording ? "Stop" : "Mic"}
          </button>
          <button type="submit" disabled={!message.trim() || isSending || isRecording}>
            {isSending ? "Sending..." : "Send"}
          </button>
        </form>
        {isRecording && <p className="recording-status"><span className="recording-dot" /> Recording... stop speaking to auto-send</p>}
        <p className="disclaimer">MediKiosk collects history only. It does not provide a diagnosis or treatment advice.</p>
      </section>
    </main>
    );
  }

  return (
    <>
      <SystemStatusGate>{pageContent}</SystemStatusGate>
      <AccessibilityBar sessionId={sessionId} department={department} patientName={patientInfo?.name} page={page} />
    </>
  );
}

export default App;
