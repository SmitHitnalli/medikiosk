import { useState } from "react";
import { apiFetch } from "./api";

function StaffPinGate({ onSuccess, onBack }) {
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);

  async function submitPin(event) {
    event.preventDefault();
    if (!username.trim() || !pin.trim() || isVerifying) return;
    setIsVerifying(true);
    setError("");
    try {
      const response = await apiFetch("/staff/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim().toLowerCase(), pin: pin.trim() }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Incorrect PIN.");
      }
      const result = await response.json();
      onSuccess(result);
    } catch (verifyError) {
      setError(verifyError.message || "Unable to verify the PIN.");
      setPin("");
    } finally {
      setIsVerifying(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <div className="staff-pin-shell">
        <section className="chief-complaint-card staff-pin-card">
          <div className="section-kicker">MediKiosk · Staff access</div>
          <h1 className="staff-pin-heading">Staff sign in</h1>
          <p className="staff-pin-copy">Use your individual staff ID and PIN.</p>
          <form className="staff-pin-form" onSubmit={submitPin}>
            <input
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Staff ID"
              aria-label="Staff ID"
              disabled={isVerifying}
            />
            <input
              type="password"
              inputMode="numeric"
              autoComplete="current-password"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              placeholder="PIN"
              aria-label="Staff PIN"
              disabled={isVerifying}
            />
            <button type="submit" disabled={!username.trim() || !pin.trim() || isVerifying}>
              {isVerifying ? "Checking..." : "Unlock"}
            </button>
          </form>
          {error && <p className="error-message staff-pin-error" role="alert">{error}</p>}
          <button className="back-link staff-pin-back" type="button" onClick={onBack}>← Back to interview</button>
        </section>
      </div>
    </main>
  );
}

export default StaffPinGate;
