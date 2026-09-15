"""Parser tests for the Windows Wi-Fi hand-over, runnable on any OS."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wifi_windows as wifi  # noqa: E402

INTERFACES = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : MediaTek Wi-Fi 6 MT7921 Wireless LAN Card
    Physical address       : 2c:3b:70:d8:4e:03
    State                  : connected
    SSID                   : Krutika’s iPhone 14
    AP BSSID               : 2a:c1:a0:2e:77:64
    Band                   : 2.4 GHz
    Channel                : 6
    Radio type             : 802.11n
    Authentication         : WPA2-Personal
    Profile                : Krutika’s iPhone 14
"""


def test_connected_interface_is_parsed_with_unicode_ssid():
    c = wifi.parse_interfaces(INTERFACES)
    assert c.ssid == "Krutika’s iPhone 14"      # AP BSSID must not shadow SSID
    assert c.profile == "Krutika’s iPhone 14"
    assert c.interface == "Wi-Fi"
    assert c.channel == 6 and not c.is_5ghz
    assert not c.is_enterprise and not c.is_open


def test_disconnected_interface_returns_none():
    assert wifi.parse_interfaces(INTERFACES.replace(": connected", ": disconnected")) is None


def test_5ghz_and_enterprise_are_detected():
    c = wifi.parse_interfaces(INTERFACES.replace("Channel                : 6", "Channel                : 149")
                              .replace("WPA2-Personal", "WPA2-Enterprise"))
    assert c.is_5ghz and c.is_enterprise


def test_password_only_when_windows_reveals_it():
    shown = "Security settings\n    Security key           : Present\n    Key Content            : pa ss:word\n"
    hidden = "Security settings\n    Security key           : Present\n"
    assert wifi.parse_key_content(shown) == "pa ss:word"
    assert wifi.parse_key_content(hidden) is None


def test_setup_network_found_in_scan():
    scan = "Interface name : Wi-Fi\nThere are 2 networks currently visible.\n\nSSID 1 : SOLAR-SETUP\n    Authentication          : Open\n\nSSID 2 : Home 2.4G\n"
    assert wifi.parse_visible_ssids(scan) == ["SOLAR-SETUP", "Home 2.4G"]
