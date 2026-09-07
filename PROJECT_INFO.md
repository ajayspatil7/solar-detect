# Solar Panel Visible-Defect Inspector

**A working prototype that photographs a solar panel with an ESP32-CAM, has an
AI vision model screen the image for visible surface defects, and draws the
findings back over the photograph in a browser — with a status display on the
device itself.**

| | |
|---|---|
| **Status** | Working prototype, hardware complete, detection quality not yet validated |
| **Firmware** | `3.1.0-phase5` — 1,055,105 bytes (33% of flash), 59,808 bytes RAM (18%) |
| **Backend** | `3.1.0-phase4` — Python 3.11, FastAPI |
| **Source size** | ~2,200 lines across firmware, backend, browser UI, and tooling |
| **Repository** | https://github.com/ajayspatil7/solar-detect (public, no secrets) |
| **Last updated** | 2026-09-07 |

---

## 1. What it does

```
Solar panel
  → ESP32-CAM captures a 1600×1200 photograph
  → image travels over Wi-Fi to the operator's laptop
  → laptop calls the OpenAI vision API with a strict output schema
  → structured defect list with coordinates comes back
  → browser draws bounding boxes over the original photograph
  → OLED on the camera shows the verdict
```

The operator sees a live preview, presses **Capture**, presses **Analyze**, and
gets labelled regions over the image within a few seconds. The small screen on
the camera mirrors each step, so the device is usable without looking at the
laptop.

## 2. What it deliberately does not do

This distinction matters for any report, and the system's own wording enforces it.

**It can screen for** visible surface conditions: soiling, discoloration,
apparent surface cracks, burn-like marks, shading, and other visible anomalies.

**It cannot diagnose** internal microcracks, potential-induced degradation,
bypass-diode faults, electrical mismatch, or true thermal hotspots. Those need
electroluminescence imaging, thermal cameras, or electrical measurement — not an
RGB photograph.

Every result is phrased as a *visible anomaly suspected*, never as a certified
diagnosis, and every bounding box is flagged `boxes_are_approximate: true`. The
model is instructed to refuse rather than guess when image quality is poor, and
it does: the first real API call returned `retake_required` on an underexposed
frame instead of inventing findings.

---

## 3. System architecture

```
┌──────────────────────┐   Wi-Fi    ┌─────────────────────┐  HTTPS  ┌──────────┐
│   ESP32-CAM          │◄──────────►│  Operator's laptop  │◄───────►│  OpenAI  │
│                      │            │                     │         │  vision  │
│  OV2640 camera       │            │  FastAPI backend    │         │  model   │
│  2 HTTP servers      │            │  :8000              │         └──────────┘
│  SSD1306 OLED        │            │                     │
│  Wi-Fi setup portal  │            │  Holds the API key  │
└──────────────────────┘            └─────────────────────┘
          ▲                                    ▲
          │  serves the browser page           │  receives the JPEG
          └────────────┬───────────────────────┘
                       │
                ┌──────────────┐
                │   Browser    │
                │  preview,    │
                │  capture,    │
                │  SVG boxes   │
                └──────────────┘
```

**The API key never leaves the laptop.** The ESP32 has no knowledge of it, and it
never appears in browser JavaScript, browser storage, or version control. This
was a design constraint from the start, not an afterthought — an embedded device
on a shared network is the worst possible place to store a paid credential.

### Why two HTTP servers on the ESP32

The live preview is an MJPEG stream — an HTTP request that never ends. On a
single-threaded server it blocks every other request, so capture and status calls
would hang behind it. Port 80 handles control and capture; port 81 serves only
the stream. This was the root fix for the latency problem that started the
project, which turned out to be a software architecture issue rather than
defective hardware.

---

## 4. Hardware

| Component | Detail |
|---|---|
| Board | AI-Thinker ESP32-CAM, ESP32-D0WD-V3 rev 3.1 |
| Camera | OV2640, SCCB address `0x30`, PID `0x26` / VER `0x42` |
| PSRAM | Present, 3,419,448 bytes free at runtime |
| Display | 0.96" SSD1306 OLED, 128×64, I2C address `0x3c` (`RG0.96 IC V2.0`) |
| Programmer | ESP32-CAM-MB (CH340 USB-serial) |
| Storage | None — no microSD; images live in PSRAM only |

### Camera pin map (verified working)

```
PWDN=32  RESET=-1  XCLK=0   SIOD=26  SIOC=27
Y9=35    Y8=34     Y7=39    Y6=36    Y5=21
Y4=19    Y3=18     Y2=5
VSYNC=25 HREF=23   PCLK=22        XCLK = 20 MHz
```

### OLED wiring

```
OLED GND → ESP32-CAM GND (right header)
OLED VDD → ESP32-CAM 3V3     ← 3V3, never 5V
OLED SCK → ESP32-CAM IO14
OLED SDA → ESP32-CAM IO13
```

**Why `IO13` and `IO14`:** the camera occupies GPIO 0, 5, 18, 19, 21, 22, 23, 25,
26, 27, 32, 34, 35, 36 and 39; GPIO 4 is the flash LED and 33 the status LED.
Because no microSD is fitted, the SD-mux pins are free. `IO13` and `IO14` were
chosen because neither is a boot strapping pin. Avoid `IO12` (MTDI sets flash
voltage at boot — a pull-up here prevents the board starting), `IO16` (PSRAM),
`IO15` (a pull-up suppresses the boot log) and `U0R`/`U0T` (upload and serial).

**VDD must be 3V3.** The display module pulls SDA and SCL up to whatever VDD is,
and the ESP32's GPIOs are not 5V tolerant. Powering it from the adjacent 5V pin
would put 5V directly onto two microcontroller inputs.

---

## 5. Software components

### 5.1 Firmware — `solar_defect_camera.ino` (941 lines)

- QVGA (320×240) MJPEG preview on port 81; UXGA (1600×1200) JPEG stills on port 80
- Framebuffers allocated at UXGA in PSRAM at boot, sensor then dropped to QVGA
- Capture switches the sensor up, flushes transition frames, grabs, restores
- Camera mutex protects resolution changes; `CAMERA_GRAB_LATEST` with two buffers
- Browser page served as a 9,158-byte gzip resource (29,413 bytes uncompressed)
- Automatic Wi-Fi reconnection; TCP `NODELAY` on image sockets

**Endpoints**

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Browser interface (gzip) |
| `GET` | `/capture` | Fresh UXGA JPEG |
| `GET` | `/health` | JSON diagnostics including OLED state |
| `POST` | `/status` | Browser pushes inspection state to the OLED |
| `GET` | `/i2c` | I2C bus diagnostic — line levels plus address scan |
| `POST` | `/forget-wifi` | Clear credentials, reboot into setup mode |
| `GET` | `:81/stream` | QVGA MJPEG preview |

### 5.2 Display driver — `oled.h` (184 lines) + `font5x8.h`

A self-contained SSD1306/SH1106 driver written directly against `Wire`, so the
build needs no external library. Page-addressed flush in 16-byte I2C bursts,
pixel-level framebuffer, scalable text.

The font is **generated**, not hand-transcribed: `tools/generate_font.py`
rasterises ASCII from a system typeface and emits the header. Analysing the
output showed that at a 5×8 cell, `g`, `o`, `p` and `q` render *identically* and
`_` comes out blank — so **the driver folds all text to uppercase**, making an
ambiguous glyph impossible to display. A 6×8 variant was generated and compared;
it produced identical glyph shapes with fewer characters per line, so 5×8 was
kept at 21 characters per line.

**Display states:** booting, camera failure, Wi-Fi connecting, Wi-Fi lost, setup
portal, ready, capturing, analyzing, result, error.

All I2C traffic happens on the Arduino loop task. HTTP handlers only record the
desired state under a mutex, because `Wire` is not thread-safe and the HTTP
server runs on its own task. Redraw happens on change plus every two seconds, so
the address and signal strength stay current without saturating the bus.

### 5.3 Wi-Fi provisioning — `provisioning.h` (167 lines)

Credentials live in NVS, not in compiled firmware, so the camera can move
between locations without a toolchain. If none are stored, or the stored network
cannot be joined, the firmware raises a `SOLAR-SETUP` access point and serves a
setup page at `192.168.4.1` that scans for networks and stores the chosen one.
The OLED displays the network name to join and that address.

`secrets.h` survives only as a developer convenience and is **ignored once a
board has been provisioned or cleared**. Without that rule, `forget-wifi` would
silently rejoin whichever network the firmware was built against — and a handover
build would carry the developer's own Wi-Fi password in flash, where it is
recoverable.

### 5.4 Backend — `backend/main.py` (414 lines)

FastAPI service on port 8000. Two endpoints: `GET /health`, `POST /analyze`.

- Accepts only decodable JPEG at exactly 1600×1200, capped at 2 MB
- Pydantic structured output constrains status, quality, defect type, severity,
  confidence, description and coordinates — the model cannot return free-form text
- Model returns coordinates normalised `0..1000`; the backend clamps, orders and
  converts to pixels, so a malformed box cannot produce an off-image rectangle
- Results capped at eight regions
- Contradictions are corrected: a `defect_suspected` verdict with no regions is
  downgraded to `uncertain`, and vice versa
- OpenAI work runs outside the async event loop and is serialised, so health
  checks stay responsive during a long model call
- `store=False`; no image is written to disk at any point
- Token usage is reported in `meta.usage` for cost tracking
- Stable error envelope covering configuration, authentication, quota, rate
  limit, timeout, connection, rejected request, malformed image and invalid output
- A deterministic mock mode exercises the exact production HTTP contract without
  spending credit

### 5.5 Browser interface — `web_ui.h` (102 lines, 29 KB of HTML/CSS/JS)

Embedded in firmware, no external assets, no CDN, no fonts to download.

- Explicit state machine: connecting → ready → capturing → captured → analyzing → result
- Responsive SVG overlay aligned to the 1600×1200 image; boxes scale with the display
- Severity colour-coded; selecting a result card highlights its region
- Original and annotated JPEG downloads, generated in the browser
- Model text inserted with safe DOM text APIs, never as HTML
- Accepts `?backend=...` so the launcher can pre-fill the address
- Accessible: semantic regions, keyboard focus, ARIA live status, reduced-motion

### 5.6 Launcher — `tools/launcher.py` (232 lines) + `Start Solar Inspector.bat`

Removes every setup step for a non-technical operator. One double-click:

1. Finds a working Python, creates a private environment, installs dependencies
2. Asks for the API key once, stores it in the ignored `.env.local`
3. Starts the analysis service
4. Scans the local network for the camera, remembering it for next time
5. Opens the browser at the camera's page with the backend address filled in

Discovery checks the last known address first, then sweeps twice with widening
timeouts and a modest connection pool — Windows throttles large connection
fan-outs far more aggressively than macOS, which broke the first attempt.

---

## 6. Result contract

```json
{
  "analysis_id": "analysis_46bc678f0cd5",
  "status": "defect_suspected",
  "image_quality": "acceptable",
  "image_width": 1600,
  "image_height": 1200,
  "defects": [
    {
      "id": "defect_1",
      "type": "discoloration",
      "severity": "medium",
      "confidence": "medium",
      "description": "Possible localized discoloration.",
      "bounding_box": { "x_min": 904, "y_min": 294, "x_max": 1264, "y_max": 630 }
    }
  ],
  "summary": "A visible region is marked for review.",
  "retake_required": false,
  "meta": {
    "mode": "openai",
    "model": "gpt-5.6-luna",
    "latency_ms": 4017,
    "coordinates": "pixel",
    "boxes_are_approximate": true,
    "usage": { "input_tokens": 2883, "output_tokens": 50, "total_tokens": 2933 }
  }
}
```

**Status values:** `defect_suspected`, `no_visible_defect`, `uncertain`, `retake_required`
**Defect types:** `possible_surface_crack`, `discoloration`, `soiling`, `burn_mark`, `shading`, `other_visible_anomaly`
**Severity and confidence:** `low`, `medium`, `high`
**Image quality:** `acceptable`, `borderline`, `insufficient`

---

## 7. Security model

| Concern | Measure |
|---|---|
| API key exposure | Backend only, loaded from `.env.local` (permissions `600`), never in firmware, browser, or Git |
| Image privacy | Never written to disk; `store=False` on the API call; `no-store` headers |
| Prompt injection | The model is instructed to treat text visible in the image as untrusted scene content, never as instructions |
| Malformed model output | Pydantic schema plus clamping, ordering and count limits before anything reaches the browser |
| XSS from model text | Inserted with DOM text APIs, never `innerHTML` |
| Network exposure | CORS restricted to localhost, `.local` and private-LAN origins |
| Wi-Fi credentials | Stored in device NVS, not compiled into handover firmware |
| Secrets in Git | `.gitignore` excludes `secrets.h`, `.env.local`, `.venv/`; file contents were scanned before the first commit |

**Residual risk:** the backend binds `0.0.0.0:8000` without authentication, so any
device on the same network can submit an image and consume API credit. Accepted
for this deployment because the account carries a hard $5 spending cap. A shared
token would close it if the deployment model changes.

---

## 8. Measured results

All figures from the physical build, not estimates.

### Capture and delivery

| Metric | Value |
|---|---|
| Still resolution | 1600×1200 (UXGA), verified by decode |
| JPEG size | 47,869 – 95,060 bytes |
| Camera acquisition | 445 – 532 ms (avg 482 ms) |
| End-to-end delivery at −57 dBm | 0.53 – 1.21 s |
| End-to-end delivery at −71 dBm | 2.16 – 10.35 s |
| Preview | QVGA MJPEG, ~11.5 fps |
| PSRAM across repeated captures | 3,419,448 bytes, unchanged |

**Wi-Fi signal strength, not the camera, dominates delivery time.** The same
operation took 0.53 s at −57 dBm and up to 10.35 s at −71 dBm. Camera-side
acquisition stayed within 445–532 ms throughout.

### First real model call

| Metric | Value |
|---|---|
| Round trip | 4.0 s |
| Tokens | 2,883 input, 50 output, 2,933 total, 0 reasoning |
| Result | `retake_required` — correctly refused an underexposed frame |

The refusal was verified against the image: mean luminance 21.9/255, standard
deviation 3.3, with 100% of pixels below level 40. The frame really was almost
black. **Roughly 293,000 tokens per 100 images** is the scaling basis.

### Build

| Metric | Value |
|---|---|
| Program storage | 1,055,105 bytes (33% of 3,145,728) |
| Global/static RAM | 59,808 bytes (18% of 327,680) |
| Compiler warnings | None, with `--warnings all` |
| Backend test suite | 5 tests, passing |
| Browser page | 29,413 bytes → 9,158 bytes gzip |

---

## 9. Key engineering decisions

**The original problem was latency, not hardware.** Early diagnosis pointed at a
faulty camera. Instrumentation showed acquisition was consistently sub-second and
that the delay was the blocking MJPEG stream plus Wi-Fi conditions. No hardware
was replaced.

**Preview and capture are deliberately different resolutions.** QVGA keeps the
preview responsive on a weak link; UXGA gives the model 6.25× the pixels for
analysis. The preview pauses during capture to avoid bandwidth contention.

**Coordinates are normalised, then converted server-side.** Asking the model for
`0..1000` coordinates rather than pixels keeps its task resolution-independent
and lets the backend clamp and order every box before the browser sees it.

**The display is uppercase-only, by measurement.** Four glyph collision groups
were found in the generated 5×8 font. Rather than accept ambiguous text, the
driver makes it impossible.

**Wi-Fi credentials moved out of firmware for handover.** This also closed a
privacy hole: a handover build compiled against a real `secrets.h` would carry the
developer's home Wi-Fi password in recoverable flash.

**Soldering is not optional.** Header pins resting in plated through-holes make
essentially no electrical contact — the holes are wider than the pins, and solder
is what forms the joint. This cost an evening of diagnosis and is worth stating
plainly in any build instructions.

---

## 10. Development phases

| Phase | Outcome |
|---|---|
| **1** | Dual HTTP servers, QVGA preview + VGA still, latency resolved |
| **2** | Professional browser interface, explicit state machine, accessibility |
| **2.1** | Analysis still raised to UXGA without harming preview responsiveness |
| **3** | FastAPI backend, OpenAI structured vision, SVG bounding boxes |
| **5** | OLED status display, soldered and verified on hardware |
| **4** | *In progress* — real-key smoke test passed; detection calibration outstanding |
| **Handover** | Wi-Fi provisioning, one-click Windows launcher, public repository |

---

## 11. Running it

**Operator (Windows):** double-click `Start Solar Inspector.bat`. First run asks
for the API key once and takes a few minutes to set up. Allow Python through
Windows Firewall on **private networks** when prompted — without this the camera
cannot reach the laptop.

**Camera first-run at a new location:** if the OLED shows `SETUP`, join the
`SOLAR-SETUP` Wi-Fi network from a phone or laptop, open `http://192.168.4.1`,
pick the network and enter its password. The camera restarts onto it and shows
its address on the OLED.

**Developer (macOS):**

```bash
cd solar_defect_camera
.venv/bin/python start_backend.py                      # real analysis
ANALYSIS_MODE=mock .venv/bin/python start_backend.py   # no API cost
.venv/bin/python -m pytest backend/test_main.py -q     # tests
.venv/bin/python tools/generate_web_ui.py              # after any UI edit
```

Firmware builds headlessly using the CLI bundled with Arduino IDE:

```bash
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" \
  compile --fqbn esp32:esp32:esp32cam:PartitionScheme=huge_app --warnings all solar_defect_camera
```

Board: **AI Thinker ESP32-CAM**, core **3.3.11**, partition **Huge APP (3 MB No OTA)**, **115200** baud.

---

## 12. Limitations and next steps

### Known limitations

- **Detection quality is unvalidated.** The pipeline is proven end to end, but the
  system has not yet been run against a curated set of real defective panels. No
  accuracy, precision or localisation figures exist yet.
- General RGB vision may miss small, low-contrast or internal faults, and may
  mislocalise visible evidence. Regions are screening cues, not measurements.
- The OLED is detected only during startup, so it must be connected before power
  is applied.
- The backend has no authentication; exposure is bounded by the account spend cap.
- The Windows launcher is tested; the ESP32 setup portal is written and compiles
  but has not yet been exercised on hardware.

### Next steps

1. **Evaluation harness** — push a folder of real panel images through the exact
   production contract, score bounding boxes against ground truth with IoU, and
   tune the prompt and thresholds against numbers rather than impressions.
2. **Curated image set** — clear, defective, blurred, dark, and partial-panel
   images, so failure modes are characterised rather than discovered live.
3. **Verify the Wi-Fi setup portal** on hardware before handover.
4. **Controlled capture guidance** — lighting and framing prompts, since image
   quality dominates result quality more than any prompt change will.

---

## 13. File map

```
solar-detect/
├── PROJECT_INFO.md                  This document
├── checkpoint.md                    Detailed engineering log and measurements
├── Start Solar Inspector.bat        Windows one-click launcher
├── Start Solar Inspector.command    macOS equivalent
└── solar_defect_camera/
    ├── solar_defect_camera.ino      Firmware: camera, servers, display, state
    ├── oled.h                       Self-contained SSD1306/SH1106 driver
    ├── font5x8.h                    Generated display font
    ├── provisioning.h               Wi-Fi storage and setup portal page
    ├── web_ui.h                     Browser interface source
    ├── web_ui_gzip.h                Generated compressed copy served by the ESP32
    ├── secrets.example.h            Wi-Fi placeholder template
    ├── .env.local.example           Backend settings template
    ├── requirements.txt             fastapi, openai, pillow, pydantic, uvicorn
    ├── start_backend.py             Backend entry point for developers
    ├── backend/main.py              Analysis service
    ├── backend/test_main.py         Contract tests
    ├── tools/launcher.py            Setup, discovery, browser launch
    ├── tools/generate_web_ui.py     Compresses the UI into firmware
    ├── tools/generate_font.py       Generates and previews the display font
    ├── tools/preview_oled.py        Renders OLED screens for design review
    ├── tools/generate_*_diagram.py  Wiring, breadboard and overview diagrams
    └── design/                      Wiring diagrams, screen mockups, QA captures
```

Files never committed: `secrets.h`, `.env.local`, `.venv/`.
