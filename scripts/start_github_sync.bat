@echo off
title GitHub Auto-Sync - ai-teacher
cd /d "%~dp0.."
echo Starting GitHub auto-sync watcher...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0github_auto_sync.ps1" -DebounceSeconds 60
pause
