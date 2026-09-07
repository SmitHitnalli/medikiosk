@echo off
setlocal
set "MEDIKIOSK_ROOT=%~dp0"

netstat -ano | findstr /R /C:":8080 .*LISTENING" >nul
if errorlevel 1 start "MediKiosk Backend" cmd /k "cd /d ""%MEDIKIOSK_ROOT%backend"" && .venv\Scripts\python.exe run_server.py"

netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul
if errorlevel 1 start "MediKiosk Frontend" cmd /k "cd /d ""%MEDIKIOSK_ROOT%frontend"" && npm run dev"

endlocal
