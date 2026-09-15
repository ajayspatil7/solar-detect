#pragma once

// Inspection record store on the microSD card.
//
//   /records/index.jsonl          one fixed-width line per inspection
//   /records/store.txt            random id for this card (cache validation)
//   /records/<id>/image.jpg       full 1600x1200 capture
//   /records/<id>/thumb.jpg       small preview made by the dashboard
//   /records/<id>/result.json     analysis result including root causes
//
// Index lines are exactly LINE bytes, so record N always sits at offset
// (N - 1) * LINE. Listing a page and deleting a record are therefore direct
// seeks rather than scans, however many records accumulate, and a power cut
// mid-append can only damage the final line. Ids are issued from the line
// count and never reused; a deleted record keeps its line, marked deleted.

#include <Arduino.h>
#include <FS.h>
#include <SD_MMC.h>
#include <esp_random.h>
#include <time.h>

namespace records {

constexpr char ROOT[] = "/records";
constexpr char INDEX_PATH[] = "/records/index.jsonl";
constexpr char STORE_PATH[] = "/records/store.txt";
constexpr size_t LINE = 192;
constexpr size_t MAX_RESULT_BYTES = 32768;
constexpr size_t MAX_THUMB_BYTES = 65536;

inline bool mounted = false;
inline uint32_t lineCount = 0;  // equals the highest id ever issued
inline uint32_t liveCount = 0;
inline uint64_t freeBytes = 0;
inline char storeId[9] = "";

struct Meta {
  char status[24] = "";
  char priority[12] = "";
  uint8_t defects = 0;
  char clientTime[24] = "";
};

inline void idString(uint32_t id, char *out, size_t size) {
  snprintf(out, size, "%06lu", static_cast<unsigned long>(id));
}

inline bool clockSet() { return time(nullptr) > 1700000000; }

inline void isoNow(char *out, size_t size) {
  const time_t now = time(nullptr);
  struct tm utc;
  gmtime_r(&now, &utc);
  strftime(out, size, "%Y-%m-%dT%H:%M:%SZ", &utc);
}

// Enum-like values are written into JSON unescaped, so only allow the
// characters the backend's enums actually use.
inline void sanitize(const char *in, char *out, size_t size) {
  size_t n = 0;
  for (const char *c = in; *c && n + 1 < size; ++c) {
    if ((*c >= 'a' && *c <= 'z') || *c == '_') out[n++] = *c;
  }
  out[n] = '\0';
}

inline bool isDeletedLine(const char *line) { return strstr(line, "\"deleted\":true") != nullptr; }

inline bool writeLine(uint32_t id, const char *json) {
  char line[LINE];
  memset(line, ' ', LINE);
  const size_t len = strnlen(json, LINE - 1);
  memcpy(line, json, len);
  line[LINE - 1] = '\n';
  File index = SD_MMC.exists(INDEX_PATH) ? SD_MMC.open(INDEX_PATH, "r+") : SD_MMC.open(INDEX_PATH, FILE_WRITE);
  if (!index) return false;
  const bool ok = index.seek(static_cast<size_t>(id - 1) * LINE) && index.write(reinterpret_cast<const uint8_t *>(line), LINE) == LINE;
  index.close();
  return ok;
}

inline bool readLine(uint32_t id, char *line) {
  if (id == 0 || id > lineCount) return false;
  File index = SD_MMC.open(INDEX_PATH, FILE_READ);
  if (!index) return false;
  const bool ok = index.seek(static_cast<size_t>(id - 1) * LINE) && index.read(reinterpret_cast<uint8_t *>(line), LINE) == LINE;
  index.close();
  if (ok) line[LINE - 1] = '\0';
  return ok;
}

inline bool writeFile(const String &path, const uint8_t *data, size_t len) {
  File file = SD_MMC.open(path, FILE_WRITE);
  if (!file) return false;
  const bool ok = file.write(data, len) == len;
  file.close();
  return ok;
}

inline void removeRecordFiles(const String &dir) {
  for (const char *name : {"/image.jpg", "/thumb.jpg", "/result.json"}) {
    const String path = dir + name;
    if (SD_MMC.exists(path)) SD_MMC.remove(path);
  }
  SD_MMC.rmdir(dir);
}

inline bool begin() {
  mounted = false;
  // 1-bit mode uses GPIO2 (D0), GPIO14 (CLK) and GPIO15 (CMD), leaving IO13
  // free for the OLED's SDA line.
  if (!SD_MMC.begin("/sdcard", true) || SD_MMC.cardType() == CARD_NONE) return false;
  if (!SD_MMC.exists(ROOT) && !SD_MMC.mkdir(ROOT)) return false;

  File store = SD_MMC.open(STORE_PATH, FILE_READ);
  if (store && store.size() >= 8) {
    store.read(reinterpret_cast<uint8_t *>(storeId), 8);
    storeId[8] = '\0';
  }
  if (store) store.close();
  if (storeId[0] == '\0') {
    snprintf(storeId, sizeof(storeId), "%08lx", static_cast<unsigned long>(esp_random()));
    writeFile(STORE_PATH, reinterpret_cast<const uint8_t *>(storeId), 8);
  }

  lineCount = 0;
  liveCount = 0;
  File index = SD_MMC.open(INDEX_PATH, FILE_READ);
  if (index) {
    lineCount = index.size() / LINE;  // a torn final line is overwritten by the next save
    char block[LINE];
    for (uint32_t i = 0; i < lineCount; ++i) {
      if (index.read(reinterpret_cast<uint8_t *>(block), LINE) != LINE) break;
      block[LINE - 1] = '\0';
      if (block[0] == '{' && !isDeletedLine(block)) ++liveCount;
    }
    index.close();
  }
  freeBytes = SD_MMC.totalBytes() - SD_MMC.usedBytes();
  mounted = true;
  return true;
}

// Returns the new record id, or 0 on failure.
inline uint32_t create(const uint8_t *image, size_t imageLen, const uint8_t *result, size_t resultLen,
                       const uint8_t *thumb, size_t thumbLen, const Meta &meta) {
  if (!mounted || imageLen == 0) return 0;
  const uint32_t id = lineCount + 1;
  char idText[12];
  idString(id, idText, sizeof(idText));
  const String dir = String(ROOT) + "/" + idText;

  if (SD_MMC.exists(dir)) removeRecordFiles(dir);  // leftovers from an interrupted save
  if (!SD_MMC.mkdir(dir) || !writeFile(dir + "/image.jpg", image, imageLen) ||
      (resultLen && !writeFile(dir + "/result.json", result, resultLen)) ||
      (thumbLen && !writeFile(dir + "/thumb.jpg", thumb, thumbLen))) {
    removeRecordFiles(dir);
    return 0;
  }

  char created[24] = "";
  if (clockSet()) {
    isoNow(created, sizeof(created));
  } else if (strlen(meta.clientTime) == 20 && meta.clientTime[10] == 'T' && meta.clientTime[19] == 'Z') {
    strncpy(created, meta.clientTime, sizeof(created) - 1);
  }
  char status[24], priority[12];
  sanitize(meta.status, status, sizeof(status));
  sanitize(meta.priority, priority, sizeof(priority));

  char json[LINE];
  snprintf(json, sizeof(json),
           "{\"id\":\"%s\",\"created\":%s%s%s,\"status\":\"%s\",\"priority\":\"%s\","
           "\"defects\":%u,\"image_bytes\":%lu,\"thumb\":%s,\"analyzed\":%s}",
           idText, created[0] ? "\"" : "", created[0] ? created : "null", created[0] ? "\"" : "",
           status, priority, static_cast<unsigned>(meta.defects), static_cast<unsigned long>(imageLen),
           thumbLen ? "true" : "false", resultLen ? "true" : "false");
  if (!writeLine(id, json)) {
    removeRecordFiles(dir);
    return 0;
  }
  lineCount = id;
  ++liveCount;
  const size_t used = imageLen + resultLen + thumbLen;
  freeBytes = freeBytes > used ? freeBytes - used : 0;
  return id;
}

inline bool remove(uint32_t id) {
  char line[LINE];
  char idText[12];
  idString(id, idText, sizeof(idText));
  if (!mounted || !readLine(id, line) || line[0] != '{' || isDeletedLine(line)) return false;

  char marker[64];
  snprintf(marker, sizeof(marker), "{\"id\":\"%s\",\"deleted\":true}", idText);
  if (!writeLine(id, marker)) return false;
  removeRecordFiles(String(ROOT) + "/" + idText);
  if (liveCount) --liveCount;
  return true;
}

// Newest first. `before` is exclusive; pass 0 for the newest page.
inline String list(uint32_t before, uint8_t limit) {
  String out = "{\"records\":[";
  uint32_t id = (before == 0 || before > lineCount + 1) ? lineCount : before - 1;
  uint8_t taken = 0;
  uint32_t lastId = 0;
  char line[LINE];
  File index = mounted ? SD_MMC.open(INDEX_PATH, FILE_READ) : File();
  while (index && id >= 1 && taken < limit) {
    if (index.seek(static_cast<size_t>(id - 1) * LINE) && index.read(reinterpret_cast<uint8_t *>(line), LINE) == LINE) {
      line[LINE - 1] = '\0';
      if (line[0] == '{' && !isDeletedLine(line)) {
        size_t len = strnlen(line, LINE - 1);
        while (len && (line[len - 1] == ' ' || line[len - 1] == '\n')) --len;
        line[len] = '\0';
        if (taken) out += ",";
        out += line;
        ++taken;
        lastId = id;
      }
    }
    --id;
  }
  if (index) index.close();
  out += "],\"next_before\":";
  out += (taken == limit && lastId > 1) ? String(lastId) : String("null");
  out += ",\"total\":" + String(liveCount) + "}";
  return out;
}

}  // namespace records
