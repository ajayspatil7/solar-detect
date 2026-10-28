"""The launcher's Wi-Fi menu, with the Windows Wi-Fi calls replaced."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
import launcher  # noqa: E402
import wifi_windows  # noqa: E402

N = wifi_windows.Network


class FakeWifi:
    def __init__(self, current="Home", networks=None, saved=("Home",), connects=True):
        self.current = SimpleNamespace(ssid=current, interface="Wi-Fi") if current else None
        self.networks = networks if networks is not None else [
            N("Home", "WPA2-Personal", 80, {1}),
            N("Krutika’s iPhone 14", "WPA2-Personal", 95, {6}),
            N("Office 5G", "WPA2-Personal", 60, {149}),
            N("Cafe", "Open", 40, {11}),
        ]
        self.saved, self.ok, self.joined = list(saved), connects, []

    def current_connection(self): return self.current
    def visible_networks(self): return self.networks
    def saved_profiles(self): return self.saved
    def connect(self, ssid, password, interface="Wi-Fi", seconds=30):
        self.joined.append((ssid, password, interface))
        return self.ok


def run(wifi, answer, secret="hunter2"):
    asked = []
    launcher.choose_wifi(wifi=wifi, ask=lambda _: answer, ask_secret=lambda _: asked.append(1) or secret)
    return asked


def test_enter_keeps_the_current_network():
    wifi = FakeWifi()
    run(wifi, "")
    assert wifi.joined == []


def test_choosing_a_known_network_uses_the_saved_password():
    wifi = FakeWifi(saved=("Home", "Krutika’s iPhone 14"))
    asked = run(wifi, "2")
    assert wifi.joined == [("Krutika’s iPhone 14", None, "Wi-Fi")] and asked == []


def test_choosing_a_new_network_asks_for_its_password():
    wifi = FakeWifi()
    asked = run(wifi, "2")
    assert wifi.joined == [("Krutika’s iPhone 14", "hunter2", "Wi-Fi")] and asked == [1]


def test_open_network_needs_no_password():
    wifi = FakeWifi()
    asked = run(wifi, "4")
    assert wifi.joined == [("Cafe", "", "Wi-Fi")] and asked == []


def test_5ghz_only_network_is_refused():
    wifi = FakeWifi()
    run(wifi, "3")
    assert wifi.joined == []


def test_choosing_the_current_network_changes_nothing():
    wifi = FakeWifi()
    run(wifi, "1")
    assert wifi.joined == []


def test_an_answer_not_in_the_list_keeps_the_current_network():
    for answer in ("9", "x", "0"):
        wifi = FakeWifi()
        run(wifi, answer)
        assert wifi.joined == []


def test_no_visible_networks_does_not_ask():
    wifi = FakeWifi(networks=[])
    launcher.choose_wifi(wifi=wifi, ask=lambda _: (_ for _ in ()).throw(AssertionError("asked")))
    assert wifi.joined == []
