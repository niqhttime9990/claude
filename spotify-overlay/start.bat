@echo off
setlocal
cd /d "%~dp0"

REM --- must be run from the extracted folder, not from inside the zip ---
if not exist "package.json" (
  echo.
  echo  ERROR: package.json is not in this folder.
  echo  You probably launched start.bat from INSIDE the .zip. Right-click the
  echo  downloaded zip -^> "Extract All", then run start.bat from the
  echo  extracted folder.
  echo.
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Node.js isn't on PATH. Install the LTS build from https://nodejs.org,
  echo  then CLOSE this window, reopen the folder, and run start.bat again.
  echo.
  pause
  exit /b 1
)

echo Node version:
node -v
echo.

if not exist "node_modules\electron\dist\electron.exe" (
  echo Installing dependencies the first time - this downloads Electron ~100 MB.
  echo Please wait, it can take a few minutes...
  echo.
  call npm install
  if errorlevel 1 (
    echo.
    echo  npm install FAILED ^(see the red text above^). Usual causes: no
    echo  internet, a proxy, or antivirus blocking the Electron download.
    echo.
    pause
    exit /b 1
  )
)

REM --- if the Electron binary still isn't there, the download failed: retry once ---
if not exist "node_modules\electron\dist\electron.exe" (
  echo Electron did not download correctly. Removing it and retrying once...
  rmdir /s /q "node_modules\electron" 2>nul
  call npm install
)

echo.
echo Starting the overlay...
echo.
call npm start

echo.
echo ============================================================
echo  The overlay window has closed. If it never appeared, copy the
echo  error text shown ABOVE this line and send it to me.
echo ============================================================
pause
endlocal
