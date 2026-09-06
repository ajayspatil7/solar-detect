from __future__ import annotations

import gzip
import re
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "web_ui.h"
OUTPUT = PROJECT / "web_ui_gzip.h"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r'R"HTML\((.*)\)HTML";', source, re.DOTALL)
    if not match:
        raise SystemExit("Could not find the HTML raw string in web_ui.h")
    html = match.group(1).encode("utf-8")
    compressed = gzip.compress(html, compresslevel=9, mtime=0)
    rows = []
    for offset in range(0, len(compressed), 16):
        chunk = compressed[offset : offset + 16]
        rows.append("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    output = "\n".join(
        [
            "#pragma once",
            "",
            "// Generated from web_ui.h by tools/generate_web_ui.py.",
            "const uint8_t PHASE3_INDEX_HTML_GZ[] PROGMEM = {",
            *rows,
            "};",
            f"const size_t PHASE3_INDEX_HTML_GZ_LEN = {len(compressed)};",
            "",
        ]
    )
    OUTPUT.write_text(output, encoding="utf-8")
    if gzip.decompress(compressed) != html:
        raise SystemExit("Generated UI failed the round-trip check")
    print(f"UI: {len(html):,} bytes -> {len(compressed):,} bytes gzip")


if __name__ == "__main__":
    main()
