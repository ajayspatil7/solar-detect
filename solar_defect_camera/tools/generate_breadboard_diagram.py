"""Render the solderless breadboard wiring option.

The ESP32-CAM's two headers are 0.9 in apart, so on a 0.1 in breadboard they
land in rows b and i and leave exactly one reachable hole per pin: row a on one
side and row j on the other. This diagram shows that, plus how the MB keeps
supplying power once the camera is no longer sitting in it.

    .venv/bin/python tools/generate_breadboard_diagram.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "design" / "oled-breadboard.png"

W, H = 1860, 1500
CANVAS = (245, 243, 238)
SURFACE = (255, 253, 250)
INK = (41, 44, 50)
MUTED = (116, 116, 123)
LINE = (222, 218, 210)
BB_BODY = (238, 235, 228)
BB_EDGE = (206, 201, 191)
HOLE = (168, 164, 156)
HOLE_FREE = (198, 160, 74)
BOARD = (32, 34, 40)
PCB_BLUE = (40, 88, 144)
DIM = (138, 142, 152)

RED = (197, 83, 63)
BLACK = (52, 55, 63)
BLUE = (85, 127, 196)
GREEN = (62, 138, 104)
RAIL_RED = (198, 96, 78)
RAIL_BLUE = (78, 112, 170)

AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"
F_TITLE = ImageFont.truetype(AVENIR, 40, index=2)
F_H2 = ImageFont.truetype(AVENIR, 25, index=2)
F_BODY = ImageFont.truetype(AVENIR, 19, index=0)
F_SMALL = ImageFont.truetype(AVENIR, 17, index=0)
F_TINY = ImageFont.truetype(AVENIR, 15, index=0)
F_PIN = ImageFont.truetype(MENLO, 15)
F_PIN_B = ImageFont.truetype(MENLO, 16, index=1)
F_NUM = ImageFont.truetype(AVENIR, 18, index=2)

base = Image.new("RGB", (W, H), CANVAS)
d = ImageDraw.Draw(base)


def card(x0, y0, x1, y1, r=16, fill=SURFACE, outline=LINE):
    d.rounded_rectangle([x0, y0, x1, y1], r, fill=fill, outline=outline, width=2)


def wire(dr, points, colour, width=7):
    dr.line(points, fill=CANVAS, width=width + 8, joint="curve")
    dr.line(points, fill=colour, width=width, joint="curve")


def marker(dr, cx, cy, colour, label, r=14):
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour, outline=SURFACE, width=3)
    dr.text((cx - dr.textlength(label, font=F_NUM) / 2, cy - 11), label, font=F_NUM, fill=SURFACE)


d.text((60, 44), "Solderless option: ESP32-CAM on a breadboard", font=F_TITLE, fill=INK)
d.text((62, 98), "The camera leaves the MB to run. The MB stays plugged into USB and feeds it "
                 "5V over two wires.", font=F_BODY, fill=MUTED)

# ---------------------------------------------------------------- breadboard -
PITCH = 26
COLS = 28
BX = 470
RAIL_P_Y, RAIL_N_Y = 392, 418
ROW_Y = {}
for i, r in enumerate("abcde"):
    ROW_Y[r] = 470 + i * PITCH
for i, r in enumerate("fghij"):
    ROW_Y[r] = 626 + i * PITCH
RAIL_P2_Y, RAIL_N2_Y = 786, 812

d.rounded_rectangle([BX - 40, 366, BX + COLS * PITCH + 20, 838], 10,
                    fill=BB_BODY, outline=BB_EDGE, width=2)
d.rectangle([BX - 30, ROW_Y["e"] + 14, BX + COLS * PITCH + 10, ROW_Y["f"] - 14],
            fill=(228, 224, 216))

def col_x(c):
    return BX + c * PITCH

for y, colour, sign in ((RAIL_P_Y, RAIL_RED, "+"), (RAIL_N_Y, RAIL_BLUE, "-"),
                        (RAIL_P2_Y, RAIL_RED, "+"), (RAIL_N2_Y, RAIL_BLUE, "-")):
    d.line([(BX - 22, y), (BX + COLS * PITCH + 2, y)], fill=colour, width=2)
    d.text((BX - 38, y - 10), sign, font=F_PIN_B, fill=colour)
    for c in range(COLS):
        d.ellipse([col_x(c) - 4, y - 4, col_x(c) + 4, y + 4], fill=HOLE)

for r in "abcdefghij":
    d.text((BX - 34, ROW_Y[r] - 9), r, font=F_PIN, fill=MUTED)
    for c in range(COLS):
        d.ellipse([col_x(c) - 5, ROW_Y[r] - 5, col_x(c) + 5, ROW_Y[r] + 5], fill=HOLE)

# --------------------------------------------------------- ESP32-CAM overlay -
LEFT = ["5V", "GND", "IO12", "IO13", "IO15", "IO14", "IO2", "IO4"]
RIGHT = ["3V3", "IO16", "IO0", "GND", "VCC", "U0R", "U0T", "GND"]
C0 = 5
cam_x0, cam_x1 = col_x(C0) - 30, col_x(C0 + 7) + 30
cam_y0, cam_y1 = ROW_Y["b"] - 26, ROW_Y["i"] + 26

overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)
od.rounded_rectangle([cam_x0, cam_y0, cam_x1, cam_y1], 10, fill=(32, 34, 40, 236),
                     outline=(84, 88, 96, 255), width=3)
base.paste(Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB"), (0, 0))
d = ImageDraw.Draw(base)

d.text((cam_x0 - 4, 240), "ESP32-CAM, seen from above, pressed into rows b and i",
       font=F_SMALL, fill=MUTED)
d.line([(cam_x0 + 90, 262), (cam_x0 + 90, cam_y0 - 6)], fill=DIM, width=1)
d.ellipse([col_x(C0 + 3) - 34, ROW_Y["e"] - 26, col_x(C0 + 3) + 34, ROW_Y["f"] + 26],
          fill=(16, 17, 22), outline=(92, 96, 106), width=3)
d.ellipse([col_x(C0 + 3) - 16, (ROW_Y["e"] + ROW_Y["f"]) // 2 - 16,
           col_x(C0 + 3) + 16, (ROW_Y["e"] + ROW_Y["f"]) // 2 + 16], fill=(30, 32, 40))

TARGETS = {"GND": (BLACK, "1"), "IO13": (BLUE, "4"), "IO14": (GREEN, "3")}
free_a, free_j = {}, {}
for i, name in enumerate(LEFT):
    x = col_x(C0 + i)
    d.ellipse([x - 6, ROW_Y["b"] - 6, x + 6, ROW_Y["b"] + 6], fill=(228, 224, 216))
    free_a[name] = (x, ROW_Y["a"])
    hot = name in TARGETS or name == "5V"
    d.ellipse([x - 8, ROW_Y["a"] - 8, x + 8, ROW_Y["a"] + 8],
              fill=SURFACE, outline=HOLE_FREE if hot else HOLE, width=3)
for i, name in enumerate(RIGHT):
    x = col_x(C0 + i)
    d.ellipse([x - 6, ROW_Y["i"] - 6, x + 6, ROW_Y["i"] + 6], fill=(228, 224, 216))
    free_j[name] = (x, ROW_Y["j"])
    d.ellipse([x - 8, ROW_Y["j"] - 8, x + 8, ROW_Y["j"] + 8],
              fill=SURFACE, outline=HOLE_FREE if name == "3V3" else HOLE, width=3)

# Row/column call-outs for the pins that matter.
for name, tier, colour in [("5V", 0, RED), ("GND", 1, BLACK),
                           ("IO13", 0, BLUE), ("IO14", 1, GREEN)]:
    x, y = free_a[name]
    top = 300 if tier == 0 else 332
    d.line([(x, y - 14), (x, top + 22)], fill=DIM, width=1)
    d.text((x - d.textlength(name, font=F_PIN_B) / 2, top), name, font=F_PIN_B, fill=colour)
x, y = free_j["3V3"]
d.line([(x, y + 14), (x, 870)], fill=DIM, width=1)
d.text((x - d.textlength("3V3", font=F_PIN_B) / 2, 874), "3V3", font=F_PIN_B, fill=RED)

# ----------------------------------------------------------------- MB block --
MX0, MY0, MX1, MY1 = 70, 430, 330, 700
card(MX0, MY0, MX1, MY1, r=12, fill=BOARD, outline=(84, 88, 96))
d.text((MX0 + 22, MY0 + 18), "ESP32-CAM-MB", font=F_SMALL, fill=(150, 154, 164))
d.text((MX0 + 22, MY0 + 46), "empty, still on USB", font=F_TINY, fill=(120, 124, 134))
d.rounded_rectangle([MX0 + 20, MY1 - 54, MX0 + 92, MY1 - 22], 5, fill=(180, 184, 192))
d.text((MX0 + 100, MY1 - 48), "USB", font=F_TINY, fill=(140, 144, 154))
mb_5v = (MX1 - 40, MY0 + 96)
mb_gnd = (MX1 - 40, MY0 + 146)
for (mx, my), lbl, col in ((mb_5v, "5V", RED), (mb_gnd, "GND", BLACK)):
    d.rectangle([mx - 11, my - 11, mx + 11, my + 11], fill=(58, 60, 68), outline=HOLE_FREE, width=3)
    d.text((mx - 30 - d.textlength(lbl, font=F_PIN_B), my - 9), lbl, font=F_PIN_B, fill=col)

# ---------------------------------------------------------------- OLED block -
OX0, OY0, OX1, OY1 = 1480, 420, 1800, 700
card(OX0, OY0, OX1, OY1, r=12, fill=PCB_BLUE, outline=(24, 58, 100))
d.rounded_rectangle([OX0 + 96, OY0 + 60, OX1 - 26, OY1 - 40], 6, fill=(12, 14, 20),
                    outline=(22, 54, 92), width=2)
d.text((OX0 + 120, OY0 + 140), "SOLAR INSPECTOR", font=F_PIN, fill=(150, 226, 255))
d.text((OX0 + 96, OY1 - 32), "header must be pre-soldered", font=F_TINY, fill=(190, 214, 238))
OLED = [("GND", BLACK, "1"), ("VDD", RED, "2"), ("SCK", GREEN, "3"), ("SDA", BLUE, "4")]
oled_xy = {}
for i, (name, colour, _n) in enumerate(OLED):
    cx, cy = OX0 + 26, OY0 + 56 + i * 52
    oled_xy[name] = (cx, cy)
    d.rectangle([cx - 10, cy - 10, cx + 10, cy + 10], fill=colour, outline=HOLE_FREE, width=3)
    d.text((cx + 24, cy - 9), name, font=F_PIN_B, fill=(228, 238, 250))

# ------------------------------------------------------------------- wires ---
wire(d, [mb_5v, (400, mb_5v[1]), (400, RAIL_P_Y), (col_x(1), RAIL_P_Y)], RED)
wire(d, [mb_gnd, (368, mb_gnd[1]), (368, RAIL_N_Y), (col_x(0), RAIL_N_Y)], BLACK)
wire(d, [(col_x(2), RAIL_P_Y), (col_x(2), 444), (free_a["5V"][0], 444), free_a["5V"]], RED)
wire(d, [(col_x(3), RAIL_N_Y), (col_x(3), 452), (free_a["GND"][0], 452), free_a["GND"]], BLACK)
wire(d, [(col_x(COLS - 1), RAIL_N_Y), (1420, RAIL_N_Y), (1420, oled_xy["GND"][1]),
         oled_xy["GND"]], BLACK)
wire(d, [free_j["3V3"], (free_j["3V3"][0], 862), (1444, 862),
         (1444, oled_xy["VDD"][1]), oled_xy["VDD"]], RED)
wire(d, [free_a["IO14"], (free_a["IO14"][0], 356), (1396, 356),
         (1396, oled_xy["SCK"][1]), oled_xy["SCK"]], GREEN)
wire(d, [free_a["IO13"], (free_a["IO13"][0], 372), (1372, 372),
         (1372, oled_xy["SDA"][1]), oled_xy["SDA"]], BLUE)

for name, key in (("GND", "GND"), ("IO13", "SDA"), ("IO14", "SCK")):
    colour, num = TARGETS[name]
    marker(d, *free_a[name], colour, num)
    marker(d, *oled_xy[key], colour, num)
marker(d, *free_j["3V3"], RED, "2")
marker(d, *oled_xy["VDD"], RED, "2")

# ------------------------------------------------------------ bottom cards ---
CY0, CY1 = 940, 1430
card(60, CY0, 640, CY1)
d.text((84, CY0 + 20), "What to buy", font=F_H2, fill=INK)
for i, (t, c) in enumerate([
        ("Half-size breadboard, 400 points", INK), ("about Rs 100", MUTED), ("", MUTED),
        ("Jumper wire set with male-to-male", INK),
        ("and male-to-female — about Rs 150", MUTED), ("", MUTED),
        ("An OLED module with the 4-pin header", INK),
        ("ALREADY SOLDERED — about Rs 200.", MUTED),
        ("Your current one ships loose and cannot", MUTED),
        ("go into a breadboard without an iron.", MUTED), ("", MUTED),
        ("Roughly Rs 450 total.", INK)]):
    d.text((84, CY0 + 64 + i * 26), t, font=F_SMALL, fill=c)

card(670, CY0, 1250, CY1)
d.text((694, CY0 + 20), "How it works", font=F_H2, fill=INK)
for i, (t, c) in enumerate([
        ("1  Flash the firmware with the camera", INK),
        ("     still in the MB, exactly as you do now.", MUTED), ("", MUTED),
        ("2  Unplug the camera and press it into", INK),
        ("     the breadboard. Its downward pins", MUTED),
        ("     land in rows b and i.", MUTED), ("", MUTED),
        ("3  Leave the MB plugged into USB and", INK),
        ("     run two wires from its now-empty 5V", MUTED),
        ("     and GND sockets to the power rails.", MUTED), ("", MUTED),
        ("4  Check /health over Wi-Fi — it reports", INK),
        ("     oled.present and the I2C address.", MUTED)]):
    d.text((694, CY0 + 64 + i * 26), t, font=F_SMALL, fill=c)

card(1280, CY0, 1800, CY1, fill=(252, 246, 240), outline=(226, 196, 170))
d.text((1304, CY0 + 20), "Read this before choosing it", font=F_H2, fill=(158, 86, 52))
for i, (t, c) in enumerate([
        ("The fit is tight. The headers are 0.9 in", INK),
        ("apart, so only row a and row j stay", MUTED),
        ("reachable — one hole per pin. Every", MUTED),
        ("hole under the board is unusable.", MUTED), ("", MUTED),
        ("No Serial Monitor while it runs, unless", INK),
        ("you add two more wires for U0T/U0R.", MUTED),
        ("Wi-Fi /health covers most of it.", MUTED), ("", MUTED),
        ("You move the camera between two", INK),
        ("boards for every reflash.", MUTED), ("", MUTED),
        ("Nothing here is fixed down. A nudged", INK),
        ("jumper looks like a dead display.", MUTED)]):
    d.text((1304, CY0 + 64 + i * 26), t, font=F_SMALL, fill=c)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
base.save(OUTPUT)
print(f"Wrote {OUTPUT.relative_to(PROJECT)}  ({W}x{H})")
