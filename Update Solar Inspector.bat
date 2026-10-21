@echo off
setlocal
title Update Solar Inspector
cd /d "%~dp0"

echo.
echo  ============================================================
echo    UPDATE SOLAR PANEL INSPECTOR
echo  ============================================================
echo.

where git >nul 2>&1
if errorlevel 1 goto NOGIT
if not exist ".git" goto NOREPO

echo   Downloading the latest version...
echo.
git pull --ff-only
if errorlevel 1 goto PULLFAIL

echo.
echo   Up to date. Your API key and settings were not changed.
echo   Now double-click "Start Solar Inspector".
echo.
pause
goto END

:NOGIT
echo   Git is not installed, so this folder cannot update itself.
echo.
echo   Download the latest version instead:
echo     1. A download page will open. Click Code, then Download ZIP.
echo     2. Unzip it, and copy the file solar_defect_camera\.env.local
echo        from this old folder into the new one (it holds the API key).
echo.
start "" "https://github.com/ajayspatil7/solar-detect"
pause
goto END

:NOREPO
echo   This folder was not downloaded with Git, so it cannot update itself.
echo.
echo   Download the latest version instead:
echo     1. A download page will open. Click Code, then Download ZIP.
echo     2. Unzip it, and copy the file solar_defect_camera\.env.local
echo        from this old folder into the new one (it holds the API key).
echo.
start "" "https://github.com/ajayspatil7/solar-detect"
pause
goto END

:PULLFAIL
echo.
echo   The update did not complete. Check this computer is online.
echo   If it mentions local changes, send a photo of this window to the developer.
echo.
pause
goto END

:END
endlocal
