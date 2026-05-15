"""Render the system-tray icon: white square with the wattage number centered."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_DIRS = [
    Path(r"C:\Windows\Fonts"),
]
_FONT_FALLBACKS = ["segoeui.ttf", "arial.ttf", "tahoma.ttf"]


def _resolve_font(name: str) -> str | None:
    candidates = [name] + [f for f in _FONT_FALLBACKS if f != name]
    for cand in candidates:
        for d in _FONT_DIRS:
            p = d / cand
            if p.exists():
                return str(p)
    return None


def _fit_font(text: str, target_px: int, font_path: str | None, max_pt: int, min_pt: int) -> ImageFont.ImageFont:
    if font_path is None:
        return ImageFont.load_default()
    lo, hi = min_pt, max_pt
    best = ImageFont.truetype(font_path, min_pt)
    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w <= target_px and h <= target_px:
            best = font
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def render_icon(watts: float, cfg: dict) -> Image.Image:
    size = int(cfg.get("icon_size_px", 64))
    bg = cfg.get("icon_bg", "#FFFFFF")
    fg = cfg.get("icon_fg", "#000000")
    font_name = cfg.get("font_family", "segoeui.ttf")
    max_pt = int(cfg.get("font_max_pt", 36))
    min_pt = int(cfg.get("font_min_pt", 14))

    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)

    text = str(int(round(max(0.0, watts))))
    target = int(size * 0.92)
    font_path = _resolve_font(font_name)
    font = _fit_font(text, target, font_path, max_pt, min_pt)

    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (size - w) // 2 - bbox[0]
    y = (size - h) // 2 - bbox[1]
    draw.text((x, y), text, fill=fg, font=font)
    return img
