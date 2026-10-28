"""The laptop side of every conversation with the ESP32-CAM.

The dashboard is served by this backend, so all camera calls except the live
MJPEG stream pass through here. The browser stays same-origin, and the
camera's address can change -- DHCP, a new venue -- without the page having
to know. Discovery lives here too, shared with the launcher.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


class CameraError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


NOT_FOUND = CameraError(
    "camera_not_found",
    "The camera can't be reached. Check it has power and its screen shows READY "
    "with an address, then press Find camera.",
    503,
)

_lock = threading.Lock()
_address: str | None = None
last_health: dict = {}  # the most recent /health, so callers can adapt to the firmware
_last_seen = 0.0        # monotonic time the camera last answered anything

# A camera on a slow or busy link can miss a status check while it streams the
# live view. One miss is not a missing camera: report it missing only after it
# has been silent this long. Status checks also get a generous time limit.
GRACE_S = 45.0
STATUS_TIMEOUT_S = 6.0


# ------------------------------------------------------------- discovery ----
def lan_address() -> str | None:
    """The address other devices on this Wi-Fi can reach this computer at."""
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe_socket.connect(("8.8.8.8", 80))  # selects a route; sends nothing
        return probe_socket.getsockname()[0]
    except OSError:
        return None
    finally:
        probe_socket.close()


def probe(address: str, timeout: float = 2.5) -> dict | None:
    """Return the camera's health if `address` is a Solar Inspector camera in
    normal mode, otherwise None."""
    try:
        with urllib.request.urlopen(f"http://{address}/health", timeout=timeout) as response:
            health = json.loads(response.read(4000).decode("utf-8", "replace"))
    except (OSError, ValueError):
        return None
    return health if "capture_width" in health and "firmware" in health else None


def discover(host_ip: str | None = None, remembered: str = "") -> str | None:
    """Check the remembered address, then sweep the local network.

    An iPhone hotspot is always 172.20.10.0/28 -- fourteen addresses -- so that
    range is swept directly. Elsewhere the low addresses go first, then the
    full /24 with a longer timeout for cameras on a weak link. Windows
    tolerates large connection fan-outs poorly, so worker counts stay modest.
    """
    if remembered and probe(remembered, 3.0):
        return remembered
    host_ip = host_ip or lan_address()
    if not host_ip:
        return None
    prefix = ".".join(host_ip.split(".")[:3])
    if host_ip.startswith("172.20.10."):
        passes = [([f"{prefix}.{n}" for n in range(1, 15)], 2.0, 14)]
    else:
        near = [f"{prefix}.{n}" for n in range(1, 26)]
        full = [str(a) for a in ipaddress.ip_network(f"{host_ip}/24", strict=False).hosts()]
        passes = [(near, 1.5, 25), (full, 1.5, 64), (full, 3.0, 32)]

    for candidates, timeout, workers in passes:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for address, health in zip(candidates, pool.map(lambda a: probe(a, timeout), candidates)):
                if health:
                    return address
    return None


def _seen() -> None:
    global _last_seen
    _last_seen = time.monotonic()


def seen_recently() -> bool:
    return _address is not None and time.monotonic() - _last_seen < GRACE_S


def check(search: bool = False) -> tuple[str, dict]:
    """The camera's address and health from a single request. A full network
    search only runs when asked, because it takes seconds."""
    global _address, last_health
    with _lock:
        remembered = [a for a in (_address, os.getenv("CAMERA_IP", "").strip()) if a]
        for candidate in dict.fromkeys(remembered):
            health_now = probe(candidate, STATUS_TIMEOUT_S)
            if health_now:
                _address, last_health = candidate, health_now
                _seen()
                return candidate, health_now
        if search:
            found = discover()
            if found:
                _address, last_health = found, probe(found, STATUS_TIMEOUT_S) or last_health
                _seen()
                return found, last_health
        elif seen_recently():
            return _address, last_health  # a missed check on a busy link
        _address = None
    raise NOT_FOUND


def address(search: bool = False) -> str:
    """The camera's current address. If it answered recently, that is trusted
    without asking again, so every request doesn't cost an extra round trip."""
    if not search and seen_recently():
        return _address
    return check(search)[0]


def forget() -> None:
    global _address
    with _lock:
        _address = None


# --------------------------------------------------------------- requests ---
def _call(method: str, path: str, data: bytes | None = None, headers: dict | None = None,
          timeout: float = 30.0) -> tuple[int, dict, bytes]:
    host = address()
    request = urllib.request.Request(f"http://{host}{path}", data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except urllib.error.HTTPError as exc:
        _seen()
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
    except OSError as exc:
        # One failed request on a slow link is not proof the camera has gone;
        # the status check decides that, after GRACE_S of silence.
        raise NOT_FOUND from exc
    _seen()
    return reply


def _camera_error(status: int, body: bytes, fallback: str) -> CameraError:
    try:
        error = json.loads(body)["error"]
        return CameraError(error["code"], error["message"], status)
    except (ValueError, KeyError, TypeError):
        return CameraError("camera_error", fallback, status if status >= 400 else 502)


def health() -> dict:
    global last_health
    status, _, body = _call("GET", "/health", timeout=STATUS_TIMEOUT_S)
    if status != 200:
        raise _camera_error(status, body, "The camera did not report its status.")
    last_health = json.loads(body)
    return last_health


def capture() -> tuple[bytes, str]:
    """A fresh 1600x1200 JPEG and the id the camera holds it under for saving."""
    status, headers, body = _call("GET", "/capture", timeout=60)
    if status != 200:
        raise CameraError("capture_failed", "The camera could not take a picture. Try again.", 502)
    return body, headers.get("x-capture-id", "0")


def show_status(payload: dict) -> None:
    """Mirror progress on the camera's OLED. Best effort: a missed update must
    never interrupt an inspection."""
    try:
        _call("POST", "/status", data=json.dumps(payload).encode(),
              headers={"Content-Type": "application/json"}, timeout=4)
    except CameraError:
        pass


def save_record(capture_id: str, result: dict, thumbnail: bytes, client_time: str) -> str:
    result_bytes = json.dumps(result, separators=(",", ":")).encode()
    status, _, body = _call("POST", "/records", data=result_bytes + thumbnail, timeout=30, headers={
        "Content-Type": "application/octet-stream",
        "X-Capture-Id": capture_id,
        "X-Result-Length": str(len(result_bytes)),
        "X-Client-Time": client_time,
    })
    if status != 201:
        raise _camera_error(status, body, "The camera could not save this inspection.")
    return json.loads(body)["id"]


def list_records(before: int = 0, limit: int = 24) -> dict:
    status, _, body = _call("GET", f"/records?before={before}&limit={limit}", timeout=15)
    if status != 200:
        raise _camera_error(status, body, "The camera could not list its inspections.")
    return json.loads(body)


def record_file(record_id: str, name: str, etag: str | None = None) -> tuple[int, dict, bytes]:
    headers = {"If-None-Match": etag} if etag else {}
    return _call("GET", f"/records/{record_id}/{name}", headers=headers, timeout=60)


def delete_record(record_id: str) -> None:
    status, _, body = _call("DELETE", f"/records/{record_id}", timeout=15)
    if status != 200:
        raise _camera_error(status, body, "The camera could not delete that inspection.")
