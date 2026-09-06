# ESP32 Solar Inspector — Phase 5

This prototype combines an AI-Thinker ESP32-CAM, a private Mac backend, and
OpenAI vision analysis. The camera provides a responsive QVGA live preview and
a separate UXGA still. The browser sends only the captured still to the Mac;
the Mac holds the API key, calls the model, validates the result, and returns
pixel-coordinate regions for the browser to draw over the original image.

The application screens for obvious visible surface anomalies. It is not a
certified electrical, thermal, or microcrack diagnosis.

## What Phase 3 includes

- QVGA (`320 × 240`) MJPEG preview and UXGA (`1600 × 1200`) JPEG capture.
- Local FastAPI backend with `GET /health` and `POST /analyze`.
- Backend-only OpenAI API key loaded from ignored `.env.local`.
- `gpt-5.6-luna` image input at `detail: original`.
- Strict Pydantic structured output and defensive result normalization.
- Validated, clamped pixel-coordinate bounding boxes, limited to eight regions.
- Real OpenAI mode and deterministic mock mode behind the same response shape.
- Professional responsive UI with backend health, retry states, selectable SVG
  regions, annotation visibility control, and original/annotated JPEG download.
- No server-side image persistence, no browser-side API key, and no credential
  embedded in the firmware.

## Start the Mac backend

The included local environment already has a `.venv`. From this folder run:

```bash
.venv/bin/python start_backend.py
```

The server listens on port `8000`. Keep that terminal open while using Analyze.
Open the ESP32 URL shown in the Arduino Serial Monitor. In **Backend connection**,
use:

```text
http://ajays-macbook-pro-2.local:8000
```

If the `.local` name does not resolve, use the Mac's current Wi-Fi address, for
example `http://192.168.1.3:8000`, then choose **Save & test**. Both devices must
be on the same local network and macOS may ask permission for incoming access.

For a new machine, create the environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configure the API key

Copy `.env.local.example` to `.env.local`, then replace the placeholder locally:

```text
OPENAI_API_KEY=your-project-key
OPENAI_MODEL=gpt-5.6-luna
ANALYSIS_MODE=openai
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
```

Never put this key in `secrets.h`, `solar_defect_camera.ino`, `web_ui.h`, browser
storage, screenshots, Git, or project documentation. `.env.local` and `.env`
are ignored. Restrict `.env.local` to the current macOS account (`chmod 600`).

To exercise the complete UI without API credit, start in mock mode:

```bash
ANALYSIS_MODE=mock .venv/bin/python start_backend.py
```

Mock mode validates and uploads a real UXGA capture but returns deterministic
sample regions. It never calls OpenAI.

## Backend contract

`POST /analyze` accepts a raw JPEG body with `Content-Type: image/jpeg`. It
requires a valid `1600 × 1200` JPEG and rejects oversized, malformed, or wrong
resolution input. A successful response has this shape:

```json
{
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
      "bounding_box": {
        "x_min": 904,
        "y_min": 294,
        "x_max": 1264,
        "y_max": 630
      }
    }
  ],
  "summary": "A visible region is marked for review.",
  "retake_required": false,
  "meta": {
    "mode": "openai",
    "model": "gpt-5.6-luna",
    "latency_ms": 3100,
    "coordinates": "pixel",
    "boxes_are_approximate": true
  }
}
```

Expected statuses are `defect_suspected`, `no_visible_defect`, `uncertain`, and
`retake_required`. Errors use a stable `{ "error": { ... } }` envelope. The UI
keeps the capture available after a timeout, quota problem, or backend error.

## Status display (Phase 5)

A four-pin I2C OLED shows the inspection state on the device itself.

```text
OLED VCC -> 3V3      OLED SDA -> GPIO 13
OLED GND -> GND      OLED SCL -> GPIO 14
```

Start with `design/oled-overview.png` — it shows only what joins to what.
Wiring routes in more detail:

- `design/oled-wiring.png` — soldered directly to the ESP32-CAM's top-side pads,
  from `tools/generate_wiring_diagram.py`. Keeps the board in the MB programmer.
- `design/oled-breadboard.png` — the camera pressed into a breadboard and powered
  from the MB over two wires, from `tools/generate_breadboard_diagram.py`. Needs
  an OLED whose header is already soldered.

The OLED module's own header usually ships loose and must be soldered on. The
ESP32-CAM's pins are occupied by the MB programmer's sockets while it is seated,
so tack the four wires to the top-side pads; the board then still seats in the MB
and keeps power, flashing and Serial Monitor.

GPIO 13 and 14 are free because no microSD is fitted, and neither is a boot
strapping pin. Do not use GPIO 12 (sets flash voltage at boot), GPIO 16 (PSRAM),
or GPIO 1/3 (UART upload and Serial Monitor).

The driver in `oled.h` needs no external library and supports SSD1306 and
SH1106 at 128x64 or 128x32. The two controllers cannot be distinguished over
I2C, so the build defaults to SSD1306; for a 1.3" panel, uncomment
`#define OLED_CONTROLLER_SH1106` in `oled.h` and reflash. `GET /health` reports
`oled.present` and the detected address so wiring can be confirmed first.

Display text is uppercase only: at a 5x8 cell the generated font renders `g`,
`o`, `p` and `q` identically, so the driver folds input to uppercase rather than
showing ambiguous glyphs.

`POST /status` accepts a small JSON body and drives the panel:

```json
{ "state": "result", "status": "defect_suspected", "defects": 2, "severity": "medium" }
```

Valid states are `ready`, `capturing`, `analyzing`, `result`, and `error`. The
browser posts these as fire-and-forget requests, so a missing or slow display
never delays analysis. `/capture` also drives the panel directly.

Regenerate the font and review the screen layouts with:

```bash
.venv/bin/python tools/generate_font.py
.venv/bin/python tools/preview_oled.py
```

## Build from the command line

Arduino IDE ships a CLI, so the IDE UI is not required:

```bash
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn esp32:esp32:esp32cam:PartitionScheme=huge_app --warnings all solar_defect_camera
```

## Firmware and Arduino settings

- Board: **AI Thinker ESP32-CAM**
- FQBN: `esp32:esp32:esp32cam`
- ESP32 Arduino core: **3.3.11**
- Upload/monitor port: `/dev/cu.usbserial-140`
- Serial Monitor: **115200 baud**
- Recommended partition: **Huge APP (3 MB No OTA / 1 MB SPIFFS)**

Wi-Fi credentials stay in ignored `secrets.h`. The browser endpoints are `/`,
`/capture`, and `/health`; the MJPEG stream is `/stream` on port `81`.

`web_ui.h` is the readable source. Regenerate the compressed firmware resource
after every UI edit:

```bash
.venv/bin/python tools/generate_web_ui.py
```

## Verification

Run backend tests:

```bash
.venv/bin/python -m pytest backend/test_main.py -q
```

Phase 3 was compiled with all warnings enabled, flashed to the physical camera,
and browser-tested using a real UXGA capture. Mock analysis produced two visible,
selectable regions, the annotation toggle worked, and the installed firmware
reported `3.0.0-phase3`. The temporary no-credit API test reached OpenAI and was
mapped cleanly to `quota_exceeded` without exposing provider internals.

## Known limits

General RGB vision may miss small, low-contrast, or internal faults and can
mislocalize visible evidence. Treat all regions as approximate screening cues.
Use controlled lighting, close framing, and manual review. Detecting internal
microcracks generally needs electroluminescence or other specialized imaging;
true hotspot diagnosis needs thermal or electrical measurement.
