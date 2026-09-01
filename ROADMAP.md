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
- [ ] Guided multi-document scanning with confidence-based fallback chain (fuzzy match -> ask patient -> mark illegible)
- [ ] Nurse Station live red-flag alert view
- [ ] Split frontend into frontend-patient/ and frontend-doctor/, staff PIN gate on doctor app
- [ ] Doctor dashboard: transcript view + trust ledger
- [ ] Session data clearing confirmation UI
- [ ] Voice polish (alternate Piper voice) and performance polish (smaller Whisper model, Ollama keep-alive, image downscaling)
- [ ] Accessibility baseline (large fonts, high contrast, big touch targets, repeat button, help button)
- [ ] Graceful failure fallback screens
- [ ] Mock ABDM/FHIR push endpoint
- [ ] Kiosk-mode deployment setup
- [ ] Testing with sample patients
- [ ] Backup demo video

## Known gaps
- All Hindi audio currently uses browser speechSynthesis as a workaround; a real Hindi Piper voice should be downloaded and integrated during the voice polish step.
