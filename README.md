# watt-tray

> **Archived — superseded.** This standalone repo is read-only and no longer maintained. In May 2026, right after its only commit, the code was merged into a private monorepo, where development of a newer version continued. This copy is kept for reference. See [PROJECT-DOCUMENTATION.md](PROJECT-DOCUMENTATION.md) for the audited state of this code, including known issues.

System-tray icon for Windows that shows your machine's **total wattage** as a number. It samples LibreHardwareMonitor's hardware sensors every second. It was built for a Ryzen 9 5950X + dual Radeon workstation, but it works on any machine where LibreHardwareMonitor can read the CPU package power and GPU power sensors.

The icon is a white square with a black number: the rolling average of the watt readings (10 samples by default). The total includes CPU and each GPU (from sensors), plus static estimates for RAM, SSDs, motherboard and fans. Hover over the icon to see Total, CPU and each GPU, with temperatures.

---

## Screenshot

No image is included. The icon shows a number like `385`. It samples every second and redraws every 10 s by default (`update_interval_sec`). The tooltip shows Total / CPU / GPU watts and temperatures.

The right-click menu has:
- **Refresh now**
- **Pause/Resume measurement**
- **Restart sensors**
- **Show breakdown**: a dialog listing Total, CPU and each GPU (watts and temperature), with the data source of the CPU and each GPU value. The RAM, motherboard, SSD and fan estimates count toward the total but aren't listed.
- **Exit**

---

## Repository layout

```
watt-tray/
├── watt_tray.pyw            # Tray app entry point (pystray + tk for dialogs)
├── power_reader.py          # LibreHardwareMonitor wrapper via pythonnet
├── tray_icon.py             # Render the icon image (PIL)
├── config.example.json      # Tunable defaults — copy to config.json before first run
├── requirements.txt         # Python deps (psutil is missing — see below)
├── install.ps1              # Installer: LHM DLLs + venv + pip deps + logon task
├── register_task.ps1        # Register the WattTray logon task only
├── install_pawnio.ps1       # Optional: install the PawnIO driver for real CPU power
├── uninstall.ps1            # Stop the tray + remove the logon task (keeps files)
├── PROJECT-DOCUMENTATION.md
├── README.md
├── LICENSE
└── .gitignore
```

Files **not** in the repo (download them or create them yourself):
- `*.dll`: `LibreHardwareMonitorLib.dll` and `HidSharp.dll`, plus possibly some support DLLs for newer LHM releases. See "Required DLLs" below.
- The PawnIO installer, which `install_pawnio.ps1` downloads to `%TEMP%`.
- `venv/`: your local Python virtual environment.
- `config.json`: your live config for this machine. `config.example.json` is the template.
- `*.log`: runtime log (`watt_tray.log`) and the installer transcript (`install.log`).

---

## How it works

```
+----------------+   wattage   +----------------+   icon image   +-----------+
| power_reader   | ----------> | tray_icon      | -------------> | pystray   |
| (LHM via clr)  |             | (PIL drawing)  |                | (tray UI) |
+----------------+             +----------------+                +-----------+
```

* **`power_reader.py`** uses `pythonnet`'s `clr` to load `LibreHardwareMonitorLib.dll`. It opens the `Computer` object with CPU, GPU, motherboard, memory and storage monitoring enabled, then walks the sensor tree. It sums:
  - the top-level **CPU Package** sensor. Fallback names are configurable in `config.json`. If the sensor reads below 1 W, a CPU-load estimate is used instead, which needs `psutil`.
  - the **GPU Total** sensor for each GPU (or its fallbacks).
  - static estimates for RAM, motherboard, SSDs and fans, in the style of HWiNFO. LHM can't read these directly on most consumer hardware. Wattages and counts are configurable. The RAM stick count and DDR type are auto-detected through WMI.
* **`tray_icon.py`** draws a 64×64 square (white by default) with the watt number centered. The font size scales to fit.
* **`watt_tray.pyw`** creates the pystray icon and runs two background threads:
  - a sampling thread (once per second by default)
  - a render thread, which averages the last N samples and updates the icon and tooltip on a configurable schedule.

  A single-instance mutex (`Global\WattTrayMutex`) stops two trays running at once.

The LHM `Computer` object is reopened periodically (every 5 min by default, checked on each sample). This picks up hardware changes, such as a GPU changing power state, without restarting the app.

---

## Required DLLs (one-time setup)

These are third-party binaries and are **not** redistributed in this repo. `install.ps1` downloads them automatically from the latest LibreHardwareMonitor release (it prefers the `net472` zip). To do it by hand, put them in the repo root next to `watt_tray.pyw`:

| DLL | Source |
|---|---|
| `LibreHardwareMonitorLib.dll` | LibreHardwareMonitor [releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases): extract it from the release zip |
| `HidSharp.dll` | Ships alongside it in the same zip |

`install.ps1` copies only these two. The LHM zip ships more DLLs:

- `BlackSharp.Core.dll`, `DiskInfoToolkit.dll` and `RAMSPDToolkit-NDD.dll`: support libraries, not UI. From LHM 0.9.5 on, LHM's NuGet package lists `DiskInfoToolkit` and `RAMSPDToolkit-NDD` (both of which need `BlackSharp.Core`) as dependencies. Judging by their names, they back the storage and memory support this code enables. Whether the app fails without them is untested.
- `Microsoft.Bcl.*.dll`, `Microsoft.Win32.TaskScheduler.dll` and `System.*.dll`: earlier versions of this README listed these as needed. From 0.9.5 on, the NuGet package also lists `System.Memory` and `System.Threading.AccessControl`. Whether a given release needs these files next to the library is unverified.
- `OxyPlot.dll`, `OxyPlot.WindowsForms.dll` and `Aga.Controls.dll`: LHM's own UI. Not used here.

If `watt_tray.log` shows `Computer.Open() failed`, or memory and storage hardware is missing from its `LHM hardware discovered:` line, copy the support DLLs (and the matching `System.*.dll` files) next to `LibreHardwareMonitorLib.dll`.

For real CPU package power readings, also install **PawnIO**. It's the kernel driver that LHM 0.9.x uses in place of WinRing0. Run `install_pawnio.ps1`, which re-launches itself elevated. It downloads the latest installer from the GitHub releases of `namazso/PawnIO.Setup` and runs it silently. Without PawnIO, the CPU figure falls back to the load estimate (tooltip shows `[CPU est]`).

---

## Install / run

> `install.ps1` and `register_task.ps1` hard-code the original author's setup in three variables:
> - `$ProjectDir`: the project folder
> - `$Python`: the Python 3.11 path (`install.ps1` only)
> - `$userPrincipal`: the Windows username
>
> Edit them before running either script.

**Installer path:** run from the repo folder. The script re-launches itself elevated. It downloads the DLLs, creates the venv, installs the pip deps and registers the `WattTray` logon task.

Run this from an elevated PowerShell. Otherwise the script re-opens in a new admin window and returns immediately; wait until that window prints `=== Install complete ===` before running the next two lines. The admin window closes a few seconds after it finishes; if it closes without that line, check `install.log`.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install.ps1
.\venv\Scripts\python.exe -m pip install psutil   # not installed by the script; needed for the CPU estimate
copy config.example.json config.json              # not done by the script; the app exits without it
```

**Manual path:**

```powershell
git clone https://github.com/SexualMoose/watt-tray.git <project-dir>
cd <project-dir>

# Put the LibreHardwareMonitor DLLs in this directory (see table above).

# Create venv + install Python deps (psutil is not in requirements.txt):
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt psutil

# Seed config from template:
copy config.example.json config.json

# Run:
.\venv\Scripts\pythonw.exe watt_tray.pyw
```

The tray icon appears once LHM has opened, and shows its first value after about 2 s. If it doesn't appear, check `watt_tray.log` next to the script. pythonw silently throws away stderr, but the app writes a rotating log file.

### Autostart on Windows login

`install.ps1` registers the autostart task for you. To register it on its own, run `register_task.ps1`. Edit `$ProjectDir` and `$userPrincipal` in it first. It re-launches itself elevated the same way, so from a non-elevated prompt wait until the admin window prints `Scheduled task 'WattTray' registered.` before running `Start-ScheduledTask`.

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\register_task.ps1
Start-ScheduledTask -TaskName WattTray      # start now, or just log off/on
```

The task has these properties:
- runs at logon with **RunLevel Highest** (elevated), so LHM can use the low-level driver
- hidden
- restarts up to 3 times, 1 minute apart
- no execution time limit
- starts and keeps running on battery power

To remove it, run `uninstall.ps1`. It kills running `watt_tray.pyw` processes and unregisters the task, but leaves the files in place.

To register the task by hand from an elevated prompt, replace `<project-dir>` with your path:

```powershell
schtasks /Create /F /SC ONLOGON /RL HIGHEST /TN "WattTray" /TR '"<project-dir>\venv\Scripts\pythonw.exe" "<project-dir>\watt_tray.pyw"'
```

Note: a task created this way uses Task Scheduler defaults: it is stopped after 72 hours, runs only on AC power, doesn't restart on failure and isn't hidden. Use `register_task.ps1` for the configured task.

The archived sibling repo [ai-servers-tray](https://github.com/SexualMoose/ai-servers-tray) also has a companion `watt-tray-installer.py`. Its build script turns it into `dist/watt-tray-installer.exe`, which is not committed. That installer only creates or removes the same task and starts or stops the process (it also has a status mode). It hard-codes a fixed install folder and registers the task at LIMITED run level. The scripts in this repo replace it.

---

## Config reference (`config.json`)

| Key | Default | Meaning |
|---|---|---|
| `update_interval_sec` | 10 | How often the icon redraws |
| `sample_interval_sec` | 1 | How often `PowerReader.get_breakdown()` is called |
| `rolling_window_samples` | 10 | Trailing samples for the rolling average |
| `reenumerate_interval_sec` | 300 | How often to reopen the LHM Computer object |
| `icon_size_px` | 64 | Icon canvas size |
| `icon_bg`, `icon_fg` | `#FFFFFF`/`#000000` | Icon background and number color |
| `font_family`, `font_max_pt`, `font_min_pt` | `segoeui.ttf`, 36, 14 | Auto-scaled font for the wattage number. Falls back to arial/tahoma, then PIL default |
| `static.ram.*` | auto-detect; DDR4 6 W / DDR5 9 W per stick; fallback 6 W × 4 sticks | RAM power estimate |
| `static.motherboard_w` | 50 | Static motherboard estimate |
| `static.ssd_w_each`, `static.ssd_count` | 5 W × 8 | SSD power estimate |
| `static.fan_w_each`, `static.fan_count` | 2 W × 6 | Fan power estimate |
| `cpu_estimate.enabled` | true | Allow the load-based CPU estimate (needs `psutil`) |
| `cpu_estimate.idle_w` / `max_w` | 30 / 145 | Linear-interpolation fallback if LHM can't read the CPU Package sensor |
| `cpu_estimate.use_when_sensor_below_w` | 1.0 | The estimate kicks in below this threshold |
| `sensor_priority.cpu` / `gpu` | name lists | Ordered names to search in the LHM sensor tree |

Tune `static.*` to match your physical hardware. The defaults are tuned for one specific 5950X + dual-Radeon build.

---

## Hard-won lessons

These bit me during development. I'm recording them so they don't bite again:

* **`pythonnet` has to pick CoreCLR or .NET Framework (netfx) before `clr` is imported.** LibreHardwareMonitorLib is a .NET Framework 4.7.2 DLL. `power_reader.py` forces netfx with `from pythonnet import load; load("netfx")` *before* `import clr`. Setting `PYTHONNET_RUNTIME=netfx` in the environment is the equivalent. The wrong runtime gives a silent load failure with confusing errors.
* **pywin32 import order.** Keep the imports in the order `watt_tray.pyw` uses: `win32event`, `winerror`, then `pywintypes`, with `win32api` imported lazily. I originally noted that some Python builds raise an obscure DLL load error with a different order (unverified).
* **LHM needs `IsCpuEnabled = True` / `IsGpuEnabled = True` (and the other `Is*Enabled` flags) set _before_ `Computer.Open()`.** Setting them after `Open()` silently does nothing.
* **Use `pythonw.exe`, not `python.exe`.** A console window flashing up is jarring. pythonw throws away stdout and stderr, so write a real log file instead.
* **`pystray` on Windows is strict about the menu-action signature `(icon, item)`.** The handlers here are bound methods that take `(icon, item)`. Avoid lambdas with extra default kwargs.

---

## Working on this with a fresh Claude session

Point a new conversation at the repo. Start with:

> Read README.md and PROJECT-DOCUMENTATION.md to understand the project, then look at watt_tray.pyw, power_reader.py, and tray_icon.py.

Useful pointers for the LLM:
- `watt_tray.pyw` holds both background threads:
  - Sampling: `WattTrayApp._sample_loop()` fills a rolling deque.
  - Averaging and redraw: `WattTrayApp._render_loop()` / `_render_once()`.
  - The main thread runs `pystray.Icon.run()`.
- Sensor walking and name matching are in `power_reader.py`: `PowerReader._pick_sensor()`, `_read_cpu()`, `_read_gpus()` and `_read_cpu_temp()`. `get_breakdown()` assembles the result.
- Icon rendering is in `tray_icon.py:render_icon()`. Config controls colors and font.
- The single-instance mutex is named `Global\WattTrayMutex`.

---

## License

MIT — see [LICENSE](LICENSE).
