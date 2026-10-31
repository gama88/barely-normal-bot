@echo off
rem Double-click after copying the new GitHub renewal token. See set-renewal-token.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set-renewal-token.ps1"
