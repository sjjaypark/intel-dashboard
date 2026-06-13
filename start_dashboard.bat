@echo off
cd /d D:\AI_Research
start "Intelligence Dashboard" python -m uvicorn app:app --port 8000
timeout /t 3 /nobreak > nul
start "" "http://localhost:8000"
