@echo off
REM Start/stop the Induduzo stack from Command Prompt or by double-click.
REM
REM cmd.exe cannot execute a .ps1 directly -- typing ".\start.ps1" there just
REM hands the file to its default handler and opens it in Notepad. This wrapper
REM passes it to PowerShell properly.
REM
REM   induduzo.cmd          start everything
REM   induduzo.cmd -Stop    stop everything
REM
REM Named "induduzo" rather than "start" or "run" on purpose: "start" collides
REM with a cmd built-in, and nvm already puts a "run.cmd" on the PATH that would
REM shadow this one.

setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "EXITCODE=%ERRORLEVEL%"

REM No arguments means the start path, which prints the URLs -- hold the window
REM so they are readable after a double-click. Anything with arguments (-Stop)
REM is being scripted, so it exits straight away.
if "%~1"=="" (
  echo.
  pause
)

exit /b %EXITCODE%
