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


NETWORKS = """
Interface name : Wi-Fi
There are 4 networks currently visible.

SSID 1 : Krutika’s iPhone 14
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 2a:c1:a0:2e:77:64
         Signal             : 92%
         Radio type         : 802.11n
         Band               : 2.4 GHz
         Channel            : 6

SSID 2 : Airtel_home
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : 34:24:3e:b3:e4:94
         Signal             : 70%
         Channel            : 1
    BSSID 2                 : 34:24:3e:b3:e4:95
         Signal             : 88%
         Channel            : 36

SSID 3 : Office 5G
    Authentication          : WPA2-Personal
    BSSID 1                 : 11:22:33:44:55:66
         Signal             : 60%
         Channel            : 149

SSID 4 : SOLAR-SETUP
    Authentication          : Open
    BSSID 1                 : 78:1c:3c:f6:87:b5
         Signal             : 99%
         Channel            : 1

SSID 5 : 
    Authentication          : WPA2-Personal
    BSSID 1                 : aa:bb:cc:dd:ee:ff
         Signal             : 40%
         Channel            : 11
"""


def test_visible_networks_are_listed_strongest_first_with_bands():
    nets = wifi.parse_networks(NETWORKS)
    assert [n.ssid for n in nets] == ["Krutika’s iPhone 14", "Airtel_home", "Office 5G"]
    home = nets[1]
    assert home.signal == 88 and home.has_2ghz and home.has_5ghz   # best of its two radios
    assert not nets[2].has_2ghz                                    # 5 GHz only: camera cannot use it
    assert nets[0].authentication == "WPA2-Personal"


def test_camera_setup_network_and_hidden_networks_are_not_offered():
    names = [n.ssid for n in wifi.parse_networks(NETWORKS)]
    assert "SOLAR-SETUP" not in names and "" not in names


def test_saved_profiles_are_parsed():
    out = "Profiles on interface Wi-Fi:\n\nUser profiles\n-------------\n    All User Profile     : Krutika’s iPhone 14\n    All User Profile     : Airtel_home\n"
    assert wifi.parse_profiles(out) == ["Krutika’s iPhone 14", "Airtel_home"]


def test_new_network_profile_escapes_names_and_passwords():
    xml = wifi.profile_xml("Tom & Jerry’s <Wi-Fi>", "p<a>ss&word")
    assert "Tom &amp; Jerry’s &lt;Wi-Fi&gt;" in xml
    assert "<keyMaterial>p&lt;a&gt;ss&amp;word</keyMaterial>" in xml
    assert "<authentication>WPA2PSK</authentication>" in xml
    assert "<authentication>open</authentication>" in wifi.profile_xml("Cafe", "")
