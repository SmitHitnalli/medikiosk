@echo off
start "MediKiosk Backend" cmd /k "cd /d C:\Smit\medikiosk\backend && .venv\Scripts\uvicorn.exe main:app --reload --port 8080"
start "MediKiosk Frontend" cmd /k "cd /d C:\Smit\medikiosk\frontend && npm run dev"
