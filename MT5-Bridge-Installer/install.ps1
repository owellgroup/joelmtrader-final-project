$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dir  = 'C:\MT5Bridge'
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$PyUrl = 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe'

function Step($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }

function Find-Python {
    foreach ($c in @('C:\Python312\python.exe',
                     "$env:ProgramFiles\Python312\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*WindowsApps*') {
        $v = & $cmd.Source --version 2>&1
        # numpy below 2 (needed by MetaTrader5 to place orders) has no wheels for Python 3.13
        if ("$v" -match 'Python 3\.(9|1[0-2])\.') { return $cmd.Source }
    }
    return $null
}

Step 'Checking Python'
$py = Find-Python
if (-not $py) {
    Write-Host 'Python not found. Downloading Python 3.12 ...'
    $tmp = Join-Path $env:TEMP 'python-3.12.8-amd64.exe'
    Invoke-WebRequest -Uri $PyUrl -OutFile $tmp -UseBasicParsing
    Write-Host 'Installing Python 3.12 (silent) ...'
    $p = Start-Process -FilePath $tmp -ArgumentList '/quiet','InstallAllUsers=1','PrependPath=1','Include_test=0','TargetDir=C:\Python312' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Python installer failed (exit code $($p.ExitCode))." }
    $py = Find-Python
    if (-not $py) { throw 'Python installed but could not be found.' }
}
Write-Host "Using $py"

Step 'Copying bridge files to C:\MT5Bridge'
# Stop an older running copy first so files can be replaced
Get-ScheduledTask -TaskName 'MT5 Bridge' -ErrorAction SilentlyContinue | Stop-ScheduledTask -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$Dir\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path "$Dir\scripts","$Dir\logs" | Out-Null
Copy-Item "$Src\scripts\mt5_bridge.py" "$Dir\scripts\mt5_bridge.py" -Force
Copy-Item "$Src\bridge_runner.py"      "$Dir\bridge_runner.py"      -Force
if ((Test-Path "$Src\.env") -and -not (Test-Path "$Dir\.env")) { Copy-Item "$Src\.env" "$Dir\.env" }

Step 'Creating Python environment and installing packages (first time takes a minute)'
# An older install may have a Python 3.13 environment, which cannot use numpy below 2. Rebuild it.
if (Test-Path "$Dir\.venv\Scripts\python.exe") {
    $vv = & "$Dir\.venv\Scripts\python.exe" --version 2>&1
    if ("$vv" -match 'Python 3\.13') { Remove-Item "$Dir\.venv" -Recurse -Force }
}
if (-not (Test-Path "$Dir\.venv\Scripts\pythonw.exe")) {
    & $py -m venv "$Dir\.venv"
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
$vp = "$Dir\.venv\Scripts\python.exe"
& $vp -m pip install --upgrade pip
# numpy 2.x makes MetaTrader5 reject every order with (-2, 'Unnamed arguments not allowed')
& $vp -m pip install "MetaTrader5>=5.0.45" "websockets>=13" "numpy>=1.26,<2"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed. Check the internet connection and run INSTALL.bat again.' }
& $vp -m pip install --upgrade "numpy>=1.26,<2"
$nv = & $vp -c "import numpy; print(numpy.__version__)"
$mv = & $vp -c "import MetaTrader5; print(MetaTrader5.__version__)"
Write-Host "Installed: MetaTrader5 $mv, numpy $nv"
if ("$nv" -like '2.*') { throw "numpy $nv is still installed. Orders would fail. Send this screen to support." }

Step "Registering auto-start for user $User"
function New-Settings($restart) {
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
         -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    if ($restart) { $s.RestartCount = 999; $s.RestartInterval = 'PT1M' }
    return $s
}
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

# Bridge: runs hidden (pythonw) at every login, restarts itself if it ever stops
$trigB = New-ScheduledTaskTrigger -AtLogOn -User $User
$trigB.Delay = 'PT20S'
$actB  = New-ScheduledTaskAction -Execute "$Dir\.venv\Scripts\pythonw.exe" -Argument "`"$Dir\bridge_runner.py`"" -WorkingDirectory $Dir
Register-ScheduledTask -TaskName 'MT5 Bridge' -Trigger $trigB -Action $actB -Principal $principal -Settings (New-Settings $true) -Force | Out-Null

# MetaTrader 5 itself: also open it automatically at login
$term = Get-ChildItem "$env:ProgramFiles","${env:ProgramFiles(x86)}" -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like '*MetaTrader 5*' } |
        ForEach-Object { Join-Path $_.FullName 'terminal64.exe' } | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($term) {
    $trigM = New-ScheduledTaskTrigger -AtLogOn -User $User
    $trigM.Delay = 'PT5S'
    $actM  = New-ScheduledTaskAction -Execute $term -WorkingDirectory (Split-Path $term)
    Register-ScheduledTask -TaskName 'MT5 Terminal' -Trigger $trigM -Action $actM -Principal $principal -Settings (New-Settings $false) -Force | Out-Null
    Write-Host "MetaTrader 5 will also open at login: $term"
} else {
    Write-Host 'Could not find MetaTrader 5 (terminal64.exe). Add MT5 to Windows Startup yourself (Win+R, type shell:startup).' -ForegroundColor Yellow
}

Step 'Starting the bridge now'
Start-ScheduledTask -TaskName 'MT5 Bridge'
Start-Sleep -Seconds 8
if (Test-Path "$Dir\logs\bridge.log") { Get-Content "$Dir\logs\bridge.log" -Tail 6 }

Write-Host "`nDONE. The bridge now starts by itself every time you log in to Windows." -ForegroundColor Green
Write-Host 'Run VIEW-LOG.bat any time to see whether it says "Connected to the server".'
