#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "esp_timer.h"
#include <lwip/sockets.h>
#include "secrets.h"
#include "web_ui_gzip.h"
#include "oled.h"
#include "provisioning.h"

// Confirmed AI-Thinker ESP32-CAM / OV2640 pin map.
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

namespace {

constexpr uint16_t CONTROL_PORT = 80;
constexpr uint16_t STREAM_PORT = 81;
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
constexpr uint32_t WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t STREAM_LOG_INTERVAL_FRAMES = 30;
constexpr framesize_t PREVIEW_FRAME_SIZE = FRAMESIZE_QVGA;
constexpr framesize_t CAPTURE_FRAME_SIZE = FRAMESIZE_UXGA;
constexpr uint16_t CAPTURE_WIDTH = 1600;
constexpr uint16_t CAPTURE_HEIGHT = 1200;
constexpr int PREVIEW_JPEG_QUALITY = 15;
constexpr int CAPTURE_JPEG_QUALITY = 10;

enum class RunMode : uint8_t { Normal, Setup };
RunMode runMode = RunMode::Normal;

httpd_handle_t controlServer = nullptr;
httpd_handle_t streamServer = nullptr;
SemaphoreHandle_t cameraMutex = nullptr;

volatile uint32_t lastCaptureMs = 0;
volatile uint32_t lastTransferMs = 0;
volatile uint32_t lastJpegBytes = 0;
volatile uint32_t streamFpsX10 = 0;
volatile bool streamConnected = false;

uint32_t lastWiFiRetryMs = 0;
wl_status_t previousWiFiStatus = WL_NO_SHIELD;

constexpr char STREAM_CONTENT_TYPE[] =
    "multipart/x-mixed-replace;boundary=frame";

// ---------------------------------------------------------------------------
// Status display
//
// HTTP handlers run on the server task, so they only record the desired state.
// All I2C traffic happens from loop() to keep Wire access single-threaded.
// ---------------------------------------------------------------------------

enum class DisplayState : uint8_t {
  Booting,
  CameraFail,
  SetupPortal,
  WifiConnecting,
  WifiFail,
  Ready,
  Capturing,
  Analyzing,
  Result,
  Failed,
};

struct DisplayModel {
  DisplayState state = DisplayState::Booting;
  char headline[22] = "STARTING";
  char detail[22] = "";
  uint8_t defects = 0;
};

DisplayModel displayModel;
SemaphoreHandle_t displayMutex = nullptr;
volatile bool displayDirty = true;

void setDisplay(DisplayState state, const char *headline, const char *detail = "",
                uint8_t defects = 0) {
  if (displayMutex != nullptr &&
      xSemaphoreTake(displayMutex, pdMS_TO_TICKS(50)) != pdTRUE) {
    return;
  }
  displayModel.state = state;
  snprintf(displayModel.headline, sizeof(displayModel.headline), "%s", headline);
  snprintf(displayModel.detail, sizeof(displayModel.detail), "%s", detail);
  displayModel.defects = defects;
  displayDirty = true;
  if (displayMutex != nullptr) xSemaphoreGive(displayMutex);
}

void renderDisplay() {
  if (!oled::present) return;

  DisplayModel snapshot;
  if (displayMutex != nullptr &&
      xSemaphoreTake(displayMutex, pdMS_TO_TICKS(50)) != pdTRUE) {
    return;
  }
  snapshot = displayModel;
  displayDirty = false;
  if (displayMutex != nullptr) xSemaphoreGive(displayMutex);

  const bool online = WiFi.status() == WL_CONNECTED;
  char line[24];

  oled::clear();
  oled::drawText(0, 0, "SOLAR INSPECTOR");
  oled::drawHLine(9);

  if (oled::HEIGHT >= 64) {
    // A short headline gets double height; longer wording stays single height.
    const uint8_t scale = strlen(snapshot.headline) <= 10 ? 2 : 1;
    const int16_t headlineY = scale == 2 ? 15 : 19;
    oled::drawText(0, headlineY, snapshot.headline, scale);

    int16_t nextLineY = 36;
    if (snapshot.detail[0] != '\0') {
      oled::drawText(0, nextLineY, snapshot.detail);
      nextLineY = 46;
    }
    if (snapshot.state == DisplayState::Result) {
      snprintf(line, sizeof(line), "%u REGION%s", snapshot.defects,
               snapshot.defects == 1 ? "" : "S");
      oled::drawText(0, nextLineY, line);
    }

    // The footer sits at y=56 so its 8-pixel cell ends exactly on row 63.
    oled::drawHLine(54);
    if (snapshot.state == DisplayState::SetupPortal) {
      snprintf(line, sizeof(line), "%s", WiFi.softAPIP().toString().c_str());
    } else if (online) {
      snprintf(line, sizeof(line), "%s", WiFi.localIP().toString().c_str());
    } else {
      snprintf(line, sizeof(line), "NO WIFI");
    }
    oled::drawText(0, 56, line);
    if (online && snapshot.state != DisplayState::SetupPortal) {
      snprintf(line, sizeof(line), "%d", WiFi.RSSI());
      oled::drawText(oled::WIDTH - 24, 56, line);
    }
  } else {
    // 128x32 panels only have room for the headline and one context line.
    oled::drawText(0, 12, snapshot.headline);
    if (snapshot.detail[0] != '\0') {
      oled::drawText(0, 22, snapshot.detail);
    } else if (online) {
      oled::drawText(0, 22, WiFi.localIP().toString().c_str());
    }
  }

  oled::flush();
}

// Minimal field readers for the small, fixed JSON the browser posts. A full
// parser is not warranted for three known keys.
bool jsonStringField(const char *body, const char *key, char *out, size_t outSize) {
  char pattern[24];
  snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char *found = strstr(body, pattern);
  if (found == nullptr) return false;
  found = strchr(found + strlen(pattern), ':');
  if (found == nullptr) return false;
  ++found;
  while (*found == ' ') ++found;
  if (*found != '"') return false;
  ++found;
  size_t index = 0;
  while (*found != '\0' && *found != '"' && index + 1 < outSize) {
    out[index++] = *found++;
  }
  out[index] = '\0';
  return true;
}

long jsonNumberField(const char *body, const char *key, long fallback) {
  char pattern[24];
  snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char *found = strstr(body, pattern);
  if (found == nullptr) return fallback;
  found = strchr(found + strlen(pattern), ':');
  if (found == nullptr) return fallback;
  return strtol(found + 1, nullptr, 10);
}

const char *headlineForStatus(const char *status) {
  if (strcmp(status, "defect_suspected") == 0) return "DEFECT";
  if (strcmp(status, "no_visible_defect") == 0) return "CLEAR";
  if (strcmp(status, "uncertain") == 0) return "UNCERTAIN";
  if (strcmp(status, "retake_required") == 0) return "RETAKE";
  return "RESULT";
}

void setNoCacheHeaders(httpd_req_t *request) {
  httpd_resp_set_hdr(request, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(request, "Pragma", "no-cache");
  httpd_resp_set_hdr(request, "Expires", "0");
}

void optimizeSocketForLowLatency(httpd_req_t *request) {
  const int socketFd = httpd_req_to_sockfd(request);
  if (socketFd < 0) return;
  const int enabled = 1;
  setsockopt(socketFd, IPPROTO_TCP, TCP_NODELAY, &enabled, sizeof(enabled));
}

esp_err_t indexHandler(httpd_req_t *request) {
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  httpd_resp_set_hdr(request, "Content-Encoding", "gzip");
  setNoCacheHeaders(request);
  return httpd_resp_send(
      request, reinterpret_cast<const char *>(PHASE3_INDEX_HTML_GZ),
      PHASE3_INDEX_HTML_GZ_LEN);
}

esp_err_t healthHandler(httpd_req_t *request) {
  char json[640];
  const bool cameraReady = esp_camera_sensor_get() != nullptr;
  const String ip = WiFi.localIP().toString();
  const int length = snprintf(
      json, sizeof(json),
      "{\"camera\":%s,\"wifi\":%s,\"ip\":\"%s\",\"rssi\":%d,"
      "\"free_heap\":%lu,\"free_psram\":%lu,\"last_capture_ms\":%lu,"
      "\"last_transfer_ms\":%lu,\"last_jpeg_bytes\":%lu,"
      "\"stream_connected\":%s,\"stream_fps\":%.1f,"
      "\"capture_width\":%u,\"capture_height\":%u,"
      "\"oled\":{\"present\":%s,\"address\":\"0x%02x\",\"controller\":\"%s\","
      "\"width\":%u,\"height\":%u},"
      "\"uptime_ms\":%lu,\"firmware\":\"3.1.0-phase5\"}",
      cameraReady ? "true" : "false",
      WiFi.status() == WL_CONNECTED ? "true" : "false", ip.c_str(), WiFi.RSSI(),
      static_cast<unsigned long>(ESP.getFreeHeap()),
      static_cast<unsigned long>(ESP.getFreePsram()),
      static_cast<unsigned long>(lastCaptureMs),
      static_cast<unsigned long>(lastTransferMs),
      static_cast<unsigned long>(lastJpegBytes),
      streamConnected ? "true" : "false", streamFpsX10 / 10.0f,
      static_cast<unsigned>(CAPTURE_WIDTH),
      static_cast<unsigned>(CAPTURE_HEIGHT),
      oled::present ? "true" : "false", oled::address, oled::CONTROLLER_NAME,
      static_cast<unsigned>(oled::WIDTH), static_cast<unsigned>(oled::HEIGHT),
      static_cast<unsigned long>(millis()));

  if (length < 0 || static_cast<size_t>(length) >= sizeof(json)) {
    return httpd_resp_send_500(request);
  }
  httpd_resp_set_type(request, "application/json");
  setNoCacheHeaders(request);
  return httpd_resp_send(request, json, length);
}

// Bus-level diagnostic. Reading SDA/SCL as plain inputs distinguishes a display
// that is powered but unreachable from one that is not powered at all: an
// SSD1306 module holds both lines high through its own pull-up resistors, so a
// low reading means nothing live is attached to that pin.
esp_err_t i2cHandler(httpd_req_t *request) {
  Wire.end();
  pinMode(OLED_SDA_PIN, INPUT);
  pinMode(OLED_SCL_PIN, INPUT);
  delayMicroseconds(500);
  const int sdaLevel = digitalRead(OLED_SDA_PIN);
  const int sclLevel = digitalRead(OLED_SCL_PIN);

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN, 100000);
  char devices[128] = "";
  size_t offset = 0;
  int count = 0;
  for (uint8_t address = 0x08; address <= 0x77; ++address) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() != 0) continue;
    ++count;
    const int written = snprintf(devices + offset, sizeof(devices) - offset,
                                 "%s\"0x%02x\"", offset > 0 ? "," : "", address);
    if (written < 0 || static_cast<size_t>(written) >= sizeof(devices) - offset) break;
    offset += static_cast<size_t>(written);
  }

  const char *hint;
  if (count > 0) {
    hint = "A device answered. Wiring and power are good.";
  } else if (sdaLevel == 1 && sclLevel == 1) {
    hint = "Both lines are pulled high, so the display has power, but it never "
           "answered. Suspect a swapped SDA/SCL pair or a different controller.";
  } else if (sdaLevel == 0 && sclLevel == 0) {
    hint = "Both lines read low. Nothing is pulling them up, so the display is "
           "not powered or neither signal wire reaches it. Check VDD and GND first.";
  } else if (sdaLevel == 0) {
    hint = "SCL is pulled high but SDA is not. The SDA wire or its pin is the fault.";
  } else {
    hint = "SDA is pulled high but SCL is not. The SCL wire or its pin is the fault.";
  }

  char json[512];
  const int length = snprintf(
      json, sizeof(json),
      "{\"sda_pin\":%d,\"scl_pin\":%d,\"sda_level\":%d,\"scl_level\":%d,"
      "\"devices\":[%s],\"device_count\":%d,\"expected\":[\"0x3c\",\"0x3d\"],"
      "\"hint\":\"%s\"}",
      OLED_SDA_PIN, OLED_SCL_PIN, sdaLevel, sclLevel, devices, count, hint);

  // Leave the panel initialised again so a passing scan lights it immediately.
  oled::begin();
  displayDirty = true;

  if (length < 0 || static_cast<size_t>(length) >= sizeof(json)) {
    return httpd_resp_send_500(request);
  }
  httpd_resp_set_type(request, "application/json");
  setNoCacheHeaders(request);
  return httpd_resp_send(request, json, length);
}

esp_err_t statusHandler(httpd_req_t *request) {
  char body[288];
  const size_t declared = request->content_len;
  if (declared == 0 || declared >= sizeof(body)) {
    httpd_resp_set_status(request, "413 Payload Too Large");
    return httpd_resp_sendstr(request, "Status body must be under 288 bytes");
  }
  int received = httpd_req_recv(request, body, declared);
  if (received <= 0) {
    httpd_resp_set_status(request, "400 Bad Request");
    return httpd_resp_sendstr(request, "Could not read the status body");
  }
  body[received] = '\0';

  char state[24] = "";
  if (!jsonStringField(body, "state", state, sizeof(state))) {
    httpd_resp_set_status(request, "400 Bad Request");
    return httpd_resp_sendstr(request, "Missing state field");
  }

  if (strcmp(state, "ready") == 0) {
    setDisplay(DisplayState::Ready, "READY", "AWAITING CAPTURE");
  } else if (strcmp(state, "capturing") == 0) {
    setDisplay(DisplayState::Capturing, "CAPTURING", "UXGA STILL");
  } else if (strcmp(state, "analyzing") == 0) {
    setDisplay(DisplayState::Analyzing, "ANALYZING", "UPLOADED TO MAC");
  } else if (strcmp(state, "result") == 0) {
    char status[28] = "";
    char severity[12] = "";
    jsonStringField(body, "status", status, sizeof(status));
    jsonStringField(body, "severity", severity, sizeof(severity));
    const long defects = jsonNumberField(body, "defects", 0);
    char detail[22] = "";
    if (severity[0] != '\0') {
      snprintf(detail, sizeof(detail), "SEVERITY %s", severity);
    } else if (strcmp(status, "no_visible_defect") == 0) {
      snprintf(detail, sizeof(detail), "NO VISIBLE DEFECT");
    } else if (strcmp(status, "retake_required") == 0) {
      snprintf(detail, sizeof(detail), "IMAGE UNUSABLE");
    }
    setDisplay(DisplayState::Result, headlineForStatus(status), detail,
               static_cast<uint8_t>(defects < 0 ? 0 : (defects > 255 ? 255 : defects)));
  } else if (strcmp(state, "error") == 0) {
    char message[22] = "";
    jsonStringField(body, "message", message, sizeof(message));
    setDisplay(DisplayState::Failed, "ERROR", message);
  } else {
    httpd_resp_set_status(request, "400 Bad Request");
    return httpd_resp_sendstr(request, "Unknown state");
  }

  setNoCacheHeaders(request);
  httpd_resp_set_status(request, "204 No Content");
  return httpd_resp_send(request, nullptr, 0);
}

esp_err_t captureHandler(httpd_req_t *request) {
  optimizeSocketForLowLatency(request);
  setDisplay(DisplayState::Capturing, "CAPTURING", "UXGA STILL");
  const int64_t captureStartedUs = esp_timer_get_time();
  if (cameraMutex == nullptr ||
      xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(10000)) != pdTRUE) {
    setDisplay(DisplayState::Failed, "CAMERA BUSY", "RETRY CAPTURE");
    httpd_resp_set_status(request, "503 Service Unavailable");
    return httpd_resp_sendstr(request, "Camera is busy");
  }

  sensor_t *sensor = esp_camera_sensor_get();
  camera_fb_t *frame = nullptr;
  if (sensor != nullptr) {
    sensor->set_quality(sensor, CAPTURE_JPEG_QUALITY);
    sensor->set_framesize(sensor, CAPTURE_FRAME_SIZE);

    // Flush both continuous framebuffers after changing sensor resolution.
    // Frame metadata can change before queued JPEG data does, so a fixed flush
    // is more reliable than checking the reported width.
    for (uint8_t staleFrame = 0; staleFrame < 3; ++staleFrame) {
      camera_fb_t *stale = esp_camera_fb_get();
      if (stale == nullptr) break;
      esp_camera_fb_return(stale);
      delay(20);
    }
    frame = esp_camera_fb_get();

    sensor->set_framesize(sensor, PREVIEW_FRAME_SIZE);
    sensor->set_quality(sensor, PREVIEW_JPEG_QUALITY);
  }
  xSemaphoreGive(cameraMutex);

  const uint32_t captureTimeMs =
      static_cast<uint32_t>((esp_timer_get_time() - captureStartedUs) / 1000);

  if (frame == nullptr) {
    Serial.println("[capture] Camera framebuffer unavailable");
    httpd_resp_set_status(request, "503 Service Unavailable");
    return httpd_resp_sendstr(request, "Camera capture failed");
  }

  // esp_http_server retains these pointers until the response is sent, so each
  // header needs its own buffer for the full lifetime of this handler.
  char captureTimeHeader[24];
  char jpegBytesHeader[24];
  char imageWidthHeader[12];
  char imageHeightHeader[12];
  snprintf(captureTimeHeader, sizeof(captureTimeHeader), "%lu",
           static_cast<unsigned long>(captureTimeMs));
  httpd_resp_set_hdr(request, "X-Capture-Time-Ms", captureTimeHeader);
  snprintf(jpegBytesHeader, sizeof(jpegBytesHeader), "%u",
           static_cast<unsigned>(frame->len));
  httpd_resp_set_hdr(request, "X-JPEG-Bytes", jpegBytesHeader);
  snprintf(imageWidthHeader, sizeof(imageWidthHeader), "%u",
           static_cast<unsigned>(frame->width));
  httpd_resp_set_hdr(request, "X-Image-Width", imageWidthHeader);
  snprintf(imageHeightHeader, sizeof(imageHeightHeader), "%u",
           static_cast<unsigned>(frame->height));
  httpd_resp_set_hdr(request, "X-Image-Height", imageHeightHeader);
  httpd_resp_set_hdr(request, "Content-Disposition", "inline; filename=solar-panel-uxga.jpg");
  httpd_resp_set_type(request, "image/jpeg");
  setNoCacheHeaders(request);

  const size_t frameLength = frame->len;
  const uint16_t frameWidth = frame->width;
  const uint16_t frameHeight = frame->height;
  const int64_t transferStartedUs = esp_timer_get_time();
  const esp_err_t result =
      httpd_resp_send(request, reinterpret_cast<const char *>(frame->buf), frameLength);
  const uint32_t transferTimeMs =
      static_cast<uint32_t>((esp_timer_get_time() - transferStartedUs) / 1000);
  esp_camera_fb_return(frame);

  lastCaptureMs = captureTimeMs;
  lastTransferMs = transferTimeMs;
  lastJpegBytes = static_cast<uint32_t>(frameLength);

  Serial.printf("[capture] camera=%lu ms, network=%lu ms, jpeg=%u bytes, size=%ux%u, rssi=%d dBm\n",
                static_cast<unsigned long>(captureTimeMs),
                static_cast<unsigned long>(transferTimeMs),
                static_cast<unsigned>(frameLength),
                static_cast<unsigned>(frameWidth),
                static_cast<unsigned>(frameHeight), WiFi.RSSI());
  char captured[22];
  snprintf(captured, sizeof(captured), "%lu KB IN %lu MS",
           static_cast<unsigned long>(frameLength / 1024),
           static_cast<unsigned long>(captureTimeMs));
  setDisplay(DisplayState::Ready, "CAPTURED", captured);
  return result;
}

esp_err_t streamHandler(httpd_req_t *request) {
  optimizeSocketForLowLatency(request);
  esp_err_t result = httpd_resp_set_type(request, STREAM_CONTENT_TYPE);
  if (result != ESP_OK) return result;

  setNoCacheHeaders(request);
  httpd_resp_set_hdr(request, "Access-Control-Allow-Origin", "*");
  streamConnected = true;
  Serial.println("[stream] Browser connected");

  uint32_t intervalFrames = 0;
  uint32_t intervalBytes = 0;
  int64_t intervalStartedUs = esp_timer_get_time();

  while (true) {
    if (cameraMutex == nullptr ||
        xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(5000)) != pdTRUE) {
      result = ESP_ERR_TIMEOUT;
      break;
    }
    camera_fb_t *frame = esp_camera_fb_get();
    xSemaphoreGive(cameraMutex);
    if (frame == nullptr) {
      Serial.println("[stream] Camera framebuffer unavailable");
      result = ESP_FAIL;
      break;
    }

    // A still capture can leave a high-resolution frame in the continuous queue. Never
    // push that large transition frame into the low-bandwidth preview.
    if (frame->width != 320 || frame->height != 240) {
      esp_camera_fb_return(frame);
      continue;
    }

    char partHeader[112];
    const int headerLength = snprintf(
        partHeader, sizeof(partHeader),
        "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
        static_cast<unsigned>(frame->len));

    if (headerLength <= 0 || static_cast<size_t>(headerLength) >= sizeof(partHeader)) {
      esp_camera_fb_return(frame);
      result = ESP_FAIL;
      break;
    }

    result = httpd_resp_send_chunk(request, partHeader, headerLength);
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
          request, reinterpret_cast<const char *>(frame->buf), frame->len);
    }

    const size_t frameLength = frame->len;
    esp_camera_fb_return(frame);
    if (result != ESP_OK) break;

    ++intervalFrames;
    intervalBytes += static_cast<uint32_t>(frameLength);

    if (intervalFrames >= STREAM_LOG_INTERVAL_FRAMES) {
      const int64_t nowUs = esp_timer_get_time();
      const uint32_t elapsedMs = static_cast<uint32_t>((nowUs - intervalStartedUs) / 1000);
      if (elapsedMs > 0) {
        streamFpsX10 = (intervalFrames * 10000U) / elapsedMs;
      }
      Serial.printf("[stream] fps=%.1f, average=%lu bytes, rssi=%d dBm, free_heap=%lu\n",
                    streamFpsX10 / 10.0f,
                    static_cast<unsigned long>(intervalBytes / intervalFrames),
                    WiFi.RSSI(), static_cast<unsigned long>(ESP.getFreeHeap()));
      intervalFrames = 0;
      intervalBytes = 0;
      intervalStartedUs = nowUs;
    }
  }

  streamConnected = false;
  streamFpsX10 = 0;
  Serial.println("[stream] Browser disconnected");
  return result;
}

bool initializeCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    // Allocate framebuffers for the largest still we will request. The sensor
    // is switched down to QVGA immediately after initialization for streaming.
    config.frame_size = CAPTURE_FRAME_SIZE;
    config.jpeg_quality = CAPTURE_JPEG_QUALITY;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  }

  const esp_err_t error = esp_camera_init(&config);
  if (error != ESP_OK) {
    Serial.printf("[camera] Initialization failed: 0x%X\n", error);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor == nullptr) {
    Serial.println("[camera] Sensor handle unavailable");
    return false;
  }
  cameraMutex = xSemaphoreCreateMutex();
  if (cameraMutex == nullptr) {
    Serial.println("[camera] Could not create camera lock");
    return false;
  }

  sensor->set_framesize(sensor, PREVIEW_FRAME_SIZE);
  sensor->set_quality(sensor, PREVIEW_JPEG_QUALITY);

  // Let automatic exposure settle so the first browser image is usable.
  delay(300);
  for (uint8_t i = 0; i < 3; ++i) {
    camera_fb_t *warmupFrame = esp_camera_fb_get();
    if (warmupFrame != nullptr) esp_camera_fb_return(warmupFrame);
    delay(60);
  }

  Serial.printf("[camera] Ready: OV2640 PID=0x%02X, QVGA preview + UXGA capture, PSRAM=%s\n",
                sensor->id.PID, psramFound() ? "yes" : "no");
  return true;
}

esp_err_t setupPageHandler(httpd_req_t *request) {
  httpd_resp_set_type(request, "text/html; charset=utf-8");
  setNoCacheHeaders(request);
  return httpd_resp_sendstr(request, provisioning::SETUP_HTML);
}

esp_err_t scanHandler(httpd_req_t *request) {
  const int found = WiFi.scanNetworks();
  String json = "[";
  for (int i = 0; i < found && i < 20; ++i) {
    String ssid = WiFi.SSID(i);
    if (ssid.isEmpty()) continue;
    ssid.replace("\\", "\\\\");
    ssid.replace("\"", "\\\"");
    if (json.length() > 1) json += ",";
    json += "{\"ssid\":\"" + ssid + "\",\"rssi\":" + String(WiFi.RSSI(i)) + "}";
  }
  json += "]";
  WiFi.scanDelete();
  httpd_resp_set_type(request, "application/json");
  setNoCacheHeaders(request);
  return httpd_resp_sendstr(request, json.c_str());
}

esp_err_t saveWifiHandler(httpd_req_t *request) {
  char body[256];
  const size_t declared = request->content_len;
  if (declared == 0 || declared >= sizeof(body)) {
    httpd_resp_set_status(request, "413 Payload Too Large");
    return httpd_resp_sendstr(request, "Credentials are too long");
  }
  const int received = httpd_req_recv(request, body, declared);
  if (received <= 0) {
    httpd_resp_set_status(request, "400 Bad Request");
    return httpd_resp_sendstr(request, "Could not read the form");
  }
  body[received] = '\0';

  const String form(body);
  const String ssid = provisioning::formField(form, "ssid");
  const String pass = provisioning::formField(form, "pass");
  if (ssid.isEmpty()) {
    httpd_resp_set_status(request, "400 Bad Request");
    return httpd_resp_sendstr(request, "A network name is required");
  }

  if (!provisioning::save(ssid, pass)) {
    httpd_resp_set_status(request, "500 Internal Server Error");
    return httpd_resp_sendstr(request, "Could not store the credentials");
  }
  Serial.printf("[wifi] Stored credentials for \"%s\"; restarting\n", ssid.c_str());
  setDisplay(DisplayState::Booting, "SAVED", "RESTARTING");
  renderDisplay();
  httpd_resp_sendstr(request, "saved");
  delay(600);
  ESP.restart();
  return ESP_OK;
}

// Available in normal mode so the camera can be handed to a new location
// without a serial cable.
esp_err_t forgetWifiHandler(httpd_req_t *request) {
  provisioning::clear();
  Serial.println("[wifi] Stored credentials cleared; restarting into setup");
  setDisplay(DisplayState::Booting, "CLEARED", "RESTARTING");
  renderDisplay();
  setNoCacheHeaders(request);
  httpd_resp_sendstr(request, "cleared");
  delay(600);
  ESP.restart();
  return ESP_OK;
}

bool startSetupPortal() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(provisioning::AP_SSID)) {
    Serial.println("[wifi] Could not raise the setup access point");
    return false;
  }
  Serial.printf("[wifi] Setup portal: join \"%s\" then open http://%s/\n",
                provisioning::AP_SSID, WiFi.softAPIP().toString().c_str());

  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = CONTROL_PORT;
  config.ctrl_port = 32768;
  config.max_uri_handlers = 4;
  config.lru_purge_enable = true;
  config.stack_size = 8192;

  static const httpd_uri_t pageUri = {
      .uri = "/", .method = HTTP_GET, .handler = setupPageHandler, .user_ctx = nullptr};
  static const httpd_uri_t scanUri = {
      .uri = "/scan", .method = HTTP_GET, .handler = scanHandler, .user_ctx = nullptr};
  static const httpd_uri_t saveUri = {
      .uri = "/wifi", .method = HTTP_POST, .handler = saveWifiHandler, .user_ctx = nullptr};

  if (httpd_start(&controlServer, &config) != ESP_OK) {
    Serial.println("[http] Could not start the setup portal");
    return false;
  }
  httpd_register_uri_handler(controlServer, &pageUri);
  httpd_register_uri_handler(controlServer, &scanUri);
  httpd_register_uri_handler(controlServer, &saveUri);
  return true;
}

bool connectWiFi() {
  // Stored credentials win. secrets.h is only a convenience for a developer's
  // own board and is ignored once this board has been provisioned or cleared.
  const provisioning::Credentials stored = provisioning::load();
  String ssid = stored.ssid;
  String password = stored.password;
  const bool provisioned = !ssid.isEmpty();

  if (!provisioned) {
    if (stored.configured) {
      Serial.println("[wifi] No stored network; going to setup");
      return false;
    }
    ssid = WIFI_SSID;
    password = WIFI_PASSWORD;
  }
  if (ssid.isEmpty() || ssid == "YOUR_WIFI_NAME") {
    Serial.println("[wifi] No credentials stored and no usable fallback");
    return false;
  }

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname("esp32-solar-camera");
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid.c_str(), password.c_str());

  Serial.printf("[wifi] Connecting to %s (%s)", ssid.c_str(),
                provisioned ? "stored" : "secrets.h");
  const uint32_t startedMs = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - startedMs < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] Connected: http://%s  RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("[wifi] Initial connection timed out");
  }
  previousWiFiStatus = WiFi.status();
  return WiFi.status() == WL_CONNECTED;
}

bool startServers() {
  httpd_config_t controlConfig = HTTPD_DEFAULT_CONFIG();
  controlConfig.server_port = CONTROL_PORT;
  controlConfig.ctrl_port = 32768;
  controlConfig.max_uri_handlers = 8;
  controlConfig.lru_purge_enable = true;
  controlConfig.recv_wait_timeout = 5;
  controlConfig.send_wait_timeout = 10;
  controlConfig.stack_size = 8192;

  static const httpd_uri_t indexUri = {
      .uri = "/", .method = HTTP_GET, .handler = indexHandler, .user_ctx = nullptr};
  static const httpd_uri_t captureUri = {
      .uri = "/capture", .method = HTTP_GET, .handler = captureHandler, .user_ctx = nullptr};
  static const httpd_uri_t healthUri = {
      .uri = "/health", .method = HTTP_GET, .handler = healthHandler, .user_ctx = nullptr};
  static const httpd_uri_t statusUri = {
      .uri = "/status", .method = HTTP_POST, .handler = statusHandler, .user_ctx = nullptr};
  static const httpd_uri_t i2cUri = {
      .uri = "/i2c", .method = HTTP_GET, .handler = i2cHandler, .user_ctx = nullptr};
  static const httpd_uri_t forgetUri = {
      .uri = "/forget-wifi", .method = HTTP_POST, .handler = forgetWifiHandler,
      .user_ctx = nullptr};

  if (httpd_start(&controlServer, &controlConfig) != ESP_OK) {
    Serial.println("[http] Could not start control server");
    return false;
  }
  httpd_register_uri_handler(controlServer, &indexUri);
  httpd_register_uri_handler(controlServer, &captureUri);
  httpd_register_uri_handler(controlServer, &healthUri);
  httpd_register_uri_handler(controlServer, &statusUri);
  httpd_register_uri_handler(controlServer, &i2cUri);
  httpd_register_uri_handler(controlServer, &forgetUri);

  httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
  streamConfig.server_port = STREAM_PORT;
  streamConfig.ctrl_port = 32769;
  streamConfig.max_uri_handlers = 2;
  streamConfig.lru_purge_enable = true;
  streamConfig.recv_wait_timeout = 5;
  streamConfig.send_wait_timeout = 10;
  streamConfig.stack_size = 8192;

  static const httpd_uri_t streamUri = {
      .uri = "/stream", .method = HTTP_GET, .handler = streamHandler, .user_ctx = nullptr};

  if (httpd_start(&streamServer, &streamConfig) != ESP_OK) {
    Serial.println("[http] Could not start stream server");
    httpd_stop(controlServer);
    controlServer = nullptr;
    return false;
  }
  httpd_register_uri_handler(streamServer, &streamUri);
  Serial.println("[http] Control server on port 80; MJPEG stream on port 81");
  return true;
}

void maintainWiFi() {
  const wl_status_t status = WiFi.status();
  if (status != previousWiFiStatus) {
    if (status == WL_CONNECTED) {
      Serial.printf("[wifi] Reconnected: http://%s  RSSI=%d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      setDisplay(DisplayState::Ready, "READY", "AWAITING CAPTURE");
    } else {
      Serial.printf("[wifi] Disconnected (status=%d)\n", status);
      setDisplay(DisplayState::WifiFail, "WIFI LOST", "RECONNECTING");
    }
    previousWiFiStatus = status;
  }

  if (status != WL_CONNECTED && millis() - lastWiFiRetryMs >= WIFI_RETRY_INTERVAL_MS) {
    lastWiFiRetryMs = millis();
    Serial.println("[wifi] Retrying connection");
    WiFi.reconnect();
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n=== ESP32 SOLAR CAMERA — PHASE 5 ===");

  displayMutex = xSemaphoreCreateMutex();
  if (oled::begin()) {
    Serial.printf("[oled] %s panel at 0x%02x, %ux%u on SDA=%d SCL=%d\n",
                  oled::CONTROLLER_NAME, oled::address,
                  static_cast<unsigned>(oled::WIDTH),
                  static_cast<unsigned>(oled::HEIGHT), OLED_SDA_PIN, OLED_SCL_PIN);
  } else {
    Serial.printf("[oled] No I2C display answered on SDA=%d SCL=%d; continuing without it\n",
                  OLED_SDA_PIN, OLED_SCL_PIN);
  }
  setDisplay(DisplayState::Booting, "STARTING", "CAMERA INIT");
  renderDisplay();

  if (!initializeCamera()) {
    Serial.println("[fatal] Camera startup failed; restart after checking configuration");
    setDisplay(DisplayState::CameraFail, "CAMERA FAIL", "CHECK RIBBON");
    renderDisplay();
    return;
  }

  setDisplay(DisplayState::WifiConnecting, "WIFI", "CONNECTING");
  renderDisplay();

  if (!connectWiFi()) {
    // No usable network: raise the setup access point instead of sitting on a
    // dead retry loop that an operator has no way to act on.
    runMode = RunMode::Setup;
    if (!startSetupPortal()) {
      setDisplay(DisplayState::Failed, "SETUP FAIL", "RESTART BOARD");
      renderDisplay();
      return;
    }
    char detail[22];
    snprintf(detail, sizeof(detail), "JOIN %s", provisioning::AP_SSID);
    setDisplay(DisplayState::SetupPortal, "SETUP", detail);
    renderDisplay();
    Serial.println("[system] Running in setup mode");
    return;
  }

  if (!startServers()) {
    Serial.println("[fatal] Web server startup failed");
    setDisplay(DisplayState::Failed, "HTTP FAIL", "RESTART BOARD");
    renderDisplay();
    return;
  }

  setDisplay(DisplayState::Ready, "READY", "AWAITING CAPTURE");
  renderDisplay();

  Serial.printf("[system] Free heap=%lu, free PSRAM=%lu\n",
                static_cast<unsigned long>(ESP.getFreeHeap()),
                static_cast<unsigned long>(ESP.getFreePsram()));
}

void loop() {
  // The setup portal owns the radio while provisioning; station-mode
  // reconnection would fight it.
  if (runMode == RunMode::Normal) maintainWiFi();

  // Redraw on change, and periodically so the address and RSSI stay current
  // without flooding the I2C bus.
  static uint32_t lastRenderMs = 0;
  if (displayDirty || millis() - lastRenderMs >= 2000) {
    lastRenderMs = millis();
    renderDisplay();
  }

  delay(100);
}
