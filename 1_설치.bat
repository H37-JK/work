@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] playwright install...
py -m pip install --upgrade playwright anthropic
echo [2/2] browser install...
py -m playwright install chromium
echo.
echo Done. Next: 2_로그인.bat
pause
