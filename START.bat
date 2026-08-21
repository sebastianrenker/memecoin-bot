@echo off
REM Memecoin Paper-Trading Analysis Tool - Windows launcher
REM SIMULATED MONEY ONLY. Live trading is locked. Memecoins mostly go to zero.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

:menu
echo.
echo ============================================================
echo   MEMECOIN PAPER TRADER  --  SIMULATED MONEY ONLY
echo   Live trading is locked. Not advice. Memecoins go to zero.
echo ============================================================
echo   [1] Install dependencies (pip install -r requirements.txt)
echo   [2] Doctor (self-test)
echo   [3] Doctor + real data check
echo   [4] Rank strategies on real data (save to db)
echo   [5] Export active combos (active_combos.yaml)
echo   [6] Serve paper trader (Ctrl-C to stop)
echo   [7] One ci-tick (writes BOT_STATUS_REPORT.md)
echo   [8] Open dashboard (streamlit)
echo   [9] Run tests (pytest -q)
echo   [0] Exit
echo.
set /p choice="Choose: "

if "%choice%"=="1" ( python -m pip install -r requirements.txt & goto menu )
if "%choice%"=="2" ( python cli.py doctor & goto menu )
if "%choice%"=="3" ( python cli.py doctor --data & goto menu )
if "%choice%"=="4" ( python cli.py rank --db --limit 40 & goto menu )
if "%choice%"=="5" ( python cli.py export-active --min-score 55 & goto menu )
if "%choice%"=="6" ( python cli.py serve & goto menu )
if "%choice%"=="7" ( python cli.py ci-tick & goto menu )
if "%choice%"=="8" ( streamlit run dashboard/app.py & goto menu )
if "%choice%"=="9" ( python -m pytest -q & goto menu )
if "%choice%"=="0" ( exit /b 0 )
goto menu
