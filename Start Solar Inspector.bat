@echo off
setlocal
title Solar Panel Inspector
cd /d "%~dp0solar_defect_camera"

echo.
echo  ============================================================
echo    SOLAR PANEL INSPECTOR
echo  ============================================================
echo.

rem ---- find a Python that actually runs --------------------------
set "PYEXE="
py -3 -c "print(1)" >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE python -c "print(1)" >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE goto NOPYTHON

rem ---- create the private environment on first run ---------------
if not exist ".venv\Scripts\python.exe" (
  echo   First run: setting up. This takes a few minutes, once only.
  echo.
  %PYEXE% -m venv .venv
  if errorlevel 1 goto VENVFAIL
)

rem ---- install components if anything is missing -----------------
".venv\Scripts\python.exe" -c "import uvicorn,fastapi,openai,PIL" >nul 2>&1
if errorlevel 1 (
  echo   Installing components. Please wait...
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto PIPFAIL
)

".venv\Scripts\python.exe" "tools\launcher.py"
goto END

:NOPYTHON
echo.
echo   Python is not installed on this computer.
echo.
echo   1. A download page will open in your browser.
echo   2. Download Python for Windows and run the installer.
echo   3. IMPORTANT: tick "Add python.exe to PATH" on the first screen.
echo   4. When it finishes, close this window and double-click
echo      "Start Solar Inspector" again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
goto END

:VENVFAIL
echo.
echo   Could not create the Python environment.
echo   Try moving this folder somewhere simple such as C:\SolarInspector
echo   and run it again.
pause
goto END

:PIPFAIL
echo.
echo   Could not download the required components.
echo   Check this computer is connected to the internet, then try again.
pause
goto END

:END
endlocal
