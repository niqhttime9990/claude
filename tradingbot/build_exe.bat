@echo off
rem Build a single-file Windows executable of the ctabot simulator.
rem Run this on Windows from the tradingbot\ directory:
rem     build_exe.bat
rem Output: dist\ctabot-simulator.exe
rem
rem The exe defaults to LIVE paper-trading mode (replay mode needs the
rem repo's data\ directory next to the exe; copy it if you want replays).

where python >nul 2>nul || (echo Python not found in PATH & exit /b 1)
python -m pip install --upgrade pyinstaller yfinance pandas numpy scipy || exit /b 1

python -m PyInstaller --onefile --name ctabot-simulator ^
  --collect-submodules yfinance ^
  --hidden-import simulator --hidden-import ctabot ^
  --paths . ^
  scripts\run_simulator_exe.py

echo.
echo Done: dist\ctabot-simulator.exe
echo Double-click it (or run from cmd) and the dashboard opens in your browser.
