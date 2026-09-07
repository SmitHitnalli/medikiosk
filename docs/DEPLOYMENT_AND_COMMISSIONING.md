# Multi-kiosk deployment and commissioning

## Pilot architecture

Run one central MediKiosk API and record database inside the hospital network. Point every kiosk frontend to it with `VITE_API_URL`, and give each device a stable `VITE_KIOSK_ID`. Sessions, patient records, staff accounts, audit events, rate-limit attempts, care contexts, sign-offs, and alerts then share one authority. The kiosk ID is stored on each visit and shown on alerts.

The bundled SQLite database is suitable for a single-process hackathon or small supervised pilot. A production multi-process/high-availability deployment needs a managed relational database adapter, backups, encryption at rest, tested recovery, and data-retention rules approved by the hospital.

Staff login failures are stored in the shared database, so moving to another kiosk does not reset the five-attempt window. `/staff/fleet/status` gives administrators kiosk last-seen state plus active alert, visit, and pending-review counts. Each frontend health poll updates its kiosk heartbeat; a kiosk becomes offline after 90 seconds without a heartbeat.

Unacknowledged clinical alerts escalate after `ALERT_ESCALATION_SECONDS` and stay visibly escalated until a named staff member acknowledges them. The escalation and acknowledgement are audit events. Connect the central Nurse Station display to the same API and create a hospital-owned paging/SMS integration before an unattended rollout.

## TLS and network

The kiosk launcher now uses `backend/run_server.py`. Set both `TLS_CERT_FILE` and `TLS_KEY_FILE`; the launcher rejects incomplete or missing TLS files. A central deployment should normally terminate TLS at a managed reverse proxy, restrict API access to kiosk/staff subnets, set `FORWARDED_ALLOW_IPS` narrowly, and keep ABDM callbacks on a separately protected route.

## Commissioning checklist

Open **Device check** on the welcome screen on every installed kiosk and record the result for:

1. Touch: all corners, repeated taps, long press, on-screen keyboard, wet/gloved fingers if relevant, and 44-pixel controls.
2. Microphone: quiet room, busy OPD, soft voice, Hindi/English, different distances, silence-stop, and interruption.
3. Speaker: spoken prompts remain private and understandable at the chosen volume.
4. Camera: printed and handwritten pages, glare, low light, rotation, blur, and retake flow.
5. Network: central API loss and recovery, Ollama loss, delayed requests, and kiosk restart.
6. Privacy: identifiers are entered by touch, kiosk mode blocks navigation, no prior session remains, and screen placement limits shoulder surfing.
7. Alert drill: raise a test red flag, confirm the correct kiosk appears, wait for escalation, acknowledge it, and verify the audit entry.

The device page can check browser access and basic signal presence. A human must confirm audio quality, camera readability, touch accuracy, mounting, accessibility, cleaning, power backup, and network failover.

## Clinical validation

`backend/clinical_validation_cases.json` is a versioned, deidentified starter safety set. Run `python clinical_dataset_test.py` from `backend`; it must pass alongside `regression_test.py`. Add clinician-approved local-language paraphrases, negations, vulnerable-population scenarios, and representative hospital documents. Track sensitivity, specificity, extraction completeness, and clinician disagreement before changing a clinical rule.
