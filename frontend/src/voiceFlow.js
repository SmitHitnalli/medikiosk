import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
import { playAudioBlob, stopAllAudio } from "./audio";

const YES_WORDS = ["yes", "yeah", "yep", "correct", "right", "continue", "haan", "han", "हाँ", "हां", "सही", "जी"];
const NO_WORDS = ["no", "nope", "wrong", "incorrect", "nahin", "nahi", "नहीं", "नही", "गलत"];
const MAX_LISTEN_MS = 30000;
const SILENCE_AFTER_SPEECH_MS = 3200;
const MIN_LISTEN_MS = 1200;
const SPEECH_RMS_THRESHOLD = 0.011;

export function normaliseVoiceText(value = "") {
  return value.toLowerCase().replace(/[.,!?;:]/g, " ").replace(/\s+/g, " ").trim();
}

export function voiceYesNo(value) {
  const text = normaliseVoiceText(value);
  if (YES_WORDS.some((word) => text === word || text.includes(` ${word} `) || text.startsWith(`${word} `) || text.endsWith(` ${word}`))) return true;
  if (NO_WORDS.some((word) => text === word || text.includes(` ${word} `) || text.startsWith(`${word} `) || text.endsWith(` ${word}`))) return false;
  return null;
}

export function isCancelCommand(value) {
  const text = normaliseVoiceText(value);
  return ["cancel", "clear my data", "clear data", "start over", "radd", "data mita", "रद्द", "डेटा मिटा", "डाटा मिटा"].some((phrase) => text.includes(phrase));
}

export function isSwitchToChatCommand(value) {
  const text = normaliseVoiceText(value);
  return ["switch to chat", "change to chat", "use chat", "chat mode", "chat par", "type karna", "चैट पर", "चैट मोड", "टाइप करना"].some((phrase) => text.includes(phrase));
}

export function playBrowserSpeech(text, language) {
  if (!window.speechSynthesis) return Promise.reject(new Error("Speech playback is unavailable."));
  return new Promise((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === "hi" ? "hi-IN" : "en-IN";
    const voices = window.speechSynthesis.getVoices();
    utterance.voice = voices.find((voice) => voice.lang.toLowerCase() === utterance.lang.toLowerCase())
      || voices.find((voice) => voice.lang.toLowerCase().startsWith(language === "hi" ? "hi" : "en"))
      || null;
    utterance.rate = 0.94;
    utterance.onend = resolve;
    utterance.onerror = (event) => reject(new Error(event.error || "Browser speech failed."));
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  });
}

export function useVoiceFlow(language = "en") {
  const [state, setState] = useState("ready");
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");
  const activeRef = useRef(true);
  const operationRef = useRef(0);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const monitorRef = useRef(null);
  const audioContextRef = useRef(null);
  const pendingResolveRef = useRef(null);
  const controllersRef = useRef(new Set());

  const closeCapture = useCallback(() => {
    window.clearTimeout(timerRef.current);
    if (monitorRef.current) cancelAnimationFrame(monitorRef.current);
    monitorRef.current = null;
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const cancel = useCallback(() => {
    operationRef.current += 1;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    closeCapture();
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
    stopAllAudio();
    window.speechSynthesis?.cancel();
    pendingResolveRef.current?.("");
    pendingResolveRef.current = null;
  }, [closeCapture]);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      cancel();
    };
  }, [cancel]);

  const speak = useCallback(async (text, spokenLanguage = language) => {
    if (!text || !activeRef.current) return false;
    const operation = ++operationRef.current;
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
    stopAllAudio();
    setCaption(text);
    setError("");
    setState("speaking");
    const controller = new AbortController();
    controllersRef.current.add(controller);
    let played = false;
    try {
      const response = await apiFetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language: spokenLanguage || "en" }),
        signal: controller.signal,
      }, 45000);
      if (!response.ok) throw new Error("Speech playback is unavailable.");
      if (operation !== operationRef.current || !activeRef.current) return false;
      await playAudioBlob(await response.blob());
      played = true;
    } catch (speechError) {
      if (controller.signal.aborted || operation !== operationRef.current || speechError.name === "AbortError" || speechError.message === "Audio playback stopped.") return false;
      try {
        await playBrowserSpeech(text, spokenLanguage);
        played = true;
      } catch {
        if (activeRef.current && operation === operationRef.current) setError("The prompt is shown as a caption because audio is unavailable.");
      }
    } finally {
      controllersRef.current.delete(controller);
      if (activeRef.current && operation === operationRef.current) setState("ready");
    }
    return played;
  }, [language]);

  const listen = useCallback((listenLanguage = language, timeoutMs = MAX_LISTEN_MS) => new Promise((resolve, reject) => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      const unsupported = new Error("Microphone input is unavailable. Please use the buttons or keyboard.");
      setError(unsupported.message);
      reject(unsupported);
      return;
    }
    const operation = ++operationRef.current;
    pendingResolveRef.current = resolve;
    (async () => {
      try {
        stopAllAudio();
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        if (!activeRef.current || operation !== operationRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          resolve("");
          return;
        }
        const options = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? { mimeType: "audio/webm;codecs=opus" } : {};
        const recorder = new MediaRecorder(stream, options);
        streamRef.current = stream;
        recorderRef.current = recorder;
        chunksRef.current = [];
        recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
        recorder.onstop = async () => {
          closeCapture();
          if (recorderRef.current === recorder) recorderRef.current = null;
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
          chunksRef.current = [];
          if (!activeRef.current || operation !== operationRef.current || !blob.size) return resolve("");
          setState("thinking");
          const controller = new AbortController();
          controllersRef.current.add(controller);
          try {
            const formData = new FormData();
            formData.append("file", blob, "voice-answer.webm");
            formData.append("language", listenLanguage || "en");
            const response = await apiFetch("/transcribe", { method: "POST", body: formData, signal: controller.signal }, 45000);
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "I could not understand that answer.");
            const transcript = result.text?.trim() || "";
            if (!transcript) throw new Error("No speech was detected.");
            if (activeRef.current && operation === operationRef.current) {
              setCaption(transcript);
              setState("ready");
              setError("");
            }
            resolve(transcript);
          } catch (transcriptionError) {
            if (activeRef.current && operation === operationRef.current && !controller.signal.aborted) {
              setError(transcriptionError.message || "I could not understand that answer.");
              setState("error");
            }
            reject(transcriptionError);
          } finally {
            controllersRef.current.delete(controller);
            if (pendingResolveRef.current === resolve) pendingResolveRef.current = null;
          }
        };
        recorder.start(250);
        setError("");
        setState("listening");
        const startedAt = Date.now();
        let heardSpeech = false;
        let silenceStartedAt = null;
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
          const context = new AudioContextClass();
          const analyser = context.createAnalyser();
          analyser.fftSize = 2048;
          context.createMediaStreamSource(stream).connect(analyser);
          audioContextRef.current = context;
          void context.resume();
          const monitor = () => {
            if (recorder.state === "inactive" || operation !== operationRef.current) return;
            const samples = new Uint8Array(analyser.fftSize);
            analyser.getByteTimeDomainData(samples);
            const rms = Math.sqrt(samples.reduce((sum, sample) => sum + ((sample - 128) / 128) ** 2, 0) / samples.length);
            const now = Date.now();
            if (rms >= SPEECH_RMS_THRESHOLD) {
              heardSpeech = true;
              silenceStartedAt = null;
            } else if (heardSpeech && now - startedAt >= MIN_LISTEN_MS) {
              silenceStartedAt ??= now;
              if (now - silenceStartedAt >= SILENCE_AFTER_SPEECH_MS) {
                recorder.stop();
                return;
              }
            }
            monitorRef.current = requestAnimationFrame(monitor);
          };
          monitorRef.current = requestAnimationFrame(monitor);
        }
        timerRef.current = window.setTimeout(() => {
          if (recorder.state !== "inactive") recorder.stop();
        }, Math.max(10000, Math.min(timeoutMs, MAX_LISTEN_MS)));
      } catch (microphoneError) {
        closeCapture();
        const message = microphoneError.name === "NotAllowedError" ? "Microphone permission is required. Please allow it or use the screen." : "The microphone could not be opened. Please use the screen.";
        if (activeRef.current && operation === operationRef.current) {
          setError(message);
          setState("error");
        }
        reject(new Error(message));
      }
    })();
  }), [closeCapture, language]);

  const stopListening = useCallback(() => {
    window.clearTimeout(timerRef.current);
    if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop();
  }, []);

  const promptAndListen = useCallback(async (text, options = {}) => {
    const spokenLanguage = options.spokenLanguage || language;
    const listenLanguage = options.listenLanguage || language;
    const retryText = options.retryText || (listenLanguage === "hi"
      ? "मैं समझ नहीं पाया। कृपया फिर से बोलें।"
      : "I did not understand that. Please speak again.");
    const retries = options.retries ?? 1;
    await speak(text, spokenLanguage);
    if (!activeRef.current) return "";
    for (let attempt = 0; attempt <= retries; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 350));
      try {
        return await listen(listenLanguage, options.timeoutMs || MAX_LISTEN_MS);
      } catch (listenError) {
        if (!activeRef.current || attempt >= retries || /permission|unavailable|opened/i.test(listenError.message || "")) throw listenError;
        await speak(retryText, spokenLanguage);
      }
    }
    return "";
  }, [language, listen, speak]);

  return { state, caption, error, setError, speak, listen, promptAndListen, stopListening, cancel };
}
