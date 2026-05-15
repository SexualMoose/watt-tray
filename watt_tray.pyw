"""Watt-Tray: system tray icon showing 1-min rolling average total wattage."""
from __future__ import annotations

import collections
import json
import logging
import statistics
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox, Tk

import pystray
import win32event
import winerror
from pywintypes import error as PyWinError

from power_reader import PowerReader
from tray_icon import render_icon

_PROJECT_DIR = Path(__file__).resolve().parent
_MUTEX_NAME = "Global\\WattTrayMutex"


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


def _acquire_single_instance() -> object | None:
    try:
        handle = win32event.CreateMutex(None, True, _MUTEX_NAME)
    except PyWinError as exc:
        # Mutex creation itself failed (e.g., permissions); proceed anyway.
        logging.getLogger("watt_tray").warning("Mutex create failed: %s", exc)
        return None
    import win32api
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return None
    return handle


def _fmt_temp(temp_c) -> str:
    if temp_c is None:
        return ""
    return f", {int(round(float(temp_c)))}°C"


def _build_tooltip(values: dict, sources: dict) -> str:
    total = int(round(values.get("total", 0)))
    parts = [f"Total: {total} W"]
    cpu_src = sources.get("cpu", "missing")
    cpu_tag = "" if cpu_src == "sensor" else (" (est)" if cpu_src == "estimate" else " (n/a)")
    cpu_w = int(round(values.get("cpu", 0)))
    parts.append(f"CPU: {cpu_w} W{_fmt_temp(values.get('cpu_temp'))}{cpu_tag}")
    gpu_keys = sorted(k for k in values if k.startswith("gpu_") and not k.endswith("_temp"))
    for k in gpu_keys:
        src = sources.get(k, "missing")
        tag = "" if src.startswith("sensor") else " (n/a)"
        w = int(round(values[k]))
        t = values.get(f"{k}_temp")
        parts.append(f"{k.upper()}: {w} W{_fmt_temp(t)}{tag}")
    return "\n".join(parts)


class WattTrayApp:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.log = _setup_logger()
        self.reader = PowerReader(cfg)
        self.buffer: collections.deque[float] = collections.deque(
            maxlen=int(cfg["rolling_window_samples"])
        )
        self.refresh_event = threading.Event()
        self.stop_event = threading.Event()
        self.restart_event = threading.Event()
        self.paused = False
        self.last_breakdown: tuple[dict, dict] = ({}, {})
        self._breakdown_lock = threading.Lock()
        self._reader_lock = threading.Lock()

        initial_img = render_icon(0, cfg)
        self.icon = pystray.Icon(
            "watt-tray",
            initial_img,
            "Watt Tray (initializing)",
            menu=pystray.Menu(
                pystray.MenuItem("Refresh now", self._on_refresh),
                pystray.MenuItem(
                    lambda item: "Resume measurement" if self.paused else "Pause measurement",
                    self._on_pause_toggle,
                ),
                pystray.MenuItem("Restart sensors", self._on_restart),
                pystray.MenuItem("Show breakdown", self._on_show_breakdown),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._on_exit),
            ),
        )

    # --- menu handlers ---
    def _on_refresh(self, _icon=None, _item=None) -> None:
        self.refresh_event.set()

    def _on_pause_toggle(self, icon=None, _item=None) -> None:
        self.paused = not self.paused
        self.log.info("Pause toggled: paused=%s", self.paused)
        if icon is not None:
            icon.update_menu()
        # Re-render immediately so the tooltip prefix and last value reflect state.
        self._render_once()

    def _on_restart(self, _icon=None, _item=None) -> None:
        self.log.info("Restart sensors requested via menu.")
        self.restart_event.set()
        self.refresh_event.set()  # wake the sample loop now

    def _on_show_breakdown(self, _icon=None, _item=None) -> None:
        with self._breakdown_lock:
            values, sources = self.last_breakdown
        if not values:
            text = "No data yet — try again in a few seconds."
        else:
            lines = [f"Total: {int(round(values['total']))} W", ""]
            cpu_w = int(round(values.get("cpu", 0)))
            cpu_t = values.get("cpu_temp")
            cpu_t_str = f", {int(round(cpu_t))}°C" if cpu_t is not None else ""
            lines.append(f"CPU: {cpu_w} W{cpu_t_str}  [{sources.get('cpu', '?')}]")
            for k in sorted(k for k in values if k.startswith("gpu_") and not k.endswith("_temp")):
                w = int(round(values[k]))
                t = values.get(f"{k}_temp")
                t_str = f", {int(round(t))}°C" if t is not None else ""
                lines.append(f"{k.upper()}: {w} W{t_str}  [{sources.get(k, '?')}]")
            text = "\n".join(lines)
        threading.Thread(target=self._show_messagebox, args=(text,), daemon=True).start()

    @staticmethod
    def _show_messagebox(text: str) -> None:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo("Watt Tray — breakdown", text)
        root.destroy()

    def _on_exit(self, _icon=None, _item=None) -> None:
        self.stop_event.set()
        self.icon.stop()

    # --- loops ---
    def _sample_loop(self) -> None:
        interval = float(self.cfg["sample_interval_sec"])
        while not self.stop_event.is_set():
            if self.restart_event.is_set():
                self.restart_event.clear()
                self._restart_reader()
            if not self.paused:
                try:
                    with self._reader_lock:
                        values, sources = self.reader.get_breakdown()
                    self.buffer.append(values["total"])
                    with self._breakdown_lock:
                        self.last_breakdown = (values, sources)
                except Exception as exc:
                    self.log.warning("sample failed: %s", exc)
            if self.refresh_event.wait(timeout=interval):
                self.refresh_event.clear()

    def _restart_reader(self) -> None:
        self.log.info("Restarting PowerReader (closing + reopening LHM)...")
        with self._reader_lock:
            try:
                self.reader.close()
            except Exception as exc:
                self.log.warning("reader.close() during restart failed: %s", exc)
            try:
                self.reader = PowerReader(self.cfg)
                self.buffer.clear()
                self.log.info("PowerReader restarted successfully.")
            except Exception as exc:
                self.log.exception("Failed to recreate PowerReader: %s", exc)

    def _render_loop(self) -> None:
        interval = float(self.cfg["update_interval_sec"])
        # Render once quickly after startup so user sees something within seconds.
        time.sleep(2)
        self._render_once()
        while not self.stop_event.is_set():
            if self.stop_event.wait(timeout=interval):
                return
            self._render_once()

    def _render_once(self) -> None:
        try:
            avg = statistics.mean(self.buffer) if self.buffer else 0.0
            self.icon.icon = render_icon(avg, self.cfg)
            with self._breakdown_lock:
                values, sources = self.last_breakdown
            prefixes = []
            if self.paused:
                prefixes.append("[PAUSED]")
            cpu_src = sources.get("cpu", "") if sources else ""
            if cpu_src == "estimate":
                prefixes.append("[CPU est]")
            elif cpu_src == "missing":
                prefixes.append("[CPU n/a]")
            prefix = " ".join(prefixes) + " " if prefixes else ""
            if values:
                tooltip = prefix + _build_tooltip(values, sources)
            else:
                tooltip = prefix + f"Watt Tray: {int(round(avg))} W (warming up)"
            self.icon.title = tooltip[:127]
        except Exception as exc:
            self.log.warning("render failed: %s", exc)

    def run(self) -> None:
        threading.Thread(target=self._sample_loop, daemon=True).start()
        threading.Thread(target=self._render_loop, daemon=True).start()
        self.log.info("Watt Tray started; entering icon.run() ...")
        try:
            self.icon.run()
        except BaseException as exc:
            self.log.exception("icon.run() raised: %s", exc)
            raise
        finally:
            self.stop_event.set()
            self.reader.close()
            self.log.info("Watt Tray exiting normally.")


def main() -> int:
    log = _setup_logger()
    log.info("=== Watt Tray launch: pid=%s exe=%s ===", __import__("os").getpid(), sys.executable)
    try:
        cfg = json.loads((_PROJECT_DIR / "config.json").read_text(encoding="utf-8"))
    except Exception as exc:
        log.exception("Failed to load config.json: %s", exc)
        return 1
    handle = _acquire_single_instance()
    if handle is None:
        log.info("Another Watt Tray instance is already running; exiting.")
        return 0
    try:
        app = WattTrayApp(cfg)
        app.run()
    except BaseException as exc:
        log.exception("main() crashed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
