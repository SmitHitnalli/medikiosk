@echo off
setlocal
set "MEDIKIOSK_ROOT=%~dp0"

netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul
if errorlevel 1 (
    echo Starting MediKiosk backend...
    start "MediKiosk Backend" cmd /k "cd /d ""%MEDIKIOSK_ROOT%backend"" && .venv\Scripts\python.exe run_server.py"
)

netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul
if errorlevel 1 (
    echo Starting MediKiosk frontend...
    start "MediKiosk Frontend" cmd /k "cd /d ""%MEDIKIOSK_ROOT%frontend"" && npm run dev"
)

echo Waiting for MediKiosk services...
for /L %%G in (1,1,30) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/health -TimeoutSec 1).StatusCode -eq 200 -and (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 -TimeoutSec 1).StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
    if not errorlevel 1 goto services_ready
    timeout /t 1 /nobreak >nul
)
echo MediKiosk did not become ready. Check the backend and frontend windows.
exit /b 1

:services_ready
set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if exist "%CHROME_PATH%" (
    start "" "%CHROME_PATH%" --kiosk --incognito --noerrdialogs --disable-pinch --overscroll-history-navigation=0 http://localhost:5173
) else (
    echo Chrome not found; opening Microsoft Edge kiosk mode.
    start "" msedge --kiosk --inprivate --noerrdialogs --edge-kiosk-type=fullscreen http://localhost:5173
)

endlocal
