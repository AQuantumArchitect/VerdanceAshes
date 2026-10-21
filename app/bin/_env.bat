@echo off
REM Shared paths for Verdance app launchers (design forge / product). ASCII only:
REM this file ships to every player and a non-ASCII byte here renders as
REM mojibake on a cp437 console.
REM
REM Python discovery order (no hard dependency on umwelt/yurt):
REM   1) runtime\python\python.exe   (the SHIP zip embeds it)
REM   2) VERDANCE_PY env             (explicit override)
REM   3) py -3 launcher
REM   4) python.exe / python3.exe on PATH
REM   5) optional dev venv under %USERPROFILE%\ws-win\umwelt (never required)
REM Every candidate must actually run (import sys, version 3.10+) before it is
REM accepted, and anything under WindowsApps is rejected: on a box with no
REM Python installed, "where python" returns the Microsoft Store stub, which
REM opens the Store instead of running anything.

set "VERDANCE_ROOT=%~dp0..\.."
for %%I in ("%VERDANCE_ROOT%") do set "VERDANCE_ROOT=%%~fI"
set "PYTHONPATH=%VERDANCE_ROOT%\tools;%PYTHONPATH%"
cd /d "%VERDANCE_ROOT%"

REM Subscription steam only by default
set "XAI_API_KEY="
set "GROK_API_KEY="
set "GROK_ALLOW_API="

set "VA_PY_OK="
set "VA_PY_CAND="

REM 1) embedded runtime (ship zip)
call :try_py "%VERDANCE_ROOT%\runtime\python\python.exe"
if defined VA_PY_OK goto :py_ok

REM 2) explicit override
if defined VERDANCE_PY call :try_py "%VERDANCE_PY%"
if defined VA_PY_OK goto :py_ok

REM 3) py launcher (only sees real installs, never the Store stub)
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :try_py "%%P"
)
if defined VA_PY_OK goto :py_ok

REM 4) python / python3 on PATH (every hit is tried; WindowsApps stubs are skipped)
for /f "delims=" %%P in ('where python.exe 2^>nul') do call :try_py "%%P"
if defined VA_PY_OK goto :py_ok
for /f "delims=" %%P in ('where python3.exe 2^>nul') do call :try_py "%%P"
if defined VA_PY_OK goto :py_ok

REM 5) dev-machine venv. Written against %USERPROFILE% rather than a literal
REM path so no account name ships in anyone's copy. Optional discovery only.
call :try_py "%USERPROFILE%\ws-win\umwelt\.venv\Scripts\python.exe"
if defined VA_PY_OK goto :py_ok

echo.
echo  ERROR: No working Python 3.10+ was found on this machine.
echo.
echo  Install Python 3.10 or newer from https://www.python.org/downloads/
echo  (tick "Add python.exe to PATH" in the installer), then run this again.
echo  Or use the SHIP zip build of Verdance's Ashes, which embeds its own
echo  Python under runtime\python\ and needs nothing installed.
echo.
set "VA_PY_CAND="
exit /b 1

REM ---------------------------------------------------------------------------
REM :try_py <path>  - accept the first candidate that exists, is not the Store
REM                   stub, and really runs as Python 3.10+.
:try_py
if defined VA_PY_OK goto :eof
set "VA_PY_CAND=%~1"
if not defined VA_PY_CAND goto :eof
if not exist "%VA_PY_CAND%" goto :eof
if /I not "%VA_PY_CAND:WindowsApps=%"=="%VA_PY_CAND%" goto :eof
"%VA_PY_CAND%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "VERDANCE_PY=%VA_PY_CAND%"
set "VA_PY_OK=1"
goto :eof

:py_ok
set "VA_PY_CAND="
REM Optional research paths (forge only, never required for play). Discovery,
REM not assumption: a missing clone changes nothing.
if exist "%USERPROFILE%\ws-win\umwelt\src" set "PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\ws-win\umwelt\src"
if exist "%USERPROFILE%\ws-win\yurt-sync\work\_wargen\coral" set "PYTHONPATH=%PYTHONPATH%;%USERPROFILE%\ws-win\yurt-sync\work\_wargen\coral"
