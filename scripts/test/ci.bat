@echo off
rem Local CI, the gate before every push (GitHub Actions is manual only). See ci_local.ps1.
rem   scripts\test\ci.bat              hub tests + ship dry run
rem   scripts\test\ci.bat -TestsOnly   hub tests only
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ci_local.ps1" %*
exit /b %ERRORLEVEL%
