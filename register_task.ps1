# Register the Watt-Tray scheduled task. Requires admin (RunLevel Highest is
# what enables WinRing0 driver loading for CPU package power readings).
# Run this once via: powershell.exe -ExecutionPolicy Bypass -File register_task.ps1

$ErrorActionPreference = "Stop"

$ProjectDir = "C:\Users\Tyler\watt-tray"
$VenvPyw    = Join-Path $ProjectDir "venv\Scripts\pythonw.exe"
$ScriptPath = Join-Path $ProjectDir "watt_tray.pyw"
$TaskName   = "WattTray"

# Self-elevate
$current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Re-launching elevated..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",("`"" + $MyInvocation.MyCommand.Path + "`"") `
        -Verb RunAs
    exit
}

if (-not (Test-Path $VenvPyw))    { throw "pythonw.exe not found at $VenvPyw. Run install steps first." }
if (-not (Test-Path $ScriptPath)) { throw "watt_tray.pyw not found at $ScriptPath." }

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

Write-Host "Scheduled task '$TaskName' registered."
Write-Host "Start it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Or reboot -- it auto-launches at next logon."
Start-Sleep -Seconds 4
