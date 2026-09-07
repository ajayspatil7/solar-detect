"""Render a 16:9 system-architecture diagram sized for projection."""

from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "design" / "slide-architecture.png"

W, H = 1920, 1080
BG = (250, 249, 246)
INK = (32, 35, 42)
MUTED = (110, 112, 120)
LINE = (206, 202, 194)
BLUE = (70, 112, 182)
SAGE = (58, 130, 98)
APRICOT = (196, 122, 52)
RED = (188, 78, 60)

A = "/System/Library/Fonts/Avenir Next.ttc"
M = "/System/Library/Fonts/Menlo.ttc"
F_T = ImageFont.truetype(A, 58, index=2)
F_S = ImageFont.truetype(A, 28, index=0)
F_B = ImageFont.truetype(A, 36, index=2)
F_D = ImageFont.truetype(A, 25, index=0)
F_A = ImageFont.truetype(A, 24, index=2)
F_C = ImageFont.truetype(M, 22)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

d.text((90, 62), "System Architecture", font=F_T, fill=INK)
d.text((94, 138), "Capture on the edge, analyse on the laptop, review in the browser",
        font=F_S, fill=MUTED)

BOXES = [
    (90,   "ESP32-CAM",      "OV2640 sensor\n2 HTTP servers\nOLED status\nWi-Fi setup portal", BLUE),
    (740,  "Laptop service", "FastAPI backend\nHolds the API key\nValidates + clamps\nNo image stored", SAGE),
    (1390, "Vision model",   "Structured output\nSchema-constrained\nNormalised\n0-1000 coords", APRICOT),
]
BY, BH, BW = 300, 330, 440

for x, title, body, colour in BOXES:
    d.rounded_rectangle([x, BY, x + BW, BY + BH], 18, fill=(255, 255, 255),
                        outline=colour, width=4)
    d.rectangle([x, BY, x + BW, BY + 10], fill=colour)
    d.text((x + 34, BY + 44), title, font=F_B, fill=INK)
    for i, line in enumerate(body.split("\n")):
        d.text((x + 34, BY + 108 + i * 40), line, font=F_D, fill=MUTED)

def arrow(x0, x1, y, label, sub, colour):
    d.line([(x0, y), (x1 - 22, y)], fill=colour, width=5)
    d.polygon([(x1, y), (x1 - 24, y - 13), (x1 - 24, y + 13)], fill=colour)
    tw = d.textlength(label, font=F_A)
    d.text(((x0 + x1) / 2 - tw / 2, y - 62), label, font=F_A, fill=INK)
    tw = d.textlength(sub, font=F_D)
    d.text(((x0 + x1) / 2 - tw / 2, y - 30), sub, font=F_D, fill=MUTED)

arrow(546, 736, BY + 175, "1600x1200 JPEG", "over Wi-Fi", BLUE)
arrow(1196, 1386, BY + 175, "image + schema", "HTTPS", SAGE)
d.line([(1610, BY + 340), (1610, 762), (770, 762)], fill=APRICOT, width=5)
d.polygon([(744, 762), (770, 748), (770, 776)], fill=APRICOT)
d.text((980, 706), "defect list + pixel boxes", font=F_A, fill=INK)

d.rounded_rectangle([330, 800, 790, 990], 18, fill=(255, 255, 255), outline=RED, width=4)
d.rectangle([330, 800, 790, 810], fill=RED)
d.text((364, 838), "Browser", font=F_B, fill=INK)
d.text((364, 896), "SVG regions over the photo", font=F_D, fill=MUTED)
d.text((364, 934), "Original + annotated download", font=F_D, fill=MUTED)

d.rounded_rectangle([900, 800, 1830, 990], 18, fill=(244, 246, 250), outline=LINE, width=3)
d.text((934, 828), "The API key never leaves the laptop", font=F_A, fill=INK)
d.text((934, 872), "Not in firmware. Not in browser JavaScript.", font=F_D, fill=MUTED)
d.text((934, 908), "Not in browser storage. Not in version control.", font=F_D, fill=MUTED)
d.text((934, 944), "Images are never written to disk.", font=F_D, fill=MUTED)

d.text((90, 1022), "Measured: 1600x1200 capture delivered in 0.53 s   |   "
                   "model round trip 4.0 s   |   2,933 tokens per image",
        font=F_C, fill=MUTED)

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
print(f"Wrote {OUT.relative_to(PROJECT)} ({W}x{H})")
