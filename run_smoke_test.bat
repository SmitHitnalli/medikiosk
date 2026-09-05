@echo off
setlocal
cd /d "%~dp0backend"
set "SMOKE_EXIT=0"
.venv\Scripts\python.exe regression_test.py
if errorlevel 1 (
    set "SMOKE_EXIT=1"
    goto :done
)
.venv\Scripts\python.exe smoke_test.py
if errorlevel 1 set "SMOKE_EXIT=1"
:done
echo.
echo Press any key to close this window...
pause >nul
exit /b %SMOKE_EXIT%
