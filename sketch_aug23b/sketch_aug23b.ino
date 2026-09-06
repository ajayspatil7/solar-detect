#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

// Wi-Fi credentials were removed from this preserved experiment. Fill them in
// locally to run it again; keep real values out of committed source.
const char *ssid = "YOUR_WIFI_SSID";

const char *password = "YOUR_WIFI_PASSWORD";

// AI Thinker ESP32-CAM
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WebServer server(80);

void handleCapture() {
  camera_fb_t *fb = esp_camera_fb_get();

  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  WiFiClient client = server.client();

  client.printf(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: image/jpeg\r\n"
    "Content-Length: %u\r\n"
    "Cache-Control: no-cache\r\n"
    "Connection: close\r\n"
    "\r\n",
    fb->len
  );

  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

void handleRoot() {
  const char html[] = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <title>ESP32 Solar Panel Camera</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family:Arial;text-align:center">
  <h2>Solar Panel Defect Detection Prototype</h2>

  <img
    id="camera"
    src="/capture"
    style="max-width:95%;"
  >

  <br><br>

  <button onclick="refreshImage()">
    Capture Image
  </button>

  <script>
    function refreshImage() {
      document.getElementById("camera").src =
        "/capture?t=" + Date.now();
    }
  </script>
</body>
</html>
)rawliteral";

  server.send(200, "text/html", html);
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== SOLAR PANEL CAMERA ===");

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

  // Start higher than our diagnostic image
  config.frame_size = FRAMESIZE_VGA;   // 640x480
  config.jpeg_quality = 10;
  config.fb_count = 2;

  if (psramFound()) {
    config.fb_location = CAMERA_FB_IN_PSRAM;
    Serial.println("PSRAM found");
  } else {
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%X\n", err);
    return;
  }

  Serial.println("Camera initialized!");

  WiFi.begin(ssid, password);

  Serial.print("Connecting to Wi-Fi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected!");
  Serial.print("Open this address: http://");
  Serial.println(WiFi.localIP());

  server.on("/", handleRoot);
  server.on("/capture", handleCapture);

  server.begin();

  Serial.println("Camera web server started!");
}

void loop() {
  server.handleClient();
}