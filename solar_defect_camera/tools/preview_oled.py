"""Render the OLED status screens to a PNG for design review.

This mirrors renderDisplay() in solar_defect_camera.ino using the same
generated font, so the panel layout can be judged before hardware is wired.
It is a review aid, not a second implementation: if renderDisplay() changes,
update the LAYOUTS below to match.

    .venv/bin/python tools/preview_oled.py
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT = Path(__file__).resolve().parents[1]
FONT_HEADER = PROJECT / "font5x8.h"
OUTPUT = PROJECT / "design" / "oled-screens.png"

WIDTH, HEIGHT = 128, 64
FONT_WIDTH, FONT_HEIGHT = 5, 8
SCALE = 4
IP = "192.168.1.9"
RSSI = "-68"

# state, headline, detail, defect count
SCREENS = [
    ("Boot", "STARTING", "CAMERA INIT", None),
    ("Wi-Fi", "WIFI", "CONNECTING", None),
    ("Ready", "READY", "AWAITING CAPTURE", None),
    ("Capturing", "CAPTURING", "UXGA STILL", None),
    ("Captured", "CAPTURED", "62 KB IN 486 MS", None),
    ("Analyzing", "ANALYZING", "UPLOADED TO MAC", None),
    ("Defect found", "DEFECT", "SEVERITY MEDIUM", 2),
    ("Panel clear", "CLEAR", "NO VISIBLE DEFECT", 0),
    ("Uncertain", "UNCERTAIN", "", 1),
    ("Retake", "RETAKE", "IMAGE UNUSABLE", 0),
    ("Error", "ERROR", "ANALYSIS TIMEOUT", None),
    ("Camera fail", "CAMERA FAIL", "CHECK RIBBON", None),
]


def load_font() -> dict[str, list[int]]:
    text = FONT_HEADER.read_text()
    rows = re.findall(r"^  ((?:0x[0-9a-f]{2}, ){4}0x[0-9a-f]{2}),", text, re.M)
    glyphs = {}
    for index, row in enumerate(rows):
        glyphs[chr(32 + index)] = [int(b, 16) for b in row.split(", ")]
    return glyphs


class Panel:
    """A 1-bit framebuffer with the same primitives the driver exposes."""

    def __init__(self) -> None:
        self.pixels = [[0] * WIDTH for _ in range(HEIGHT)]

    def set_pixel(self, x: int, y: int) -> None:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.pixels[y][x] = 1

    def text(self, x: int, y: int, value: str, glyphs, scale: int = 1) -> None:
        for char in value.upper():
            columns = glyphs.get(char, glyphs["?"])
            for column, bits in enumerate(columns):
                for row in range(FONT_HEIGHT):
                    if not bits & (1 << row):
                        continue
                    for sy in range(scale):
                        for sx in range(scale):
                            self.set_pixel(x + column * scale + sx, y + row * scale + sy)
            x += (FONT_WIDTH + 1) * scale
            if x >= WIDTH:
                break

    def hline(self, y: int) -> None:
        for x in range(WIDTH):
            self.set_pixel(x, y)


def render(headline: str, detail: str, defects: int | None, glyphs) -> Panel:
    panel = Panel()
    panel.text(0, 0, "SOLAR INSPECTOR", glyphs)
    panel.hline(9)

    scale = 2 if len(headline) <= 10 else 1
    panel.text(0, 15 if scale == 2 else 19, headline, glyphs, scale)

    next_y = 36
    if detail:
        panel.text(0, next_y, detail, glyphs)
        next_y = 46
    if defects is not None:
        panel.text(0, next_y, f"{defects} REGION{'' if defects == 1 else 'S'}", glyphs)

    panel.hline(54)
    panel.text(0, 56, IP, glyphs)
    panel.text(WIDTH - 24, 56, RSSI, glyphs)
    return panel


def main() -> None:
    glyphs = load_font()
    columns = 3
    rows = (len(SCREENS) + columns - 1) // columns
    cell_w, cell_h = WIDTH * SCALE + 24, HEIGHT * SCALE + 44
    image = Image.new("RGB", (columns * cell_w, rows * cell_h), (26, 26, 30))
    draw = ImageDraw.Draw(image)

    for index, (label, headline, detail, defects) in enumerate(SCREENS):
        panel = render(headline, detail, defects, glyphs)
        ox = (index % columns) * cell_w + 12
        oy = (index // columns) * cell_h + 32
        draw.rectangle([ox - 2, oy - 2, ox + WIDTH * SCALE + 1, oy + HEIGHT * SCALE + 1],
                       fill=(4, 6, 10), outline=(70, 70, 78))
        draw.text((ox, oy - 20), label, fill=(190, 190, 200))
        pixels = image.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if not panel.pixels[y][x]:
                    continue
                for sy in range(SCALE):
                    for sx in range(SCALE):
                        pixels[ox + x * SCALE + sx, oy + y * SCALE + sy] = (150, 226, 255)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(f"Wrote {OUTPUT.relative_to(PROJECT)} — {len(SCREENS)} screens")


if __name__ == "__main__":
    main()
