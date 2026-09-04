import { Component } from "react";

// Catches unexpected render-time crashes (a malformed AI response shape that
// slips past validation, a null-reference bug, etc.) so a patient or doctor
// never sees a blank white screen mid-interview - the worst possible failure
// for a kiosk running unattended. A full reload is deliberately the only
// recovery path offered: it's the safest way to reset a kiosk's state after
// an error whose cause isn't known, and MediKiosk already treats a fresh
// session as the normal starting point (see the existing clear-data flow).
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Logged for whoever is debugging later - never shown to the patient, who
    // just needs to know what to do next, not a stack trace.
    console.error("MediKiosk crashed:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="start-shell">
          <section className="start-card" aria-label="Unexpected error" role="alert">
            <div className="brand-mark small" aria-hidden="true">M</div>
            <p className="start-eyebrow">MediKiosk</p>
            <h1>Something went wrong</h1>
            <p className="start-copy">
              Sorry about that - MediKiosk hit an unexpected error. Please restart below, or let a staff member
              know if this keeps happening.
            </p>
            <button className="start-button" type="button" onClick={() => window.location.reload()}>
              Restart MediKiosk
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
