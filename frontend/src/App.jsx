import { useCallback, useEffect, useRef, useState } from "react";
import AccessibilityBar from "./AccessibilityBar";
import ClearDataButton from "./ClearDataButton";
import ConsentScreen from "./ConsentScreen";
import DepartmentSelection from "./DepartmentSelection";
import DoctorDashboard from "./DoctorDashboard";
import DocumentScanner from "./DocumentScanner";
import LanguageSelection from "./LanguageSelection";
import ModeSelection from "./ModeSelection";
import NurseStation from "./NurseStation";
import PatientIdentification from "./PatientIdentification";
import StaffPinGate from "./StaffPinGate";
import SystemStatusGate from "./SystemStatusGate";
import { apiFetch, patientHeaders, staffHeaders } from "./api";
import { clearRepeatAudio, playAudioBlob, stopAllAudio } from "./audio";

const SESSION_STORAGE_KEY = "medikiosk-active-session";
const IDLE_WARNING_MS = 4 * 60 * 1000;
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
const STAFF_PAGES = new Set(["dashboard", "nurse-station"]);
const PATIENT_PAGES = new Set(["consent", "language", "mode", "patient", "department", "chat", "documents"]);

function createSessionId() {
  return window.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function greeting(language) {
  return language === "hi"
    ? "नमस्ते। आज आपको किस परेशानी के लिए सहायता चाहिए?"
    : "Hello. I’m here to understand what brings you in today.";
}

function readStoredSession() {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(SESSION_STORAGE_KEY) || "null");
    return value && typeof value.sessionId === "string" && typeof value.sessionToken === "string" ? value : null;
  } catch {
    return null;
  }
}

function StartScreen({ onStart, confirmation }) {
  return (
    <main className="start-shell">
      <section className="start-card" aria-label="MediKiosk welcome screen">
        <div className="brand-mark" aria-hidden="true">M</div>
        <p className="start-eyebrow">MediKiosk</p>
        <h1>Patient history, made simple.</h1>
        <p className="start-copy">A guided conversation to help your physician understand how you are feeling.</p>
        <button className="start-button" type="button" onClick={onStart}>Start</button>
        <p className="start-note">Tap Start when you are ready.</p>
        {confirmation && <p className="clear-confirmation" role="status">{confirmation}</p>}
      </section>
    </main>
  );
}

function App() {
  const stored = useRef(readStoredSession()).current;
  const initialHash = window.location.hash.slice(1);
  const [page, setPage] = useState(STAFF_PAGES.has(initialHash) ? initialHash : stored?.page || "idle");
  const [interviewData, setInterviewData] = useState(stored?.interviewData || null);
  const [interviewComplete, setInterviewComplete] = useState(Boolean(stored?.interviewComplete));
  const [language, setLanguage] = useState(stored?.language || null);
  const [interactionMode, setInteractionMode] = useState(stored?.interactionMode || null);
  const [patientInfo, setPatientInfo] = useState(stored?.patientInfo || null);
  const [department, setDepartment] = useState(stored?.department || null);
  const [sessionId, setSessionId] = useState(stored?.sessionId || createSessionId);
  const [sessionToken, setSessionToken] = useState(stored?.sessionToken || null);
  const [staffToken, setStaffToken] = useState(null);
  const [staffUser, setStaffUser] = useState(null);
  const [staffRecord, setStaffRecord] = useState(null);
  const [clearConfirmation, setClearConfirmation] = useState("");
  const [idleWarning, setIdleWarning] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState(stored?.messages || [{ role: "assistant", content: greeting(stored?.language) }]);
  const [redFlagReason, setRedFlagReason] = useState(stored?.redFlagReason || "");
  const [redFlagEvents, setRedFlagEvents] = useState(stored?.redFlagEvents || []);
  const [isSending, setIsSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [scannedDocuments, setScannedDocuments] = useState(stored?.scannedDocuments || []);
  const [error, setError] = useState("");
  const [isStartingSession, setIsStartingSession] = useState(false);
  const messageListRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const silenceStartedAtRef = useRef(null);
  const recordingStartedAtRef = useRef(null);
  const silenceAnimationRef = useRef(null);
  const requestGenerationRef = useRef(0);
  const controllersRef = useRef(new Set());
  const pageRef = useRef(page);
  const spokenGreetingSessionRef = useRef("");

  useEffect(() => { pageRef.current = page; }, [page]);

  const abortPatientWork = useCallback(() => {
    requestGenerationRef.current += 1;
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    if (silenceAnimationRef.current) cancelAnimationFrame(silenceAnimationRef.current);
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    mediaRecorderRef.current = null;
    mediaStreamRef.current = null;
    audioChunksRef.current = [];
    audioContextRef.current = null;
    analyserRef.current = null;
    silenceStartedAtRef.current = null;
    recordingStartedAtRef.current = null;
    silenceAnimationRef.current = null;
    setIsSending(false);
    setIsRecording(false);
    stopAllAudio();
  }, []);

  const resetLocalSession = useCallback((confirmation = "") => {
    abortPatientWork();
    clearRepeatAudio();
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    setPage("idle");
    setLanguage(null);
    setInteractionMode(null);
    setPatientInfo(null);
    setDepartment(null);
    setSessionId(createSessionId());
    setSessionToken(null);
    setStaffToken(null);
    setStaffUser(null);
    setStaffRecord(null);
    setInterviewData(null);
    setInterviewComplete(false);
    setMessages([{ role: "assistant", content: greeting("en") }]);
    setMessage("");
    setRedFlagReason("");
    setRedFlagEvents([]);
    setScannedDocuments([]);
    setError("");
    setIdleWarning(false);
    setClearConfirmation(confirmation);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, [abortPatientWork]);

  const returnToStart = useCallback(async (showConfirmation = false, forceLocal = false) => {
    abortPatientWork();
    try {
      if (sessionToken) {
        const response = await apiFetch(`/sessions/${encodeURIComponent(sessionId)}`, {
          method: "DELETE",
          headers: patientHeaders(sessionId, sessionToken),
        }, 10000);
        if (!response.ok && ![401, 404].includes(response.status)) throw new Error("Could not clear the server session.");
      }
      resetLocalSession(showConfirmation ? "This visit’s data has been cleared. Your reusable Medi ID remains registered." : "");
    } catch (clearError) {
      if (forceLocal) resetLocalSession("This kiosk was cleared, but server cleanup could not be confirmed. Please notify staff.");
      else setError(clearError.message || "Unable to clear this visit. Please try again.");
    }
  }, [abortPatientWork, resetLocalSession, sessionId, sessionToken]);

  const navigate = useCallback((nextPage) => {
    stopAllAudio();
    if (nextPage !== "chat") {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = null;
        recorder.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
    setPage(nextPage);
    const nextUrl = nextPage === "idle"
      ? window.location.pathname + window.location.search
      : `${window.location.pathname}${window.location.search}#${nextPage}`;
    window.history.pushState(null, "", nextUrl);
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const requested = window.location.hash.slice(1) || "idle";
      if (STAFF_PAGES.has(requested)) return setPage(requested);
      if (requested === "consent" && !sessionToken) return setPage("consent");
      if (requested === "language" && sessionToken && !language) return setPage("language");
      if (requested === "mode" && sessionToken && language && !interactionMode) return setPage("mode");
      if (requested === "patient" && sessionToken && language && interactionMode && !department) return setPage("patient");
      if (requested === "department" && sessionToken && patientInfo && !department) return setPage("department");
      if (["chat", "documents"].includes(requested) && sessionToken && patientInfo && department) return setPage(requested);
      if (requested === "idle" && !sessionToken) return setPage("idle");
      const fallback = !sessionToken ? "idle" : !language ? "language" : !interactionMode ? "mode" : !patientInfo ? "patient" : !department ? "department" : "chat";
      setPage(fallback);
      window.location.hash = fallback === "idle" ? "" : fallback;
    };
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("popstate", handleHashChange);
    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("popstate", handleHashChange);
    };
  }, [department, interactionMode, language, patientInfo, sessionToken]);

  useEffect(() => {
    if (!sessionToken || STAFF_PAGES.has(page)) return;
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({
      page, sessionId, sessionToken, language, interactionMode, patientInfo, department,
      interviewData, interviewComplete, messages, redFlagReason, redFlagEvents, scannedDocuments,
    }));
  }, [page, sessionId, sessionToken, language, interactionMode, patientInfo, department, interviewData, interviewComplete, messages, redFlagReason, redFlagEvents, scannedDocuments]);

  useEffect(() => {
    if (!stored?.sessionToken) return undefined;
    const controller = new AbortController();
    (async () => {
      try {
        const response = await apiFetch(`/sessions/${encodeURIComponent(stored.sessionId)}`, {
          headers: patientHeaders(stored.sessionId, stored.sessionToken), signal: controller.signal,
        }, 10000);
        if (!response.ok) throw new Error("Stored visit is no longer available");
        const record = await response.json();
        setLanguage(record.language || null);
        setInteractionMode(record.interaction_mode || null);
        setPatientInfo(record.patient_medi_id ? {
          medi_id: record.patient_medi_id, name: record.patient_name, returning_patient: true,
          prakriti: record.data?.ayush_assessment?.prakriti || null,
        } : null);
        setDepartment(record.department);
        setInterviewData(record.data);
        setInterviewComplete(Boolean(record.interview_complete));
        setMessages(record.transcript?.length ? record.transcript : [{ role: "assistant", content: greeting(record.language) }]);
        setScannedDocuments(record.documents || []);
        const restoredPage = !record.language
          ? "language"
          : !record.interaction_mode
            ? "mode"
            : record.department
              ? (["chat", "documents"].includes(stored.page) ? stored.page : "chat")
              : (record.patient_medi_id ? "department" : "patient");
        setPage(restoredPage);
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${restoredPage}`);
      } catch (restoreError) {
        if (restoreError.name !== "AbortError") resetLocalSession("The previous visit could not be restored, so a fresh session was started.");
      }
    })();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!clearConfirmation) return undefined;
    const timeoutId = window.setTimeout(() => setClearConfirmation(""), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [clearConfirmation]);

  useEffect(() => {
    if (!PATIENT_PAGES.has(page) || isSending || isRecording) return undefined;
    let warningId;
    let timeoutId;
    const resetIdleTimeout = () => {
      setIdleWarning(false);
      window.clearTimeout(warningId);
      window.clearTimeout(timeoutId);
      warningId = window.setTimeout(() => setIdleWarning(true), IDLE_WARNING_MS);
      timeoutId = window.setTimeout(() => void returnToStart(false, true), IDLE_TIMEOUT_MS);
    };
    const events = ["pointerdown", "pointermove", "keydown", "touchstart", "scroll"];
    events.forEach((name) => window.addEventListener(name, resetIdleTimeout, { passive: true }));
    resetIdleTimeout();
    return () => {
      window.clearTimeout(warningId);
      window.clearTimeout(timeoutId);
      events.forEach((name) => window.removeEventListener(name, resetIdleTimeout));
    };
  }, [page, isSending, isRecording, returnToStart]);

  useEffect(() => {
    if (messageListRef.current) messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
  }, [messages, isSending]);

  useEffect(() => {
    if (page !== "chat" || interactionMode !== "speak" || !sessionToken || messages.length !== 1) return;
    if (spokenGreetingSessionRef.current === sessionId) return;
    spokenGreetingSessionRef.current = sessionId;
    void speakAssistant(messages[0]?.content || greeting(language), requestGenerationRef.current);
  }, [interactionMode, language, messages, page, sessionId, sessionToken]);

  async function startSecureSession() {
    if (isStartingSession) return;
    setIsStartingSession(true);
    setError("");
    const nextId = createSessionId();
    try {
      const response = await apiFetch("/sessions/start", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: nextId, consent: true }),
      }, 10000);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not start the visit.");
      setSessionId(result.session_id);
      setSessionToken(result.session_token);
      navigate("language");
    } catch (startError) {
      setError(startError.message || "Unable to start a secure visit.");
    } finally {
      setIsStartingSession(false);
    }
  }

  async function chooseInteractionMode(value) {
    if (!sessionToken || !language) return;
    setError("");
    try {
      const response = await apiFetch(`/sessions/${encodeURIComponent(sessionId)}/preferences`, {
        method: "PATCH",
        headers: patientHeaders(sessionId, sessionToken, true),
        body: JSON.stringify({ language, interaction_mode: value }),
      }, 10000);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not save your interaction preference.");
      setInteractionMode(result.interaction_mode);
      setMessages([{ role: "assistant", content: greeting(language) }]);
      navigate("patient");
    } catch (preferenceError) {
      setError(preferenceError.message || "Unable to save your interaction preference.");
    }
  }

  async function chooseDepartment(value) {
    try {
      const response = await apiFetch(`/sessions/${encodeURIComponent(sessionId)}/department`, {
        method: "PATCH", headers: patientHeaders(sessionId, sessionToken, true),
        body: JSON.stringify({ department: value }),
      }, 10000);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not save the department.");
      setDepartment(result.department);
      navigate("chat");
    } catch (departmentError) {
      setError(departmentError.message || "Unable to save the department.");
    }
  }

  async function persistDocuments(documents) {
    setScannedDocuments(documents);
    if (!sessionToken) return;
    try {
      const response = await apiFetch(`/sessions/${encodeURIComponent(sessionId)}/documents`, {
        method: "PUT", headers: patientHeaders(sessionId, sessionToken, true), body: JSON.stringify({ documents }),
      }, 10000);
      if (!response.ok) throw new Error("Could not save document changes.");
    } catch (documentError) {
      setError(documentError.message || "Document changes could not be saved.");
    }
  }

  async function speakAssistant(text, generation) {
    if (interactionMode !== "speak" || !text) return;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const response = await apiFetch("/speak", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language: language || "en" }), signal: controller.signal,
      });
      if (!response.ok || requestGenerationRef.current !== generation || pageRef.current !== "chat") return;
      await playAudioBlob(await response.blob());
    } catch (speechError) {
      if (speechError.name !== "AbortError" && speechError.message !== "Audio playback stopped.") {
        setError("The reply is shown on screen, but its audio could not be played.");
      }
    } finally {
      controllersRef.current.delete(controller);
    }
  }

  async function sendTextMessage(text, alreadySending = false) {
    const trimmed = text.trim();
    if (!trimmed || !sessionToken || interviewComplete) return;
    const generation = requestGenerationRef.current;
    const currentId = sessionId;
    const currentToken = sessionToken;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);
    setMessage("");
    setError("");
    if (!alreadySending) setIsSending(true);
    try {
      const response = await apiFetch("/chat", {
        method: "POST", headers: patientHeaders(currentId, currentToken, true),
        body: JSON.stringify({ message: trimmed, session_id: currentId }), signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "The assistant could not respond.");
      if (generation !== requestGenerationRef.current || currentId !== sessionId) return;
      setMessages((current) => [...current, { role: "assistant", content: result.reply }]);
      setInterviewData(result.data);
      setInterviewComplete(Boolean(result.interview_complete));
      if (result.red_flag) {
        const reason = result.red_flag_reason || "Urgent symptoms detected";
        setRedFlagReason(reason);
        if (result.red_flag_source) {
          setRedFlagEvents((current) => current.some((event) => event.reason === reason && event.source === result.red_flag_source)
            ? current
            : [...current, { reason, source: result.red_flag_source, timestamp: new Date().toISOString() }]);
        }
      }
      const prakriti = result.data?.ayush_assessment?.prakriti;
      if (prakriti && patientInfo?.medi_id) {
        void apiFetch(`/patients/${encodeURIComponent(patientInfo.medi_id)}/prakriti`, {
          method: "PATCH", headers: patientHeaders(currentId, currentToken, true), body: JSON.stringify({ prakriti }),
        }, 10000).catch(() => {});
      }
      void speakAssistant(result.reply, generation);
    } catch (requestError) {
      if (requestError.name !== "AbortError" && generation === requestGenerationRef.current) setError(requestError.message || "Unable to reach the backend.");
    } finally {
      controllersRef.current.delete(controller);
      if (generation === requestGenerationRef.current && !alreadySending) setIsSending(false);
    }
  }

  async function transcribeRecording(blob) {
    const generation = requestGenerationRef.current;
    const controller = new AbortController();
    controllersRef.current.add(controller);
    setIsSending(true);
    try {
      const formData = new FormData();
      formData.append("file", blob, "patient-recording.webm");
      const response = await apiFetch("/transcribe", { method: "POST", body: formData, signal: controller.signal });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "The audio could not be transcribed.");
      if (!result.text?.trim()) throw new Error("No speech was detected. Please try again.");
      if (generation === requestGenerationRef.current && pageRef.current === "chat") await sendTextMessage(result.text, true);
    } catch (requestError) {
      if (requestError.name !== "AbortError" && generation === requestGenerationRef.current) setError(requestError.message || "Unable to transcribe the recording.");
    } finally {
      controllersRef.current.delete(controller);
      if (generation === requestGenerationRef.current) setIsSending(false);
    }
  }

  function stopSilenceMonitor() {
    if (silenceAnimationRef.current) cancelAnimationFrame(silenceAnimationRef.current);
    silenceAnimationRef.current = null;
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    audioContextRef.current = null;
    analyserRef.current = null;
    silenceStartedAtRef.current = null;
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    mediaRecorderRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
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
      if (now - silenceStartedAtRef.current >= 2500) return stopRecording();
    } else silenceStartedAtRef.current = null;
    silenceAnimationRef.current = requestAnimationFrame(monitorSilence);
  }

  async function startRecording() {
    if (isSending || isRecording || interviewComplete) return;
    stopAllAudio();
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return setError("Audio recording is not supported in this browser.");
    const generation = requestGenerationRef.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation !== requestGenerationRef.current || pageRef.current !== "chat") {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const recorder = new MediaRecorder(stream, MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {});
      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size) audioChunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];
        if (blob.size && generation === requestGenerationRef.current) void transcribeRecording(blob);
      };
      recorder.start();
      recordingStartedAtRef.current = Date.now();
      setError("");
      setIsRecording(true);
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        const context = new AudioContextClass();
        const analyser = context.createAnalyser();
        analyser.fftSize = 2048;
        context.createMediaStreamSource(stream).connect(analyser);
        audioContextRef.current = context;
        analyserRef.current = analyser;
        void context.resume();
        silenceAnimationRef.current = requestAnimationFrame(monitorSilence);
      }
    } catch (requestError) {
      setError(requestError.name === "NotAllowedError" ? "Microphone permission is required to record." : "Unable to access the microphone.");
    }
  }

  const expireStaffSession = useCallback(() => {
    setStaffToken(null);
    setStaffUser(null);
    setStaffRecord(null);
  }, []);

  function completeStaffLogin(result) {
    setStaffToken(result.token);
    setStaffUser(result.user);
    if (result.user?.role === "nurse" && pageRef.current === "dashboard") navigate("nurse-station");
  }

  async function logoutStaff() {
    const token = staffToken;
    expireStaffSession();
    if (!token) return;
    try {
      await apiFetch("/staff/logout", { method: "POST", headers: staffHeaders(token) }, 10000);
    } catch {
      // The local staff view is locked even if the server is temporarily unavailable.
    }
  }

  async function loadStaffSession(selectedId) {
    try {
      const response = await apiFetch(`/staff/sessions/${encodeURIComponent(selectedId)}`, { headers: staffHeaders(staffToken) }, 10000);
      if (response.status === 401) return expireStaffSession();
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Could not load the clinical session.");
      setStaffRecord(result);
    } catch (loadError) {
      setError(loadError.message || "Unable to load the clinical session.");
    }
  }

  let pageContent;
  if (STAFF_PAGES.has(page)) {
    if (!staffToken) pageContent = <StaffPinGate onSuccess={completeStaffLogin} onBack={() => navigate(sessionToken && patientInfo && department ? "chat" : "idle")} />;
    else if (page === "nurse-station" || staffUser?.role === "nurse") pageContent = <NurseStation staffToken={staffToken} staffUser={staffUser} onSessionExpired={expireStaffSession} onBack={staffUser?.role === "nurse" ? null : () => navigate("dashboard")} onLogout={() => void logoutStaff()} />;
    else {
      const record = staffRecord;
      pageContent = <DoctorDashboard patientData={record?.data || interviewData} documents={record?.documents || scannedDocuments} transcript={record?.transcript || messages} redFlagEvents={record?.data?.red_flag ? [{ reason: record.data.red_flag_reason || "Urgent symptoms detected", source: "recorded", timestamp: record.updated_at }] : redFlagEvents} department={record?.department || department} sessionId={record?.session_id || sessionId} mediId={record?.patient_medi_id || patientInfo?.medi_id} patientName={record?.patient_name || patientInfo?.name} language={record?.language || language} staffToken={staffToken} staffUser={staffUser} onSessionExpired={expireStaffSession} onLoadSession={loadStaffSession} onBack={() => navigate(sessionToken && patientInfo && department ? "chat" : "idle")} onClearData={!record && sessionToken ? () => void returnToStart(true) : null} onOpenNurseStation={() => navigate("nurse-station")} onLogout={() => void logoutStaff()} />;
    }
  } else if (page === "idle") pageContent = <StartScreen confirmation={clearConfirmation} onStart={() => { setClearConfirmation(""); navigate("consent"); }} />;
  else if (page === "consent") pageContent = <ConsentScreen onAgree={() => void startSecureSession()} onDecline={() => resetLocalSession()} onClearData={() => resetLocalSession()} actionError={error} isSubmitting={isStartingSession} />;
  else if (page === "language") pageContent = <LanguageSelection onSelect={(value) => { setLanguage(value); setMessages([{ role: "assistant", content: greeting(value) }]); navigate("mode"); }} onBack={() => void returnToStart(false)} />;
  else if (page === "mode") pageContent = <ModeSelection language={language} onSelect={(value) => void chooseInteractionMode(value)} onBack={() => navigate("language")} />;
  else if (page === "patient") pageContent = <PatientIdentification language={language} interactionMode={interactionMode} sessionId={sessionId} sessionToken={sessionToken} onComplete={(patient) => { setPatientInfo(patient); navigate("department"); }} onBack={() => void returnToStart(false)} onClearData={() => void returnToStart(true)} />;
  else if (page === "department") pageContent = <DepartmentSelection language={language} interactionMode={interactionMode} onSelect={(value) => void chooseDepartment(value)} onBack={() => navigate("patient")} onClearData={() => void returnToStart(true)} />;
  else if (page === "documents") pageContent = <DocumentScanner language={language} interactionMode={interactionMode} initialDocuments={scannedDocuments} onDocumentsChange={(docs) => void persistDocuments(docs)} onDone={(docs) => { void persistDocuments(docs); navigate("chat"); }} onBack={() => navigate("chat")} onClearData={() => void returnToStart(true)} />;
  else pageContent = (
    <main className="app-shell">
      <section className="chat-card" aria-label="MediKiosk patient interview">
        <header className="app-header">
          <div><p className="eyebrow">MediKiosk</p><h1>{language === "hi" ? "रोगी साक्षात्कार" : "Patient interview"}</h1><p className="subtitle">{language === "hi" ? "डॉक्टर की समीक्षा के लिए संरचित स्वास्थ्य इतिहास।" : "A structured history for your physician to review."}</p></div>
          <div className="header-actions"><ClearDataButton language={language} onClearData={() => void returnToStart(true)} /><a className="dashboard-link" href="#documents" onClick={(event) => { event.preventDefault(); navigate("documents"); }}>{scannedDocuments.length ? (language === "hi" ? `दस्तावेज़ (${scannedDocuments.length}) →` : `Documents (${scannedDocuments.length}) →`) : (language === "hi" ? "दस्तावेज़ स्कैन करें →" : "Scan documents →")}</a><a className="dashboard-link" href="#dashboard" onClick={(event) => { event.preventDefault(); navigate("dashboard"); }}>{language === "hi" ? "डॉक्टर सारांश →" : "Doctor dashboard →"}</a></div>
        </header>
        {redFlagReason && <div className="red-alert" role="alert"><span className="alert-icon">!</span><div><strong>{language === "hi" ? "तुरंत ध्यान देने की आवश्यकता है" : "Urgent attention needed"}</strong><p>{redFlagReason}</p></div></div>}
        <div className="message-list" ref={messageListRef} aria-live="polite">
          {messages.map((entry, index) => <div className={`message-row ${entry.role}`} key={`${entry.role}-${index}`}><div className="message-bubble"><span className="message-author">{entry.role === "user" ? (language === "hi" ? "आप" : "You") : "MediKiosk"}</span><p>{entry.content}</p></div></div>)}
          {isSending && <div className="message-row assistant"><div className="message-bubble typing" aria-label="MediKiosk is typing"><span className="dot" /><span className="dot" /><span className="dot" /></div></div>}
        </div>
        {interviewComplete && interviewData && <div className="completion-card"><div><strong>{language === "hi" ? "साक्षात्कार पूरा हुआ" : "Interview complete"}</strong><p>{language === "hi" ? "संरचित सारांश डॉक्टर की समीक्षा के लिए तैयार है।" : "The structured summary is ready for physician review."}</p></div><button type="button" onClick={() => navigate("dashboard")}>{language === "hi" ? "डॉक्टर का सारांश देखें →" : "View doctor summary →"}</button></div>}
        {idleWarning && <p className="idle-warning" role="alert">{language === "hi" ? "निष्क्रियता के कारण यह मुलाकात एक मिनट में रीसेट हो जाएगी। जारी रखने के लिए स्क्रीन छुएँ।" : "This visit will reset in one minute due to inactivity. Touch the screen to continue."}</p>}
        {error && <p className="error-message" role="alert">{error}</p>}
        <form className="composer" onSubmit={(event) => { event.preventDefault(); void sendTextMessage(message); }}>
          <input value={message} onChange={(event) => setMessage(event.target.value)} placeholder={language === "hi" ? "अपनी परेशानी बताइए..." : "Tell me what brings you in today..."} aria-label={language === "hi" ? "आपका संदेश" : "Your message"} disabled={isSending || interviewComplete} maxLength={4000} />
          <button className={`mic-button ${isRecording ? "recording" : ""}`} type="button" onClick={isRecording ? stopRecording : startRecording} disabled={(isSending && !isRecording) || interviewComplete} aria-label={isRecording ? (language === "hi" ? "रिकॉर्डिंग रोकें" : "Stop recording") : (language === "hi" ? "रिकॉर्डिंग शुरू करें" : "Start recording")}><span className="mic-icon">●</span>{isRecording ? (language === "hi" ? "रोकें" : "Stop") : (language === "hi" ? "माइक" : "Mic")}</button>
          <button type="submit" disabled={!message.trim() || isSending || isRecording || interviewComplete}>{isSending ? (language === "hi" ? "भेजा जा रहा है..." : "Sending...") : (language === "hi" ? "भेजें" : "Send")}</button>
        </form>
        {isRecording && <p className="recording-status"><span className="recording-dot" /> {language === "hi" ? "रिकॉर्डिंग जारी है... भेजने के लिए बोलना बंद करें" : "Recording... stop speaking to auto-send"}</p>}
        <p className="disclaimer">{language === "hi" ? "MediKiosk केवल स्वास्थ्य इतिहास एकत्र करता है। यह निदान या उपचार की सलाह नहीं देता।" : "MediKiosk collects history only. It does not provide a diagnosis or treatment advice."}</p>
      </section>
    </main>
  );

  return <><SystemStatusGate>{pageContent}</SystemStatusGate><AccessibilityBar sessionId={sessionId} sessionToken={sessionToken} page={page} /></>;
}

export default App;
