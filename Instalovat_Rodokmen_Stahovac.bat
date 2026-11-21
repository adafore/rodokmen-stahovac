@echo off
chcp 65001 >nul
title Instalator - Rodokmen Stahovac (adafore)
echo Stahuji a spoustim instalator (PowerShell)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/adafore/rodokmen-stahovac/main/instalator.ps1' -OutFile \"$env:TEMP\rodokmen_instalator.ps1\"; & \"$env:TEMP\rodokmen_instalator.ps1\" } catch { Write-Host ('CHYBA: ' + $_.Exception.Message) -ForegroundColor Red }"
echo.
pause
