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

## Next up (v2 feature plan)
- [x] Start button / idle screen with session clearing and idle timeout
- [ ] Consent screen with persistent cancel/clear-data option
- [ ] Mode selection (hands-free vs chat)
- [ ] Medi ID system (patients table: medi_id, name, phone, prakriti; non-sequential IDs, lockout after 3 failed attempts, masked phone display)
- [ ] Department selection (named departments + 'not sure/general' option)
- [ ] Rewritten nurse-persona system prompt, AYUSH-default, hard cap at 15-20 exchanges
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
