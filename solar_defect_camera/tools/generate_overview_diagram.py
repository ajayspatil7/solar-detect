"""Render the plain 'what connects to what' overview.

Deliberately not to scale and not physically positioned: this answers only which
pin joins which pin. design/oled-wiring.png shows where each pad actually sits.

    .venv/bin/python tools/generate_overview_diagram.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "design" / "oled-overview.png"

W, H = 1720, 1180
CANVAS = (245, 243, 238)
SURFACE = (255, 253, 250)
INK = (41, 44, 50)
MUTED = (116, 116, 123)
LINE = (222, 218, 210)
BOARD = (32, 34, 40)
PCB_BLUE = (40, 88, 144)
GOLD = (198, 160, 74)

RED = (197, 83, 63)
BLACK = (58, 61, 69)
BLUE = (85, 127, 196)
GREEN = (62, 138, 104)

AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"
F_TITLE = ImageFont.truetype(AVENIR, 42, index=2)
F_H2 = ImageFont.truetype(AVENIR, 27, index=2)
F_BODY = ImageFont.truetype(AVENIR, 21, index=0)
F_SMALL = ImageFont.truetype(AVENIR, 18, index=0)
F_LABEL = ImageFont.truetype(AVENIR, 19, index=2)
F_PIN = ImageFont.truetype(MENLO, 20, index=1)
F_CAP = ImageFont.truetype(AVENIR, 17, index=0)

img = Image.new("RGB", (W, H), CANVAS)
d = ImageDraw.Draw(img)


def box(x0, y0, x1, y1, fill, outline, r=14):
    d.rounded_rectangle([x0, y0, x1, y1], r, fill=fill, outline=outline, width=3)


def pin(x, y, colour, label, side):
    d.rectangle([x - 11, y - 11, x + 11, y + 11], fill=colour, outline=GOLD, width=3)
    tw = d.textlength(label, font=F_PIN)
    d.text((x + 26 if side == "right" else x - 26 - tw, y - 12), label,
           font=F_PIN, fill=(232, 238, 246))


def wire(p0, p1, colour, label, width=8):
    mid = (p0[0] + p1[0]) // 2
    pts = [p0, (mid, p0[1]), (mid, p1[1]), p1]
    d.line(pts, fill=CANVAS, width=width + 8, joint="curve")
    d.line(pts, fill=colour, width=width, joint="curve")
    tw = d.textlength(label, font=F_LABEL)
    d.rectangle([mid - tw / 2 - 10, p1[1] - 15, mid + tw / 2 + 10, p1[1] + 14],
                fill=CANVAS)
    d.text((mid - tw / 2, p1[1] - 12), label, font=F_LABEL, fill=colour)


d.text((60, 46), "What connects to what", font=F_TITLE, fill=INK)
d.text((62, 104), "Only two jobs. The MB supplies power. The camera drives the display.",
       font=F_BODY, fill=MUTED)
d.text((62, 138), "The OLED never connects to the MB. All six wires go onto the pins on the "
                  "UNDERSIDE of the camera.", font=F_BODY, fill=INK)

TOP, BOT = 250, 620

# ------------------------------------------------------------------ boards ---
box(80, TOP, 400, BOT, BOARD, (84, 88, 96))
d.text((110, TOP + 26), "ESP32-CAM-MB", font=F_H2, fill=(206, 210, 218))
d.text((110, TOP + 66), "stays plugged into", font=F_SMALL, fill=(140, 144, 154))
d.text((110, TOP + 90), "your Mac by USB", font=F_SMALL, fill=(140, 144, 154))
d.rounded_rectangle([110, BOT - 76, 196, BOT - 40], 6, fill=(180, 184, 192))
d.text((208, BOT - 70), "USB", font=F_SMALL, fill=(140, 144, 154))

box(660, TOP, 1000, BOT, BOARD, (84, 88, 96))
d.text((700, TOP + 26), "ESP32-CAM", font=F_H2, fill=(206, 210, 218))
d.ellipse([772, BOT - 132, 888, BOT - 34], fill=(16, 17, 22), outline=(92, 96, 106), width=3)
d.ellipse([806, BOT - 112, 854, BOT - 64], fill=(30, 32, 40))

box(1290, TOP, 1640, BOT, PCB_BLUE, (24, 58, 100))
d.text((1400, TOP + 26), "OLED", font=F_H2, fill=(226, 236, 248))
d.rounded_rectangle([1360, TOP + 92, 1610, BOT - 48], 6, fill=(12, 14, 20),
                    outline=(22, 54, 92), width=2)
d.text((1392, TOP + 190), "SOLAR INSPECTOR", font=ImageFont.truetype(MENLO, 17),
       fill=(150, 226, 255))

# -------------------------------------------------------------------- pins ---
mb = {"5V": (400, 330), "GND": (400, 400)}
cam_in = {"5V": (660, 330), "GND": (660, 400)}   # left row, camera end
cam_out = {"GND": (1000, 320), "3V3": (1000, 386), "IO14": (1000, 452), "IO13": (1000, 518)}
oled = {"GND": (1290, 320), "VDD": (1290, 386), "SCK": (1290, 452), "SDA": (1290, 518)}

for name, xy in mb.items():
    pin(*xy, RED if name == "5V" else BLACK, name, "left")
for name, xy in cam_in.items():
    pin(*xy, RED if name == "5V" else BLACK, name, "right")
for name, xy in cam_out.items():
    pin(*xy, {"GND": BLACK, "3V3": RED, "IO14": GREEN, "IO13": BLUE}[name], name, "left")
for name, xy in oled.items():
    pin(*xy, {"GND": BLACK, "VDD": RED, "SCK": GREEN, "SDA": BLUE}[name], name, "right")

# ------------------------------------------------------------------- wires ---
wire(mb["5V"], cam_in["5V"], RED, "5V")
wire(mb["GND"], cam_in["GND"], BLACK, "GND")
wire(cam_out["GND"], oled["GND"], BLACK, "GND")
wire(cam_out["3V3"], oled["VDD"], RED, "3V3")
wire(cam_out["IO14"], oled["SCK"], GREEN, "IO14")
wire(cam_out["IO13"], oled["SDA"], BLUE, "IO13")

d.text((452, 250), "POWER  ·  2 wires", font=F_LABEL, fill=MUTED)
d.text((1052, 250), "DISPLAY  ·  4 wires", font=F_LABEL, fill=MUTED)

# ------------------------------------------------------------------- cards ---
CY0, CY1 = 700, 1090
card_pad = 26

d.rounded_rectangle([60, CY0, 560, CY1], 16, fill=SURFACE, outline=LINE, width=2)
d.text((60 + card_pad, CY0 + 20), "Power — 2 wires", font=F_H2, fill=INK)
d.text((60 + card_pad, CY0 + 62), "Male-to-female jumpers.", font=F_SMALL, fill=MUTED)
d.text((60 + card_pad, CY0 + 86), "Male end into the MB's empty socket,", font=F_SMALL, fill=MUTED)
d.text((60 + card_pad, CY0 + 110), "female end onto the camera's pin.", font=F_SMALL, fill=MUTED)
for i, (a, b, c) in enumerate([("5V", "5V", RED), ("GND", "GND", BLACK)]):
    y = CY0 + 156 + i * 42
    d.text((60 + card_pad, y), "MB", font=F_SMALL, fill=MUTED)
    d.text((60 + card_pad + 46, y - 2), a, font=F_PIN, fill=c)
    d.text((60 + card_pad + 130, y), "to camera", font=F_SMALL, fill=MUTED)
    d.text((60 + card_pad + 232, y - 2), b, font=F_PIN, fill=c)
d.text((60 + card_pad, CY0 + 250), "Use the LEFT row's GND here (2nd pin", font=F_SMALL, fill=INK)
d.text((60 + card_pad, CY0 + 274), "from the camera end).", font=F_SMALL, fill=INK)
d.text((60 + card_pad, CY0 + 312), "This is the only reason the MB stays", font=F_SMALL, fill=MUTED)
d.text((60 + card_pad, CY0 + 336), "in the picture after flashing.", font=F_SMALL, fill=MUTED)

d.rounded_rectangle([600, CY0, 1150, CY1], 16, fill=SURFACE, outline=LINE, width=2)
d.text((600 + card_pad, CY0 + 20), "Display — 4 wires", font=F_H2, fill=INK)
d.text((600 + card_pad, CY0 + 62), "Female-to-female jumpers. Both boards", font=F_SMALL, fill=MUTED)
d.text((600 + card_pad, CY0 + 86), "have male pins, so both ends are female.", font=F_SMALL, fill=MUTED)
for i, (a, b, c) in enumerate([("GND", "GND", BLACK), ("3V3", "VDD", RED),
                               ("IO14", "SCK", GREEN), ("IO13", "SDA", BLUE)]):
    y = CY0 + 132 + i * 42
    d.text((600 + card_pad, y), "camera", font=F_SMALL, fill=MUTED)
    d.text((600 + card_pad + 82, y - 2), a, font=F_PIN, fill=c)
    d.text((600 + card_pad + 190, y), "to OLED", font=F_SMALL, fill=MUTED)
    d.text((600 + card_pad + 280, y - 2), b, font=F_PIN, fill=c)
d.text((600 + card_pad, CY0 + 306), "Take this GND from the RIGHT row — the left", font=F_SMALL, fill=INK)
d.text((600 + card_pad, CY0 + 330), "one is used by the power wire above.", font=F_SMALL, fill=INK)
d.text((600 + card_pad, CY0 + 356), "3V3, never 5V. The ESP32 is not 5V tolerant.",
       font=F_SMALL, fill=RED)

d.rounded_rectangle([1190, CY0, 1660, CY1], 16, fill=(252, 246, 240),
                    outline=(226, 196, 170), width=2)
d.text((1190 + card_pad, CY0 + 20), "Order of work", font=F_H2, fill=(158, 86, 52))
for i, (t, c) in enumerate([
        ("1  Stack the camera on the MB as", INK),
        ("     usual and flash the firmware.", MUTED), ("", MUTED),
        ("2  Unstack the camera. Leave the", INK),
        ("     MB plugged into USB.", MUTED), ("", MUTED),
        ("3  Run the 2 power wires, then", INK),
        ("     the 4 display wires.", MUTED), ("", MUTED),
        ("4  Open /health in a browser. It", INK),
        ("     tells you if the OLED answered.", MUTED)]):
    d.text((1190 + card_pad, CY0 + 66 + i * 26), t, font=F_SMALL, fill=c)

d.text((60, H - 44), "This picture shows only which pin joins which pin. "
                     "design/oled-wiring.png shows where each pin sits on the board.",
       font=F_CAP, fill=MUTED)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUTPUT)
print(f"Wrote {OUTPUT.relative_to(PROJECT)}  ({W}x{H})")
