@echo off
REM Launches MediKiosk full-screen in kiosk mode: no address bar, no tabs, no
REM way to navigate away - for the live SIH demo and for how an actual ward
REM deployment would run. Starts the dev servers first (same as
REM start-dev.bat) if they aren't already running, waits for them to come up,
REM then opens the browser locked down.
REM
REM To exit kiosk mode: Alt+F4 closes the browser window.

netstat -ano | findstr ":5173" >nul
if %errorlevel% neq 0 (
    echo Starting MediKiosk dev servers...
    start "MediKiosk Backend" cmd /k "cd /d C:\Smit\medikiosk\backend && .venv\Scripts\uvicorn.exe main:app --reload --port 8080"
    start "MediKiosk Frontend" cmd /k "cd /d C:\Smit\medikiosk\frontend && npm run dev"
    echo Waiting for them to come up...
    timeout /t 10 /nobreak >nul
) else (
    echo MediKiosk dev servers already running - reusing them.
)

set CHROME_PATH="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_PATH% set CHROME_PATH="%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME_PATH% set CHROME_PATH="%LocalAppData%\Google\Chrome\Application\chrome.exe"

if exist %CHROME_PATH% (
    start "" %CHROME_PATH% --kiosk --incognito --noerrdialogs --disable-pinch --overscroll-history-navigation=0 http://localhost:5173
) else (
    echo Chrome not found at the usual install paths - falling back to Edge.
    start "" msedge --kiosk --inprivate --noerrdialogs --edge-kiosk-type=fullscreen http://localhost:5173
)
