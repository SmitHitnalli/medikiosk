# MediKiosk build roadmap

## Done
- [x] Complete MediKiosk product and SIH26047 study guide exported as `output/pdf/MediKiosk_Complete_Product_Guide.pdf` (20-page A4 PDF with workflows, architecture, usage, limitations, setup, demo plan, judge Q&A, and sources; rendered and visually verified page by page)
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
- [x] Voice polish (remaining): real hi_IN-pratham-medium Hindi voice downloaded into backend/voices/ (by smit) and verified live (backend correctly loads and synthesizes Devanagari text). Frontend preference flipped in all 5 screens (ConsentScreen, DepartmentSelection, DocumentScanner, ModeSelection, PatientIdentification) to prefer the real Piper voice, with browser speechSynthesis now only a last-resort fallback if Piper playback itself fails.
- [x] Accessibility baseline: global text-size (A/A+/A++ via CSS zoom) and high-contrast toggle (persisted in localStorage, applied via data attributes on <html> so it survives page navigation), 44px minimum touch targets on all interactive controls, a repeat button that replays the last spoken prompt from anywhere in the app, and a help button that posts a patient-initiated help request into the same Nurse Station alert feed as red-flag alerts (shown with a distinct amber badge). LanguageSelection.jsx's independent Hindi-audio path was also brought in line with the real Piper voice (was still using the browser-placeholder-first order and stale "known gap" copy).
- [x] Graceful failure fallback screens: ErrorBoundary (class component wrapping the whole app in main.jsx) catches unexpected render crashes with a friendly "Restart MediKiosk" screen instead of a blank page; SystemStatusGate polls /health every 8s and distinguishes backend-unreachable (full-screen block, auto-retries) from backend-up-but-Ollama-down (non-blocking banner, since patient ID/department/Nurse Station don't need Ollama). /health now also reports Ollama reachability (short-timeout probe of its /api/tags).
- [x] Mock ABDM/FHIR push endpoint: POST /abdm/push builds a real FHIR-shaped Bundle (Patient, Condition, MedicationStatement, AllergyIntolerance, Flag for red flags, plus Condition/MedicationStatement/Observation entries from digitized documents) from the session's accumulated chat data, "pushes" it by recording it server-side with a mock ABDM reference (no real ABDM sandbox reachable from this environment), and GET /abdm/push/{session_id} retrieves it. Doctor dashboard gained a "Push to ABDM/HIS" card with push status, a mock reference, and a collapsible raw-Bundle viewer - disabled for the sample patient. Verified live end-to-end against the real /chat-populated session data.
- [x] Kiosk-mode deployment setup: kiosk-mode.bat starts the dev servers if needed and opens the app full-screen in Chrome's --kiosk mode (Edge fallback), no address bar/tabs/way to navigate away. App-level hardening: right-click/context menu disabled app-wide, pinch/double-tap zoom disabled, text selection disabled except on doctor-facing transcript/summary/FHIR-bundle text. docs/KIOSK.md documents the genuine OS-level steps (screen sleep, auto-login, Windows-key lockdown) left as manual, conscious setup on the physical kiosk machine rather than something a script silently changes.
- [x] Testing with sample patients: ran all 3 of docs/conversation_scripts.md's scripts as real multi-turn /chat conversations against the live backend (general OPD chest pain, red-flag chest pain + breathlessness, AYUSH digestive complaint) - not scripted replays, genuine Ollama inference each turn. Verified: no false-positive red flag on the benign case, the red-flag case correctly triggers on its first turn and lands in the Nurse Station feed with the right reason/source, AYUSH fields populate for the ayush script, and a full ABDM push produces a correct Bundle from the resulting session data. See Known gaps for a data-extraction completeness observation worth being aware of before the live demo.
- [ ] Backup demo video

## Known gaps
- [x] Engineering audit remediation completed on 2026-09-05: all B01-B40 findings in `docs/BUG_AUDIT_2026-09-05.md` were fixed. Added authenticated SQLite-backed sessions, scoped patient/staff authorization, deterministic emergency persistence, strict clinical schema validation, complete interview scheduling, physician-review export gating, refresh recovery, bilingual patient UI, request/audio/recording lifecycle cleanup, fixed-port launchers, and isolated regression coverage. Final checks: backend regressions 12/12, frontend production build, Python compile, schema parse, `pip check`, `git diff --check`, npm production audit (0 advisories), and a browser walkthrough of the Hindi patient journey plus English staff views.
- (Resolved) Hindi audio now uses a real Piper voice (hi_IN-pratham-medium); browser speechSynthesis is a last-resort fallback only.
- Clinical rule quality, Hindi pronunciation, OCR accuracy across real hospital documents, microphone/camera behavior on the physical kiosk, and FHIR/ABDM conformance still require clinician/device/integration validation. These are validation limits for the prototype rather than known broken engineering flows.
