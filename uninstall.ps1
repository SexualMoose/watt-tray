# Watt-Tray uninstaller — unregisters the scheduled task and stops any running
# instance. Leaves the project files and venv in place so reinstalling is fast;
# delete C:\Users\Tyler\watt-tray manually if you want a full removal.

$ErrorActionPreference = "Continue"
$TaskName = "WattTray"

# --- self-elevate if not admin ---
$current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Re-launching uninstall.ps1 elevated..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",("`"" + $MyInvocation.MyCommand.Path + "`"") `
        -Verb RunAs
    exit
}

Write-Host "Stopping any running pythonw.exe under watt-tray..."
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -match "watt_tray\.pyw") {
        Write-Host "  killing PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "Unregistering scheduled task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Task removed."
} else {
    Write-Host "Task '$TaskName' not found."
}

Write-Host ""
Write-Host "Uninstall complete. Project files left at C:\Users\Tyler\watt-tray."
Write-Host "Press Enter to exit..."
[void][System.Console]::ReadLine()
