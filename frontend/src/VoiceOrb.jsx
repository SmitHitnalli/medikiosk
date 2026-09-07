function VoiceOrb({ state = "ready", compact = false, label }) {
  const stateLabels = {
    ready: "Ready",
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    paused: "Paused",
    error: "Needs attention",
  };
  const visibleLabel = label || stateLabels[state] || stateLabels.ready;

  return (
    <div className={`voice-orb-wrap ${compact ? "compact" : ""}`} role="status" aria-live="polite" aria-label={`MediKiosk voice: ${visibleLabel}`}>
      <div className={`voice-orb ${state}`} aria-hidden="true">
        <span className="voice-orb-halo halo-one" />
        <span className="voice-orb-halo halo-two" />
        <span className="voice-orb-glow" />
        <span className="voice-orb-core" />
        <span className="voice-orb-shine" />
        <span className="voice-orb-wave wave-one" />
        <span className="voice-orb-wave wave-two" />
        <span className="voice-orb-wave wave-three" />
      </div>
      <p className="voice-orb-label">{visibleLabel}</p>
    </div>
  );
}

export function OrbSelectionLayout({ children, state = "ready", label, caption = "" }) {
  return (
    <main className="start-shell orb-selection-shell">
      <div className="orb-selection-layout">
        <div className="orb-selection-visual">
          <p className="orb-brand">MediKiosk</p>
          <VoiceOrb state={state} label={label} />
          {caption && <p className="orb-live-caption" aria-live="polite">{caption}</p>}
          <p className="orb-support-copy">Touch a choice or use your voice.</p>
        </div>
        {children}
      </div>
    </main>
  );
}

export default VoiceOrb;
