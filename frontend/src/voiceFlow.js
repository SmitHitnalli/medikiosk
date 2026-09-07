import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
import { playAudioBlob, stopAllAudio } from "./audio";

const YES_WORDS = ["yes", "yeah", "yep", "correct", "right", "continue", "haan", "han", "हाँ", "हां", "सही", "जी"];
const NO_WORDS = ["no", "nope", "wrong", "incorrect", "nahin", "nahi", "नहीं", "नही", "गलत"];

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
  return ["cancel", "clear my data", "clear data", "start over", "रद्द", "डेटा मिटा", "डाटा मिटा"].some((phrase) => text.includes(phrase));
}

export function isSwitchToChatCommand(value) {
  const text = normaliseVoiceText(value);
  return ["switch to chat", "change to chat", "use chat", "chat mode", "चैट पर", "चैट मोड", "टाइप करना"].some((phrase) => text.includes(phrase));
}

function browserSpeech(text, language) {
  if (!window.speechSynthesis) return Promise.reject(new Error("Speech playback is unavailable."));
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === "hi" ? "hi-IN" : "en-IN";
    utterance.onend = resolve;
    utterance.onerror = resolve;
    window.speechSynthesis.speak(utterance);
  });
}

export function useVoiceFlow(language = "en") {
  const [state, setState] = useState("ready");
  const [caption, setCaption] = useState("");
  const [error, setError] = useState("");
  const activeRef = useRef(true);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const controllersRef = useRef(new Set());

  const cancel = useCallback(() => {
    window.clearTimeout(timerRef.current);
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
    stopAllAudio();
    window.speechSynthesis?.cancel();
  }, []);

  useEffect(() => {
    activeRef.current = true;
    return () => {
      activeRef.current = false;
      cancel();
    };
  }, [cancel]);

  const speak = useCallback(async (text, spokenLanguage = language) => {
    if (!text || !activeRef.current) return;
    stopAllAudio();
    window.speechSynthesis?.cancel();
    setCaption(text);
    setError("");
    setState("speaking");
    const controller = new AbortController();
    controllersRef.current.add(controller);
    try {
      const response = await apiFetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language: spokenLanguage || "en" }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Speech playback is unavailable.");
      await playAudioBlob(await response.blob());
    } catch (speechError) {
      if (controller.signal.aborted || speechError.name === "AbortError" || speechError.message === "Audio playback stopped.") return;
      await browserSpeech(text, spokenLanguage).catch(() => {
        if (activeRef.current) setError("The prompt is shown as a caption because audio is unavailable.");
      });
    } finally {
      controllersRef.current.delete(controller);
      if (activeRef.current) setState("ready");
    }
  }, [language]);

  const listen = useCallback((listenLanguage = language, timeoutMs = 6500) => new Promise((resolve, reject) => {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      const unsupported = new Error("Microphone input is unavailable. Please use the buttons or keyboard.");
      setError(unsupported.message);
      reject(unsupported);
      return;
    }
    (async () => {
      try {
        stopAllAudio();
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!activeRef.current) {
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
          window.clearTimeout(timerRef.current);
          stream.getTracks().forEach((track) => track.stop());
          if (streamRef.current === stream) streamRef.current = null;
          if (recorderRef.current === recorder) recorderRef.current = null;
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
          chunksRef.current = [];
          if (!activeRef.current || !blob.size) return resolve("");
          setState("thinking");
          const controller = new AbortController();
          controllersRef.current.add(controller);
          try {
            const formData = new FormData();
            formData.append("file", blob, "voice-answer.webm");
            formData.append("language", listenLanguage || "en");
            const response = await apiFetch("/transcribe", { method: "POST", body: formData, signal: controller.signal });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || "I could not understand that answer.");
            const transcript = result.text?.trim() || "";
            if (!transcript) throw new Error("I did not hear an answer. Please try again or use the screen.");
            if (activeRef.current) {
              setCaption(transcript);
              setState("ready");
            }
            resolve(transcript);
          } catch (transcriptionError) {
            if (activeRef.current && !controller.signal.aborted) {
              setError(transcriptionError.message || "I could not understand that answer.");
              setState("error");
            }
            reject(transcriptionError);
          } finally {
            controllersRef.current.delete(controller);
          }
        };
        recorder.start();
        setError("");
        setState("listening");
        timerRef.current = window.setTimeout(() => {
          if (recorder.state !== "inactive") recorder.stop();
        }, timeoutMs);
      } catch (microphoneError) {
        const message = microphoneError.name === "NotAllowedError" ? "Microphone permission is required. Please allow it or use the screen." : "The microphone could not be opened. Please use the screen.";
        if (activeRef.current) {
          setError(message);
          setState("error");
        }
        reject(new Error(message));
      }
    })();
  }), [language]);

  const stopListening = useCallback(() => {
    window.clearTimeout(timerRef.current);
    if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop();
  }, []);

  const promptAndListen = useCallback(async (text, options = {}) => {
    await speak(text, options.spokenLanguage || language);
    if (!activeRef.current) return "";
    await new Promise((resolve) => window.setTimeout(resolve, 220));
    return listen(options.listenLanguage || language, options.timeoutMs || 6500);
  }, [language, listen, speak]);

  return { state, caption, error, setError, speak, listen, promptAndListen, stopListening, cancel };
}
