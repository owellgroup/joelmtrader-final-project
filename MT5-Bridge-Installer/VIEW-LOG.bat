@echo off
if exist C:\MT5Bridge\logs\bridge.log (
  powershell -NoProfile -Command "Get-Content C:\MT5Bridge\logs\bridge.log -Tail 40 -Wait"
) else (
  echo No log yet. Install first, or wait a few seconds after login.
  pause
)
