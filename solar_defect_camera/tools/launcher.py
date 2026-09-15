"""One-command startup for the Solar Inspector demo.

Does everything an operator would otherwise have to do by hand: checks the API
key, starts the local analysis service, finds the camera on the network, and
opens the browser with the backend address already filled in.

Run it through "Start Solar Inspector.bat" (Windows) or
"Start Solar Inspector.command" (macOS) rather than directly.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from getpass import getpass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend import camera as cam  # noqa: E402  (stdlib-only; safe before the venv check)
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
    return cam.lan_address()


def find_camera(host_ip: str | None, remembered: str = "") -> str | None:
    return cam.discover(host_ip, remembered)


# ------------------------------------------------------- follow the laptop --
def follow_laptop_wifi() -> str | None:
    """Put the camera on whatever Wi-Fi this laptop is using. Windows only."""
    if sys.platform != "win32":
        return None
    import wifi_windows as wifi

    connection = wifi.current_connection()
    if connection is None:
        fail("This laptop is not connected to Wi-Fi. Connect it to the network you "
             "want the camera on, then start again.")
        return None

    banner("CONNECT THE CAMERA TO THIS WI-FI")
    print(f"  This laptop is on : {connection.ssid}")
    if connection.is_enterprise:
        fail("This network asks for a username as well as a password (company or "
             "university Wi-Fi). The camera cannot join that kind of network. Use a "
             "phone hotspot instead.")
        return None
    if connection.is_5ghz:
        print("\n  Note: the laptop is using this network's 5 GHz band. The camera can")
        print("  only use 2.4 GHz. Most home routers offer both under one name, so it")
        print("  will usually still work. A 5 GHz-only network will not.")

    print("\n  Waiting for the camera's setup network (up to 45 seconds)...")
    print("  If the camera screen does not show SETUP, unplug and replug the camera")
    print("  three times quickly, about two seconds each time.")
    if not wifi.setup_network_visible(45):
        fail("The camera's SOLAR-SETUP network did not appear. Check the camera has "
             "power, do the three quick replugs, then start again.")
        return None

    password = "" if connection.is_open else wifi.saved_password(connection.profile)
    if password is None:
        print(f"\n  Windows did not share the saved password for '{connection.ssid}'.")
        print("  Type it below so the camera can join. It is sent only to the camera,")
        print("  and nothing appears on screen while you type.")
        try:
            password = getpass("  Wi-Fi password: ")
        except (EOFError, KeyboardInterrupt):
            return None

    print(f"\n  This laptop will leave '{connection.ssid}' for about 20 seconds.")
    try:
        input("  Press Enter to continue, or close this window to cancel. ")
    except (EOFError, KeyboardInterrupt):
        return None

    if not wifi.hand_over(connection, password):
        fail("The camera did not receive the network details. Start again, or use a "
             "phone to join SOLAR-SETUP and open http://192.168.4.1")
        return None

    print("\n  Camera is restarting onto this network. Looking for it (up to 60 seconds)...")
    deadline = time.time() + 60
    while time.time() < deadline:
        host_ip = lan_address()
        camera = find_camera(host_ip) if host_ip else None
        if camera:
            return camera
        time.sleep(4)
    fail(f"The camera did not appear on '{connection.ssid}'. If its screen shows SETUP "
         "again, the password was probably wrong. Start again and re-enter it.")
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
    if not camera:
        camera = follow_laptop_wifi()
        host_ip = lan_address() or host_ip  # the address can change after reconnecting
    if camera:
        settings = read_env()
        if settings.get("CAMERA_IP") != camera:
            settings["CAMERA_IP"] = camera  # remembered so the next run is instant
            write_env(settings)

    dashboard = f"http://localhost:{PORT}/"
    if camera:
        os.environ["CAMERA_IP"] = camera  # the service in this process reads it
        banner("READY")
        print(f"  Camera    : {camera}")
    else:
        banner("CAMERA NOT FOUND")
        print("  The dashboard will open, but no camera answered on this network.")
        print("  Check that:")
        print("    - the camera has power (its small screen is lit)")
        print("    - its screen shows READY, not SETUP or NO WIFI")
        print("    - it is on the SAME Wi-Fi as this computer")
        print("\n  Then press Find camera in the dashboard.")
        print("\n  To move the camera to this network by hand: unplug and replug it")
        print("  three times quickly until its screen shows SETUP, join 'SOLAR-SETUP'")
        print("  from a phone, and open http://192.168.4.1")
    print(f"  Dashboard : {dashboard}")
    print("\n  Opening the dashboard in your browser...")
    webbrowser.open(dashboard)

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
