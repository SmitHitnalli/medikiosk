import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, staffHeaders } from "./api";
const POLL_INTERVAL_MS = 4000;

function formatTimeAgo(isoString) {
  if (!isoString) return "just now";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

// One audio tone, played through the Web Audio API - no external
// SMS/pager integration and no audio asset file needed. Escalated alerts
// (already flagged by the backend once they go unacknowledged past
// ALERT_ESCALATION_SECONDS) get a louder, two-beep tone; fresh alerts get a
// quieter single beep. Best-effort: browsers that block audio without a
// prior user gesture, or don't support Web Audio, simply stay silent - the
// visible alert card remains the primary signal either way.
function playAlertTone(audioCtxRef, hasEscalated) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!audioCtxRef.current) audioCtxRef.current = new Ctx();
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") void ctx.resume();
    const playTone = (delaySeconds, frequency, volume, duration) => {
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = frequency;
      gain.gain.value = volume;
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      const startAt = ctx.currentTime + delaySeconds;
      oscillator.start(startAt);
      oscillator.stop(startAt + duration);
    };
    if (hasEscalated) {
      playTone(0, 1046, 0.35, 0.35);
      playTone(0.4, 1046, 0.35, 0.35);
    } else {
      playTone(0, 784, 0.12, 0.15);
    }
  } catch {
    // Audio unavailable or blocked - the visible alert card is still shown.
  }
}

// Nurse Station: polls the backend for active red-flag alerts (deterministic
// keyword check + LLM secondary check, combined server-side) and lets staff
// acknowledge each one. No websockets - simple polling fits the hackathon
// scale and keeps the backend stateless-ish and easy to reason about.
function NurseStation({ onBack, staffToken, staffUser, onSessionExpired, onLogout }) {
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [acknowledgingId, setAcknowledgingId] = useState(null);
  const [, forceTick] = useState(0);
  const pollRef = useRef(null);
  const tickRef = useRef(null);
  const audioCtxRef = useRef(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiFetch("/nurse-station/alerts", { headers: staffHeaders(staffToken) }, 10000);
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error("Could not load alerts");
      const result = await response.json();
      const activeAlerts = result.alerts || [];
      setAlerts(activeAlerts);
      setError("");
      if (activeAlerts.length > 0) {
        playAlertTone(audioCtxRef, activeAlerts.some((alert) => alert.escalated));
      }
    } catch (fetchError) {
      setError(fetchError.message || "Unable to reach the backend.");
    } finally {
      setIsLoading(false);
    }
  }, [staffToken, onSessionExpired]);

  useEffect(() => {
    void fetchAlerts();
    pollRef.current = window.setInterval(fetchAlerts, POLL_INTERVAL_MS);
    tickRef.current = window.setInterval(() => forceTick((tick) => tick + 1), 1000);
    return () => {
      window.clearInterval(pollRef.current);
      window.clearInterval(tickRef.current);
    };
  }, [fetchAlerts]);

  async function acknowledgeAlert(alertId) {
    setAcknowledgingId(alertId);
    setError("");
    try {
      const response = await apiFetch(`/nurse-station/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
        method: "POST",
        headers: staffHeaders(staffToken),
      }, 10000);
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error("Could not acknowledge this alert.");
      setAlerts((current) => current.filter((alert) => alert.id !== alertId));
    } catch (ackError) {
      setError(ackError.message || "Unable to acknowledge this alert.");
    } finally {
      setAcknowledgingId(null);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">MediKiosk · Nurse Station</p>
          <h1>Live red-flag alerts</h1>
          {staffUser && <p className="staff-pin-copy">Signed in as {staffUser.display_name} · {staffUser.role}</p>}
          <p className="subtitle">
            {alerts.length > 0
              ? `${alerts.length} patient${alerts.length === 1 ? "" : "s"} need immediate attention`
              : "No active alerts right now - this view refreshes automatically."}
          </p>
        </div>
        <div className="dashboard-actions">
          {onLogout && <button className="back-link" type="button" onClick={onLogout}>Lock staff view</button>}
          {onBack && <button className="back-link" type="button" onClick={onBack}>← Back to dashboard</button>}
        </div>
      </header>

      {error && <p className="error-message nurse-station-error" role="alert">{error}</p>}

      {isLoading ? (
        <section className="chief-complaint-card nurse-station-empty">
          <div className="section-kicker">Loading</div>
          <p className="nurse-station-empty-copy">Checking for active alerts...</p>
        </section>
      ) : error ? null : alerts.length === 0 ? (
        <section className="chief-complaint-card nurse-station-empty">
          <div className="section-kicker">All clear</div>
          <p className="nurse-station-empty-copy">No patients are currently flagged. New alerts will appear here within a few seconds of being triggered.</p>
        </section>
      ) : (
        <div className="nurse-station-list">
          {alerts.map((alert) => (
            <section
              className={`dashboard-card nurse-alert-card ${alert.kind !== "red_flag" ? "nurse-alert-help" : ""} ${alert.escalated ? "nurse-alert-escalated" : ""}`}
              key={alert.id}
            >
              <div className="nurse-alert-heading">
                <span className="nurse-alert-pulse" aria-hidden="true" />
                <div>
                  <p className="section-kicker">
                    {alert.kind === "help_request" ? "🆘 Help requested" : alert.kind === "read_back_dispute" ? "📝 Summary flagged" : "🚩 Red flag"} · {alert.department || "General"}
                    {alert.escalated ? " · ESCALATED" : ""}
                  </p>
                  <h2>{alert.patient_name || "Unknown patient"}</h2>
                </div>
                <span className="nurse-alert-time">{formatTimeAgo(alert.triggered_at)}</span>
              </div>
              <p className="nurse-alert-reason">{alert.reason}</p>
              <p className="trust-metric-note">Kiosk {alert.kiosk_id || "unknown"} · {alert.severity || "urgent"} priority</p>
              <button
                className="nurse-alert-ack-button"
                type="button"
                onClick={() => acknowledgeAlert(alert.id)}
                disabled={acknowledgingId === alert.id}
              >
                {acknowledgingId === alert.id ? "Acknowledging..." : "Acknowledge"}
              </button>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}

export default NurseStation;
