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
rem --- Umwelt at the pin (private repo: the machine needs GitHub access to clone it once)
for /f "usebackq delims=" %%c in (`powershell -NoProfile -Command "(Get-Content -Raw tools\umwelt_pin.json | ConvertFrom-Json).commit"`) do set "PIN=%%c"
if not exist export\cache\umwelt\.git (
  echo === cloning umwelt >> "%LOG%"
  git clone -q https://github.com/AQuantumArchitect/umwelt.git export\cache\umwelt >> "%LOG%" 2>&1
)
echo === umwelt to pin %PIN% >> "%LOG%"
git -C export\cache\umwelt fetch -q origin >> "%LOG%" 2>&1
git -C export\cache\umwelt checkout -q --detach %PIN% >> "%LOG%" 2>&1
git -C export\cache\umwelt rev-parse HEAD >> "%LOG%" 2>&1
set "UMWELT_SRC=%CD%\export\cache\umwelt\src"
echo === git >> "%LOG%"
git log --oneline -1 >> "%LOG%" 2>&1
echo === autopilot --stock%ARGS% >> "%LOG%"
export\venv\Scripts\python.exe -u tools\autopilot_campaign_v1.py --stock%ARGS% >> "%LOG%" 2>&1
echo AUTOPILOT_EXIT %ERRORLEVEL% >> "%LOG%"
echo finished %DATE% %TIME% >> "%LOG%"
