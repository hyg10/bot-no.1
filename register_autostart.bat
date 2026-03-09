@echo off
echo Registering bot as Windows startup program...

set "BOT_DIR=C:\Users\rlask\Downloads\backpack-advanced-bot-v2"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP%\TradingBot.bat"

copy "%BOT_DIR%\start_bot.bat" "%SHORTCUT%"

echo.
echo Done! The bot will now auto-start when Windows boots.
echo Shortcut created at:
echo   %SHORTCUT%
echo.
echo To remove auto-start, delete:
echo   %SHORTCUT%
echo.
pause
