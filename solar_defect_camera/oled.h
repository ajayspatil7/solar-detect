#pragma once

// Minimal self-contained I2C OLED driver for the status display.
//
// Supports SSD1306 and SH1106 controllers at 128x64 or 128x32. It is written
// directly against Wire so the sketch keeps its no-external-library build.
//
// Wiring on the AI-Thinker ESP32-CAM (no microSD fitted, so the SD-mux pins are
// free). GPIO 13 and 14 are used because neither is a boot strapping pin:
//   OLED VCC -> 3V3      OLED GND -> GND
//   OLED SDA -> GPIO 13  OLED SCL -> GPIO 14
// Avoid GPIO 12 (MTDI strapping sets flash voltage), GPIO 16 (PSRAM), and
// GPIO 1/3 (UART upload and Serial Monitor).

#include <Arduino.h>
#include <Wire.h>

#include "font5x8.h"

#ifndef OLED_SDA_PIN
#define OLED_SDA_PIN 13
#endif
#ifndef OLED_SCL_PIN
#define OLED_SCL_PIN 14
#endif
#ifndef OLED_HEIGHT
#define OLED_HEIGHT 64  // Set to 32 for a 128x32 module.
#endif
// Define OLED_CONTROLLER_SH1106 for a 1.3" SH1106 panel. A 0.96" panel is
// almost always SSD1306. The controllers are indistinguishable over I2C, so
// this stays a build switch: if the image is shifted two pixels sideways or
// shows noise columns, flip it.
// #define OLED_CONTROLLER_SH1106

namespace oled {

constexpr uint8_t WIDTH = 128;
constexpr uint8_t HEIGHT = OLED_HEIGHT;
constexpr uint8_t PAGES = HEIGHT / 8;
constexpr size_t BUFFER_BYTES = static_cast<size_t>(WIDTH) * PAGES;
constexpr uint32_t I2C_FREQUENCY = 400000;

#ifdef OLED_CONTROLLER_SH1106
constexpr uint8_t COLUMN_OFFSET = 2;
constexpr char CONTROLLER_NAME[] = "sh1106";
#else
constexpr uint8_t COLUMN_OFFSET = 0;
constexpr char CONTROLLER_NAME[] = "ssd1306";
#endif

inline uint8_t buffer[BUFFER_BYTES];
inline uint8_t address = 0;
inline bool present = false;

inline void command(uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(0x00);  // Co=0, D/C=0: the following byte is a command.
  Wire.write(value);
  Wire.endTransmission();
}

inline void command(uint8_t value, uint8_t argument) {
  Wire.beginTransmission(address);
  Wire.write(0x00);
  Wire.write(value);
  Wire.write(argument);
  Wire.endTransmission();
}

inline bool probe(uint8_t candidate) {
  Wire.beginTransmission(candidate);
  return Wire.endTransmission() == 0;
}

inline void clear() { memset(buffer, 0, BUFFER_BYTES); }

inline void setPixel(int16_t x, int16_t y) {
  if (x < 0 || y < 0 || x >= WIDTH || y >= HEIGHT) return;
  buffer[(y / 8) * WIDTH + x] |= static_cast<uint8_t>(1u << (y % 8));
}

// Draws uppercase text. The 5x8 cell has no descender room, so lowercase
// g/o/p/q rasterise identically; input is folded to uppercase to keep every
// glyph distinguishable on the panel.
inline uint8_t drawText(int16_t x, int16_t y, const char *text, uint8_t scale = 1) {
  const int16_t startX = x;
  for (const char *cursor = text; *cursor != '\0'; ++cursor) {
    char character = *cursor;
    if (character >= 'a' && character <= 'z') character -= 32;
    if (character < FONT_FIRST_CHAR || character > FONT_LAST_CHAR) character = '?';
    const uint16_t offset =
        static_cast<uint16_t>(character - FONT_FIRST_CHAR) * FONT_WIDTH;
    for (uint8_t column = 0; column < FONT_WIDTH; ++column) {
      const uint8_t bits = pgm_read_byte(&OLED_FONT[offset + column]);
      for (uint8_t row = 0; row < FONT_HEIGHT; ++row) {
        if (!(bits & (1u << row))) continue;
        for (uint8_t sy = 0; sy < scale; ++sy) {
          for (uint8_t sx = 0; sx < scale; ++sx) {
            setPixel(x + column * scale + sx, y + row * scale + sy);
          }
        }
      }
    }
    x += (FONT_WIDTH + 1) * scale;
    if (x >= WIDTH) break;
  }
  return static_cast<uint8_t>(x - startX);
}

inline void drawHLine(int16_t y, int16_t from = 0, int16_t to = WIDTH - 1) {
  for (int16_t x = from; x <= to; ++x) setPixel(x, y);
}

inline void drawFrame(int16_t x, int16_t y, int16_t width, int16_t height) {
  for (int16_t i = 0; i < width; ++i) {
    setPixel(x + i, y);
    setPixel(x + i, y + height - 1);
  }
  for (int16_t i = 0; i < height; ++i) {
    setPixel(x, y + i);
    setPixel(x + width - 1, y + i);
  }
}

inline void flush() {
  if (!present) return;
  for (uint8_t page = 0; page < PAGES; ++page) {
    command(0xB0 + page);
    command(0x00 | (COLUMN_OFFSET & 0x0F));
    command(0x10 | (COLUMN_OFFSET >> 4));
    const uint8_t *row = buffer + static_cast<size_t>(page) * WIDTH;
    // Wire's transmit buffer is limited, so the page is sent in short bursts.
    for (uint8_t start = 0; start < WIDTH; start += 16) {
      Wire.beginTransmission(address);
      Wire.write(0x40);  // Co=0, D/C=1: the following bytes are display data.
      Wire.write(row + start, 16);
      Wire.endTransmission();
    }
  }
}

inline bool begin() {
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN, I2C_FREQUENCY);
  for (const uint8_t candidate : {0x3C, 0x3D}) {
    if (probe(candidate)) {
      address = candidate;
      break;
    }
  }
  if (address == 0) {
    present = false;
    return false;
  }

  command(0xAE);              // Display off while configuring.
  command(0xD5, 0x80);        // Display clock divide / oscillator frequency.
  command(0xA8, HEIGHT - 1);  // Multiplex ratio.
  command(0xD3, 0x00);        // No display offset.
  command(0x40);              // Start line 0.
#ifdef OLED_CONTROLLER_SH1106
  command(0xAD, 0x8B);        // SH1106 built-in DC-DC on.
  command(0x33);              // Pump voltage 9.0 V.
#else
  command(0x8D, 0x14);        // SSD1306 charge pump on.
  command(0x20, 0x02);        // Page addressing mode, matching flush().
#endif
  command(0xA1);                             // Segment remap.
  command(0xC8);                             // COM scan direction reversed.
  command(0xDA, HEIGHT == 32 ? 0x02 : 0x12);  // COM pin layout.
  command(0x81, 0xCF);                       // Contrast.
  command(0xD9, 0xF1);                       // Pre-charge period.
  command(0xDB, 0x40);                       // VCOMH deselect level.
  command(0xA4);                             // Follow RAM contents.
  command(0xA6);                             // Normal (not inverted).
  command(0x2E);                             // Scrolling off.
  command(0xAF);                             // Display on.

  present = true;
  clear();
  flush();
  return true;
}

}  // namespace oled
