@echo off
call "%~dp0app\bin\EXPORT_CUSTOMER.bat" %*
exit /b %ERRORLEVEL%

