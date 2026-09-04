import { useState } from "react";

const VERIFY_PIN_ENDPOINT = "http://localhost:8080/staff/verify-pin";

// Hackathon-simple staff gate: one shared PIN, verified server-side (backend/.env
// STAFF_PIN) so it isn't just sitting in the frontend bundle. Not real per-user
// auth - matches the "prototype, not production" scope of the rest of the app.
function StaffPinGate({ onSuccess, onBack }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);

  async function submitPin(event) {
    event.preventDefault();
    if (!pin.trim() || isVerifying) return;
    setIsVerifying(true);
    setError("");
    try {
      const response = await fetch(VERIFY_PIN_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pin.trim() }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Incorrect PIN.");
      }
      onSuccess();
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
          <h1 className="staff-pin-heading">Enter staff PIN</h1>
          <p className="staff-pin-copy">This area is for hospital staff only.</p>
          <form className="staff-pin-form" onSubmit={submitPin}>
            <input
              type="password"
              inputMode="numeric"
              autoFocus
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              placeholder="PIN"
              aria-label="Staff PIN"
              disabled={isVerifying}
            />
            <button type="submit" disabled={!pin.trim() || isVerifying}>
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
