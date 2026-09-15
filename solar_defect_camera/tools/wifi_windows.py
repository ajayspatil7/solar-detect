"""Hand the laptop's current Wi-Fi network to the camera, on Windows.

The camera cannot see which network the laptop is on, so the laptop tells it:
it briefly joins the camera's open SOLAR-SETUP network, posts the network name
and password to the camera, then rejoins its own network. The camera restarts
onto that network and the launcher finds it there.

Everything goes through `netsh wlan`, which ships with Windows. Output is read
as UTF-8 via `chcp 65001`, because network names such as an iPhone's use
characters (a typographic apostrophe) that the default console code page
mangles, and a mangled name cannot be reconnected to.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SETUP_SSID = "SOLAR-SETUP"
SETUP_ADDRESS = "192.168.4.1"


@dataclass
class Connection:
    interface: str
    ssid: str
    profile: str
    authentication: str
    channel: int | None

    @property
    def is_5ghz(self) -> bool:
        return self.channel is not None and self.channel > 14

    @property
    def is_enterprise(self) -> bool:
        return "enterprise" in self.authentication.lower() or "802.1x" in self.authentication.lower()

    @property
    def is_open(self) -> bool:
        return self.authentication.lower() == "open"


def netsh(*args: str, timeout: float = 20.0) -> str:
    command = "chcp 65001 >nul && netsh " + subprocess.list2cmdline(args)
    result = subprocess.run(["cmd", "/d", "/c", command], capture_output=True, timeout=timeout)
    return result.stdout.decode("utf-8", errors="replace")


def _fields(block: str) -> dict[str, str]:
    """Parse 'Key : Value' lines. Keys are matched exactly, so 'AP BSSID' is
    never confused with 'SSID'."""
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if " : " not in line:
            continue
        key, value = line.split(" : ", 1)
        fields.setdefault(key.strip(), value.strip())
    return fields


def parse_interfaces(output: str) -> Connection | None:
    for block in re.split(r"\n\s*\n", output):
        f = _fields(block)
        if f.get("State", "").lower() != "connected" or not f.get("SSID"):
            continue
        channel = f.get("Channel", "")
        return Connection(
            interface=f.get("Name", "Wi-Fi"),
            ssid=f["SSID"],
            profile=f.get("Profile", f["SSID"]),
            authentication=f.get("Authentication", ""),
            channel=int(channel) if channel.isdigit() else None,
        )
    return None


def parse_key_content(output: str) -> str | None:
    """Windows only reveals a saved password to an elevated prompt for most
    profiles; None means 'ask the operator', not 'no password'."""
    match = re.search(r"^\s*Key Content\s*:\s*(.*)$", output, re.MULTILINE)
    return match.group(1).rstrip("\r") if match else None


def parse_visible_ssids(output: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^SSID \d+ : (.*)$", output, re.MULTILINE)]


def current_connection() -> Connection | None:
    return parse_interfaces(netsh("wlan", "show", "interfaces"))


def saved_password(profile: str) -> str | None:
    return parse_key_content(netsh("wlan", "show", "profile", f"name={profile}", "key=clear"))


def setup_network_visible(wait_seconds: float) -> bool:
    deadline = time.time() + wait_seconds
    while True:
        if SETUP_SSID in parse_visible_ssids(netsh("wlan", "show", "networks")):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(3)  # Windows refreshes its network list on its own schedule


def _http(url: str, data: bytes | None = None, timeout: float = 4.0) -> str:
    request = urllib.request.Request(url, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(2000).decode("utf-8", "replace")


def _wait_connected(interface: str, ssid: str, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        connection = current_connection()
        if connection and connection.ssid == ssid and connection.interface == interface:
            return True
        time.sleep(1.5)
    return False


OPEN_PROFILE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{ssid}</name>
  <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security><authEncryption>
    <authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX>
  </authEncryption></security></MSM>
</WLANProfile>
"""


def hand_over(original: Connection, password: str, log=print) -> bool:
    """Send the laptop's network to the camera. Always tries to put the laptop
    back on its original network, even if a step in between fails."""
    profile_file = Path(tempfile.gettempdir()) / "solar-setup-profile.xml"
    profile_file.write_text(OPEN_PROFILE.format(ssid=SETUP_SSID), encoding="utf-8")
    delivered = False
    try:
        netsh("wlan", "add", "profile", f"filename={profile_file}", "user=current")
        log(f"  Switching this laptop to {SETUP_SSID} for a moment...")
        netsh("wlan", "connect", f"name={SETUP_SSID}", f"ssid={SETUP_SSID}",
              f"interface={original.interface}")
        if not _wait_connected(original.interface, SETUP_SSID, 25):
            log(f"  Could not join {SETUP_SSID}.")
            return False

        deadline = time.time() + 20
        while True:  # DHCP from the camera takes a few seconds after association
            try:
                if '"mode":"setup"' in _http(f"http://{SETUP_ADDRESS}/health"):
                    break
            except Exception:
                pass
            if time.time() >= deadline:
                log("  Joined the setup network, but the camera did not answer.")
                return False
            time.sleep(1)

        body = urllib.parse.urlencode({"ssid": original.ssid, "pass": password}).encode()
        log(f"  Sending '{original.ssid}' to the camera...")
        try:
            delivered = "saved" in _http(f"http://{SETUP_ADDRESS}/wifi", data=body, timeout=8)
        except Exception:
            # The camera restarts right after replying; a dropped response
            # usually still means it saved.
            delivered = True
        return delivered
    finally:
        log(f"  Reconnecting this laptop to '{original.ssid}'...")
        netsh("wlan", "connect", f"name={original.profile}", f"ssid={original.ssid}",
              f"interface={original.interface}")
        _wait_connected(original.interface, original.ssid, 30)
        netsh("wlan", "delete", "profile", f"name={SETUP_SSID}", f"interface={original.interface}")
        profile_file.unlink(missing_ok=True)
