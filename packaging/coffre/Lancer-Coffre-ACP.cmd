@echo off
rem Menu interactif volontaire ; aucune modification durable de la politique PowerShell.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Demarrer-Coffre-ACP.ps1"
