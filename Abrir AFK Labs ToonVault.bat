@echo off
set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%dist\AFK Labs ToonVault\AFK Labs ToonVault.exe"

if exist "%APP_EXE%" (
    start "" "%APP_EXE%"
    exit /b
)

start "" pythonw.exe "%APP_DIR%app.py"
exit /b
