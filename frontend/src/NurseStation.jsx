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

  const fetchAlerts = useCallback(async () => {
    try {
      const response = await apiFetch("/nurse-station/alerts", { headers: staffHeaders(staffToken) }, 10000);
      if (response.status === 401) {
        onSessionExpired();
        return;
      }
      if (!response.ok) throw new Error("Could not load alerts");
      const result = await response.json();
      setAlerts(result.alerts || []);
      setError("");
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
              className={`dashboard-card nurse-alert-card ${alert.kind === "help_request" ? "nurse-alert-help" : ""} ${alert.escalated ? "nurse-alert-escalated" : ""}`}
              key={alert.id}
            >
              <div className="nurse-alert-heading">
                <span className="nurse-alert-pulse" aria-hidden="true" />
                <div>
                  <p className="section-kicker">
                    {alert.kind === "help_request" ? "🆘 Help requested" : "🚩 Red flag"} · {alert.department || "General"}
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
