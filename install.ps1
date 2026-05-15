# Watt-Tray installer
# Sets up venv, installs pip deps, vendors LibreHardwareMonitor DLLs,
# and registers a Task Scheduler entry that auto-starts the tray at logon
# with admin (RunLevel Highest) so WinRing0 driver can load.

$ErrorActionPreference = "Stop"

$ProjectDir = "C:\Users\Tyler\watt-tray"
$Python     = "C:\Users\Tyler\AppData\Local\Programs\Python\Python311\python.exe"
$VenvDir    = Join-Path $ProjectDir "venv"
$VenvPython = Join-Path $VenvDir   "Scripts\python.exe"
$VenvPyw    = Join-Path $VenvDir   "Scripts\pythonw.exe"
$ScriptPath = Join-Path $ProjectDir "watt_tray.pyw"
$TaskName   = "WattTray"

# --- self-elevate if not admin ---
$current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Re-launching install.ps1 elevated..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",("`"" + $MyInvocation.MyCommand.Path + "`"") `
        -Verb RunAs
    exit
}

# Capture transcript so the (separate, elevated) console output can be inspected after.
$transcriptPath = Join-Path $ProjectDir "install.log"
try { Start-Transcript -Path $transcriptPath -Force | Out-Null } catch {}

Write-Host "=== Watt-Tray install ==="
Write-Host "Project dir: $ProjectDir"

# --- 1. Vendor LHM DLLs ---
$LhmLib = Join-Path $ProjectDir "LibreHardwareMonitorLib.dll"
$HidSharp = Join-Path $ProjectDir "HidSharp.dll"
if ((Test-Path $LhmLib) -and (Test-Path $HidSharp)) {
    Write-Host "LHM DLLs already present, skipping download."
} else {
    Write-Host "Downloading LibreHardwareMonitor release info from GitHub..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest" -Headers @{ "User-Agent" = "watt-tray-install" }
    $asset = $rel.assets | Where-Object { $_.name -match "net472\.zip$" } | Select-Object -First 1
    if (-not $asset) {
        $asset = $rel.assets | Where-Object { $_.name -match "\.zip$" } | Select-Object -First 1
    }
    if (-not $asset) { throw "Could not find a zipped LHM release asset." }
    Write-Host ("Downloading: " + $asset.name + " (" + [int]($asset.size/1KB) + " KB)")
    $zipPath = Join-Path $env:TEMP "lhm-watt-tray.zip"
    $extractDir = Join-Path $env:TEMP "lhm-watt-tray-extract"
    if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -Headers @{ "User-Agent" = "watt-tray-install" }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $foundLib = Get-ChildItem -Path $extractDir -Filter "LibreHardwareMonitorLib.dll" -Recurse | Select-Object -First 1
    $foundHid = Get-ChildItem -Path $extractDir -Filter "HidSharp.dll" -Recurse | Select-Object -First 1
    if (-not $foundLib) { throw "LibreHardwareMonitorLib.dll not found in zip." }
    Copy-Item $foundLib.FullName $LhmLib -Force
    if ($foundHid) { Copy-Item $foundHid.FullName $HidSharp -Force }
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "LHM DLLs vendored."
}

# --- 2. venv + pip ---
if (-not (Test-Path $Python)) { throw "Python not found at $Python" }
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtualenv at $VenvDir"
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
}
Write-Host "Upgrading pip and installing dependencies..."
& $VenvPython -m pip install --upgrade --quiet pip
& $VenvPython -m pip install --quiet "pythonnet>=3.0,<4.0" "pystray>=0.19" "Pillow>=10.0" "pywin32>=306"
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
Write-Host "Python deps installed."

# --- 3. Register Task Scheduler entry ---
Write-Host "Registering scheduled task '$TaskName'..."
$action = New-ScheduledTaskAction -Execute $VenvPyw `
    -Argument ('"' + $ScriptPath + '"') `
    -WorkingDirectory $ProjectDir

$userPrincipal = "$env:COMPUTERNAME\Tyler"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userPrincipal
$principal = New-ScheduledTaskPrincipal -UserId $userPrincipal -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -Hidden `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Scheduled task registered."

Write-Host ""
Write-Host "=== Install complete ==="
Write-Host "Start it now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Or just reboot -- it will auto-launch at next logon."
Write-Host "Log file:  $ProjectDir\watt_tray.log"
Write-Host ""
try { Stop-Transcript | Out-Null } catch {}
Write-Host "Install transcript saved to $transcriptPath"
Start-Sleep -Seconds 3
