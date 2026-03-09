@echo off
title Self-Improving Trading Bot
cd /d "C:\Users\rlask\Downloads\backpack-advanced-bot-v2"

if not exist logs mkdir logs

:LOOP
echo.
echo ============================================================
echo  Self-Improving Bot Starting...  %DATE% %TIME%
echo ============================================================
echo.

python -X utf8 run_self_improving_bot.py

echo.
echo [!] Bot stopped or crashed. Restarting in 10 seconds...
echo     Press Ctrl+C to stop.
echo.
timeout /t 10 /nobreak
goto LOOP
