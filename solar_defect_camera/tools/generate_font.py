"""Generate a 5x8 bitmap font header for the OLED status display.

The firmware needs a tiny fixed-width font. Rather than hand-transcribing a
glyph table, this renders ASCII 32..126 from a system monospace face, picks the
rasterisation that best fits a 5x8 cell, and emits font5x8.h. It also writes a
magnified preview PNG so the result can be inspected before it is flashed.

Run from the sketch folder:
    .venv/bin/python tools/generate_font.py
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
FIRST_CHAR = 32
LAST_CHAR = 126
CELL_WIDTH = int(os.environ.get("OLED_CELL_WIDTH", "5"))
CELL_HEIGHT = 8

OUTPUT = PROJECT / f"font{CELL_WIDTH}x8.h"
PREVIEW = PROJECT / "design" / f"oled-font-preview-{CELL_WIDTH}x8.png"
FONT_CANDIDATES = [
    "/System/Library/Fonts/Monaco.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
]
# Glyphs that must survive rasterisation for the display to be readable.
LEGIBILITY_SAMPLE = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.:%-"


def rasterise(font: ImageFont.FreeTypeFont, char: str, dx: int, dy: int) -> list[list[int]]:
    """Render one character into a CELL_WIDTH x CELL_HEIGHT pixel matrix."""
    canvas = Image.new("L", (CELL_WIDTH, CELL_HEIGHT), 0)
    ImageDraw.Draw(canvas).text((dx, dy), char, font=font, fill=255)
    pixels = canvas.load()
    return [
        [1 if pixels[x, y] >= 110 else 0 for x in range(CELL_WIDTH)]
        for y in range(CELL_HEIGHT)
    ]


def score(font: ImageFont.FreeTypeFont, dx: int, dy: int) -> int:
    """Reward rasterisations that keep sample glyphs distinct and non-empty."""
    seen: dict[tuple, str] = {}
    total = 0
    for char in LEGIBILITY_SAMPLE:
        matrix = rasterise(font, char, dx, dy)
        lit = sum(sum(row) for row in matrix)
        if lit == 0:
            return -1_000_000
        key = tuple(tuple(row) for row in matrix)
        if key in seen:
            total -= 400
        seen[key] = char
        total += lit
    return total


def choose_rendering() -> tuple[ImageFont.FreeTypeFont, int, int, str]:
    best = None
    for path in FONT_CANDIDATES:
        if not Path(path).is_file():
            continue
        for size in range(6, 12):
            try:
                font = ImageFont.truetype(path, size)
            except OSError:
                continue
            for dy in range(-4, 2):
                for dx in range(-2, 2):
                    value = score(font, dx, dy)
                    if best is None or value > best[0]:
                        best = (value, font, dx, dy, f"{Path(path).name}@{size}")
    if best is None:
        raise SystemExit("No usable system font was found.")
    _, font, dx, dy, label = best
    return font, dx, dy, label


def column_bytes(matrix: list[list[int]]) -> list[int]:
    """Pack a glyph into column-major bytes, LSB = top row (SSD1306 layout)."""
    columns = []
    for x in range(CELL_WIDTH):
        byte = 0
        for y in range(CELL_HEIGHT):
            if matrix[y][x]:
                byte |= 1 << y
        columns.append(byte)
    return columns


def write_preview(glyphs: dict[str, list[list[int]]], label: str) -> None:
    lines = [
        "SOLAR INSPECTOR",
        "192.168.1.9  -68dBm",
        "DEFECT SUSPECTED",
        "2 regions  sev:med",
        "abcdefghijklmnopqrst",
        "!\"#$%&'()*+,-./:;<=>?",
    ]
    scale = 6
    columns = 128 // (CELL_WIDTH + 1)
    width = columns * (CELL_WIDTH + 1) * scale
    height = (len(lines) + 1) * (CELL_HEIGHT + 2) * scale
    image = Image.new("RGB", (width, height), (8, 12, 18))
    pixels = image.load()
    for row, text in enumerate(lines):
        for index, char in enumerate(text):
            matrix = glyphs.get(char)
            if matrix is None:
                continue
            ox = index * (CELL_WIDTH + 1) * scale
            oy = row * (CELL_HEIGHT + 2) * scale
            for y in range(CELL_HEIGHT):
                for x in range(CELL_WIDTH):
                    if not matrix[y][x]:
                        continue
                    for sy in range(scale):
                        for sx in range(scale):
                            px, py = ox + x * scale + sx, oy + y * scale + sy
                            if px < width and py < height:
                                pixels[px, py] = (150, 226, 255)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    image.save(PREVIEW)
    print(f"Preview: {PREVIEW.relative_to(PROJECT)} (source {label})")


def main() -> None:
    font, dx, dy, label = choose_rendering()
    glyphs: dict[str, list[list[int]]] = {}
    rows = []
    for code in range(FIRST_CHAR, LAST_CHAR + 1):
        char = chr(code)
        matrix = rasterise(font, char, dx, dy)
        glyphs[char] = matrix
        packed = column_bytes(matrix)
        comment = char if char != "\\" else "backslash"
        rows.append(
            "  " + ", ".join(f"0x{byte:02x}" for byte in packed) + f",  // {comment}"
        )

    header = "\n".join(
        [
            "#pragma once",
            "",
            f"// Generated by tools/generate_font.py from {label}.",
            "// Column-major 5x8 cells; bit 0 is the top pixel of each column.",
            f"constexpr uint8_t FONT_FIRST_CHAR = {FIRST_CHAR};",
            f"constexpr uint8_t FONT_LAST_CHAR = {LAST_CHAR};",
            f"constexpr uint8_t FONT_WIDTH = {CELL_WIDTH};",
            f"constexpr uint8_t FONT_HEIGHT = {CELL_HEIGHT};",
            "const uint8_t OLED_FONT[] PROGMEM = {",
            *rows,
            "};",
            "",
        ]
    )
    OUTPUT.write_text(header, encoding="utf-8")
    distinct = len({tuple(tuple(r) for r in m) for m in glyphs.values()})
    print(f"Font: {OUTPUT.relative_to(PROJECT)} — {len(glyphs)} glyphs, {distinct} distinct")
    write_preview(glyphs, label)


if __name__ == "__main__":
    main()
