@echo off
REM Shared paths for Verdance app launchers (design forge / product).
REM Python discovery order (no hard dependency on umwelt/yurt):
REM   1) VERDANCE_PY env if set and exists
REM   2) runtime\python\python.exe (ship embed)
REM   3) py -3 launcher
REM   4) python on PATH
REM   5) optional last-resort local venv if present

set "VERDANCE_ROOT=%~dp0..\.."
for %%I in ("%VERDANCE_ROOT%") do set "VERDANCE_ROOT=%%~fI"
set "PYTHONPATH=%VERDANCE_ROOT%\tools;%PYTHONPATH%"
cd /d "%VERDANCE_ROOT%"

REM Subscription steam only by default
set "XAI_API_KEY="
set "GROK_API_KEY="
set "GROK_ALLOW_API="

if defined VERDANCE_PY if exist "%VERDANCE_PY%" goto :py_ok

if exist "%VERDANCE_ROOT%\runtime\python\python.exe" (
  set "VERDANCE_PY=%VERDANCE_ROOT%\runtime\python\python.exe"
  goto :py_ok
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "VERDANCE_PY=%%P"
  if defined VERDANCE_PY if exist "%VERDANCE_PY%" goto :py_ok
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  for /f "delims=" %%P in ('where python') do (
    set "VERDANCE_PY=%%P"
    goto :py_ok
  )
)

if exist "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe" (
  set "VERDANCE_PY=C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
  goto :py_ok
)

echo.
echo  ERROR: No Python found.
echo  Install Python 3.11+ and ensure "python" is on PATH,
echo  or place an embeddable runtime at:
echo    %VERDANCE_ROOT%\runtime\python\python.exe
echo  Or set VERDANCE_PY to a python.exe full path.
echo.
exit /b 1

:py_ok
REM Optional research paths (forge only — never required for play)
if exist "C:\Users\Luke Spooner\ws-win\umwelt\src" set "PYTHONPATH=%PYTHONPATH%;C:\Users\Luke Spooner\ws-win\umwelt\src"
if exist "C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral" set "PYTHONPATH=%PYTHONPATH%;C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral"
