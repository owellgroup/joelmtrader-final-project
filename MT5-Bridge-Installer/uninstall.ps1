$Dir = 'C:\MT5Bridge'
foreach ($t in 'MT5 Bridge','MT5 Terminal') {
    Stop-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
}
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$Dir\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Remove-Item $Dir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'Removed the bridge and its auto-start tasks. Python was left installed.' -ForegroundColor Green
