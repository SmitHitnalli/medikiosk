import { useEffect, useState } from "react";
import { hasRepeatableAudio, repeatLastAudio } from "./audio";

const TEXT_SIZES = ["normal", "large", "xlarge"];
const TEXT_SIZE_LABELS = { normal: "A", large: "A+", xlarge: "A++" };
const STORAGE_KEY_SIZE = "medikiosk-text-size";
const STORAGE_KEY_CONTRAST = "medikiosk-high-contrast";
const HELP_REQUEST_ENDPOINT = "http://localhost:8080/nurse-station/help-request";
// Screens where staff themselves are looking at the alert feed - a "call for
// help" button there would be noise, not a useful patient-facing control.
const STAFF_PAGES = new Set(["dashboard", "nurse-station"]);

function readStoredTextSize() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY_SIZE);
    return TEXT_SIZES.includes(stored) ? stored : "normal";
  } catch {
    return "normal";
  }
}

function readStoredContrast() {
  try {
    return window.localStorage.getItem(STORAGE_KEY_CONTRAST) === "true";
  } catch {
    return false;
  }
}

// Kiosk-wide accessibility controls. Text size and high contrast apply via
// data attributes on <html> (see index.css) rather than component state, so
// they take effect on every screen no matter which one is currently mounted
// - this component only needs to be rendered once, anywhere. Preference is
// per-device (localStorage), not per-patient-session: a shared kiosk's
// display settings shouldn't reset just because the previous patient's
// session was cleared.
//
// Also hosts two more accessibility baseline controls: a "repeat" button that
// replays whatever prompt audio last played anywhere in the app (see
// audio.js), and a "help" button that patients can press on any patient-facing
// screen to notify staff via the Nurse Station alert feed.
function AccessibilityBar({ sessionId, department, patientName, page }) {
  const [textSize, setTextSize] = useState(readStoredTextSize);
  const [highContrast, setHighContrast] = useState(readStoredContrast);
  const [canRepeat, setCanRepeat] = useState(hasRepeatableAudio);
  const [helpStatus, setHelpStatus] = useState("idle"); // idle | sending | sent | error

  useEffect(() => {
    document.documentElement.dataset.textSize = textSize;
    try {
      window.localStorage.setItem(STORAGE_KEY_SIZE, textSize);
    } catch {
      // Private browsing / storage blocked - setting just won't persist.
    }
  }, [textSize]);

  useEffect(() => {
    document.documentElement.dataset.highContrast = highContrast ? "true" : "false";
    try {
      window.localStorage.setItem(STORAGE_KEY_CONTRAST, highContrast ? "true" : "false");
    } catch {
      // Private browsing / storage blocked - setting just won't persist.
    }
  }, [highContrast]);

  // Whether there's a prompt to repeat can change on any screen at any moment
  // (a prompt just finished loading and playing) without this component being
  // told directly, so a cheap poll is simpler and more robust than threading
  // an event or extra prop through every screen that plays audio.
  useEffect(() => {
    const interval = window.setInterval(() => setCanRepeat(hasRepeatableAudio()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  function cycleTextSize() {
    setTextSize((current) => TEXT_SIZES[(TEXT_SIZES.indexOf(current) + 1) % TEXT_SIZES.length]);
  }

  function handleRepeat() {
    void repeatLastAudio();
  }

  async function handleHelp() {
    if (helpStatus === "sending" || helpStatus === "sent") return;
    setHelpStatus("sending");
    try {
      const response = await fetch(HELP_REQUEST_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId || `anon-${Date.now()}`,
          patient_name: patientName || null,
          department: department || null,
        }),
      });
      if (!response.ok) throw new Error("Help request failed");
      setHelpStatus("sent");
      window.setTimeout(() => setHelpStatus("idle"), 15000);
    } catch {
      setHelpStatus("error");
      window.setTimeout(() => setHelpStatus("idle"), 5000);
    }
  }

  const showHelp = !STAFF_PAGES.has(page);
  const helpLabel =
    helpStatus === "sending" ? "Notifying staff..." : helpStatus === "sent" ? "Staff notified" : helpStatus === "error" ? "Could not reach staff - try again" : "Call for staff help";

  return (
    <div className="a11y-bar" role="group" aria-label="Accessibility settings">
      <button
        className="a11y-button"
        type="button"
        onClick={handleRepeat}
        disabled={!canRepeat}
        aria-label="Repeat the last spoken prompt"
        title="Repeat last prompt"
      >
        ↻
      </button>
      <button
        className="a11y-button"
        type="button"
        onClick={cycleTextSize}
        aria-label={`Text size: ${textSize}. Tap to change.`}
        title="Change text size"
      >
        {TEXT_SIZE_LABELS[textSize]}
      </button>
      <button
        className={`a11y-button ${highContrast ? "active" : ""}`}
        type="button"
        onClick={() => setHighContrast((current) => !current)}
        aria-pressed={highContrast}
        aria-label="Toggle high contrast"
        title="Toggle high contrast"
      >
        ◐
      </button>
      {showHelp && (
        <button
          className={`a11y-button a11y-help a11y-help-${helpStatus}`}
          type="button"
          onClick={handleHelp}
          disabled={helpStatus === "sending" || helpStatus === "sent"}
          aria-label={helpLabel}
          title={helpLabel}
        >
          {helpStatus === "sent" ? "✓" : "🆘"}
        </button>
      )}
    </div>
  );
}

export default AccessibilityBar;
