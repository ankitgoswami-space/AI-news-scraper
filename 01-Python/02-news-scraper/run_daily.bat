@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"

echo Starting daily refresh at %DATE% %TIME%

python src\refresh_all.py

echo Refresh finished at %DATE% %TIME%