import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
const POLL_INTERVAL_MS = 8000;
const REQUEST_TIMEOUT_MS = 4000;
// Require a couple of consecutive failures before declaring the backend down,
// so a single dropped request doesn't flash the full-screen fallback at a
// patient mid-interview. Recovery is immediate on the next success, though -
// better to under-warn than to leave a working kiosk showing an outage banner.
const FAILURES_BEFORE_DOWN = 2;

// Wraps the patient/doctor-facing pages with a lightweight backend health poll,
// distinguishing two different failure modes a kiosk can hit on demo day:
//   - the FastAPI backend itself is unreachable (network down, process crashed,
//     wrong port) - nothing works, so this blocks the whole screen with a clear
//     "let staff know" message instead of leaving every individual screen to
//     fail separately with its own confusing error.
//   - the backend is up but Ollama isn't (not started, or crashed) - the parts
//     of MediKiosk that don't need the AI model (patient ID, department
//     selection, Nurse Station) still work, so this only shows a dismissible-
//     feeling banner rather than blocking everything.
function SystemStatusGate({ children }) {
  const [status, setStatus] = useState("checking"); // checking | ok | ollama_down | backend_down
  const consecutiveFailuresRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const response = await apiFetch("/health", {}, REQUEST_TIMEOUT_MS);
        if (!response.ok) throw new Error("Backend returned an error status");
        const data = await response.json();
        if (cancelled) return;
        consecutiveFailuresRef.current = 0;
        setStatus(data.ollama === "ok" ? "ok" : "ollama_down");
      } catch {
        if (cancelled) return;
        consecutiveFailuresRef.current += 1;
        if (consecutiveFailuresRef.current >= FAILURES_BEFORE_DOWN) setStatus("backend_down");
      }
    }

    void check();
    const interval = window.setInterval(check, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  if (status === "backend_down") {
    return (
      <main className="start-shell">
        <section className="start-card" aria-label="System unavailable" role="alert">
          <div className="brand-mark small" aria-hidden="true">M</div>
          <p className="start-eyebrow">MediKiosk</p>
          <h1>Temporarily unavailable</h1>
          <p className="start-copy">
            We can't reach the MediKiosk system right now. Please let a staff member know - nothing has been lost,
            and this screen will continue on its own once the system is back.
          </p>
          <p className="prompt-status">Checking again automatically...</p>
        </section>
      </main>
    );
  }

  return (
    <>
      {status === "ollama_down" && (
        <p className="system-banner" role="status">
          The AI assistant is temporarily unavailable. Patient details and document scanning still work; the
          conversation and document analysis will resume once it's back.
        </p>
      )}
      {children}
    </>
  );
}

export default SystemStatusGate;
