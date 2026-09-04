# MediKiosk build roadmap

## Done
- [x] Git repository initialized and connected to GitHub
- [x] AGENTS.md and ROADMAP.md created
- [x] Backend skeleton (FastAPI, /health endpoint)
- [x] Conversation engine (/chat endpoint using Ollama)
- [x] Red-flag alert feature
- [x] Frontend chat UI
- [x] Doctor dashboard (fake data first)
- [x] Connect dashboard to real data
- [x] Robust Ollama JSON parsing and retry
- [x] Dashboard safely handles mismatched AI data types
- [x] Speech-to-text endpoint (/transcribe)
- [x] CPU-only faster-whisper configuration
- [x] Text-to-speech endpoint (/speak)
- [x] OCR endpoint
- [x] Language selection (spoken EN/HI prompt + manual buttons)
- [x] Consent screen with persistent cancel/clear-data option and localized Hindi audio fallback
- [x] Language selection, mode, and consent screen audio lifecycle, single-playback behavior, and Chat-mode silence
- [x] SQLite patient registry endpoints (Medi ID registration, masked lookup, prakriti update)
- [x] Patient identification screen with new and returning patient flows
- [x] Department selection screen with named AYUSH departments, general consultation option, and mode-respecting audio

## Next up (v2 feature plan)
- [x] Start button / idle screen with session clearing and idle timeout
- [x] Mode selection (Speak vs Chat, after language selection)
- [x] Medi ID system (fully tested: registration, lookup, returning-patient greeting, three-attempt lockout, masked phone display)
- [x] Department selection (fully tested: named departments, 'not sure/general' option, and mode-respecting audio)
- [x] Rewritten nurse-persona system prompt, AYUSH-default, hard cap at 15-20 exchanges
- [x] Department-only AYUSH routing and direct schema-shaped chat data responses
- [x] Removed legacy chat mode field; department is the sole AYUSH routing input
- [x] Prioritized immediate Agni/Vikriti questions for AYUSH departments
- [x] Deterministic per-turn question targeting and server-side chat data structure validation
- [x] Backend session-scoped data accumulation and non-destructive field merging
- [x] Guided multi-document scanning with confidence-based fallback chain (fuzzy match -> ask patient -> mark illegible)
- [x] Nurse Station live red-flag alert view
- [x] Staff PIN gate on doctor dashboard + Nurse Station (server-verified via STAFF_PIN in backend/.env, default 1234)
- [ ] Split frontend into frontend-patient/ and frontend-doctor/ (deferred: bigger/riskier restructure, no functional benefit beyond deployment packaging - single Vite app works fine for the demo)
- [x] Doctor dashboard: transcript view + trust ledger (history-completeness meter, red-flag audit with source attribution, document-verification summary)
- [x] Session data clearing confirmation UI (confirm dialog before wiping session data, self-contained in ClearDataButton so every screen picked it up automatically)
- [x] Performance polish: smaller Whisper model (small -> base), Ollama keep_alive (30m) on /chat and /ocr, OCR image downscaling (cap 1600px long side) - all verified live
- [x] Voice polish (backend half): /speak now accepts language and is wired for a real Hindi Piper voice; falls back safely to the English voice when Hindi voice files aren't present (verified live)
- [ ] Voice polish (remaining): download hi_IN-pratham-medium.onnx + .onnx.json from https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/hi/hi_IN/pratham/medium into backend/voices/, then flip the frontend's Hindi audio preference (currently browser speechSynthesis first, Piper as fallback - see ConsentScreen.jsx/DepartmentSelection.jsx/DocumentScanner.jsx/ModeSelection.jsx/PatientIdentification.jsx) to prefer the real Piper voice once it's in place
- [ ] Accessibility baseline (large fonts, high contrast, big touch targets, repeat button, help button)
- [ ] Graceful failure fallback screens
- [ ] Mock ABDM/FHIR push endpoint
- [ ] Kiosk-mode deployment setup
- [ ] Testing with sample patients
- [ ] Backup demo video

## Known gaps
- All Hindi audio currently uses browser speechSynthesis as a workaround; a real Hindi Piper voice should be downloaded and integrated during the voice polish step.
