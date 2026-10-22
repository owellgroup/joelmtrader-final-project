@echo off
REM Bridge from the cloud Python engine to the MT5 desktop on this PC.
REM 1. Open MetaTrader 5 and log in. Algo Trading must be green.
REM 2. Double-click this file and leave the window open.
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Install Python 3 from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv-bridge (
  python -m venv .venv-bridge
)
call .venv-bridge\Scripts\activate.bat
python -m pip install --upgrade pip
REM numpy must be below 2: MetaTrader5 cannot send orders with numpy 2.x
pip install "MetaTrader5>=5.0.45" "websockets>=13" "numpy>=1.26,<2"
echo.
echo This PC connects out to the server. No router port forward is required.
echo Leave this window open. Leave MetaTrader 5 open and logged in.
echo.
python mt5_bridge.py
pause
