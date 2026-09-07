import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";

function DeviceDiagnostics({ onBack }) {
  const [results, setResults] = useState({ touch: "waiting", network: "waiting", microphone: "waiting", camera: "waiting", speaker: "waiting" });
  const [cameraStream, setCameraStream] = useState(null);
  const videoRef = useRef(null);
  const streamsRef = useRef([]);

  useEffect(() => () => streamsRef.current.forEach((stream) => stream.getTracks().forEach((track) => track.stop())), []);
  useEffect(() => {
    if (cameraStream && videoRef.current) {
      videoRef.current.srcObject = cameraStream;
      videoRef.current.play().catch(() => setResult("camera", "failed"));
    }
  }, [cameraStream]);

  const setResult = (name, value) => setResults((current) => ({ ...current, [name]: value }));

  async function testNetwork() {
    setResult("network", "testing");
    try { const response = await apiFetch("/health", {}, 5000); setResult("network", response.ok ? "passed" : "failed"); }
    catch { setResult("network", "failed"); }
  }

  async function testMicrophone() {
    setResult("microphone", "testing");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); streamsRef.current.push(stream);
      const context = new AudioContext(); const source = context.createMediaStreamSource(stream); const analyser = context.createAnalyser(); source.connect(analyser);
      const values = new Uint8Array(analyser.frequencyBinCount); await new Promise((resolve) => setTimeout(resolve, 1000)); analyser.getByteFrequencyData(values);
      setResult("microphone", values.some((value) => value > 5) ? "passed" : "quiet");
      stream.getTracks().forEach((track) => track.stop()); await context.close();
    } catch { setResult("microphone", "failed"); }
  }

  async function testCamera() {
    setResult("camera", "testing");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }); streamsRef.current.push(stream);
      setCameraStream(stream); setResult("camera", "passed");
    } catch { setResult("camera", "failed"); }
  }

  function testSpeaker() {
    try {
      const context = new AudioContext(); const oscillator = context.createOscillator(); const gain = context.createGain();
      oscillator.frequency.value = 440; gain.gain.value = 0.08; oscillator.connect(gain).connect(context.destination); oscillator.start(); oscillator.stop(context.currentTime + 0.5);
      oscillator.onended = () => context.close(); setResult("speaker", "played");
    } catch { setResult("speaker", "failed"); }
  }

  const label = (value) => ({ waiting: "Not checked", testing: "Checking…", passed: "Passed", failed: "Needs attention", quiet: "Connected; speak louder and retry", played: "Tone played — confirm you heard it" }[value] || value);

  return (
    <main className="start-shell">
      <section className="start-card diagnostics-card">
        <p className="start-eyebrow">MediKiosk · Device check</p><h1>Commission this kiosk</h1>
        <p className="start-copy">Run these checks on the installed kiosk before patients use it.</p>
        <div className="diagnostic-list">
          <button type="button" className="diagnostic-test" onPointerDown={() => setResult("touch", "passed")}><strong>Touchscreen</strong><span>Touch and hold here</span><em>{label(results.touch)}</em></button>
          <button type="button" className="diagnostic-test" onClick={testNetwork}><strong>Backend connection</strong><span>Check the kiosk service</span><em>{label(results.network)}</em></button>
          <button type="button" className="diagnostic-test" onClick={testMicrophone}><strong>Microphone</strong><span>Speak while the one-second check runs</span><em>{label(results.microphone)}</em></button>
          <button type="button" className="diagnostic-test" onClick={testSpeaker}><strong>Speaker</strong><span>Play a short tone</span><em>{label(results.speaker)}</em></button>
          <button type="button" className="diagnostic-test" onClick={testCamera}><strong>Document camera</strong><span>Open a live preview</span><em>{label(results.camera)}</em></button>
        </div>
        {cameraStream && <video className="diagnostic-camera" ref={videoRef} muted playsInline aria-label="Camera preview" />}
        <button type="button" className="secondary-start-button" onClick={onBack}>Back to start</button>
      </section>
    </main>
  );
}

export default DeviceDiagnostics;
