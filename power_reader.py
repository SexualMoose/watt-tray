"""LibreHardwareMonitor wrapper for total system wattage.

Sums top-level power sensors only (HWiNFO-aligned): CPU Package and per-GPU
GPU Total. Components LHM can't read (RAM/mobo/SSD/fans on this hardware)
fall back to static estimates from config.
"""
from __future__ import annotations

import logging
import math
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_DIR))

# LHM ships as a .NET Framework 4.7.2 DLL; force pythonnet to use the netfx
# runtime instead of its CoreCLR default. Must be done before `import clr`.
try:
    from pythonnet import load as _pn_load
    _pn_load("netfx")
except Exception:
    pass

import clr  # noqa: E402

clr.AddReference(str(_PROJECT_DIR / "LibreHardwareMonitorLib.dll"))
clr.AddReference("System.Management")

from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType  # noqa: E402
from System.Management import ManagementObjectSearcher  # noqa: E402


# SMBIOSMemoryType values (DMTF SMBIOS spec § Memory Device)
_SMBIOS_RAM_TYPES = {
    20: "DDR",
    21: "DDR2",
    24: "DDR3",
    26: "DDR4",
    34: "DDR5",
}

# Temperature sensor name priority (LHM names vary slightly by hardware revision)
_CPU_TEMP_NAMES = [
    "Core (Tctl/Tdie)",
    "Core (Tctl)",
    "Core (Tdie)",
    "CPU Package",
    "Core Average",
    "Package",
]
_GPU_TEMP_NAMES = [
    "GPU Hot Spot",
    "GPU Core",
    "GPU Temperature",
    "GPU",
    "GPU Memory Junction",
]


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("watt_tray")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        _PROJECT_DIR / "watt_tray.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    return logger


_GPU_TYPES = {HardwareType.GpuAmd, HardwareType.GpuNvidia, HardwareType.GpuIntel}


class PowerReader:
    def __init__(self, config: dict) -> None:
        self.cfg = config
        self.log = _setup_logger()
        self._last_enum = 0.0
        self._enum_interval = float(config.get("reenumerate_interval_sec", 300))
        self.degraded = False
        self._degraded_logged = False
        self._first_sample_logged = False
        self._ram_info = self._detect_ram()
        self._ram_static_w, self._ram_label = self._compute_ram_watts()
        self._psutil = self._init_psutil()
        self._open_computer()

    def _init_psutil(self):
        try:
            import psutil
            psutil.cpu_percent(interval=None)  # prime
            return psutil
        except Exception as exc:
            self.log.warning("psutil unavailable; CPU estimation disabled: %s", exc)
            return None

    def _estimate_cpu_watts(self) -> float | None:
        """Linear estimate: idle_w + (cpu_load%/100) * (max_w - idle_w)."""
        est_cfg = self.cfg.get("cpu_estimate", {})
        if not est_cfg.get("enabled", True) or self._psutil is None:
            return None
        try:
            pct = float(self._psutil.cpu_percent(interval=None))
            idle_w = float(est_cfg.get("idle_w", 30.0))
            max_w = float(est_cfg.get("max_w", 145.0))
            return idle_w + (pct / 100.0) * (max_w - idle_w)
        except Exception as exc:
            self.log.warning("CPU estimate failed: %s", exc)
            return None

    def _detect_ram(self) -> dict | None:
        """Query WMI for installed DIMM count and type. Returns None on failure."""
        try:
            searcher = ManagementObjectSearcher(
                "SELECT Capacity, SMBIOSMemoryType FROM Win32_PhysicalMemory"
            )
            count = 0
            total_bytes = 0
            smbios_type: int | None = None
            for obj in searcher.Get():
                count += 1
                cap = obj["Capacity"]
                if cap is not None:
                    total_bytes += int(cap)
                t = obj["SMBIOSMemoryType"]
                if t is not None and smbios_type is None:
                    smbios_type = int(t)
            try:
                searcher.Dispose()
            except Exception:
                pass
            if count == 0:
                return None
            type_label = _SMBIOS_RAM_TYPES.get(smbios_type or 0, f"Unknown({smbios_type})")
            info = {
                "stick_count": count,
                "total_gb": total_bytes / (1024 ** 3),
                "smbios_type": smbios_type,
                "type_label": type_label,
            }
            self.log.info(
                "RAM detected: %d sticks, %.1f GB total, type=%s",
                info["stick_count"], info["total_gb"], info["type_label"],
            )
            return info
        except Exception as exc:
            self.log.warning("RAM auto-detect failed: %s", exc)
            return None

    def _compute_ram_watts(self) -> tuple[float, str]:
        """Return (max_watts, label) for the RAM static contribution."""
        ram_cfg = self.cfg["static"]["ram"]
        info = self._ram_info if ram_cfg.get("auto_detect", True) else None
        if info is None:
            w = ram_cfg["fallback_w_per_stick"] * ram_cfg["fallback_stick_count"]
            label = f"{ram_cfg['fallback_stick_count']} sticks (fallback)"
            return w, label
        if info["type_label"] == "DDR5":
            per_stick = ram_cfg["max_w_per_stick_ddr5"]
        else:
            per_stick = ram_cfg["max_w_per_stick_ddr4"]
        w = per_stick * info["stick_count"]
        label = f"{info['stick_count']}x {info['type_label']}"
        return w, label

    def _open_computer(self) -> None:
        self.computer = Computer()
        self.computer.IsCpuEnabled = True
        self.computer.IsGpuEnabled = True
        self.computer.IsMotherboardEnabled = True
        self.computer.IsMemoryEnabled = True
        self.computer.IsStorageEnabled = True
        self.computer.IsControllerEnabled = False
        self.computer.IsNetworkEnabled = False
        try:
            self.computer.Open()
            self._last_enum = time.time()
            self._log_inventory()
        except Exception as exc:
            self.log.error("Computer.Open() failed: %s", exc)
            self.degraded = True

    def _log_inventory(self) -> None:
        names = []
        for hw in self.computer.Hardware:
            names.append(f"{hw.HardwareType}={hw.Name}")
        self.log.info("LHM hardware discovered: %s", "; ".join(names))

    def _maybe_reenumerate(self) -> None:
        if time.time() - self._last_enum < self._enum_interval:
            return
        try:
            self.computer.Close()
        except Exception as exc:
            self.log.warning("Computer.Close() failed during re-enum: %s", exc)
        self._open_computer()

    def _update_all(self) -> None:
        for hw in self.computer.Hardware:
            try:
                hw.Update()
                for sh in hw.SubHardware:
                    sh.Update()
            except Exception as exc:
                self.log.warning("hw.Update() failed for %s: %s", hw.Name, exc)

    @staticmethod
    def _pick_sensor(hw, priority_names, sensor_type=None) -> float | None:
        if sensor_type is None:
            sensor_type = SensorType.Power
        for name in priority_names:
            for sensor in hw.Sensors:
                if sensor.SensorType != sensor_type:
                    continue
                if sensor.Name != name:
                    continue
                val = sensor.Value
                if val is None:
                    continue
                fval = float(val)
                if math.isnan(fval):
                    continue
                return fval
        return None

    def _read_cpu(self) -> float | None:
        priority = self.cfg["sensor_priority"]["cpu"]
        for hw in self.computer.Hardware:
            if hw.HardwareType == HardwareType.Cpu:
                v = self._pick_sensor(hw, priority)
                if v is not None:
                    return v
        return None

    def _read_cpu_temp(self) -> float | None:
        for hw in self.computer.Hardware:
            if hw.HardwareType == HardwareType.Cpu:
                return self._pick_sensor(hw, _CPU_TEMP_NAMES, SensorType.Temperature)
        return None

    def _read_gpus(self) -> list[tuple[str, float, float | None]]:
        """Returns list of (name, watts, temperature_c)."""
        priority = self.cfg["sensor_priority"]["gpu"]
        results: list[tuple[str, float, float | None]] = []
        for hw in self.computer.Hardware:
            if hw.HardwareType not in _GPU_TYPES:
                continue
            w = self._pick_sensor(hw, priority)
            t = self._pick_sensor(hw, _GPU_TEMP_NAMES, SensorType.Temperature)
            if w is not None:
                results.append((str(hw.Name), w, t))
        return results

    def get_breakdown(self) -> tuple[dict, dict]:
        """Return (values, sources) dicts. Sources marks each key 'sensor' or 'static'."""
        self._maybe_reenumerate()
        self._update_all()

        values: dict[str, float] = {}
        sources: dict[str, str] = {}

        cpu_w = self._read_cpu()
        sensor_threshold = float(
            self.cfg.get("cpu_estimate", {}).get("use_when_sensor_below_w", 1.0)
        )
        sensor_ok = cpu_w is not None and cpu_w >= sensor_threshold
        if sensor_ok:
            values["cpu"] = cpu_w
            sources["cpu"] = "sensor"
        else:
            est = self._estimate_cpu_watts()
            if est is not None:
                values["cpu"] = est
                sources["cpu"] = "estimate"
            elif cpu_w is None:
                values["cpu"] = 0.0
                sources["cpu"] = "missing"
            else:
                values["cpu"] = cpu_w
                sources["cpu"] = "sensor"

        cpu_t = self._read_cpu_temp()
        if cpu_t is not None:
            values["cpu_temp"] = cpu_t

        gpus = self._read_gpus()
        if not gpus:
            values["gpu_0"] = 0.0
            sources["gpu_0"] = "missing"
        else:
            for i, (name, watts, temp) in enumerate(gpus):
                key = f"gpu_{i}"
                values[key] = watts
                sources[key] = f"sensor:{name}"
                if temp is not None:
                    values[f"{key}_temp"] = temp

        static = self.cfg["static"]
        values["ram"] = self._ram_static_w
        sources["ram"] = f"static:{self._ram_label}"
        values["motherboard"] = static["motherboard_w"]
        sources["motherboard"] = "static:max"
        values["ssd"] = static["ssd_w_each"] * static["ssd_count"]
        sources["ssd"] = f"static:{static['ssd_count']}x{static['ssd_w_each']:.0f}W"
        values["fans"] = static["fan_w_each"] * static["fan_count"]
        sources["fans"] = f"static:{static['fan_count']}x{static['fan_w_each']:.0f}W"

        total = sum(
            v for k, v in values.items()
            if k != "total" and not k.endswith("_temp")
        )
        values["total"] = total

        if sources.get("cpu") in ("missing", "estimate"):
            self.degraded = True
            if not self._degraded_logged:
                if sources["cpu"] == "estimate":
                    self.log.warning(
                        "CPU package sensor reads 0/None; using load-based estimate. "
                        "For real readings, install PawnIO driver (https://pawnio.eu/)."
                    )
                else:
                    self.log.warning(
                        "CPU power neither sensor nor estimate available — degraded."
                    )
                self._degraded_logged = True

        # One-time log of the first sample so we can verify each component's value+source.
        if not self._first_sample_logged:
            self._first_sample_logged = True
            ordered_keys = [
                "cpu", "cpu_temp",
            ]
            for k in sorted(values):
                if k.startswith("gpu_"):
                    ordered_keys.append(k)
            ordered_keys += ["ram", "motherboard", "ssd", "fans", "total"]
            parts = []
            for k in ordered_keys:
                if k not in values:
                    continue
                unit = "°C" if k.endswith("_temp") else "W"
                src = sources.get(k, "")
                src_str = f"[{src}]" if src else ""
                parts.append(f"{k}={values[k]:.1f}{unit}{src_str}")
            self.log.info("First sample: %s", ", ".join(parts))

        return values, sources

    def read_total_watts(self) -> float:
        values, _ = self.get_breakdown()
        return values["total"]

    def close(self) -> None:
        try:
            self.computer.Close()
        except Exception:
            pass
