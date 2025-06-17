@echo off
title LATARA Trading - Daily Auto Update
color 0C

:: Set working directory
cd /d "%~dp0"

:: Log file for updates
set LOG_FILE=update-log.txt
echo [%date% %time%] Starting daily auto-update check >> %LOG_FILE%

:: Check for updates silently
git fetch origin >> %LOG_FILE% 2>&1

:: Check if there are updates
for /f %%i in ('git rev-list HEAD..origin/main --count 2^>nul') do set UPDATE_COUNT=%%i

if "%UPDATE_COUNT%"=="0" (
    echo [%date% %time%] No updates available >> %LOG_FILE%
    exit /b 0
)

echo [%date% %time%] Found %UPDATE_COUNT% updates, applying... >> %LOG_FILE%

:: Backup production files
copy cloudflare-credentials.json cloudflare-credentials.json.bak >nul 2>&1
copy cloudflared.yml cloudflared.yml.bak >nul 2>&1
copy run-latara.bat run-latara.bat.bak >nul 2>&1

:: Apply updates
git stash push -m "Auto-update stash %date% %time%" >> %LOG_FILE% 2>&1
git pull origin main >> %LOG_FILE% 2>&1

:: Restore production files
copy cloudflare-credentials.json.bak cloudflare-credentials.json >nul 2>&1
copy cloudflared.yml.bak cloudflared.yml >nul 2>&1
copy run-latara.bat.bak run-latara.bat >nul 2>&1

:: Clean backup files
del *.bak >nul 2>&1

:: Update dependencies and migrate
pip install -r requirements.txt --quiet >> %LOG_FILE% 2>&1
python manage.py migrate --noinput >> %LOG_FILE% 2>&1
python manage.py collectstatic --noinput --clear >> %LOG_FILE% 2>&1

echo [%date% %time%] Auto-update completed successfully >> %LOG_FILE%

:: Keep only last 30 days of logs
for /f "skip=100 delims=" %%i in ('type %LOG_FILE%') do echo %%i > %LOG_FILE%.tmp
if exist %LOG_FILE%.tmp (
    move %LOG_FILE%.tmp %LOG_FILE% >nul
)

exit /b 0
