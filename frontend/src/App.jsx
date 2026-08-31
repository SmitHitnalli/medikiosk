import { useEffect, useRef, useState } from "react";
import DoctorDashboard from "./DoctorDashboard";

const CHAT_ENDPOINT = "http://localhost:8080/chat";
const TRANSCRIBE_ENDPOINT = "http://localhost:8080/transcribe";

function App() {
  const [page, setPage] = useState(() => window.location.hash === "#dashboard" ? "dashboard" : "chat");
  const [interviewData, setInterviewData] = useState(null);
  const [interviewComplete, setInterviewComplete] = useState(false);
  const [mode, setMode] = useState("general");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello. I’m here to understand what brings you in today.",
    },
  ]);
  const [redFlagReason, setRedFlagReason] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
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

  useEffect(() => {
    const handleHashChange = () => setPage(window.location.hash === "#dashboard" ? "dashboard" : "chat");
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function navigate(nextPage) {
    window.location.hash = nextPage === "dashboard" ? "dashboard" : "";
    setPage(nextPage);
  }

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
          mode,
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
        if (result.data && typeof result.data === "object") {
          setInterviewData(result.data);
        }
      }
      if (result.red_flag) {
        setRedFlagReason(result.red_flag_reason || "Urgent symptoms detected");
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

  if (page === "dashboard") {
    return <DoctorDashboard patientData={interviewData} onBack={() => navigate("chat")} />;
  }

  return (
    <main className="app-shell">
      <section className="chat-card" aria-label="MediKiosk patient interview">
        <header className="app-header">
          <div>
            <p className="eyebrow">MediKiosk</p>
            <h1>Patient interview</h1>
            <p className="subtitle">A structured history for your physician to review.</p>
          </div>
          <div className="header-actions">
            <a className="dashboard-link" href="#dashboard" onClick={(event) => { event.preventDefault(); navigate("dashboard"); }}>{interviewData ? "View live summary →" : "Doctor dashboard →"}</a>
            <div className="mode-control">
              <span className="mode-label">{mode === "general" ? "General mode" : "AYUSH mode"}</span>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={mode === "ayush"}
                  onChange={(event) => setMode(event.target.checked ? "ayush" : "general")}
                  aria-label="Toggle General mode and AYUSH mode"
                />
                <span className="slider" />
              </label>
            </div>
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

export default App;
