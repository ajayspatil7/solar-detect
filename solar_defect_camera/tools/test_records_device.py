"""End-to-end check of the SD record store against a real camera on the LAN.

Captures a real image, produces a genuine analysis result with the backend in
mock mode (no API cost), saves it as a record the way the dashboard will, then
verifies listing, byte-exact retrieval, cache revalidation, one-save-per-capture,
cross-origin access, and deletion. Leaves no test records behind.

    .venv/bin/python tools/test_records_device.py 192.168.1.19
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:8000"


def request(method, url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), time.perf_counter() - started
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(), time.perf_counter() - started


def check(label, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{('  -- ' + detail) if detail else ''}")
    if not condition:
        raise SystemExit(1)


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.19"
    base = f"http://{host}"
    print(f"Camera: {base}\n")

    status, _, body, _ = request("GET", f"{base}/health")
    health = json.loads(body)
    check("health reachable", status == 200, health.get("firmware", ""))
    check("SD card mounted", health["sd"]["present"], f"{health['sd']['free_mb']} MB free, {health['sd']['records']} records")
    before_count = health["sd"]["records"]

    status, headers, jpeg, took = request("GET", f"{base}/capture", headers={"Origin": ORIGIN})
    capture_id = headers.get("x-capture-id", "0")
    image = Image.open(io.BytesIO(jpeg))
    check("capture returns UXGA JPEG", status == 200 and image.size == (1600, 1200), f"{len(jpeg):,} B in {took:.2f}s")
    check("capture id issued", capture_id != "0", capture_id)
    check("capture id readable cross-origin", "x-capture-id" in headers.get("access-control-expose-headers", "").lower())

    os.environ["ANALYSIS_MODE"] = "mock"
    sys.path.insert(0, str(PROJECT))
    from fastapi.testclient import TestClient
    from backend import main as backend
    result = TestClient(backend.app).post("/analyze", content=jpeg, headers={"Content-Type": "image/jpeg"}).json()
    result_bytes = json.dumps(result, separators=(",", ":")).encode()
    thumb = io.BytesIO()
    image.convert("RGB").resize((320, 240)).save(thumb, "JPEG", quality=80)
    thumb_bytes = thumb.getvalue()
    check("mock analysis produced", "defects" in result, f"{len(result['defects'])} defects, priority {result['priority']}")

    status, _, _, _ = request("OPTIONS", f"{base}/records", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-capture-id,x-result-length,content-type"})
    check("CORS preflight accepted", status == 204)

    client_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_headers = {"Content-Type": "application/octet-stream", "X-Capture-Id": capture_id,
                    "X-Result-Length": str(len(result_bytes)), "X-Client-Time": client_time, "Origin": ORIGIN}
    status, headers, body, took = request("POST", f"{base}/records", data=result_bytes + thumb_bytes, headers=save_headers)
    record_id = json.loads(body).get("id") if status == 201 else None
    check("record saved", status == 201 and record_id, f"id {record_id} in {took:.2f}s")
    check("save response readable cross-origin", headers.get("access-control-allow-origin") == ORIGIN)

    status, _, body, _ = request("POST", f"{base}/records", data=result_bytes + thumb_bytes, headers=save_headers)
    check("same capture cannot be saved twice", status == 409, json.loads(body)["error"]["code"])

    status, _, body, _ = request("GET", f"{base}/records?limit=5")
    listing = json.loads(body)
    newest = listing["records"][0]
    check("record listed newest first", newest["id"] == record_id, json.dumps(newest))
    check("index reflects the result", newest["status"] == result["status"] and newest["priority"] == result["priority"]
          and newest["defects"] == len(result["defects"]))
    check("timestamp recorded", bool(newest["created"]), str(newest["created"]))
    check("live count incremented", listing["total"] == before_count + 1, str(listing["total"]))

    status, headers, stored, took = request("GET", f"{base}/records/{record_id}/image.jpg")
    check("stored image is byte-identical", status == 200 and hashlib.sha256(stored).digest() == hashlib.sha256(jpeg).digest(),
          f"{len(stored):,} B in {took:.2f}s")
    etag = headers.get("etag")
    status, _, stored_thumb, _ = request("GET", f"{base}/records/{record_id}/thumb.jpg")
    check("thumbnail stored", status == 200 and stored_thumb == thumb_bytes, f"{len(stored_thumb):,} B")
    status, _, stored_result, _ = request("GET", f"{base}/records/{record_id}/result.json")
    check("result stored intact", status == 200 and json.loads(stored_result) == result)

    status, _, body, _ = request("GET", f"{base}/records/{record_id}/image.jpg", headers={"If-None-Match": etag})
    check("unchanged image revalidates without re-download", status == 304 and not body, etag)

    status, _, _, _ = request("DELETE", f"{base}/records/{record_id}")
    check("record deleted", status == 200)
    status, _, _, _ = request("GET", f"{base}/records/{record_id}/image.jpg")
    check("deleted image gone", status == 404)
    status, _, body, _ = request("GET", f"{base}/records?limit=5")
    listing = json.loads(body)
    check("deleted record not listed", all(r["id"] != record_id for r in listing["records"]))
    check("live count restored", listing["total"] == before_count, str(listing["total"]))

    status, _, body, _ = request("GET", f"{base}/records/{record_id}/nope.txt")
    check("unknown file rejected", status == 404)
    print("\nAll record-store checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
