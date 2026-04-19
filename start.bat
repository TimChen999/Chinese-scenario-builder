@echo off
REM Scenarios App one-click launcher.
REM Forwards to start.ps1 with execution-policy bypass so the user
REM never has to touch system policy. `pause` only on a non-zero exit
REM so successful launches close cleanly while failures stay visible.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
