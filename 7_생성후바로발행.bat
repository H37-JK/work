@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
py -m pip install --upgrade --quiet anthropic
py allinone.py
pause
