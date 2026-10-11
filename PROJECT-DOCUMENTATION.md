# watt-tray — Project Documentation

Windows system-tray icon that shows your PC's total power draw (watts) as a live number. It reads CPU and GPU power from LibreHardwareMonitor sensors and adds static estimates for the parts it can't read. **Archived. A newer version replaced this repo.**

_Last audited: 2026-10-10 against main @ cbc5c28._

## Overview / Purpose

`watt-tray` is a small Python desktop utility for Windows only. It puts an icon in the system tray: a square (white by default) with a number on it (black by default). The number is the rolling average of the machine's total wattage. The total is the sum of:

- **CPU package power**, read from the LibreHardwareMonitor (LHM) sensor named in `sensor_priority.cpu`. If that sensor is missing or reads below `cpu_estimate.use_when_sensor_below_w`, the app falls back to a linear estimate based on CPU load (`psutil`). If the estimate is also unavailable, it uses the raw sensor reading if a sensor exists (tagged `sensor`), otherwise 0 (tagged `missing`).
- **Power for each GPU** (AMD, NVIDIA or Intel), from the first sensor that matches `sensor_priority.gpu`.
- **Static estimates** for parts LHM can't read on most consumer hardware:
  - RAM: per-stick watts × stick count. Stick count and DDR type are auto-detected through WMI `Win32_PhysicalMemory`.
  - Motherboard, SSDs and fans.

It also reads CPU and GPU temperatures for display.

Hovering over the icon shows a tooltip with Total, CPU and each GPU (watts and temperature). The right-click menu has:
- **Refresh now**
- **Pause/Resume measurement**
- **Restart sensors**: reopens LHM.
- **Show breakdown**: a Tk message box listing the same items, with the data source of the CPU and each GPU value.
- **Exit**

The tool was built for a Ryzen 9 5950X workstation with two Radeon GPUs. The sensor names and static wattages are configurable for other machines that LHM supports.

## Status

**Archived and superseded. Not maintained.**

- The GitHub repository was archived (read-only) on 2026-05-16 at 02:24 UTC, about six hours after its only commit. It was archived because its code had just been merged into a private monorepo that superseded it, not because it went dormant: the monorepo's first commit, which merges this repo and the sibling `ai-servers-tray`, is from about ten minutes before the archive. `ai-servers-tray` was archived at the same moment. Development of the newer version continued in the monorepo; it has since diverged and is not public. Nothing in this repo points to it. The archive time comes from GitHub; the merge details come from the owner's records.
- History is a single commit: `cbc5c28` (2026-05-15), "Initial commit: watt-tray app + install scripts + docs". There is one branch (`main`, in sync with `origin/main`) and no tags.
- The code was complete for its purpose when archived. No TODO/FIXME markers are left, and logging and error handling are thorough. It needs third-party DLLs that are deliberately left out of the repo (fetched by `install.ps1`), so the repo can't run without that install step.
- The issues listed under Known Issues were found in this audit. They won't be fixed here because the repo is archived.

## Technical Requirements

- **OS:** Windows only. The code uses:
  - a Win32 named mutex (via `pywin32`)
  - WMI (through .NET `System.Management`)
  - Task Scheduler
  - fonts from `C:\Windows\Fonts`
  - PowerShell installer scripts

  Which Windows versions it supports was never stated (unverified).
- **Python:** 3.11. Both `install.ps1` and the README target 3.11. Other versions are untested (unverified).
- **.NET Framework 4.7.2 runtime.** `LibreHardwareMonitorLib.dll` is a .NET Framework build. `power_reader.py` calls `pythonnet.load("netfx")` before `import clr`.
- **Third-party DLLs** (not committed; see Dependencies): `LibreHardwareMonitorLib.dll` and `HidSharp.dll`, taken from LHM's GitHub release zip (`install.ps1` prefers the `net472` zip). LHM 0.9.5 and later may also need support DLLs from the same zip that `install.ps1` doesn't copy (see Dependencies and Known Issues).
- **Optional kernel driver: PawnIO.** It lets LHM read real CPU package power (on Ryzen, through the SMU). `install_pawnio.ps1` installs it. Without it, the CPU figure falls back to the load-based estimate and the tooltip shows `[CPU est]`.
- **Admin rights:**
  - All four `.ps1` scripts re-launch themselves elevated.
  - The scheduled task they register runs at `RunLevel Highest`, so LHM can use the low-level driver.
- **Windows PowerShell** with the ScheduledTasks cmdlets (`Register-ScheduledTask` and related), used by `install.ps1`, `register_task.ps1` and `uninstall.ps1`.
- **Accounts/keys:** none. The installers query the public GitHub releases API anonymously.
- **App version / IDs:** the code has no version string. Fixed identifiers:
  - scheduled task `WattTray`
  - mutex `Global\WattTrayMutex`
  - pystray icon name `watt-tray`

## Dependencies

Python packages in `requirements.txt` (no lockfile):

| Package | Constraint | Used for | License |
|---|---|---|---|
| `Pillow` | `>=10.0` | Draws the icon image (`tray_icon.py`) | MIT-CMU (HPND-style PIL license) |
| `pystray` | `>=0.19` | Tray icon and menu | LGPL-3.0 |
| `pywin32` | `>=306` | Single-instance mutex (`win32event`, `win32api`, `winerror`, `pywintypes`) | PSF-2.0 |
| `pythonnet` | `>=3.0` (`install.ps1` pins `>=3.0,<4.0`) | CLR bridge that loads the LHM .NET DLL and `System.Management` | MIT |
| `psutil` | **not declared** | CPU-load estimate in `power_reader.py` (optional import) | BSD-3-Clause |

Standard library: `tkinter` (breakdown dialog), `logging`, `json`, `statistics`, `threading` and others.

Native / .NET components, downloaded at install time and never committed (`*.dll` and `*.exe` are gitignored):

| Component | Source | License |
|---|---|---|
| `LibreHardwareMonitorLib.dll` | LibreHardwareMonitor GitHub releases (latest), via `install.ps1` | MPL-2.0 |
| `HidSharp.dll` | Same LHM release zip, via `install.ps1` | Apache-2.0 |
| .NET `System.Management` | Part of .NET Framework | Microsoft .NET Framework license |
| PawnIO driver (optional) | `namazso/PawnIO.Setup` GitHub releases (latest), via `install_pawnio.ps1` | license unverified |

Other DLLs that ship in the LHM zip. `install.ps1` copies none of them:

- **Support libraries: `DiskInfoToolkit.dll`, `RAMSPDToolkit-NDD.dll`, `BlackSharp.Core.dll`** (all MPL-2.0 per their NuGet metadata). From version 0.9.5 on, LHM's NuGet package lists `DiskInfoToolkit` and `RAMSPDToolkit-NDD` as .NET Framework dependencies; 0.9.4 lists only `HidSharp` and `System.Management`. Both depend on `BlackSharp.Core`. Judging by their names, they back the storage and memory (SPD) support that this code enables. Whether the app fails without them was not tested.
- **`Microsoft.Bcl.*`, `Microsoft.Win32.TaskScheduler.dll`, `System.*`:** the previous README called these necessary. From 0.9.5 on, the NuGet package also lists `System.Memory` and `System.Threading.AccessControl` for .NET Framework. Whether a given release needs these files next to the library is unverified.
- **`OxyPlot.dll`, `OxyPlot.WindowsForms.dll`, `Aga.Controls.dll`:** LHM's own UI. This code doesn't use them.

## Setup Instructions

All commands are for PowerShell on Windows. `<project-dir>` is wherever you cloned the repo.

```powershell
# 1. Clone
git clone https://github.com/SexualMoose/watt-tray.git <project-dir>
cd <project-dir>
```

**Before running any `.ps1` script:**
- `install.ps1` and `register_task.ps1` hard-code these variables: `$ProjectDir` (project folder), `$Python` (path to a per-user Python 3.11 install; `install.ps1` only) and the Windows username in `$userPrincipal`.
- Edit them to match your machine. `uninstall.ps1` mentions the original folder only in messages.

**Path A — installer.** `install.ps1` re-launches itself elevated. It then:
- downloads the LHM DLLs if they're missing
- creates `venv\`
- pip-installs the dependencies (without psutil)
- registers the `WattTray` logon task

Run this from an elevated PowerShell. Otherwise the script re-opens in a new admin window and returns immediately; wait until that window prints `=== Install complete ===` before running the next line. The admin window closes a few seconds after it finishes; if it closes without that line, check `install.log`.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1
.\venv\Scripts\python.exe -m pip install psutil   # enables the CPU-load estimate (see Known Issues)
```

**Path B — manual:**

```powershell
# Copy LibreHardwareMonitorLib.dll and HidSharp.dll from the LHM release zip into <project-dir>.
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt psutil
```

**Both paths:**

```powershell
# Required: install.ps1 does NOT create config.json, and the app exits without it.
copy config.example.json config.json

# Optional: install PawnIO for a real CPU package power reading (re-launches itself elevated).
powershell.exe -ExecutionPolicy Bypass -File .\install_pawnio.ps1
```

**Optional — task only.** To register the logon task without the rest of the installer (after editing the variables above):

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\register_task.ps1
```

## Build & Run

There is no build step: the project is plain Python plus downloaded DLLs.

```powershell
# Run directly (no console window):
.\venv\Scripts\pythonw.exe watt_tray.pyw

# Or start the registered task:
Start-ScheduledTask -TaskName WattTray

# Restart after installing PawnIO:
Stop-ScheduledTask -TaskName WattTray; Start-ScheduledTask -TaskName WattTray

# Remove autostart (kills running watt_tray.pyw pythonw processes, unregisters the task, leaves files):
powershell.exe -ExecutionPolicy Bypass -File .\uninstall.ps1
```

**When the icon appears:**
- The icon shows up as soon as LHM finishes opening.
- The first rendered value arrives about 2 s after startup.
- After that, the icon redraws every `update_interval_sec` (10 s by default).

`pythonw.exe` throws away stdout and stderr, so all diagnostics go to `watt_tray.log` next to the script. It rotates at 1 MB and keeps 3 backups (`watt_tray.log` plus `.1`–`.3`), so up to 4 files. `install.ps1` also writes its transcript to `install.log` in the project folder.

## Usage

- **The number on the icon** is the rolling-average total in watts: the mean of the last `rolling_window_samples` samples. With the defaults that is 10 samples × 1 s, so about 10 s.
- **Hover** for the tooltip: `Total`, `CPU` (with temperature) and `GPU_0`, `GPU_1`, … (watts and temperature).
  - CPU tags: `(est)` when the load estimate is in use, `(n/a)` when no CPU value is available.
  - Tooltip prefixes: `[PAUSED]`, `[CPU est]`, `[CPU n/a]`.
  - Windows caps the tooltip at 127 characters, so it gets truncated.
- **Right-click menu:**
  - **Refresh now**: wakes the sample loop.
  - **Pause measurement / Resume measurement**
  - **Restart sensors**: closes and recreates the `PowerReader` and clears the averaging buffer.
  - **Show breakdown**: a top-most Tk dialog with the same items plus each value's source (`sensor`, `estimate`, `missing`, `sensor:<GPU name>`).
  - **Exit**
- **Static parts** (RAM, motherboard, SSDs, fans) count toward the total but aren't shown in the tooltip or dialog. They appear only in the one-time `First sample:` line in `watt_tray.log`.
- **Single instance:** a second launch finds the `Global\WattTrayMutex` mutex already held, logs that fact and exits.

## Architecture

```
power_reader.PowerReader --(values, sources)--> watt_tray.WattTrayApp --avg--> tray_icon.render_icon --> pystray.Icon
  (LHM via pythonnet/clr,                        (sample thread +              (PIL image,              (tray UI + menu,
   WMI via System.Management,                     render thread,                font auto-fit)           main thread)
   psutil CPU estimate)                           rolling deque average)
```

### `power_reader.py` — `PowerReader`

**Startup:**
- Forces the pythonnet `netfx` runtime.
- Loads `LibreHardwareMonitorLib.dll` from the project folder, plus `System.Management`.
- Opens an LHM `Computer` with CPU, GPU, motherboard, memory and storage enabled (controller and network disabled).
- Auto-detects RAM once through WMI.

**Each `get_breakdown()` call:**
- Re-opens the `Computer` if `reenumerate_interval_sec` has passed (checked on each call; default 300 s).
- Updates every hardware node and sub-node.
- Chooses sensors by exact name in priority order.
- Applies the CPU estimate when needed, adds the static estimates and returns `(values, sources)` dicts.

**Logging:** the hardware inventory, the first sample and a one-time warning when the CPU value is estimated or missing.

### `tray_icon.py` — `render_icon(watts, cfg)`

Draws the integer wattage on a square of `icon_size_px` pixels. It binary-searches the font size (between `font_min_pt` and `font_max_pt`) so the text fits 92% of the canvas. The font is `font_family` from `C:\Windows\Fonts`, falling back to `segoeui.ttf`, `arial.ttf`, `tahoma.ttf`, then PIL's default font.

### `watt_tray.pyw` — entry point, `main()`

**Startup:** loads `config.json` (exits with code 1 if it can't), takes the single-instance mutex, then builds `WattTrayApp`.

**Threads:**
- **Sample thread** (daemon): calls `get_breakdown()` every `sample_interval_sec` and appends the total to a `deque(maxlen=rolling_window_samples)`.
- **Render thread** (daemon): redraws the icon and tooltip every `update_interval_sec`.
- **Main thread:** runs `pystray.Icon.run()`. Menu handlers set events that the threads act on.

### Install scripts (PowerShell)

- `install.ps1`: downloads the DLLs, creates the venv, installs the pip packages and registers the task.
- `register_task.ps1`: registers the task only.
- `install_pawnio.ps1`: installs the PawnIO driver.
- `uninstall.ps1`: stops the process and removes the task.

The task has these properties:
- runs at logon of the configured user, interactive, `RunLevel Highest`
- restarts 3 times, 1 minute apart
- no time limit
- hidden
- `MultipleInstances IgnoreNew`

## Integrations & Interconnects

- **LibreHardwareMonitor:** the sensor backend, loaded in-process through pythonnet. `install.ps1` gets its DLLs from the GitHub releases API (`LibreHardwareMonitor/LibreHardwareMonitor`, latest release).
- **PawnIO:** optional kernel driver that LHM uses for low-level hardware access. `install_pawnio.ps1` downloads the latest installer from the GitHub releases of `namazso/PawnIO.Setup` and runs it silently (`/S` for the EXE, `/qb` for an MSI).
- **Windows services:** WMI (`Win32_PhysicalMemory`, for RAM detection) and Task Scheduler (autostart).
- **ai-servers-tray (sibling repo, also archived and public):** contains `watt-tray-installer.py`. Its `build-installers.bat` builds that into `dist/watt-tray-installer.exe`, which is not committed. The installer only creates and removes the `WattTray` task and starts and stops the process.
  - It hard-codes a fixed install folder.
  - It registers the task at **LIMITED** run level, not the Highest level used here.
  - `install.ps1` / `register_task.ps1` in this repo replace it.
- **Self-hosted fleet server:** no integration in this repo. There is no fleet key, self-report, self-update or telemetry.
- **No network listener and no runtime network calls.** The only network traffic is the anonymous GitHub release lookups and downloads at install time.

## Configuration & Secrets

**Config file:**
- `config.json` in the project folder holds the live config and is required. It's gitignored, and you create it by copying `config.example.json`, the committed template.
- The app reads no environment variables, registry keys or other config.

| Key | Default | Meaning |
|---|---|---|
| `update_interval_sec` | `10` | How often the icon and tooltip redraw (s) |
| `sample_interval_sec` | `1` | How often `PowerReader.get_breakdown()` is called (s) |
| `rolling_window_samples` | `10` | Samples in the rolling average |
| `reenumerate_interval_sec` | `300` | How often LHM's `Computer` is closed and reopened (s) |
| `icon_size_px` | `64` | Icon canvas size (px) |
| `icon_bg` / `icon_fg` | `#FFFFFF` / `#000000` | Background and number colors |
| `font_family`, `font_max_pt`, `font_min_pt` | `segoeui.ttf`, `36`, `14` | Font file and size range for auto-fit |
| `static.ram.auto_detect` | `true` | Detect stick count and DDR type via WMI |
| `static.ram.max_w_per_stick_ddr4` / `_ddr5` | `6.0` / `9.0` | Watts per stick. Every type other than DDR5 uses the DDR4 value |
| `static.ram.fallback_w_per_stick` / `fallback_stick_count` | `6.0` / `4` | Used when detection is off or fails |
| `static.motherboard_w` | `50.0` | Static motherboard watts |
| `static.ssd_w_each` / `ssd_count` | `5.0` / `8` | SSD estimate |
| `static.fan_w_each` / `fan_count` | `2.0` / `6` | Fan estimate |
| `cpu_estimate.enabled` | `true` | Allow the load-based CPU estimate (needs `psutil`) |
| `cpu_estimate.idle_w` / `max_w` | `30.0` / `145.0` | Estimate = `idle_w + load% × (max_w − idle_w)` |
| `cpu_estimate.use_when_sensor_below_w` | `1.0` | Use the estimate when the sensor reads below this value |
| `sensor_priority.cpu` | `["CPU Package", "Package"]` | LHM CPU power sensor names, in priority order |
| `sensor_priority.gpu` | `["GPU Total", "GPU Package", "GPU Power"]` | LHM GPU power sensor names, in priority order |

**Other files and system state:**

| Item | Purpose |
|---|---|
| `watt_tray.log` | Written by the app |
| `install.log` | Written by `install.ps1` |
| `LibreHardwareMonitorLib.dll`, `HidSharp.dll` | Expected in the project folder (newer LHM releases may also need the support DLLs listed under Dependencies) |
| `WattTray` scheduled task | Created by the scripts |

**Secrets:** none are needed and none are present. There are no API keys, tokens or credentials in the tree.

## Testing

There are no automated tests, test files or CI (no `.github/workflows`). Verification is manual:
- Run the tray.
- Check that the icon and tooltip update.
- Use **Show breakdown** to see each value's source.
- Read the `LHM hardware discovered:` and `First sample:` lines in `watt_tray.log`.

## Known Issues / TODO

The repo is archived, so none of these will be fixed here.

**Setup:**
- **`psutil` is missing.** `power_reader.py` uses `psutil` for the CPU-load estimate, but neither `requirements.txt` nor the `pip install` line in `install.ps1` includes it.
  - The code degrades quietly: it logs `psutil unavailable; CPU estimation disabled`.
  - On a clean install without PawnIO, the CPU value therefore shows 0 W instead of an estimate. It is tagged `sensor` if the LHM sensor exists but reads about 0, and `missing` / `[CPU n/a]` if the sensor is absent. Install `psutil` by hand.
- **`install.ps1` doesn't create `config.json`.** The task it registers starts the app, which logs `Failed to load config.json` and exits until you copy `config.example.json` to `config.json`.
- **Hard-coded paths and user.** `install.ps1` and `register_task.ps1` hard-code the project folder, a per-user Python 3.11 path (`install.ps1`) and a specific Windows username. They need editing before they'll work on another machine.
- **Dependency pins don't match.** `install.ps1` pins `pythonnet>=3.0,<4.0` and ignores `requirements.txt`, which sets no upper bound.
- **DLL set.** `install.ps1` copies only `LibreHardwareMonitorLib.dll` and `HidSharp.dll`, but it always fetches the latest LHM release. From 0.9.5 on, LHM's NuGet metadata lists `DiskInfoToolkit`, `RAMSPDToolkit-NDD` (both of which need `BlackSharp.Core`), `System.Memory` and `System.Threading.AccessControl` as .NET Framework dependencies. With a current release, LHM may therefore fail to open (`Computer.Open() failed` in `watt_tray.log`), or memory and storage hardware may be missing from the `LHM hardware discovered:` line (inferred, untested). The fix is to copy `DiskInfoToolkit.dll`, `RAMSPDToolkit-NDD.dll`, `BlackSharp.Core.dll` and the matching `System.*.dll` files from the same zip next to `LibreHardwareMonitorLib.dll`.
- **Unpinned downloads.** The installers always fetch the *latest* LHM and PawnIO releases and pick assets by filename pattern, so a change in upstream release packaging could break installation (inferred).

**Code comments out of date:**
- The headers of `install.ps1` and `register_task.ps1` say `RunLevel Highest` is for loading the "WinRing0" driver. The comment in `install_pawnio.ps1` says LHM 0.9.x replaced WinRing0 with PawnIO.
- The module docstring in `watt_tray.pyw` says "1-min rolling average", but the defaults give a window of about 10 s (10 samples × 1 s).

**Display:**
- Static parts count toward the total but aren't shown in the tooltip or the breakdown dialog.
- The tooltip is truncated at 127 characters.

**Single-instance check:** if creating the mutex itself fails, `_acquire_single_instance()` returns `None` and `main()` exits as though another instance were running. A code comment says it should "proceed anyway".

**Minor dead code:** `PowerReader.read_total_watts()` is never called, the `PowerReader.degraded` flag is never read by the tray, and `power_reader.py` has an unused `import os`.

## Third-party & Licensing

**License:**
- MIT, "Copyright (c) 2026 Tyler Keller" (`LICENSE`).
- It covers the original code in this repo. The project is not a fork: there's one original commit and no foreign copyright headers.

**Third-party code:**
- **Nothing is vendored or bundled.** The third-party binaries (LHM DLLs, HidSharp, PawnIO) are downloaded at install time into the user's own copy and are never committed (`*.dll`/`*.exe` are gitignored). No NOTICE file is needed for the repo as it stands.
- **Copyleft flags:**
  - LibreHardwareMonitor is **MPL-2.0** (weak, file-level copyleft), and so are the `DiskInfoToolkit`, `RAMSPDToolkit-NDD` and `BlackSharp.Core` support DLLs. They are loaded unmodified at runtime and aren't redistributed here. Anyone who redistributes a package that includes the DLLs must meet MPL-2.0's source-availability terms.
  - `pystray` is **LGPL-3.0**. It's installed from PyPI, not vendored. Redistributing a frozen or bundled build would bring LGPL relinking/replacement obligations.
- **PawnIO's license is unverified.** It's a separately installed system driver, not distributed by this repo.

**Trademarks and fonts:**
- Brand names appear only to describe things: LibreHardwareMonitor, PawnIO, Ryzen, Radeon, HWiNFO, Windows. None are in the app name or the icon. Low IP risk.
- Fonts (Segoe UI, Arial, Tahoma) are loaded from the Windows system font folder, not bundled.

## Security notes

- **Trust boundary:** a local, single-user desktop tool.
  - No network listener, no telemetry and no runtime network calls.
  - Its inputs are local hardware sensors, WMI and its own `config.json`.
  - The breakdown dialog and tooltip display only locally computed numbers.
- **Privilege:**
  - The scripts re-launch themselves elevated and run with `-ExecutionPolicy Bypass`.
  - The autostart task runs the tray **elevated at every logon** so LHM can use a kernel driver.
  - PawnIO is installed system-wide as a kernel driver.
  - The elevated task runs the venv interpreter, scripts and DLLs from the project folder, so that folder's integrity matters. Keep it writable only by trusted accounts.
- **Auth model / secrets:** none. Nothing is authenticated, and the tool stores no credentials.
- **Known risk categories (high level):**
  - Install-time supply chain: the latest upstream releases are downloaded and run without pinning or integrity verification.
  - Elevated persistence: the logon task runs at the highest run level.
- **Repo is archived:** these items won't be fixed here.
