@echo off
echo Starting WINS Agent Development Environment...
echo.

:: Start Backend
echo [1/2] Starting Backend Server...
start "WINS Agent Backend" cmd /k "cd /d %~dp0\..\backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

:: Wait for backend to start
timeout /t 3 /nobreak > nul

:: Start Frontend
echo [2/2] Starting Frontend Dev Server...
start "WINS Agent Frontend" cmd /k "cd /d %~dp0\..\frontend && npm run dev"

echo.
echo Development servers started!
echo - Backend: http://localhost:8000
echo - Frontend: http://localhost:3000
echo - API Docs: http://localhost:8000/docs
echo.
pause
