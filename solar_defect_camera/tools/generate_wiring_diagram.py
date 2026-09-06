"""Render the OLED wiring diagram for the ESP32-CAM.

Physical top view with the four solder targets highlighted, so the right pad can
be picked out of a dense 8-way header before any iron touches the board.

    .venv/bin/python tools/generate_wiring_diagram.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "design" / "oled-wiring.png"

W, H = 1700, 1420
CANVAS = (245, 243, 238)
SURFACE = (255, 253, 250)
INK = (41, 44, 50)
MUTED = (116, 116, 123)
LINE = (222, 218, 210)
BOARD = (32, 34, 40)
BOARD_EDGE = (84, 88, 96)
PCB_BLUE = (40, 88, 144)
GOLD = (198, 160, 74)
DIM = (138, 142, 152)

RED = (197, 83, 63)
BLACK = (52, 55, 63)
BLUE = (85, 127, 196)
GREEN = (62, 138, 104)

AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"

F_TITLE = ImageFont.truetype(AVENIR, 40, index=2)
F_H2 = ImageFont.truetype(AVENIR, 25, index=2)
F_BODY = ImageFont.truetype(AVENIR, 19, index=0)
F_SMALL = ImageFont.truetype(AVENIR, 17, index=0)
F_TINY = ImageFont.truetype(AVENIR, 16, index=0)
F_PIN = ImageFont.truetype(MENLO, 17)
F_PIN_B = ImageFont.truetype(MENLO, 18, index=1)
F_NUM = ImageFont.truetype(AVENIR, 18, index=2)

LEFT_PINS = ["5V", "GND", "IO12", "IO13", "IO15", "IO14", "IO2", "IO4"]
RIGHT_PINS = ["3V3", "IO16", "IO0", "GND", "VCC", "U0R", "U0T", "GND"]
# CAM pin -> (colour, marker, OLED pin)
TARGET_L = {"GND": (BLACK, "1", "GND"), "IO13": (BLUE, "4", "SDA"), "IO14": (GREEN, "3", "SCK")}

image = Image.new("RGB", (W, H), CANVAS)
d = ImageDraw.Draw(image)


def card(x0, y0, x1, y1, r=16, fill=SURFACE, outline=LINE):
    d.rounded_rectangle([x0, y0, x1, y1], r, fill=fill, outline=outline, width=2)


def wire(points, colour, width=7):
    d.line(points, fill=CANVAS, width=width + 8, joint="curve")
    d.line(points, fill=colour, width=width, joint="curve")


def marker(cx, cy, colour, label, r=15):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=SURFACE, width=3)
    d.text((cx - d.textlength(label, font=F_NUM) / 2, cy - 11), label, font=F_NUM, fill=SURFACE)


d.text((60, 46), "ESP32-CAM to I2C OLED wiring", font=F_TITLE, fill=INK)
d.text((62, 100), "Both boards seen from the top, component side facing you. "
                  "Solder the four highlighted pads.", font=F_BODY, fill=MUTED)

# ------------------------------------------------------------ OLED module ---
OX0, OY0, OX1, OY1 = 200, 300, 560, 620
card(OX0, OY0, OX1, OY1, r=12, fill=PCB_BLUE, outline=(24, 58, 100))
d.rounded_rectangle([OX0 + 30, OY0 + 96, OX1 - 96, OY1 - 60], 6,
                    fill=(12, 14, 20), outline=(22, 54, 92), width=2)
d.text((OX0 + 54, OY0 + 168), "SOLAR INSPECTOR", font=F_PIN, fill=(150, 226, 255))
d.text((OX0 + 24, OY1 - 44), "0.96\" SSD1306  128x64", font=F_TINY, fill=(190, 214, 238))
for hx, hy in [(OX0 + 22, OY0 + 22), (OX1 - 22, OY0 + 22),
               (OX0 + 22, OY1 - 22), (OX1 - 22, OY1 - 22)]:
    d.ellipse([hx - 9, hy - 9, hx + 9, hy + 9], fill=CANVAS, outline=(24, 58, 100), width=2)

OLED_ORDER = [("GND", BLACK, "1"), ("VDD", RED, "2"), ("SCK", GREEN, "3"), ("SDA", BLUE, "4")]
oled_xy = {}
for i, (name, colour, _n) in enumerate(OLED_ORDER):
    cx, cy = OX1 - 20, OY0 + 50 + i * 60
    oled_xy[name] = (cx, cy)
    d.rectangle([cx - 11, cy - 11, cx + 11, cy + 11], fill=colour, outline=GOLD, width=3)
    d.text((cx - 34 - d.textlength(name, font=F_PIN_B), cy - 10), name,
           font=F_PIN_B, fill=(228, 238, 250))

# --------------------------------------------------------- ESP32-CAM board --
BX0, BY0, BX1, BY1 = 820, 220, 1180, 900
card(BX0, BY0, BX1, BY1, r=14, fill=BOARD, outline=BOARD_EDGE)
d.rounded_rectangle([BX0 + 120, BY0 + 26, BX0 + 240, BY0 + 146], 10,
                    fill=(18, 19, 24), outline=(66, 70, 78), width=2)
d.ellipse([BX0 + 144, BY0 + 50, BX0 + 216, BY0 + 122], fill=(10, 11, 14),
          outline=(94, 98, 108), width=3)
d.ellipse([BX0 + 164, BY0 + 70, BX0 + 196, BY0 + 102], fill=(28, 30, 38))
d.text((BX0 + 132, BY0 + 154), "OV2640", font=F_TINY, fill=(126, 130, 140))
d.text((BX0 + 108, BY1 - 44), "ESP32-CAM", font=F_H2, fill=(148, 152, 162))

TOP, GAP, PAD = BY0 + 210, 56, 13
left_xy, right_xy = {}, {}
for i, name in enumerate(LEFT_PINS):
    cx, cy = BX0 + 34, TOP + i * GAP
    left_xy[name] = (cx, cy)
    hot = TARGET_L.get(name)
    d.ellipse([cx - PAD, cy - PAD, cx + PAD, cy + PAD],
              fill=(hot[0] if hot else (56, 58, 66)), outline=GOLD, width=3)
    d.text((cx + 28, cy - 10), name, font=F_PIN_B if hot else F_PIN,
           fill=(hot[0] if hot else DIM))
for i, name in enumerate(RIGHT_PINS):
    cx, cy = BX1 - 34, TOP + i * GAP
    hot = (name == "3V3")
    if hot:
        right_xy["3V3"] = (cx, cy)
    d.ellipse([cx - PAD, cy - PAD, cx + PAD, cy + PAD],
              fill=(RED if hot else (56, 58, 66)), outline=GOLD, width=3)
    d.text((cx - 28 - d.textlength(name, font=F_PIN_B if hot else F_PIN), cy - 10),
           name, font=F_PIN_B if hot else F_PIN, fill=(RED if hot else DIM))

# ------------------------------------------------------------------ wires ---
routes = [
    ("GND", BLACK, "1", "GND", 700),
    ("IO13", BLUE, "4", "SDA", 660),
    ("IO14", GREEN, "3", "SCK", 620),
]
for cam_pin, colour, num, oled_pin, bend in routes:
    sx, sy = left_xy[cam_pin]
    ex, ey = oled_xy[oled_pin]
    wire([(sx, sy), (bend, sy), (bend, ey), (ex, ey)], colour)

sx, sy = right_xy["3V3"]
ex, ey = oled_xy["VDD"]
wire([(sx, sy), (1268, sy), (1268, 168), (600, 168), (600, ey), (ex, ey)], RED)

for cam_pin, colour, num, oled_pin, _b in routes:
    marker(*left_xy[cam_pin], colour, num)
    marker(*oled_xy[oled_pin], colour, num)
marker(*right_xy["3V3"], RED, "2")
marker(*oled_xy["VDD"], RED, "2")

# ----------------------------------------------------------- bottom cards ---
CY0, CY1 = 960, 1370

card(60, CY0, 560, CY1)
d.text((84, CY0 + 20), "Connections", font=F_H2, fill=INK)
d.text((132, CY0 + 66), "ESP32-CAM", font=F_TINY, fill=MUTED)
d.text((330, CY0 + 66), "OLED", font=F_TINY, fill=MUTED)
for i, (num, colour, a, b) in enumerate(
        [("1", BLACK, "GND", "GND"), ("2", RED, "3V3", "VDD"),
         ("3", GREEN, "IO14", "SCK"), ("4", BLUE, "IO13", "SDA")]):
    y = CY0 + 102 + i * 36
    marker(102, y + 9, colour, num, r=13)
    d.text((132, y), a, font=F_PIN_B, fill=INK)
    d.text((266, y), "-->", font=F_PIN, fill=MUTED)
    d.text((330, y), b, font=F_PIN_B, fill=INK)

d.text((84, CY0 + 258), "OLED pin order 1 to 4 is GND, VDD, SCK, SDA,", font=F_SMALL, fill=MUTED)
d.text((84, CY0 + 281), "matching the silkscreen on the module.", font=F_SMALL, fill=MUTED)

card(590, CY0, 1120, CY1)
d.text((614, CY0 + 20), "Before you solder", font=F_H2, fill=INK)
for i, (text, colour) in enumerate([
        ("Solder the OLED's 4-pin header first — it ships", INK),
        ("loose in the bag.", MUTED),
        ("", MUTED),
        ("VDD goes to 3V3, never 5V. The module pulls", INK),
        ("SDA and SCL up to VDD, and the ESP32's GPIOs", MUTED),
        ("are not 5V tolerant.", MUTED),
        ("", MUTED),
        ("SCK on this module is I2C SCL. No external", INK),
        ("pull-up resistors are needed.", MUTED),
        ("", MUTED),
        ("Tack the wires to the top-side pads so the board", INK),
        ("still seats in the MB programmer.", MUTED)]):
    d.text((614, CY0 + 62 + i * 23), text, font=F_SMALL, fill=colour)

card(1150, CY0, 1640, CY1, fill=(252, 246, 240), outline=(226, 196, 170))
d.text((1174, CY0 + 20), "Do not use these pins", font=F_H2, fill=(158, 86, 52))
for i, (text, colour) in enumerate([
        ("IO12   strapping pin. A pull-up at boot sets the", INK),
        ("           wrong flash voltage and the board", MUTED),
        ("           will not start.", MUTED),
        ("IO16   wired to PSRAM on this board.", INK),
        ("IO15   a pull-up here silences the boot log.", INK),
        ("           Works, but you lose diagnostics.", MUTED),
        ("U0R    UART — upload and Serial Monitor.", INK),
        ("U0T    UART — upload and Serial Monitor.", INK),
        ("", MUTED),
        ("5V     would put 5V on SDA and SCL.", INK)]):
    d.text((1174, CY0 + 62 + i * 23), text, font=F_SMALL, fill=colour)

d.text((60, H - 40), "IO13 and IO14 are free only because no microSD is fitted. "
                     "Neither is a boot strapping pin.", font=F_TINY, fill=MUTED)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUTPUT)
print(f"Wrote {OUTPUT.relative_to(PROJECT)}  ({W}x{H})")
