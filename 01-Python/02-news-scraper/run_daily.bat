@echo off
REM Windows Task Scheduler wrapper for daily refresh

cd /d "%~dp0"

echo Starting daily refresh at %DATE% %TIME%

REM Full refresh — scrapers + V3 + V4 (chunked enrichers)
python src\refresh_all.py

echo Refresh finished at %DATE% %TIME%