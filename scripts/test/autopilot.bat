@echo off
rem Verdance test rig: the autopilot on a stock-BAR copy, with the belief world on.
rem   set VA_LOG=name & scripts\test\autopilot.bat [autopilot args...]
rem Prepares export\venv (numpy, scipy) and export\cache\umwelt at the pinned commit
rem (tools\umwelt_pin.json), then runs tools\autopilot_campaign_v1.py --stock with your args.
rem The log goes to export\%VA_LOG%.log (autopilot.log if unset); the run to autopilot_runs\<stamp>.
rem Args pass through untouched (%*), so commas and "" survive.
rem Presets: campaign_hard.bat, tour.bat, finale.bat (A|B|C), resume.bat <run dir>.
setlocal
cd /d "%~dp0..\.."
set "NAME=%VA_LOG%"
if "%NAME%"=="" set "NAME=autopilot"
set ARGS= %*
if not exist export mkdir export
set "LOG=export\%NAME%.log"
echo started %DATE% %TIME% > "%LOG%"
echo === memory >> "%LOG%"
powershell -NoProfile -Command "$o=Get-CimInstance Win32_OperatingSystem; 'free RAM MB {0}  free commit MB {1}' -f [int]($o.FreePhysicalMemory/1024),[int]($o.FreeVirtualMemory/1024)" >> "%LOG%" 2>&1
rem --- a Python to make the venv with: VA_PYTHON, then the py launcher, then python on PATH
set "BASEPY=%VA_PYTHON%"
if "%BASEPY%"=="" (where py >nul 2>&1 && set "BASEPY=py -3")
if "%BASEPY%"=="" (where python >nul 2>&1 && set "BASEPY=python")
if not exist export\venv\Scripts\python.exe (
  echo === making export\venv with %BASEPY% >> "%LOG%"
  %BASEPY% -m venv export\venv >> "%LOG%" 2>&1
)
echo === numpy scipy >> "%LOG%"
export\venv\Scripts\python.exe -m pip install -q --disable-pip-version-check numpy scipy >> "%LOG%" 2>&1
echo PIP %ERRORLEVEL% >> "%LOG%"
rem --- Umwelt at the public pin (tools\umwelt_pin.json). No token: credential helper cleared.
for /f "usebackq delims=" %%c in (`powershell -NoProfile -Command "(Get-Content -Raw tools\umwelt_pin.json | ConvertFrom-Json).commit"`) do set "PIN=%%c"
for /f "usebackq delims=" %%r in (`powershell -NoProfile -Command "(Get-Content -Raw tools\umwelt_pin.json | ConvertFrom-Json).repo"`) do set "UMWELT_REPO=%%r"
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "(Get-Content -Raw tools\umwelt_pin.json | ConvertFrom-Json).tag"`) do set "UMWELT_TAG=%%t"
set "GIT_TERMINAL_PROMPT=0"
if not exist export\cache\umwelt\.git (
  echo === cloning umwelt >> "%LOG%"
  git -c credential.helper= -c http.extraheader= clone -q %UMWELT_REPO% export\cache\umwelt >> "%LOG%" 2>&1
)
rem The public history is not a fast-forward of the private pin, so retarget an old cache.
git -C export\cache\umwelt remote set-url origin %UMWELT_REPO% >> "%LOG%" 2>&1
echo === umwelt to pin %PIN% >> "%LOG%"
git -c credential.helper= -c http.extraheader= -C export\cache\umwelt fetch -q origin tag %UMWELT_TAG% >> "%LOG%" 2>&1
git -C export\cache\umwelt checkout -q --detach %PIN% >> "%LOG%" 2>&1
git -C export\cache\umwelt rev-parse HEAD >> "%LOG%" 2>&1
for /f "usebackq delims=" %%h in (`git -C export\cache\umwelt rev-parse HEAD`) do set "UMWELT_HEAD=%%h"
if not "%UMWELT_HEAD%"=="%PIN%" (
  echo Umwelt checkout %UMWELT_HEAD% is not the pin %PIN% >> "%LOG%"
  exit /b 1
)
set "UMWELT_SRC=%CD%\export\cache\umwelt\src"
echo === git >> "%LOG%"
git log --oneline -1 >> "%LOG%" 2>&1
echo === autopilot --stock%ARGS% >> "%LOG%"
export\venv\Scripts\python.exe -u tools\autopilot_campaign_v1.py --stock%ARGS% >> "%LOG%" 2>&1
echo AUTOPILOT_EXIT %ERRORLEVEL% >> "%LOG%"
echo finished %DATE% %TIME% >> "%LOG%"
