# watt-tray

System-tray icon for Windows that displays your machine's **total wattage** as a number, refreshed every second from LibreHardwareMonitor's hardware sensors. Built originally for a Ryzen 9 5950X + dual Radeon workstation, but it works on any machine where LibreHardwareMonitor can read the CPU package and GPU total power sensors.

The icon is a white square with a black number — the rolling-average watt reading. Hover the icon for the breakdown by component (CPU, each GPU, plus static estimates for RAM/SSDs/motherboard/fans).

---

## Screenshot

The icon shows a number like `385` and updates every second. Right-click for a menu with a one-line breakdown and a quit option. Tooltip shows the per-component split.

---

## Repository layout

```
watt-tray/
├── watt_tray.pyw          # Tray app entry point (pystray + tk for dialogs)
├── power_reader.py        # LibreHardwareMonitor wrapper via pythonnet
├── tray_icon.py           # Render the icon image (PIL)
├── config.example.json    # Tunable defaults — copy to config.json before first run
├── requirements.txt       # Python deps
├── README.md
├── LICENSE
└── .gitignore
```

Files **not** in the repo (download/build separately):
- `*.dll` — LibreHardwareMonitor + OxyPlot + supporting NuGet DLLs (see "Required DLLs" below).
- `PawnIO_setup.exe` — optional driver setup for low-level hardware access.
- `venv/` — your local Python virtual environment.
- `config.json` — your live config (per-machine; the example is the template).
- `*.log` — runtime logs.

---

## How it works

```
+----------------+   wattage   +----------------+   icon image   +-----------+
| power_reader   | ----------> | tray_icon      | -------------> | pystray   |
| (LHM via clr)  |             | (PIL drawing)  |                | (tray UI) |
+----------------+             +----------------+                +-----------+
```

* **`power_reader.py`** uses `pythonnet`'s `clr` to load `LibreHardwareMonitorLib.dll`. It opens the Computer object with CPU + GPU monitoring enabled and walks the sensor tree. It sums:
  - top-level **CPU Package** sensor (configurable name fallback list in `config.json`)
  - per-GPU **GPU Total** sensor (or fallbacks)
  - static per-component estimates for RAM/motherboard/SSDs/fans (configurable wattage and counts; HWiNFO-style estimates that LHM can't read directly on most consumer hardware)
* **`tray_icon.py`** draws a 64×64 white square with the watt number centered, font size auto-scaled to fit.
* **`watt_tray.pyw`** holds the pystray icon, runs a sampling thread, computes a rolling average over the last N samples, and updates the icon and tooltip on a configurable cadence. A single-instance mutex (`Global\WattTrayMutex`) prevents two trays from running at once.

A re-enumeration timer (default every 5 min) re-opens the LHM Computer object to catch hardware changes (GPU power state transitions, etc.) without restarting the app.

---

## Required DLLs (one-time setup)

These are third-party binaries — they're **not** redistributed in this repo. Drop them into the repo root (alongside `watt_tray.pyw`):

| DLL | Source |
|---|---|
| `LibreHardwareMonitorLib.dll` | LibreHardwareMonitor [releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases) — extract from the standalone build's zip |
| `HidSharp.dll` | Same zip, ships alongside |
| `Microsoft.Bcl.*.dll` | Same zip |
| `Microsoft.Win32.TaskScheduler.dll` | Same zip |
| `System.*.dll` | Same zip (BCL re-targeting set) |

Optional (only needed if you want OxyPlot graphs in a future revision; not required by the current code):

| `OxyPlot.dll`, `OxyPlot.WindowsForms.dll`, `Aga.Controls.dll`, `BlackSharp.Core.dll`, `DiskInfoToolkit.dll`, `RAMSPDToolkit-NDD.dll` |

For raw hardware access on some sensors, you may also need to install **PawnIO** (also a LibreHardwareMonitor companion) — grab `PawnIO_setup.exe` from LibreHardwareMonitor's release and run it once.

---

## Install / run

```powershell
git clone <this-repo-url> C:\Users\Tyler\watt-tray
cd C:\Users\Tyler\watt-tray

# Drop the LibreHardwareMonitor DLLs in this directory (see table above).

# Create venv + install Python deps:
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Seed config from template:
copy config.example.json config.json

# Run:
.\venv\Scripts\pythonw.exe watt_tray.pyw
```

The tray icon appears within ~2 s. If it doesn't, check `watt_tray.log` next to the script — pythonw silently discards stderr, but the app writes a rotating log file.

### Autostart on Windows login

There's a companion installer `.exe` over in the [ai-servers-tray repo](https://github.com/REPLACE-WITH-YOUR-USERNAME/ai-servers-tray) — `dist/watt-tray-installer.exe`. Run it from an elevated terminal to register a scheduled task that launches `watt_tray.pyw` at logon. Uninstall reverses that and stops the process.

If you'd rather not use the installer, you can register the task manually:

```powershell
schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "WattTray" /TR '"C:\Users\Tyler\watt-tray\venv\Scripts\pythonw.exe" "C:\Users\Tyler\watt-tray\watt_tray.pyw"'
```

---

## Config reference (`config.json`)

| Key | Default | Meaning |
|---|---|---|
| `update_interval_sec` | 10 | How often the icon redraws |
| `sample_interval_sec` | 1 | How often `power_reader.sample()` is called |
| `rolling_window_samples` | 10 | Trailing samples for the rolling average |
| `reenumerate_interval_sec` | 300 | How often to re-open LHM Computer object |
| `icon_size_px` | 64 | Icon canvas size |
| `icon_bg`, `icon_fg` | `#FFFFFF`/`#000000` | Icon background and number color |
| `font_family`, `font_max_pt`, `font_min_pt` | segoeui | Auto-scaled font for the wattage number |
| `static.ram.*` | DDR4 6 W/stick × auto-detect, fallback 4 sticks | RAM power estimate |
| `static.motherboard_w` | 50 | Static motherboard estimate |
| `static.ssd_w_each`, `static.ssd_count` | 5 W × 8 | SSD power estimate |
| `static.fan_w_each`, `static.fan_count` | 2 W × 6 | Fan power estimate |
| `cpu_estimate.idle_w` / `max_w` | 30 / 145 | Linear-interp fallback if LHM can't read the CPU Package sensor |
| `cpu_estimate.use_when_sensor_below_w` | 1.0 | Threshold under which the estimate kicks in |
| `sensor_priority.cpu` / `gpu` | name list | Ordered names to search in the LHM sensor tree |

Tune `static.*` to match your physical hardware — the defaults are tuned for a specific 5950X + dual-Radeon build.

---

## Hard-won lessons

These bit me during development; recording so they don't bite again:

* **`pythonnet` requires CoreCLR-vs-netfx selection at import time.** LibreHardwareMonitorLib is a .NET Framework 4.7.2 DLL — force `pythonnet` into netfx mode with `os.environ["PYTHONNET_RUNTIME"] = "netfx"` *before* `import clr`. Wrong runtime = silent load failure with confusing errors.
* **`pywintypes` import order matters.** Importing `win32event` before `pywintypes` raises an obscure DLL load error on some Python builds. Order them as in the source.
* **LHM needs `Computer.Open()` and `IsCpuEnabled = True` / `IsGpuEnabled = True` set _before_ Open.** Setting them after Open silently does nothing.
* **Use `pythonw.exe`, not `python.exe`.** A console window flashing for every minor I/O is jarring; pythonw discards stdout/stderr cleanly — write a real log file instead.
* **`pystray` on Windows enforces a strict `(icon, item)` action signature.** Use closure factories, not lambdas with default kwargs.

---

## Working on this with a fresh Claude session

Point a new conversation at the repo. Start with:

> Read README.md to understand the project, then look at watt_tray.pyw, power_reader.py, and tray_icon.py.

Useful pointers for the LLM:
- The sampling/averaging loop is in `watt_tray.pyw`'s main thread.
- LHM sensor walking + name matching is in `power_reader.py:PowerReader._collect_*()`.
- Icon rendering is in `tray_icon.py:render_icon()` — config controls colors and font.
- The single-instance mutex name is `Global\WattTrayMutex`.

---

## License

MIT — see [LICENSE](LICENSE).
