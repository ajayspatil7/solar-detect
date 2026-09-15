"""Save a Wi-Fi network to the camera over USB (developer machine, macOS).

Use while the camera is stacked on the ESP32-CAM-MB and plugged into this Mac.
The password is typed at a hidden prompt, sent once over the serial link, and
never written to firmware, source files, or the console. The camera remembers
up to five networks and joins whichever saved one is strongest in range.

    .venv/bin/python tools/add_wifi_usb.py "Network name"
    .venv/bin/python tools/add_wifi_usb.py --list
"""

from __future__ import annotations

import argparse
import re
import glob
import shutil
import subprocess
import sys
import tempfile
import time
from getpass import getpass
from pathlib import Path

IDE_CLI = "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"


def find_cli() -> str:
    cli = shutil.which("arduino-cli") or (IDE_CLI if Path(IDE_CLI).exists() else None)
    if not cli:
        sys.exit("arduino-cli not found. Install Arduino IDE or arduino-cli.")
    return cli


def find_port() -> str:
    ports = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        sys.exit("No camera found on USB. Stack it on the MB and plug it in.")
    return ports[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ssid", nargs="?", help="network name, exactly as it appears")
    parser.add_argument("--list", action="store_true", help="only list saved networks")
    args = parser.parse_args()
    if not args.list and not args.ssid:
        parser.error("give a network name, or --list")

    password = "" if args.list else getpass(f"Password for '{args.ssid}' (hidden, blank if open): ")
    log_path = Path(tempfile.mkstemp(suffix=".log")[1])
    log = open(log_path, "ab", buffering=0)
    monitor = subprocess.Popen([find_cli(), "monitor", "-p", find_port(), "--config", "baudrate=115200", "--quiet"],
                               stdin=subprocess.PIPE, stdout=log, stderr=log)

    def wait_for(token: str, after: int = 0, seconds: float = 75) -> int:
        deadline = time.time() + seconds
        while time.time() < deadline:
            index = log_path.read_text(errors="replace").find(token, after)
            if index >= 0:
                return index + len(token)
            time.sleep(0.4)
        return -1

    def send(text: str) -> None:
        monitor.stdin.write(text.encode("utf-8"))
        monitor.stdin.flush()

    try:
        print("Waiting for the camera to start...")
        position = wait_for("SERIAL_READY")
        if position < 0:
            print("The camera did not respond. Check it is stacked on the MB and plugged in.")
            return 1
        if not args.list:
            send(f"WIFI_ADD {args.ssid}\t{password}\n")
            position = wait_for("WIFI_SAVED", position, 15)
            if position < 0:
                print("The camera did not confirm the save.")
                return 1
            print(f"Saved '{args.ssid}'. Camera is restarting...")
            position = wait_for("SERIAL_READY", position, 90)
        send("WIFI_LIST\n")
        wait_for("WIFI_LIST", max(position, 0), 10)
        time.sleep(1.5)
    finally:
        monitor.terminate()
        try:
            monitor.wait(5)
        except subprocess.TimeoutExpired:
            monitor.kill()

    output = log_path.read_text(errors="replace")
    log_path.unlink(missing_ok=True)
    if password and password in output:
        print("Warning: the password appeared in serial output.")
    for line in output.replace("\r", "").splitlines():
        if line.startswith(("[wifi] Connected", "[wifi] Setup portal", "WIFI_LIST")) or re.match(r"\s+\d+\. ", line):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
