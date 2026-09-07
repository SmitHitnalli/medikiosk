# MediKiosk — Claude Code build brief task tracker

Tracks every numbered item in `docs/CLAUDE_CODE_BUILD_BRIEF.md` against its final acceptance checklist.
Full rationale for each item lives in `ROADMAP.md`; this file is the flat status index the checklist asks for.

Status legend: **Fixed** (code changed) · **Confirmed-fine** (verified correct, no change needed) · **Escalated** (routed to Future Roadmap, not closed here).

## Phase 1 — Security — commit `1b320ed`
| # | Item | Status | Test |
|---|------|--------|------|
| 1 | XSS audit | Confirmed-fine | `test_chat_transcript_preserves_script_payload_as_literal_text` |
| 2 | Image decompression bomb | Fixed | `test_ocr_rejects_decompression_bomb_dimensions` |
| 3 | Session token storage (HttpOnly cookie) | Fixed | cookie-based session helpers across the suite; `assertNotIn("session_token", ...)` |
| 4 | Voice recording retention | Confirmed-fine | `test_transcribe_bytes_deletes_temp_file_after_success_and_failure` |
| 5 | `PATCH /patients/{medi_id}/prakriti` | Confirmed-fine | `test_prakriti_patch_endpoint_always_rejects_patient_writes` |
| 6 | Medi ID lookup lockout scope | Fixed | `test_medi_id_lookup_locks_by_medi_id_and_survives_a_new_session` |

## Phase 2 — Safety — commit `6629b4d`
| # | Item | Status | Test |
|---|------|--------|------|
| 1 | Untrusted-input framing for the LLM | Fixed | `test_prompt_injection_cannot_suppress_the_deterministic_red_flag` |
| 2 | Three new red-flag categories | Fixed | `test_new_red_flag_categories_are_detected_in_english_and_hindi`, `test_chat_exposes_red_flag_category_for_patient_facing_tone` |
| 3 | Nurse Station audible alarm | Fixed | Manual browser walkthrough (Web Audio output isn't verifiable from the Python suite) - open Nurse Station with an unacknowledged alert, confirm a tone plays and escalates past `ALERT_ESCALATION_SECONDS` |
| 4 | Alert de-duplication / SOS cooldown | Fixed | `test_repeated_red_flag_triggers_append_evidence_not_duplicate_alerts`, `test_help_request_is_rate_limited_by_a_cooldown` |
| 5 | Automatic session clear after export | Fixed | `test_patient_session_is_invalidated_once_the_record_is_exported` |
| 6 | Spoken read-back before submission | Fixed | `test_read_back_summary_builder_covers_english_and_hindi`, `test_chat_offers_read_back_before_marking_interview_done_for_the_patient`, `test_read_back_confirm_and_dispute_endpoints` |
| 7 | Consent screen TTS | Confirmed-fine | Code inspection: `ConsentScreen.jsx` already uses `/speak` in both languages |

## Phase 3 — Compliance and data hygiene — commit `ee7a147`
| # | Item | Status | Test |
|---|------|--------|------|
| 1 | Retention window + purge job | Fixed | `test_expired_patient_registry_entries_are_purged_but_recent_ones_kept` |
| 2 | Patient/staff-initiated erasure path | Fixed | `test_patient_can_erase_their_own_registry_entry`, `test_staff_can_erase_a_patient_registry_entry_on_request` |

## Phase 4 — Terminology and data-model alignment — commit `d52673e`
| # | Item | Status | Test |
|---|------|--------|------|
| 1 | Ahara-Vihara relabel | Fixed | `test_ahara_vihara_history_schema_key_unchanged` |
| 2 | Trividha/Ashtavidha Pariksha placeholders | Fixed | `test_dashavidha_trividha_and_ashtavidha_placeholders` |

## Phase 5 — UI/UX, accessibility, broken-feature refinement — commit `d52673e`
| # | Item | Status | Test |
|---|------|--------|------|
| 1 | Accessibility preference scope | Fixed | Reset control added; esbuild syntax check |
| 2 | Staff-side accessibility | Confirmed-fine | Code inspection: `AccessibilityBar` mounts on every page |
| 3 | Default color contrast (WCAG AA) | Fixed | `frontend/contrast_check.mjs` (6/6 pairs pass 4.5:1) |
| 4 | Devanagari font rendering (browser + PDF) | Fixed | `test_pdf_uses_bundled_devanagari_font_even_without_os_fonts` |
| 5 | Loading/thinking feedback | Fixed (Speak mode) / Confirmed-fine (Chat mode) | esbuild syntax check; Chat mode's existing typing-dots animation |
| 6 | Speak → Chat mid-interview cleanup | Fixed | Code fix (`discardActiveRecording`); esbuild syntax check |
| 7 | Device Check resource teardown | Confirmed-fine | Code inspection: unmount cleanup stops all tracks |
| 8 | "Repeat last spoken prompt" staleness | Fixed | `frontend/audio_repeat_check.mjs` |
| 9 | Locked staff view background polling | Confirmed-fine | Code inspection: unmount clears both poll intervals |
| 10 | Formulary suggestions patient-facing boundary | Confirmed-fine | Code inspection: patient view shows counts only |
| 11 | Red-flag banner tone differentiation | Confirmed-fine | Code inspection: distinct calm vs. urgent alert markup already exists |
| 12 | Kiosk identity visibility | Fixed | `frontend/kiosk_identity_check.mjs` |

None of the 29 items required escalation to the Future Roadmap.

## Verification run (this session, Phase 4 + 5 work)
- `backend/regression_test.py`: 43/43 passing
- `frontend` production bundle (`App.jsx` + all touched components): esbuild clean
- `frontend/contrast_check.mjs`, `frontend/audio_repeat_check.mjs`, `frontend/kiosk_identity_check.mjs`: all passing

## Hands-free voice and kiosk UI redesign — commit `d52673e`

- Automatic bilingual consent, language, interaction-mode, identity, phone, Medi ID, department, and clinical-interview voice flow: **Fixed and live-tested**
- Spoken clear-data and Speak-to-Chat confirmation: **Fixed**
- Captions, typed fallbacks, and three-attempt Medi ID behavior: **Fixed**
- Stateful orb, light/dark theme, and 1366×768 patient-screen fit: **Fixed and visually verified**
- Chromium recorder codec media type compatibility: **Fixed**, covered by `test_transcribe_accepts_browser_codec_content_type`

## Outstanding

- No open engineering item remains in this build brief. Physical microphone acoustics, real Bhashini/AI4Bharat credentials, and ABDM Sandbox certification remain deployment gates documented in `ROADMAP.md`.
