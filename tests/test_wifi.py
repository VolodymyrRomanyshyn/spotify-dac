"""Tests for the Wi-Fi settings backend, with a fake Wi-Fi (no Pi needed): python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
os.environ.setdefault("SPOTIFY_DAC_CONFIG", "/nonexistent/config-for-tests")

from api import wifi  # noqa: E402
from api.common import ApiError  # noqa: E402

NEARBY = [
    {"name": "Home-WiFi", "signal": 82, "secure": True},
    {"name": "Cafe Free", "signal": 40, "secure": False},
    {"name": "Office", "signal": 30, "secure": True},
]


class ModeRuleTests(unittest.TestCase):
    def test_ethernet_wins_over_wifi_and_hotspot(self):
        self.assertEqual(wifi.next_mode(True, True, 999, 60), "ethernet")

    def test_wifi_when_no_cable(self):
        self.assertEqual(wifi.next_mode(False, True, 999, 60), "wifi")

    def test_hotspot_only_after_the_fallback_time(self):
        self.assertEqual(wifi.next_mode(False, False, 59, 60), "none")
        self.assertEqual(wifi.next_mode(False, False, 60, 60), "hotspot")
        self.assertEqual(wifi.next_mode(False, False, 200, 300), "none")

    def test_fallback_limits(self):
        self.assertTrue(wifi.valid_fallback(60))
        self.assertTrue(wifi.valid_fallback(300))
        self.assertFalse(wifi.valid_fallback(59))
        self.assertFalse(wifi.valid_fallback(301))
        self.assertFalse(wifi.valid_fallback(True))
        self.assertEqual(wifi.parse_fallback("120"), 120)
        with self.assertRaises(ApiError):
            wifi.parse_fallback("10")


class InputRuleTests(unittest.TestCase):
    def test_names(self):
        self.assertTrue(wifi.valid_name("Home-WiFi"))
        self.assertFalse(wifi.valid_name(""))
        self.assertFalse(wifi.valid_name("   "))
        self.assertFalse(wifi.valid_name("x" * 33))

    def test_passwords_are_8_to_63(self):
        self.assertFalse(wifi.valid_password("1234567"))
        self.assertTrue(wifi.valid_password("12345678"))
        self.assertTrue(wifi.valid_password("x" * 63))
        self.assertFalse(wifi.valid_password("x" * 64))


class ScanParsingTests(unittest.TestCase):
    def test_parses_and_sorts_by_signal(self):
        text = "Home-WiFi:82:WPA2\nCafe Free:40:\nOffice:30:WPA2\n"
        networks = wifi.parse_scan(text)
        self.assertEqual([n["name"] for n in networks], ["Home-WiFi", "Cafe Free", "Office"])
        self.assertTrue(networks[0]["secure"])
        self.assertFalse(networks[1]["secure"])

    def test_escaped_colon_in_a_name(self):
        networks = wifi.parse_scan("Cafe\\:Net:55:WPA2\n")
        self.assertEqual(networks[0]["name"], "Cafe:Net")

    def test_keeps_the_strongest_copy_of_a_duplicate_name(self):
        networks = wifi.parse_scan("Home:20:WPA2\nHome:70:WPA2\n")
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["signal"], 70)

    def test_skips_bad_lines(self):
        self.assertEqual(wifi.parse_scan("\n:50:WPA2\nName:abc:WPA2\n"), [])


class SaveTests(unittest.TestCase):
    def service(self, **kwargs):
        return wifi.WifiService(wifi.FakeWifi(nearby=NEARBY, **kwargs))

    def test_right_password_joins_and_stops_the_hotspot(self):
        svc = self.service(current=None)
        svc.backend.hotspot = True
        result = svc.save("Home-WiFi", "right-password")
        self.assertTrue(result["ok"])
        self.assertEqual(svc.backend.current, "Home-WiFi")
        self.assertFalse(svc.backend.hotspot)
        self.assertIn("Home-WiFi", svc.backend.saved)

    def test_wrong_password_from_wifi_goes_back_to_the_previous_network(self):
        svc = self.service(current="Office", saved={"Office": "office-pass"})
        result = svc.save("Home-WiFi", "wrong-password")
        self.assertFalse(result["ok"])
        self.assertEqual(svc.backend.current, "Office")
        self.assertFalse(svc.backend.hotspot)
        self.assertNotIn("Home-WiFi", svc.backend.saved)

    def test_wrong_password_with_no_network_starts_the_hotspot(self):
        svc = self.service(current=None)
        result = svc.save("Home-WiFi", "wrong-password")
        self.assertFalse(result["ok"])
        self.assertTrue(svc.backend.hotspot)
        self.assertIsNone(svc.backend.current)

    def test_open_network_needs_no_password(self):
        svc = self.service(current=None)
        result = svc.save("Cafe Free", None)
        self.assertTrue(result["ok"])
        self.assertEqual(svc.backend.current, "Cafe Free")

    def test_secured_network_needs_a_valid_password(self):
        svc = self.service(current=None)
        with self.assertRaises(ApiError):
            svc.save("Home-WiFi", "short")
        with self.assertRaises(ApiError):
            svc.save("Home-WiFi", None)

    def test_unknown_network_is_refused(self):
        svc = self.service(current=None)
        with self.assertRaises(ApiError) as caught:
            svc.save("Not Around", "12345678")
        self.assertEqual(caught.exception.args[0], "That network is not in the list. Scan again.")

    def test_bad_name_is_refused(self):
        svc = self.service(current=None)
        with self.assertRaises(ApiError):
            svc.save("", "12345678")


class ForgetAndStateTests(unittest.TestCase):
    def test_forget_removes_a_saved_network(self):
        svc = wifi.WifiService(wifi.FakeWifi(saved={"Office": "office-pass"}))
        svc.forget("Office")
        self.assertNotIn("Office", svc.backend.saved)

    def test_forget_refuses_an_unknown_network(self):
        svc = wifi.WifiService(wifi.FakeWifi())
        with self.assertRaises(ApiError):
            svc.forget("Nope")

    def test_state_reports_the_mode(self):
        self.assertEqual(wifi.WifiService(wifi.FakeWifi(ethernet=True)).state()["mode"], "ethernet")
        self.assertEqual(wifi.WifiService(wifi.FakeWifi(current="Office")).state()["mode"], "wifi")
        self.assertEqual(wifi.WifiService(wifi.FakeWifi()).state()["mode"], "none")
        svc = wifi.WifiService(wifi.FakeWifi())
        svc.backend.hotspot = True
        self.assertEqual(svc.state()["mode"], "hotspot")

    def test_nearby_marks_saved_networks(self):
        svc = wifi.WifiService(wifi.FakeWifi(nearby=NEARBY, saved={"Office": "office-pass"}))
        marks = {n["name"]: n["saved"] for n in svc.nearby()}
        self.assertTrue(marks["Office"])
        self.assertFalse(marks["Home-WiFi"])


class WatcherTests(unittest.TestCase):
    def make(self, **kwargs):
        clock = {"now": 1000.0}
        backend = wifi.FakeWifi(nearby=NEARBY, **kwargs)
        service = wifi.WifiService(backend)
        watcher = wifi.Watcher(service, fallback_seconds=60, clock=lambda: clock["now"])
        watcher.tick()  # the first tick starts the offline timer
        return backend, watcher, clock

    def test_hotspot_starts_only_after_the_fallback_time(self):
        backend, watcher, clock = self.make()
        clock["now"] += 59
        self.assertEqual(watcher.tick(), "none")
        self.assertFalse(backend.hotspot)
        clock["now"] += 1
        self.assertEqual(watcher.tick(), "hotspot")
        self.assertTrue(backend.hotspot)

    def test_hotspot_stops_when_ethernet_comes_back(self):
        backend, watcher, clock = self.make()
        clock["now"] += 60
        watcher.tick()
        backend.ethernet = True
        self.assertEqual(watcher.tick(), "ethernet")
        self.assertFalse(backend.hotspot)

    def test_a_connection_resets_the_offline_timer(self):
        backend, watcher, clock = self.make()
        watcher.tick()
        clock["now"] += 50
        backend.current = "Office"
        watcher.tick()
        backend.current = None
        clock["now"] += 30
        self.assertEqual(watcher.tick(), "none")  # the 30 s count starts again
        self.assertFalse(backend.hotspot)

    def test_hotspot_retries_saved_networks_and_stops_on_success(self):
        backend, watcher, clock = self.make(saved={"Office": "office-pass"})
        clock["now"] += 60
        watcher.tick()
        self.assertTrue(backend.hotspot)
        clock["now"] += wifi.RETRY_SECONDS
        watcher.tick()
        self.assertFalse(backend.hotspot)
        self.assertEqual(backend.current, "Office")


class NmcliOutputTests(unittest.TestCase):
    def test_ethernet_is_connected_only_when_up(self):
        up = "eth0:ethernet:connected:netplan-eth0\nwlan0:wifi:connected:Home\n"
        down = "eth0:ethernet:unavailable:--\nwlan0:wifi:connected:Home\n"
        self.assertTrue(wifi.ethernet_connected(up))
        self.assertFalse(wifi.ethernet_connected(down))

    def test_active_wifi_name(self):
        text = "netplan-wlan0-home:802-11-wireless:wlan0\nlo:loopback:lo\n"
        self.assertEqual(wifi.active_wifi_name(text), "netplan-wlan0-home")
        self.assertIsNone(wifi.active_wifi_name("eth0:802-3-ethernet:eth0\n"))

    def test_saved_wifi_names_skip_the_hotspot_and_other_types(self):
        text = "Home-WiFi:802-11-wireless\ndevice-hotspot:802-11-wireless\nwired:802-3-ethernet\n"
        self.assertEqual(wifi.saved_wifi_names(text), ["Home-WiFi"])

    def test_hotspot_command_uses_the_device_name_and_no_shell(self):
        argv = wifi.hotspot_command("right-password")
        self.assertIn("device", argv)
        self.assertEqual(argv[argv.index("password") + 1], "right-password")
        self.assertTrue(all(isinstance(part, str) for part in argv))

    def test_captive_dns_sends_every_name_to_the_hotspot(self):
        self.assertEqual(wifi.captive_dns_conf().strip(), "address=/#/10.42.0.1")

    def test_hotspot_password_is_read_from_the_root_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hotspot.env"
            path.write_text('HOTSPOT_PASSWORD="hot-spot-pass"\n', encoding="utf-8")
            self.assertEqual(wifi.read_hotspot_password(str(path)), "hot-spot-pass")
            self.assertIsNone(wifi.read_hotspot_password(str(Path(tmp) / "missing")))


if __name__ == "__main__":
    unittest.main()
