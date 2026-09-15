// SD card probe for the AI-Thinker ESP32-CAM.
//
// Proves, before the record store is built on top of it, that the card mounts
// in 1-bit SDMMC mode on this exact board and can store an inspection-sized
// file reliably. Results repeat on the serial port every 20 seconds so they can
// be read whenever a monitor attaches.

#include <Arduino.h>
#include "FS.h"
#include "SD_MMC.h"

constexpr size_t TEST_BYTES = 70000;  // a typical 1600x1200 JPEG from this camera
constexpr int FLASH_LED_PIN = 4;

const char *cardTypeName(uint8_t type) {
  switch (type) {
    case CARD_MMC: return "MMC";
    case CARD_SD: return "SDSC";
    case CARD_SDHC: return "SDHC/SDXC";
    default: return "unknown";
  }
}

void runProbe() {
  Serial.println("\n=== SD PROBE ===");
  // 1-bit mode uses GPIO2 (D0), GPIO14 (CLK) and GPIO15 (CMD) only.
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("RESULT: FAIL mount -- card missing, not FAT, or GUID-partitioned");
    return;
  }
  const uint8_t type = SD_MMC.cardType();
  if (type == CARD_NONE) {
    Serial.println("RESULT: FAIL no card detected");
    SD_MMC.end();
    return;
  }
  Serial.printf("card type : %s\n", cardTypeName(type));
  Serial.printf("card size : %.2f GB\n", SD_MMC.cardSize() / 1073741824.0);
  Serial.printf("fs total  : %.2f GB\n", SD_MMC.totalBytes() / 1073741824.0);
  Serial.printf("fs used   : %.2f MB\n", SD_MMC.usedBytes() / 1048576.0);

  uint8_t *buffer = static_cast<uint8_t *>(ps_malloc(TEST_BYTES));
  if (!buffer) buffer = static_cast<uint8_t *>(malloc(TEST_BYTES));
  if (!buffer) {
    Serial.println("RESULT: FAIL could not allocate test buffer");
    SD_MMC.end();
    return;
  }
  uint32_t expected = 0;
  for (size_t i = 0; i < TEST_BYTES; ++i) {
    buffer[i] = static_cast<uint8_t>((i * 31 + 7) & 0xFF);
    expected += buffer[i];
  }

  bool ok = SD_MMC.mkdir("/records") || SD_MMC.exists("/records");
  Serial.printf("mkdir     : %s\n", ok ? "ok" : "FAILED");

  unsigned long t0 = millis();
  File out = SD_MMC.open("/records/probe.bin", FILE_WRITE);
  size_t written = out ? out.write(buffer, TEST_BYTES) : 0;
  if (out) out.close();
  const unsigned long writeMs = millis() - t0;

  t0 = millis();
  File in = SD_MMC.open("/records/probe.bin", FILE_READ);
  uint32_t actual = 0;
  size_t readBytes = 0;
  if (in) {
    while (in.available()) {
      const int n = in.read(buffer, TEST_BYTES);
      if (n <= 0) break;
      for (int i = 0; i < n; ++i) actual += buffer[i];
      readBytes += n;
    }
    in.close();
  }
  const unsigned long readMs = millis() - t0;
  const bool removed = SD_MMC.remove("/records/probe.bin");
  free(buffer);

  Serial.printf("write     : %u / %u bytes in %lu ms\n", static_cast<unsigned>(written),
                static_cast<unsigned>(TEST_BYTES), writeMs);
  Serial.printf("read      : %u bytes in %lu ms\n", static_cast<unsigned>(readBytes), readMs);
  Serial.printf("checksum  : %s\n", actual == expected ? "match" : "MISMATCH");
  Serial.printf("cleanup   : %s\n", removed ? "ok" : "FAILED");

  const bool pass = written == TEST_BYTES && readBytes == TEST_BYTES && actual == expected && removed;
  Serial.printf("RESULT: %s\n", pass ? "PASS" : "FAIL read/write check");
  SD_MMC.end();
}

void setup() {
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
  Serial.begin(115200);
  delay(2500);
  runProbe();
}

void loop() {
  delay(20000);
  runProbe();
}
