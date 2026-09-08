"""Breadboard assembly layout for the finished demo rig.

Replaces the loose jumper-on-pin wiring that kept losing contact. Every
connection becomes a friction-gripped breadboard hole instead.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "design" / "assembly-breadboard.png"

W, H = 1900, 1250
CANVAS = (245, 243, 238); SURFACE = (255, 253, 250); INK = (41, 44, 50)
MUTED = (116, 116, 123); LINE = (222, 218, 210); BB = (240, 237, 230)
BBE = (206, 201, 191); HOLE = (170, 166, 158); GOLD = (198, 160, 74)
BOARD = (32, 34, 40); PCB = (40, 88, 144)
RED = (197, 83, 63); BLACK = (52, 55, 63); BLUE = (85, 127, 196); GREEN = (62, 138, 104)

A = "/System/Library/Fonts/Avenir Next.ttc"; M = "/System/Library/Fonts/Menlo.ttc"
F_T = ImageFont.truetype(A, 40, index=2); F_H = ImageFont.truetype(A, 24, index=2)
F_B = ImageFont.truetype(A, 19); F_S = ImageFont.truetype(A, 16)
F_P = ImageFont.truetype(M, 15); F_PB = ImageFont.truetype(M, 16, index=1)
F_N = ImageFont.truetype(A, 16, index=2)

img = Image.new("RGB", (W, H), CANVAS); d = ImageDraw.Draw(img)
d.text((60, 40), "Breadboard assembly", font=F_T, fill=INK)
d.text((62, 92), "Camera straddles the centre channel in rows b and i. "
                 "Every wire goes into a hole, nothing clips onto a pin.", font=F_B, fill=MUTED)

P = 34; BX = 250; COLS = 30
RAIL_P, RAIL_N = 190, 216
ROW = {}
for i, r in enumerate("abcde"): ROW[r] = 280 + i * P
for i, r in enumerate("fghij"): ROW[r] = 470 + i * P
RAIL_P2, RAIL_N2 = 660, 686

def cx(c): return BX + (c - 1) * P

d.rounded_rectangle([BX - 46, 168, cx(COLS) + 26, 712], 10, fill=BB, outline=BBE, width=2)
d.rectangle([BX - 36, ROW["e"] + 16, cx(COLS) + 16, ROW["f"] - 16], fill=(228, 224, 216))

for y, col, sign in ((RAIL_P, RED, "+"), (RAIL_N, BLUE, "-"),
                     (RAIL_P2, RED, "+"), (RAIL_N2, BLUE, "-")):
    d.line([(BX - 26, y), (cx(COLS) + 6, y)], fill=col, width=2)
    d.text((BX - 44, y - 11), sign, font=F_PB, fill=col)
    for c in range(1, COLS + 1):
        d.ellipse([cx(c) - 5, y - 5, cx(c) + 5, y + 5], fill=HOLE)

for r in "abcdefghij":
    d.text((BX - 40, ROW[r] - 10), r, font=F_P, fill=MUTED)
    for c in range(1, COLS + 1):
        d.ellipse([cx(c) - 6, ROW[r] - 6, cx(c) + 6, ROW[r] + 6], fill=HOLE)
for c in range(1, COLS + 1, 5):
    d.text((cx(c) - 6, 740), str(c), font=F_S, fill=MUTED)

LEFT = ["5V", "GND", "IO12", "IO13", "IO15", "IO14", "IO2", "IO4"]
RIGHT = ["3V3", "IO16", "IO0", "GND", "VCC", "U0R", "U0T", "GND"]
C0 = 5
ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
od.rounded_rectangle([cx(C0) - 26, ROW["b"] - 26, cx(C0 + 7) + 26, ROW["i"] + 26],
                     10, fill=(32, 34, 40, 238), outline=(84, 88, 96, 255), width=3)
img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"), (0, 0))
d = ImageDraw.Draw(img)
d.text((cx(C0) - 14, ROW["d"] + 4), "ESP32-CAM", font=F_H, fill=(150, 154, 164))

USED = {"5V": (RED, "+ rail"), "GND": (BLACK, "- rail"),
        "IO13": (BLUE, "SDA"), "IO14": (GREEN, "SCK")}
free_a, free_j = {}, {}
for i, n in enumerate(LEFT):
    x = cx(C0 + i); free_a[n] = (x, ROW["a"])
    d.ellipse([x - 6, ROW["b"] - 6, x + 6, ROW["b"] + 6], fill=(226, 222, 214))
    hot = n in USED
    d.ellipse([x - 9, ROW["a"] - 9, x + 9, ROW["a"] + 9],
              fill=SURFACE, outline=GOLD if hot else HOLE, width=3)
    if hot:
        d.text((x - d.textlength(n, font=F_PB) / 2, 148), n, font=F_PB, fill=USED[n][0])
for i, n in enumerate(RIGHT):
    x = cx(C0 + i); free_j[i] = (x, ROW["j"])
    d.ellipse([x - 6, ROW["i"] - 6, x + 6, ROW["i"] + 6], fill=(226, 222, 214))
    hot = i in (0, 3)
    d.ellipse([x - 9, ROW["j"] - 9, x + 9, ROW["j"] + 9],
              fill=SURFACE, outline=GOLD if hot else HOLE, width=3)
    if hot:
        d.text((x - d.textlength(n, font=F_PB) / 2, ROW["j"] + 18), n, font=F_PB,
               fill=RED if i == 0 else BLACK)

OC = 20
OLED = [("GND", BLACK), ("VDD", RED), ("SCK", GREEN), ("SDA", BLUE)]
ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
od.rounded_rectangle([cx(OC) - 30, ROW["e"] - 24, cx(OC + 3) + 30, ROW["i"] + 20],
                     10, fill=(40, 88, 144, 232), outline=(24, 58, 100, 255), width=3)
img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"), (0, 0))
d = ImageDraw.Draw(img)
d.text((cx(OC) - 16, ROW["g"] - 6), "OLED", font=F_H, fill=(214, 230, 246))
oled_free = {}
for i, (n, col) in enumerate(OLED):
    x = cx(OC + i)
    d.ellipse([x - 6, ROW["e"] - 6, x + 6, ROW["e"] + 6], fill=(226, 222, 214))
    oled_free[n] = (x, ROW["c"])
    d.ellipse([x - 9, ROW["c"] - 9, x + 9, ROW["c"] + 9], fill=SURFACE, outline=GOLD, width=3)
    d.text((x - d.textlength(n, font=F_PB) / 2, 148), n, font=F_PB, fill=col)

# Power arrives from the MB's empty sockets; drawing the whole board here
# would crowd the layout, and the wiring table already names both ends.
for y, col, lbl in ((RAIL_P, RED, "from MB  5V"), (RAIL_N, BLACK, "from MB  GND")):
    d.line([(60, y), (196, y)], fill=col, width=6)
    d.polygon([(216, y), (192, y - 12), (192, y + 12)], fill=col)
    d.text((60, y - 30), lbl, font=F_PB, fill=col)

def wire(pts, col, w=6):
    d.line(pts, fill=CANVAS, width=w + 7, joint="curve")
    d.line(pts, fill=col, width=w, joint="curve")

wire([(cx(2), RAIL_P), (cx(2), ROW["a"]), free_a["5V"]], RED)
wire([(cx(3), RAIL_N), (cx(3), 250), (free_a["GND"][0], 250), free_a["GND"]], BLACK)
wire([oled_free["VDD"], (cx(OC + 1), 258), (cx(15), 258), (cx(15), ROW["j"]), free_j[0]], RED)
wire([oled_free["GND"], (cx(OC), 246), (cx(14), 246), (cx(14), ROW["j"]), free_j[3]], BLACK)
wire([oled_free["SCK"], (cx(OC + 2), 236), (free_a["IO14"][0], 236), free_a["IO14"]], GREEN)
wire([oled_free["SDA"], (cx(OC + 3), 226), (free_a["IO13"][0], 226), free_a["IO13"]], BLUE)

TX = 90
d.rounded_rectangle([TX, 830, TX + 620, 1190], 14, fill=SURFACE, outline=LINE, width=2)
d.text((TX + 26, 852), "Eight wires, all male-to-male", font=F_H, fill=INK)
rows = [("MB 5V", "+ rail", RED), ("MB GND", "- rail", BLACK),
        ("+ rail", "a5   (CAM 5V)", RED), ("- rail", "a6   (CAM GND)", BLACK),
        ("c20  (OLED GND)", "j8   (CAM GND)", BLACK), ("c21  (OLED VDD)", "j5   (CAM 3V3)", RED),
        ("c22  (OLED SCK)", "a10  (CAM IO14)", GREEN), ("c23  (OLED SDA)", "a8   (CAM IO13)", BLUE)]
for i, (a_, b_, col) in enumerate(rows):
    y = 900 + i * 34
    d.ellipse([TX + 30, y + 4, TX + 44, y + 18], fill=col)
    d.text((TX + 60, y), a_, font=F_P, fill=INK)
    d.text((TX + 300, y), "->", font=F_P, fill=MUTED)
    d.text((TX + 350, y), b_, font=F_P, fill=INK)

NX = 780
d.rounded_rectangle([NX, 830, NX + 750, 1190], 14, fill=(252, 246, 240), outline=(226, 196, 170), width=2)
d.text((NX + 26, 852), "Before you power it", font=F_H, fill=(158, 86, 52))
for i, (t, c) in enumerate([
        ("Camera pins go into row b and row i. Only row a", INK),
        ("and row j stay reachable - every hole under the", MUTED),
        ("board is unusable, which is why each pin gets", MUTED),
        ("exactly one wire.", MUTED), ("", MUTED),
        ("Push the camera down until it seats flat. Half-", INK),
        ("seated pins are what caused the dropouts.", MUTED), ("", MUTED),
        ("VDD to 3V3, never 5V. The ESP32 is not 5V", RED),
        ("tolerant and 5V sits one hole away.", MUTED), ("", MUTED),
        ("Wire everything first, apply power last. The", INK),
        ("display is only detected during startup.", MUTED)]):
    d.text((NX + 26, 892 + i * 23), t, font=F_S, fill=c)

OUT.parent.mkdir(parents=True, exist_ok=True); img.save(OUT)
print(f"Wrote {OUT.relative_to(PROJECT)} ({W}x{H})")
