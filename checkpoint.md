# ESP32 Solar Panel Defect Detection — Project Checkpoint

**Last updated:** 2026-09-04 (Asia/Kolkata)  
**Current milestone:** Phase 4 smoke test passed — first real OpenAI call returned a valid, correct result  
**Next milestone:** Phase 3.5 evaluation harness and a curated image set for detection-quality calibration

## How to resume in a fresh chat

Ask Codex to read this file and the project workspace before making changes.
Continue from **Current milestone** and the Phase 3 direction below. Do not restart the
camera hardware diagnosis unless new evidence contradicts the verified results.

## Project goal

Build a basic prototype with this flow:

```text
Solar panel
→ ESP32-CAM captures an image
→ image travels over Wi-Fi to a small backend
→ backend calls the OpenAI vision API
→ structured visible-defect result and coordinates are returned
→ responsive bounding boxes and details are shown in the browser
→ compact status is shown later on an OLED
```

This is a prototype, not a certified solar-panel inspection system. The OpenAI
API key must remain on the backend and must never be placed in ESP32 firmware.

## Verified hardware

- Classic AI-Thinker-style ESP32-CAM, not ESP32-S3.
- Chip: ESP32-D0WD-V3 revision 3.1.
- Camera: OV2640.
- PSRAM is present and working.
- ESP32-CAM-MB USB programmer/baseboard.
- Mac serial port: `/dev/cu.usbserial-140`.
- Small four-pin I2C OLED is available. Firmware support exists as of Phase 5;
  the panel is not yet physically connected or verified.
- No microSD card; none is required for the prototype.
- Images currently remain in RAM/PSRAM and are not saved permanently.

## Proven camera configuration

The following AI-Thinker pin map is known to work:

```text
PWDN=32  RESET=-1  XCLK=0   SIOD=26  SIOC=27
Y9=35    Y8=34     Y7=39    Y6=36    Y5=21
Y4=19    Y3=18     Y2=5
VSYNC=25 HREF=23   PCLK=22
XCLK frequency=20 MHz
```

Hardware diagnostics previously confirmed:

- Camera responds on SCCB address `0x30`.
- Sensor identifiers: PID `0x26`, VER `0x42`, MIDH `0x7F`, MIDL `0xA2`.
- `esp_camera_init()` succeeds with the explicit AI-Thinker pin map.
- JPEG capture succeeds.
- Do not recommend replacing the camera, ribbon cable, board, or ESP32 package
  without new contradictory evidence.

## Development environment

- macOS on a MacBook Pro M4 Pro.
- Arduino IDE.
- Espressif ESP32 Arduino core `3.3.11`.
- Board target/FQBN: `AI Thinker ESP32-CAM` / `esp32:esp32:esp32cam`.
- Serial baud: `115200`.
- Recommended partition scheme: Huge APP (3 MB No OTA / 1 MB SPIFFS).

## Workspace map

```text
/Users/ajaysp/Documents/Arduino/
├── checkpoint.md                         # This living project handoff
├── solar_defect_camera/                  # Active Phase 3 implementation
│   ├── solar_defect_camera.ino
│   ├── web_ui.h                          # Embedded professional browser UI
│   ├── web_ui_gzip.h                     # Generated compressed UI served by ESP32
│   ├── oled.h                            # Self-contained SSD1306/SH1106 I2C driver
│   ├── font5x8.h                         # Generated 5x8 display font
│   ├── backend/main.py                   # Private validation and OpenAI service
│   ├── backend/test_main.py              # Backend contract tests
│   ├── start_backend.py                  # Local service entry point
│   ├── requirements.txt
│   ├── .env.local                        # Local API settings; ignored and private
│   ├── .env.local.example
│   ├── tools/generate_web_ui.py
│   ├── tools/generate_font.py            # Regenerates font5x8.h + preview
│   ├── tools/preview_oled.py             # Renders OLED screens for design review
│   ├── README.md
│   ├── secrets.h                         # Local Wi-Fi credentials; ignored
│   ├── secrets.example.h
│   ├── design/                           # Selected visual + QA screenshots
│   └── .gitignore
├── design-qa.md                          # Phase 2 visual QA record
├── sketch_aug23b/                        # Preserved original still server
│   └── sketch_aug23b.ino
└── CameraWebServer/                      # Preserved Espressif experiment
    ├── CameraWebServer.ino
    ├── app_httpd.cpp
    ├── board_config.h
    ├── camera_index.h
    ├── camera_pins.h
    ├── partitions.csv
    └── ci.yml
```

The original experiments are preserved and were not overwritten. The active
firmware is `solar_defect_camera/solar_defect_camera.ino`; its Phase 2 browser
interface is kept separately in `solar_defect_camera/web_ui.h`.

## Phase 1 — complete

### Outcome

The user confirmed that the new browser interface and capture flow work.
Phase 1 is therefore officially complete.

### Implemented behavior

- Explicit, verified AI-Thinker camera pins.
- `esp_http_server` instead of the earlier synchronous Arduino `WebServer`.
- Control/page server on port 80.
- Independent MJPEG server on port 81.
- Bandwidth-friendly QVGA (`320×240`) live preview.
- High-quality VGA (`640×480`) still capture.
- Preview uses JPEG quality 15; still capture uses JPEG quality 10.
- `CAMERA_GRAB_LATEST` with two PSRAM framebuffers.
- Camera mutex protects resolution changes and frame acquisition.
- Stale preview frames are flushed after switching to VGA.
- Browser pauses the preview before still capture, then restarts it.
- Wi-Fi sleep is disabled.
- Automatic Wi-Fi reconnection with timeout and retry logging.
- TCP `NODELAY` is enabled for image sockets.
- Browser UI reports capture time, browser download time, JPEG size, stream
  rate, RSSI, heap, PSRAM, IP address, and device status.
- `/health` provides JSON diagnostics.
- Responses include no-cache headers.
- No image persistence and no microSD dependency.

### HTTP endpoints

```text
GET http://<device-ip>/           Browser interface
GET http://<device-ip>/capture   Fresh VGA JPEG
GET http://<device-ip>/health    JSON health/performance information
GET http://<device-ip>:81/stream QVGA MJPEG preview
```

The last observed DHCP address was `192.168.1.9`. This address may change after
router or ESP32 restarts, so use the IP printed in the Serial Monitor if needed.

### Build and device verification

- Compiled against ESP32 Arduino core 3.3.11 with all warnings enabled.
- Final build completed with no compiler warnings.
- Program storage: approximately 1,026,405 bytes (32%).
- Global/internal RAM: approximately 57,336 bytes (17%).
- Firmware was successfully uploaded to the physical ESP32-CAM.
- Runtime confirmed OV2640 initialization and approximately 4 MB free PSRAM.
- `/health` returned camera and Wi-Fi online.
- MJPEG response contained valid preview frames.
- Still endpoint returned a valid baseline JPEG at exactly `640×480`.
- Measured camera-side VGA acquisition, including resolution transition and
  stale-frame flushing, was approximately 250 ms.
- Network delivery varied substantially with local conditions. Observed RSSI
  was roughly -64 to -71 dBm. The user nevertheless confirmed the final browser
  experience is working.

## Key decisions and lessons

1. The original problem was latency, not defective camera hardware.
2. Live preview and still capture currently travel over Wi-Fi directly from the
   ESP32 to the browser. No backend or OpenAI call exists yet.
3. Preview and still capture use separate HTTP servers so the infinite MJPEG
   request cannot block control/capture requests.
4. The preview is intentionally lower resolution than the still image.
5. The preview is paused during a still capture to avoid bandwidth contention.
6. The OpenAI key will be stored only as a backend environment variable.
7. A future wired mode is viable because the ESP32-CAM is normally powered by
   the Mac. It would use high-speed UART through the ESP32-CAM-MB USB bridge and
   a Mac companion server. The cable does not provide native USB networking.
8. Wired transport remains an optional later phase. At 115200 baud it would not
   be faster; 460800 or 921600 baud must be benchmarked for a useful result.
9. VGA was a Phase 1 latency choice, not the OV2640 limit. Phase 2.1 now keeps
   QVGA only for preview and captures UXGA JPEG stills for analysis.
10. The ESP32 must not call OpenAI directly. The browser will send the captured
    JPEG to a Mac backend, which protects the API key and calls the model.
11. The Phase 3 target model is `gpt-5.6-luna`, subject to account availability
    and evaluation quality. It will return strict structured JSON containing
    defect details and coordinates.
12. Bounding boxes will be rendered as a responsive SVG overlay in the browser.
    Pillow may optionally create a downloadable annotated JPEG on the backend,
    but is not required for the interactive display.
13. Phase 3 keeps the model's coordinate task normalized to `0..1000`, then the
    backend clamps, orders, and converts every accepted box to UXGA pixels.
14. The interactive display uses SVG; annotated-JPEG export is generated in the
    browser from the same validated result so the backend never stores images.

## Security notes

- `solar_defect_camera/secrets.h` contains local Wi-Fi configuration and is
  ignored by its local `.gitignore`.
- `secrets.example.h` contains placeholders only.
- The older experimental sketches still contain the previously used Wi-Fi
  credentials in plain text. Do not publish those files without sanitizing them.
- The Wi-Fi password should eventually be rotated because it appeared in the
  original project material.
- Never add an OpenAI API key to Arduino source, browser JavaScript, or Git.
- Phase 3 stores the current local key only in ignored `.env.local`, permission
  mode `600`. The test key was pasted into chat and should be revoked/replaced.

## Detection scope and limitations

The RGB camera and general vision model can prototype detection of visible
conditions such as dirt, obvious glass damage, discoloration, burn-like marks,
strong shading, or other visible anomalies.

It cannot reliably diagnose internal microcracks, PID, bypass-diode faults,
electrical mismatch, or true thermal hotspots without specialized measurements
or thermal/electroluminescence imaging. Results should use wording such as
`visible defect suspected`, not certified diagnosis.

## Phase 2 — complete: analysis-ready browser workflow

### Objective

Turn the working camera page into a polished capture workflow that is ready to
connect to the backend in Phase 3, without calling OpenAI yet.

### Outcome

Phase 2 is implemented, compiled, flashed to the physical ESP32-CAM, and visually
verified. The selected direction is a soft professional instrument panel using
warm neutral surfaces and restrained pastel sage, blue, apricot, and lavender
accents. The interface is embedded in `web_ui.h`, uses local/system fonts only,
and has no cloud or external-asset dependency.

Implemented and verified:

- Desktop and narrow/mobile responsive layouts.
- Live QVGA preview with explicit connection/reconnection states.
- Real VGA capture at `640×480`, browser-memory preview, Retake, and timestamped
  JPEG Download.
- Capture button locking and explicit capturing/error/recovery states.
- Analyze action disabled until a valid capture exists.
- Honest local Demo analysis for success, no-visible-defect, uncertain,
  retake-required, timeout, and backend-offline UI states.
- Result contract ready for the Phase 3 backend without changing capture logic.
- Semantic regions and headings, keyboard focus states, reduced-motion support,
  useful image alternatives, and ARIA live status announcements.
- Device status, RSSI, FPS, heap, PSRAM, IP, firmware, JPEG size, camera timing,
  and browser-download timing without letting diagnostics dominate the workflow.
- Clear language that images remain temporary and results are not certified
  electrical diagnoses.

Selected design and QA artifacts are in `solar_defect_camera/design/`. The final
visual QA record is `design-qa.md` and its result is `passed`.

Final Phase 2 firmware identifier: `2.0.0-phase2`.

Final build against ESP32 Arduino core 3.3.11:

- Program storage: 1,043,497 bytes (33%).
- Global/internal RAM: 57,336 bytes (17%).
- Compiler warnings: none.
- Upload to `/dev/cu.usbserial-140`: successful.
- `/health`: camera and Wi-Fi online after final reset.

### Step 1 — formalize UI states

Implement a small, explicit browser state machine:

```text
connecting → ready → capturing → captured → ready-to-analyze
                                   ↘ error → retry
```

Prevent duplicate capture requests and make every failure recoverable without
restarting the ESP32.

### Step 2 — improve the capture workspace

- Make the live preview and captured image visually distinct.
- Preserve the latest JPEG blob in browser memory for later analysis.
- Add Retake and Download buttons.
- Show resolution, size, camera time, download time, and capture timestamp.
- Make clear that images are not permanently stored.

### Step 3 — prepare the Analyze interaction

- Add an `Analyze captured image` button that is disabled until a valid still
  image exists.
- Add an analysis status/result panel with states for uploading, analyzing,
  success, uncertain result, retake required, timeout, and backend unavailable.
- During Phase 2, use a local mock adapter only; do not put an API key or direct
  OpenAI call in the page.
- Define one frontend function that Phase 3 can point at the backend without
  changing capture logic.

### Step 4 — define the result contract

Prepare the interface for this compact backend response shape:

```json
{
  "status": "defect_suspected",
  "image_quality": "acceptable",
  "defects": [
    {
      "type": "possible_surface_crack",
      "location": "upper-right",
      "severity": "medium",
      "confidence": "medium"
    }
  ],
  "summary": "A possible visible surface defect was found.",
  "retake_required": false
}
```

Expected top-level statuses:

- `no_visible_defect`
- `defect_suspected`
- `uncertain`
- `retake_required`

### Step 5 — resilience and accessibility

- Add browser-side request timeouts with clear retry actions.
- Preserve the working stream reconnection behavior.
- Keep controls keyboard accessible with visible focus states.
- Add useful alternative text and screen-reader status announcements.
- Verify desktop and narrow/mobile layouts.
- Keep diagnostics available without making them dominate the primary workflow.

### Step 6 — verify on physical hardware

Acceptance criteria:

- Live preview remains at least as responsive as the accepted Phase 1 version.
- Capture always produces a real `640×480` JPEG.
- Retake and repeated captures work without heap degradation or restart.
- Downloaded JPEG opens correctly on the Mac.
- Analyze remains disabled before capture and activates afterward.
- Mock success, uncertainty, retake, timeout, and backend-offline results render
  correctly.
- Stream resumes after capture and after recoverable errors.
- No credentials or images appear in browser logs or permanent device storage.

### Phase 2 non-goals

- No OpenAI API request yet.
- No backend implementation yet; that is Phase 3.
- No OLED integration yet.
- No wired USB image transport yet.

## Phase 2.1 — complete: high-resolution analysis capture

### Objective

Increase the analysis still from VGA to the OV2640's maximum UXGA resolution
without reducing the accepted responsiveness of the live preview.

### Implemented behavior

- Live preview remains QVGA (`320×240`) MJPEG on port 81.
- Analysis stills are now UXGA (`1600×1200`) JPEGs on `/capture`.
- With PSRAM present, camera framebuffers are allocated at UXGA during startup;
  the sensor is then switched down to QVGA for normal streaming.
- Capture temporarily switches the sensor to UXGA, flushes transition frames,
  acquires a fresh still, and restores QVGA preview settings.
- Capture responses expose `X-Image-Width`, `X-Image-Height`, JPEG byte count,
  and camera acquisition time headers.
- `/health` now advertises the capture dimensions and firmware identifier
  `2.1.0-phase2.1`.
- The browser waits up to 30 seconds for the larger Wi-Fi transfer, decodes the
  JPEG, and refuses to enable analysis unless it is exactly `1600×1200`.
- UI labels, progress messages, capture caption, analysis prerequisite, and
  footer now identify the UXGA workflow.
- The 24,748-byte browser page is served as a 7,267-byte gzip resource to reduce
  cold-load time and improve reliability on the weak Wi-Fi link.
- Retake keeps the previous valid image available if a replacement fails, and
  analysis remains locked while a replacement capture is running.

### Physical-device verification

- Compiled with ESP32 Arduino core 3.3.11 and all warnings enabled.
- Final build: 1,027,265 bytes (32%) program storage and 57,336 bytes (17%)
  global/internal RAM; no compiler warnings.
- Uploaded successfully through `/dev/cu.usbserial-140`.
- Five consecutive `/capture` requests returned HTTP 200 and valid baseline
  JPEGs at exactly `1600×1200`.
- Camera-side acquisition across those captures: 445–532 ms, average 482 ms.
- JPEG sizes: 53,318–88,443 bytes, average approximately 63.5 KB for the current
  indoor scene. Real solar-panel images can compress differently.
- End-to-end Wi-Fi delivery observed: 2.16–10.35 seconds, average 7.29 seconds,
  at roughly -71 to -73 dBm. The large variation remains network-side rather
  than camera acquisition time.
- Free PSRAM was 3,419,448 bytes before and after the five-capture run, showing
  no PSRAM loss across repeated captures.
- After the capture run, the MJPEG endpoint delivered over 200 KB in six seconds;
  an extracted frame decoded at exactly `320×240`, and health telemetry reported
  approximately 11.5 fps during that connection.
- Browser verification decoded a `1600×1200` still, enabled Retake, Download,
  and Analyze, preserved UXGA on retake, rendered the demo result, and produced
  no browser console warnings or errors.
- The compressed interface was fetched back from the flashed device as a
  complete, valid 7,267-byte gzip response. A repeat transfer completed in
  approximately 2.89 seconds on the current Wi-Fi connection.

### Imaging limitation carried into Phase 3

UXGA supplies 6.25 times the total pixels and 2.5 times the linear resolution of
VGA, but does not make invisible internal microcracks observable. Phase 3 must
describe results as visible surface anomalies with approximate AI-estimated
regions. Close-up guided capture, controlled lighting, and focus quality will be
evaluated separately; electroluminescence or specialized thermal equipment is
outside this RGB prototype.

## Phase 3 — complete: secure vision analysis and bounding boxes

### Implemented architecture

```text
ESP32-CAM /capture (UXGA JPEG)
→ browser memory
→ POST image/jpeg to Mac :8000/analyze
→ strict OpenAI structured vision response
→ backend validation and normalized-to-pixel conversion
→ selectable SVG regions over the original browser image
```

- The ESP32 never holds or transmits the OpenAI API key.
- FastAPI backend endpoints are `GET /health` and `POST /analyze`.
- `.env.local` is ignored, owner-readable only, and loaded backend-side.
- Default model is `gpt-5.6-luna`; image detail is `original`; API response
  storage is disabled with `store=False`.
- Pydantic structured output restricts status, image quality, defect type,
  severity, confidence, descriptions, and normalized coordinates.
- The backend accepts only decodable JPEG input at exactly `1600×1200`, limits
  uploads to 2 MB, caps results at eight regions, and clamps/orders boxes.
- Stable safe errors cover configuration, authentication, quota, rate limit,
  timeout, connection, rejected request, malformed image, and invalid output.
- OpenAI work runs outside the async event loop and analysis is serialized so
  health checks remain responsive during a long model request.
- CORS is restricted to localhost, `.local`, and private-LAN browser origins.
- Responses carry `no-store` and `nosniff` privacy/security headers.
- Deterministic mock mode exercises the exact production HTTP contract without
  API credit. It still uploads and validates the real physical capture.

### Browser implementation

- Backend URL is configurable and persists in browser local storage; no key is
  present in browser source or storage.
- Backend health/mode is visible without dominating the inspection workflow.
- Real UXGA JPEGs upload directly as `image/jpeg` with a 90-second timeout.
- Result text is inserted with safe DOM text APIs rather than raw model HTML.
- Bounding boxes are responsive SVG regions aligned to the `1600×1200` image.
- Medium, high, and low severity use distinct restrained colors.
- Selecting a result card selects its matching box; annotations can be hidden.
- Original and annotated JPEG downloads are available after analysis.
- Failures retain the captured image and provide a retry action.
- Firmware/UI identifier is `3.0.0-phase3`.

### Verification completed 2026-09-04

- Backend unit suite: 5 tests passed.
- Gzip round trip and browser-JavaScript syntax checks passed.
- Source/embedded UI credential scan passed.
- UI source size: 28,432 bytes; deterministic gzip: 8,766 bytes.
- Final firmware compiled with all warnings enabled: 1,028,765 bytes (32%)
  program storage and 57,336 bytes (17%) global/internal RAM.
- Final firmware upload to `/dev/cu.usbserial-140` succeeded and flash hashes
  verified.
- Physical ESP32 health reported camera/Wi-Fi online and `3.0.0-phase3`.
- A real camera capture decoded as baseline JPEG at exactly `1600×1200`.
- Mock end-to-end analysis returned two valid pixel-coordinate boxes.
- Browser QA verified backend online state, capture, upload, result cards, two
  visible boxes, annotation toggle, and matching box/card selection.
- Visual QA found an SVG `hidden`-attribute compatibility issue; it was fixed,
  rebuilt, reflashed, and reverified with visible regions.
- The authorized no-credit OpenAI run reached the real API and returned a clean
  local `quota_exceeded` response with HTTP 402, as expected.

### How to run

From `solar_defect_camera`:

```bash
.venv/bin/python start_backend.py
```

The default `.env.local` mode is `openai`. For a no-cost end-to-end UI test:

```bash
ANALYSIS_MODE=mock .venv/bin/python start_backend.py
```

The browser defaults to `http://ajays-macbook-pro-2.local:8000`. If mDNS is not
resolved, open **Backend connection** and enter the Mac's current LAN address;
the verified address during Phase 3 was `http://192.168.1.3:8000`.

## Phase 5 — firmware complete: on-device OLED status display

### Status

Firmware is implemented, compiles clean, and the screen layouts were reviewed
against a rendered simulation. **Nothing has been verified on the physical
panel yet** because the OLED is not wired and the board was not attached during
this work. Treat every display claim below as built-and-simulated, not measured.

### Decisions

- Display text is **uppercase only**. At a 5x8 cell the generated font renders
  `g`, `o`, `p` and `q` identically and `_` blank, so the driver folds input to
  uppercase rather than showing ambiguous glyphs. Verified by inspecting the
  generated glyph table: 95 glyphs, 89 distinct, 4 collision groups.
- A 6x8 cell was generated and compared; it produced identical glyph shapes with
  fewer characters per line, so 5x8 was kept (21 characters per line).
- No external display library. `oled.h` drives the panel directly over `Wire`,
  keeping the dependency-free build and supporting SSD1306 and SH1106 behind one
  build switch.
- SSD1306 and SH1106 cannot be told apart over I2C. The build defaults to
  SSD1306; `#define OLED_CONTROLLER_SH1106` in `oled.h` switches to a 1.3" panel.

### Pin selection

`SDA = GPIO 13`, `SCL = GPIO 14`, panel powered from `3V3` and `GND`.
Confirmed from photographs on 2026-09-04: the ESP32-CAM's male header pins pass
through the PCB. Only a ~1 mm stub protrudes on the top face, which is too short
for a DuPont female connector; the full-length male pins are on the **underside**
and are long enough to seat in the MB's tall female header, so they also grip a
standard female jumper. All six wires therefore attach to the underside pins with
the camera unstacked. The camera also carries its own RST button on the underside,
usable when it runs on jumpers away from the MB.

Because the left row's single GND is taken by the power wire, the OLED's ground
should come from one of the right row's GND pins.

Connectivity overview: `solar_defect_camera/design/oled-overview.png`. The MB's
only job after flashing is to supply 5V; the OLED connects solely to the
ESP32-CAM. Six wires total: two male-to-female from the MB's empty 5V and GND
sockets to the camera's pins, and four female-to-female from the camera to the
OLED. No breadboard is required.

Labelled diagrams: `solar_defect_camera/design/oled-wiring.png` (soldered to the
ESP32-CAM's top pads) and `design/oled-breadboard.png` (camera moved to a
breadboard, powered from the MB over two wires).

The ESP32-CAM's headers are 0.9 in apart, so on a 0.1 in breadboard they land in
rows b and i and leave only row a and row j reachable — one hole per pin. That
route also requires buying an OLED with its header already soldered, since the
existing module's header ships loose. Verify the 23 mm row spacing with a ruler
before relying on the breadboard route.

Hardware confirmed from photographs on 2026-09-04: the OLED is a four-pin blue
module with silkscreen order `GND`, `VDD`, `SCK`, `SDA` (SCK is I2C SCL), almost
certainly a 0.96" SSD1306, and its header pins ship loose and unsoldered. The
ESP32-CAM-MB breaks out no spare pins, so while the camera is seated in the
programmer every one of its 16 pins is inside a socket. The four OLED wires must
therefore be tacked to the ESP32-CAM's top-side pads, which keeps the MB usable
for power, flashing and Serial Monitor. Available jumper wires are roughly seven
female-to-female plus one male-to-female; female-to-female is the correct type
because both boards present male pins.

The camera occupies GPIO 0, 5, 18, 19, 21, 22, 23, 25, 26, 27, 32, 34, 35, 36,
and 39; GPIO 4 is the flash LED and 33 the status LED. Because no microSD is
fitted, the SD-mux pins are free. GPIO 13 and 14 were chosen because neither is
a boot strapping pin. Avoid GPIO 12 (MTDI sets flash voltage at boot), GPIO 16
(PSRAM), GPIO 15 (MTDO pull-up suppresses the boot log), and GPIO 1/3 (UART).

### Implemented behavior

- `oled.h`: 128x64 or 128x32, page-addressed flush in 16-byte I2C bursts,
  pixel-level framebuffer, scalable text, rules and frames.
- Address auto-detection across `0x3C` and `0x3D`, reported in `/health`.
- Display state machine: booting, camera failure, Wi-Fi connecting, Wi-Fi lost,
  ready, capturing, analyzing, result, and error.
- All I2C traffic happens on the Arduino loop task. HTTP handlers only record
  the desired state under a mutex, so `Wire` is never touched concurrently.
- Redraw on state change plus a 2-second refresh so address and RSSI stay
  current without saturating the bus.
- New `POST /status` endpoint accepts a small JSON body (`state`, and for
  results `status`, `defects`, `severity`). Bodies are capped at 288 bytes and
  parsed with narrow field readers rather than a JSON library.
- `/capture` drives the panel by itself, so capture feedback appears even if the
  browser never posts a status.
- The browser posts `analyzing`, `result`, and `error` transitions to the device
  as fire-and-forget requests; the OLED can never delay or break analysis.
- Result verdicts are short (`DEFECT`, `CLEAR`, `UNCERTAIN`, `RETAKE`) so they
  render double-height and stay readable at a distance.

### Build verification

- Baseline Phase 3 firmware recompiled at 1,028,781 bytes, confirming the
  toolchain reproduces the recorded Phase 3 build within 16 bytes.
- Phase 5 firmware: 1,041,717 bytes (33%) program storage and 59,784 bytes (18%)
  global/internal RAM, compiled with `--warnings all` and no warnings.
- UI source 29,110 bytes, deterministic gzip 9,041 bytes, embedded copy in sync.
- Browser JavaScript passed `node --check`.
- Backend suite still 5 passed; no firmware or UI credential matches.
- Firmware identifier is now `3.1.0-phase5` (additive over `3.0.0-phase3`;
  Phase 4 changes the backend only and does not move the firmware version).

### Build tooling discovered

Arduino IDE bundles a usable CLI, so builds no longer need the IDE UI:

```bash
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" \
  compile --fqbn esp32:esp32:esp32cam:PartitionScheme=huge_app --warnings all solar_defect_camera
```

### Hardware bring-up log — 2026-09-04 evening

- `3.1.0-phase5` compiled, uploaded through `/dev/cu.usbserial-140`, flash hash
  verified. The Arduino IDE's serial-monitor helper had to be closed first
  because it held the port.
- The camera now runs **unstacked from the MB**, powered by two jumper wires from
  the MB's `5V` and `GND` sockets. Confirmed working: `/health` reachable at
  `192.168.1.9`, `camera` and `wifi` true, RSSI −56 to −66 dBm, PSRAM intact.
  This validates the six-wire topology in `design/oled-overview.png`.
- Wiring verified pin by pin against the silkscreen: `5V`→left 1, `GND`→left 2,
  `IO13`→left 4, `IO14`→left 6, `3V3`→right 1, `GND`→right row.
- The OLED's 4-pin header was **not soldered**, only pushed into the plated
  holes. With no solder the pins made essentially no contact, and `/health`
  reported `oled.present:false`, `address:0x00`.
- **The display was seen to light up while the header was pressed by hand.**
  Because `oled::begin()` runs once during `setup()`, output can only appear if
  the bus was live at that boot. This proves the pin mapping, the I2C address,
  the SSD1306 driver, the render path and the power topology are all correct.
  The sole remaining defect is the unsoldered header.
- Module identified from its own markings: `RG0.96 IC V2.0`, 24.7 × 27 × 1.2 mm —
  a 0.96" SSD1306 at 128×64, matching the firmware defaults. No SH1106 switch
  needed.
- A `GET /i2c` diagnostic was added: it samples `IO13`/`IO14` as floating inputs
  to prove whether the panel is powered, then scans 0x08–0x77 and reports every
  responder. Compiled clean at 1,043,093 bytes (33%); not yet flashed.

### Phase 5 hardware verification — passed

With the header pins **held in contact by hand — still unsoldered** — and the
camera running unstacked on jumper power:

- `/health` reports `oled.present:true`, `address:0x3c`, `ssd1306 128x64`.
- `/capture` returned HTTP 200 and a valid baseline JPEG decoding at exactly
  `1600 x 1200`, 48,241 bytes, delivered in **0.53 s** — far quicker than the
  2.16–10.35 s recorded in Phase 2.1, at RSSI −57 dBm versus −71 to −73 dBm then.
  Link quality, not the camera, was always the Phase 2.1 bottleneck.
- Uptime rose across the capture, so the board did **not** brown out while
  running the camera at UXGA through two jumper wires. Free PSRAM was
  3,419,448 bytes before and after, unchanged.
- The OLED stayed detected through the capture.
- `POST /status` with a `defect_suspected` result returned HTTP 204 and drove
  the panel.

The panel rendered the expected result screen and the user confirmed it matched
the design exactly: header rule, `DEFECT` at double height, `SEVERITY MEDIUM`,
`2 REGIONS`, and the address/RSSI footer.

Phase 5 is therefore **functionally proven but mechanically unfinished**. Every
electrical and software element is verified; the four header joints are still
unsoldered, so the link is held only by hand pressure and is lost on any knock.
Soldering is scheduled for 2026-09-05. Note also that the panel is detected only
during `setup()`, so it must be wired before power is applied.

### Phase 5 sign-off — soldered and verified 2026-09-05

The four header joints were soldered (one solder bridge occurred and was cleared
with desoldering wick). Full verification against the physical build, with the
camera unstacked and running on two jumper wires from the MB:

- `/health`: `oled.present:true`, `address:0x3c`, `ssd1306 128x64`, camera and
  Wi-Fi both true, firmware `3.1.0-phase5`.
- Two consecutive `/capture` requests returned valid baseline JPEGs at exactly
  `1600 x 1200`: 95,060 bytes in 1.21 s and 47,869 bytes in 0.53 s.
- Uptime rose across both captures — no brownout running the camera at UXGA
  through jumper power. Free PSRAM 3,419,448 bytes, unchanged throughout.
- All six `POST /status` states accepted with HTTP 204: analyzing, three result
  variants, error, ready. Unknown and missing states correctly rejected with 400.
- The panel was visually confirmed rendering `READY` / `AWAITING CAPTURE` with
  the address and RSSI footer.

**Phase 5 is complete.** The full chain now runs end to end: panel → ESP32-CAM →
Wi-Fi → Mac backend → model → browser → OLED.

Operational notes carried forward:

- DHCP moved the board to `192.168.1.10`. The address is printed on the OLED
  footer, so read it there rather than assuming a fixed value.
- RSSI is now −70 dBm, against −57 dBm earlier in the same session. A transient
  Wi-Fi association failure was seen at the weaker signal; it recovered on the
  firmware's own retry. Capture delivery tracks link quality closely — 1.21 s
  versus 0.53 s for the same operation.
- The panel is detected only during `setup()`, so it must be wired before power
  is applied.
- Soldering to the OLED's plated through-holes is mandatory. Pins resting in the
  holes make effectively no contact; this cost an evening of diagnosis.

### Remaining for Phase 5

1. Wire the panel to 3V3, GND, GPIO 13 (SDA), GPIO 14 (SCL).
2. Flash `3.1.0-phase5` and confirm `/health` reports `oled.present` true with a
   detected address.
3. If the image is shifted sideways or shows noise columns, the panel is an
   SH1106: enable `OLED_CONTROLLER_SH1106` in `oled.h` and reflash.
4. Walk the full chain and confirm each screen, including a real analysis.

### Housekeeping completed alongside

- The dead Phase 1 `INDEX_HTML` block (157 lines) was removed from the sketch;
  it had not been served since Phase 3.
- Plaintext Wi-Fi credentials were removed from `sketch_aug23b.ino` and
  `CameraWebServer.ino` and replaced with placeholders. A workspace-wide scan
  now finds no plaintext credentials. **The Wi-Fi password still needs rotating
  on the router, because it was previously exposed in project material.**
- The exposed `sk-proj…` key in `.env.local` is **still live and still needs
  revoking**.

## Phase 4 — in progress: real-key smoke test passed

### First real OpenAI call — 2026-09-05

A funded key was installed in `.env.local` (owner-only, 600). A stale backend
from an earlier session was still bound to port 8000 holding the **old** key in
its environment; it was killed and `SERVICE_VERSION` bumped to `3.1.0-phase4` so
the running process can be identified from `/health` in future.

One real UXGA capture from the physical camera was sent through the production
`POST /analyze` path. Result: **HTTP 200 in 4.0 s**, valid structured output.

```json
{"status": "retake_required", "image_quality": "insufficient",
 "defects": [], "retake_required": true,
 "summary": "The image is extremely dark and lacks sufficient visible detail..."}
```

The verdict was independently verified against the image itself: mean luminance
21.9/255, standard deviation 3.3, and 100% of pixels below level 40. The scene
really was almost black, so the model refused rather than inventing findings —
the conservative prompt behaved as designed on its first real input.

### The three carried risks are now settled

1. `"detail": "original"` is **accepted** by the API. No `BadRequestError`.
2. `max_output_tokens=1200` is ample: the call used **50** output tokens and
   **0** reasoning tokens. No risk of an empty parse from budget exhaustion.
3. `gpt-5.6-luna` **is available** on the account.

### Measured cost basis

Token usage for one 1600 x 1200 image: **2,883 input, 50 output, 2,933 total**.
`detail: "original"` did not inflate the input count. Scaling: roughly 293,000
tokens per 100 images. Multiply by the account's per-token rate for a run cost;
the figure was not assumed here.

### Backend change

`analyze_with_openai` now returns token usage alongside the parsed result, and
`serialize_result` surfaces it under `meta.usage`. The empty-parse error message
now includes usage so budget exhaustion is diagnosable rather than generic.
Backend suite still passes, 5 tests.

## Future phases

- **Phase 4:** Replace/revoke the exposed no-credit test key, run a curated real
  image set with funded API access, measure localization quality, tune the
  prompt/taxonomy/thresholds, and define explicit acceptance metrics.
- **Phase 3.5:** Offline evaluation harness (`tools/evaluate.py`) that pushes a
  folder of images through the production `/analyze` contract, plus a ground-truth
  format and IoU scoring, and a shared-secret header on `/analyze` so nothing else
  on the LAN can spend API credit.
- **Phase 6:** Test against a curated set of clear, defective-looking, blurred,
  dark, missing-panel, and partial-panel images.
- **Optional wired phase:** Benchmark USB serial at 460800 and 921600 baud using
  a framed JPEG protocol and Mac companion server, then compare it with Wi-Fi.

## Maintenance rule for this file

Update this checkpoint after every meaningful decision, implementation change,
hardware test, API contract change, completed phase, or newly discovered issue.
Record facts and measured results; do not store passwords, API keys, or other
secrets here.
