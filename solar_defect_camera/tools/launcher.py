"""One-command startup for the Solar Inspector demo.

Does everything an operator would otherwise have to do by hand: checks the API
key, starts the local analysis service, finds the camera on the network, and
opens the browser with the backend address already filled in.

Run it through "Start Solar Inspector.bat" (Windows) or
"Start Solar Inspector.command" (macOS) rather than directly.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from getpass import getpass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT / ".env.local"
PORT = 8000
PLACEHOLDER = "replace-with-your-openai-project-key"

RULE = "=" * 62

# Show progress as it happens rather than in one burst at the end.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def banner(text: str) -> None:
    print(f"\n{RULE}\n  {text}\n{RULE}")


def fail(text: str) -> None:
    print(f"\n  PROBLEM: {text}\n")


# --------------------------------------------------------------- API key ----
def read_env() -> dict[str, str]:
    settings: dict[str, str] = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip()
    return settings


def write_env(settings: dict[str, str]) -> None:
    body = "\n".join(f"{k}={v}" for k, v in settings.items()) + "\n"
    ENV_FILE.write_text(body, encoding="utf-8")
    try:
        ENV_FILE.chmod(0o600)  # no-op on Windows, meaningful elsewhere
    except OSError:
        pass


def ensure_api_key() -> bool:
    settings = read_env()
    key = settings.get("OPENAI_API_KEY", "")
    if key and key != PLACEHOLDER and len(key) > 20:
        print(f"  API key      : found ({len(key)} characters)")
        return True

    banner("FIRST-TIME SETUP")
    print("  This computer needs the OpenAI API key once. It is stored only in")
    print(f"  {ENV_FILE}")
    print("  and is never sent anywhere except OpenAI.\n")
    print("  Paste the key and press Enter. Nothing will appear on screen as")
    print("  you paste -- that is normal and means it is being hidden.\n")
    try:
        entered = getpass("  API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        return False

    if not entered:
        fail("No key entered.")
        return False
    if not entered.startswith("sk-"):
        fail("That does not look like an OpenAI key -- they begin with 'sk-'.")
        return False

    settings.setdefault("OPENAI_MODEL", "gpt-5.6-luna")
    settings.setdefault("ANALYSIS_MODE", "openai")
    settings.setdefault("BACKEND_HOST", "0.0.0.0")
    settings.setdefault("BACKEND_PORT", str(PORT))
    settings["OPENAI_API_KEY"] = entered
    write_env(settings)
    print("\n  Key saved. You will not be asked again on this computer.")
    return True


# --------------------------------------------------------------- network ----
def lan_address() -> str | None:
    """The address other devices on the Wi-Fi can reach this computer at."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))  # no packets are sent
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def probe_camera(address: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(f"http://{address}/health", timeout=timeout) as r:
            body = r.read(1400).decode("utf-8", "replace")
        return "capture_width" in body and "firmware" in body
    except Exception:
        return False


def find_camera(host_ip: str, remembered: str = "") -> str | None:
    """Check the last known address first, then sweep the subnet.

    Two passes with a widening timeout: a camera on a weak link can miss a
    short deadline, and Windows is less tolerant of large connection fan-outs
    than macOS, so the worker count stays modest.
    """
    if remembered and probe_camera(remembered, 3.0):
        return remembered

    network = ipaddress.ip_network(f"{host_ip}/24", strict=False)
    candidates = [str(a) for a in network.hosts()]

    for timeout, workers in ((1.5, 64), (3.0, 32)):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(lambda a: (a, probe_camera(a, timeout)), candidates)
            for address, ok in results:
                if ok:
                    return address
        print("  Still looking (slower sweep)...")
    return None


def wait_for_backend(seconds: float = 25.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                return json.loads(r.read().decode()).get("ok", False) is not None
        except Exception:
            time.sleep(0.4)
    return False


# ------------------------------------------------------------------ main ----
def main() -> int:
    banner("SOLAR PANEL INSPECTOR")

    if not ensure_api_key():
        fail("Cannot start without an API key.")
        input("\n  Press Enter to close. ")
        return 1

    sys.path.insert(0, str(PROJECT))
    import uvicorn  # imported late so a missing venv fails in the .bat instead
    from backend.main import load_local_env

    load_local_env()

    config = uvicorn.Config(f"backend.main:app", host="0.0.0.0", port=PORT,
                            log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    print("\n  Starting the analysis service...")
    if not wait_for_backend():
        fail("The analysis service did not start. Close this window and try again.")
        input("\n  Press Enter to close. ")
        return 1

    host_ip = lan_address()
    print(f"  Analysis service: running on this computer  ({host_ip or 'no network'}:{PORT})")

    if host_ip is None:
        fail("This computer is not on a network. Connect to Wi-Fi and restart.")
        input("\n  Press Enter to close. ")
        return 1

    print("  Looking for the camera on your Wi-Fi...")
    camera = find_camera(host_ip, read_env().get("CAMERA_IP", ""))
    if camera:
        settings = read_env()
        if settings.get("CAMERA_IP") != camera:
            settings["CAMERA_IP"] = camera  # remembered so the next run is instant
            write_env(settings)

    backend_url = f"http://{host_ip}:{PORT}"
    if camera:
        page = f"http://{camera}/?backend={backend_url}"
        banner("READY")
        print(f"  Camera  : {camera}")
        print(f"  Service : {backend_url}")
        print("\n  Opening the inspection page in your browser...")
        webbrowser.open(page)
    else:
        banner("CAMERA NOT FOUND")
        print("  The analysis service is running, but no camera answered on this")
        print("  network. Check that:")
        print("    - the camera has power (its small screen is lit)")
        print("    - its screen shows READY, not SETUP or NO WIFI")
        print("    - it is on the SAME Wi-Fi as this computer")
        print("\n  If the screen shows SETUP, connect a phone to the 'SOLAR-SETUP'")
        print("  network and open http://192.168.4.1 to choose your Wi-Fi.")
        print(f"\n  Once the camera screen shows an address, open it in a browser")
        print(f"  and set the backend to: {backend_url}")

    print("\n  Leave this window open while you use the inspector.")
    print("  Closing it stops the analysis service.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
