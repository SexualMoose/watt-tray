# Optional: install PawnIO so LHM can read real CPU package power (Ryzen SMU).
#
# Why this matters: LHM v0.9.x replaced the old WinRing0 driver with PawnIO
# (https://pawnio.eu/) — a Microsoft-attestation-signed kernel driver that runs
# small Pawn scripts in kernel mode for hardware access. The LHM DLL we vendored
# already contains the scripts (RyzenSMU.bin, AMDFamily17.bin, etc.) but the
# driver itself must be installed system-wide.
#
# Run via:  powershell.exe -ExecutionPolicy Bypass -File install_pawnio.ps1
# (will self-elevate; you'll see one UAC prompt)

$ErrorActionPreference = "Stop"

$current = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Re-launching elevated..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",("`"" + $MyInvocation.MyCommand.Path + "`"") `
        -Verb RunAs
    exit
}

Write-Host "=== PawnIO install ==="
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "Fetching latest PawnIO release info..."
$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/namazso/PawnIO.Setup/releases/latest" `
                         -Headers @{ "User-Agent" = "watt-tray-pawnio-install" }
Write-Host ("Tag: " + $rel.tag_name)

# Prefer EXE (NSIS installer); fall back to MSI
$asset = $rel.assets | Where-Object { $_.name -match "PawnIO.*setup.*\.exe$" } | Select-Object -First 1
if (-not $asset) {
    $asset = $rel.assets | Where-Object { $_.name -match "\.exe$" -and $_.name -notmatch "symbols" } | Select-Object -First 1
}
if (-not $asset) {
    $asset = $rel.assets | Where-Object { $_.name -match "\.msi$" } | Select-Object -First 1
}
if (-not $asset) { throw "No installer asset found in latest release." }

$dst = Join-Path $env:TEMP $asset.name
Write-Host ("Downloading " + $asset.name + " -> " + $dst)
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $dst `
                  -Headers @{ "User-Agent" = "watt-tray-pawnio-install" }

if ($asset.name -match "\.msi$") {
    Write-Host "Running MSI installer (silent)..."
    Start-Process -FilePath "msiexec.exe" -ArgumentList "/i",("`"$dst`""),"/qb","/norestart" -Wait
} else {
    Write-Host "Running EXE installer (silent /S flag, NSIS)..."
    Start-Process -FilePath $dst -ArgumentList "/S" -Wait
}

Start-Sleep -Seconds 2
$svc = Get-Service -Name "*PawnIO*","*pawn*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
    Write-Host ("PawnIO service: " + $svc.Name + " status=" + $svc.Status)
} else {
    Write-Host "WARNING: PawnIO service not found after install. Check installer output."
}

Write-Host ""
Write-Host "Now restart the WattTray task to pick up the driver:"
Write-Host "  Stop-ScheduledTask -TaskName WattTray; Start-ScheduledTask -TaskName WattTray"
Write-Host ""
Write-Host "After restart, tooltip should NO longer show [CPU est]."
Start-Sleep -Seconds 4
