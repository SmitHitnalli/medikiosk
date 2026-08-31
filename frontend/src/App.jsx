import { useEffect, useRef, useState } from "react";
import DoctorDashboard from "./DoctorDashboard";

const CHAT_ENDPOINT = "http://localhost:8080/chat";

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
  const [error, setError] = useState("");
  const messageListRef = useRef(null);

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

  async function sendMessage(event) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage || isSending) return;

    const patientMessage = { role: "user", content: trimmedMessage };
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((currentMessages) => [...currentMessages, patientMessage]);
    setMessage("");
    setError("");
    setIsSending(true);

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
      setIsSending(false);
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
          <button type="submit" disabled={!message.trim() || isSending}>
            {isSending ? "Sending..." : "Send"}
          </button>
        </form>
        <p className="disclaimer">MediKiosk collects history only. It does not provide a diagnosis or treatment advice.</p>
      </section>
    </main>
  );
}

export default App;
