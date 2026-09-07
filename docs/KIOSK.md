# Kiosk-mode deployment

For central multi-kiosk rollout, TLS, alert drills, device checks, and clinical validation, also follow `docs/DEPLOYMENT_AND_COMMISSIONING.md`.

How to run MediKiosk the way an actual ward deployment (or the live SIH demo) would - full-screen, no browser chrome, no way to navigate away.

## Quick start
Double-click `kiosk-mode.bat` in the repo root. It starts the backend and frontend dev servers if they aren't already running, waits for them to come up, then opens the app in Chrome's `--kiosk` mode (falls back to Edge if Chrome isn't installed).

The launcher checks ports 8080 and 5173 independently and fails clearly if both services are not ready within 30 seconds. Paths are resolved from the script location, so the repository can be moved. Vite is pinned to port 5173 rather than silently selecting a different port.

For another device on the same private network, open `http://<kiosk-host>:5173`; the frontend automatically calls port 8080 on that same host and the backend accepts private-LAN Vite origins. Set `VITE_API_URL` before starting Vite when the API lives at a different origin.

Run `run_smoke_test.bat` while the backend and Ollama are running to execute the fast isolated regression suite followed by the real Ollama, EasyOCR, Whisper, and Piper workflow. Its generated visit, alert, export, and registry test record are cleaned up afterward.

**To exit:** Alt+F4 closes the kiosk browser window. There's no in-app way out by design - that's the point of kiosk mode.

## What kiosk-mode.bat does *not* do
These are genuine OS-level changes and are left as manual, conscious steps for whoever is setting up the physical kiosk machine, rather than something a script silently changes:

- **Disable sleep / screen lock while the kiosk is in use** — Windows Settings → System → Power & battery → Screen and sleep, set both to "Never" (or use `powercfg`), on the specific machine that will run as the physical kiosk. Don't do this on a shared/personal dev machine.
- **Disable the Windows key and Alt+Tab** so a patient can't switch away to the desktop — needs either Group Policy (`gpedit.msc`, not available on Home editions) or a dedicated kiosk-lockdown tool; out of scope for a hackathon prototype but a real pre-deployment step.
- **Auto-login + auto-launch on boot** — set the machine to auto-login to a dedicated kiosk user account, with `kiosk-mode.bat` in that user's Startup folder, so the kiosk comes back up on its own after a power cycle.
- **Auto-restart the dev servers if they crash** — the current setup is hackathon-simple (`--reload` uvicorn + `npm run dev`, not a production process manager). A real deployment would run the backend behind something like NSSM (a Windows service wrapper) or build the frontend (`npm run build`) and serve the static output, rather than running Vite's dev server continuously.

## App-level kiosk hardening (already built in)
- Right-click / context menu is disabled app-wide (`main.jsx`) - no "Inspect"/"View source" escape hatch.
- Pinch-zoom and double-tap-zoom are disabled (`touch-action: manipulation` in `index.css`) so they don't fight with the app's own text-size control.
- Text selection is disabled everywhere except the doctor dashboard's transcript/summary text and the FHIR bundle viewer, where a physician might actually want to copy something.
- The app already has its own idle timeout that clears session data and returns to the start screen (see ROADMAP.md) - this is the intended way a kiosk resets between patients, not an OS-level timeout.
