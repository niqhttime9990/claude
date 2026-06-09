@echo off
REM Double-click to launch the Spotify Overlay on Windows.
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Node.js isn't installed. Get the LTS installer from https://nodejs.org
  echo  install it, then double-click this file again.
  echo.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Installing dependencies the first time, please wait...
  call npm install
  if errorlevel 1 (
    echo npm install failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)

call npm start
