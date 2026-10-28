@echo off
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a WAV or MP3 file onto analyze_audio.bat to analyze it.
  pause
  exit /b 1
)
py -m algorithm.app.main analyze --mode audio --audio "%~1"
pause
