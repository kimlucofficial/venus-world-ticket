@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto dependencies
py -3 -m venv .venv
if errorlevel 1 goto failed
:dependencies
if exist .venv\venus-installed goto run
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
type nul > .venv\venus-installed
:run
.venv\Scripts\python.exe bot.py
pause
exit /b
:failed
echo Khong cai duoc. Hay cai Python 3.12+ va kiem tra ket noi Internet.
pause
exit /b 1
