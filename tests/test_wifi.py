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


class FakeStore:
    def __init__(self, allowed=True, password="stored-pass1"):
        self.allowed = allowed
        self.password = password
        self.requests = 0

    def get_allowed(self):
        return self.allowed

    def set_allowed(self, on):
        self.allowed = on

    def has_password(self):
        return self.password is not None

    def set_password(self, password):
        self.password = password

    def request_start(self):
        self.requests += 1


class HotspotSettingsTests(unittest.TestCase):
    def service(self, allowed=True, password="stored-pass1"):
        backend = wifi.FakeWifi(nearby=NEARBY)
        store = FakeStore(allowed=allowed, password=password)
        return wifi.WifiService(backend, store=store), store

    def test_turning_on_needs_allowed_and_a_password(self):
        svc, store = self.service(allowed=False)
        with self.assertRaises(ApiError):
            svc.set_hotspot_on(True)
        svc2, _ = self.service(allowed=True, password=None)
        with self.assertRaises(ApiError):
            svc2.set_hotspot_on(True)

    def test_turning_on_asks_the_watcher_to_start_it(self):
        svc, store = self.service()
        svc.set_hotspot_on(True)
        self.assertEqual(store.requests, 1)

    def test_turning_off_stops_it_now(self):
        svc, _ = self.service()
        svc.backend.hotspot = True
        svc.set_hotspot_on(False)
        self.assertFalse(svc.backend.hotspot)

    def test_forbidding_the_hotspot_stops_it(self):
        svc, store = self.service()
        svc.backend.hotspot = True
        svc.set_hotspot_allowed(False)
        self.assertFalse(store.allowed)
        self.assertFalse(svc.backend.hotspot)

    def test_allowing_needs_a_password(self):
        svc, store = self.service(allowed=False, password=None)
        with self.assertRaises(ApiError):
            svc.set_hotspot_allowed(True)
        self.assertFalse(store.allowed)

    def test_password_must_be_8_to_63(self):
        svc, _ = self.service()
        with self.assertRaises(ApiError):
            svc.set_hotspot_password("short")
        svc.set_hotspot_password("new-password-1")
        self.assertEqual(svc.store.password, "new-password-1")

    def test_changing_the_password_restarts_a_running_hotspot(self):
        svc, store = self.service()
        svc.backend.hotspot = True
        svc.set_hotspot_password("new-password-1")
        self.assertEqual(store.requests, 1)

    def test_state_reports_allowed_and_password(self):
        svc, _ = self.service(allowed=False)
        status = svc.state()["hotspot"]
        self.assertFalse(status["allowed"])
        self.assertTrue(status["has_password"])

    def test_watcher_never_starts_a_disallowed_hotspot(self):
        svc, store = self.service(allowed=False)
        clock = {"now": 1000.0}
        watcher = wifi.Watcher(svc, fallback_seconds=60, clock=lambda: clock["now"])
        watcher.tick()
        clock["now"] += 600
        self.assertEqual(watcher.tick(), "disabled")
        self.assertFalse(svc.backend.hotspot)


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

    def test_forced_hotspot_stays_on_while_wifi_is_up(self):
        backend, watcher, clock = self.make(current="Office")
        backend.start_hotspot()
        watcher.forced = True
        clock["now"] += 10
        self.assertEqual(watcher.tick(), "wifi")
        self.assertTrue(backend.hotspot)

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

    def test_hotspot_command_uses_the_given_name_and_no_shell(self):
        argv = wifi.hotspot_command("right-password", "volodymyr-pi-dac-2")
        self.assertEqual(argv[argv.index("ssid") + 1], "volodymyr-pi-dac-2")
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


class ResetButtonTests(unittest.TestCase):
    def setUp(self):
        from api import resetbutton
        self.rb = resetbutton

    def test_quick_press_reboots_on_release(self):
        self.assertEqual(self.rb.reset_action(0.3, still_held=False), "reboot")
        self.assertEqual(self.rb.reset_action(4.9, still_held=False), "reboot")

    def test_hold_is_waiting_until_five_seconds_then_starts_the_hotspot(self):
        self.assertEqual(self.rb.reset_action(4.9, still_held=True), "wait")
        self.assertEqual(self.rb.reset_action(5.0, still_held=True), "hotspot")

    def test_releasing_after_five_seconds_does_not_reboot(self):
        self.assertEqual(self.rb.reset_action(6.0, still_held=False), "none")

    def test_hotspot_led_is_two_flashes_and_a_pause(self):
        self.assertEqual(self.rb.LED_HOTSPOT_ON, [(0.1, 0.1), (0.1, 0.7)])


class CaptiveRoutingTests(unittest.TestCase):
    def setUp(self):
        from api import captive
        self.captive = captive

    def test_setup_page_and_its_files_are_served(self):
        self.assertEqual(self.captive.decide("GET", "/"), ("file", "/network.html"))
        self.assertEqual(self.captive.decide("GET", "/network.html"), ("file", "/network.html"))
        self.assertEqual(self.captive.decide("GET", "/style.css"), ("file", "/style.css"))

    def test_wifi_api_is_served(self):
        self.assertEqual(self.captive.decide("POST", "/api/network/save"), ("api", None))
        self.assertEqual(self.captive.decide("GET", "/api/network"), ("api", None))
        self.assertEqual(self.captive.decide("POST", "/api/network/hotspot"), ("api", None))
        self.assertEqual(self.captive.decide("POST", "/api/network/hotspot-password"), ("api", None))

    def test_port_80_and_port_8443_serve_the_same_wi_fi_routes(self):
        from api import wifi
        self.assertIs(self.captive.API_ROUTES, wifi.ROUTES)

    def test_anything_else_redirects_to_the_setup_page(self):
        self.assertEqual(self.captive.decide("GET", "/settings.html"), ("redirect", "http://10.42.0.1/network.html"))
        self.assertEqual(self.captive.decide("GET", "/hotspot-detect.html"), ("redirect", "http://10.42.0.1/network.html"))
        self.assertEqual(self.captive.decide("GET", "/api/status"), ("redirect", "http://10.42.0.1/network.html"))
        self.assertEqual(self.captive.decide("DELETE", "/api/network"), ("redirect", "http://10.42.0.1/network.html"))


class PriorityAndSwitchTests(unittest.TestCase):
    def service(self, current=None):
        backend = wifi.FakeWifi(nearby=NEARBY, saved={"Home-WiFi": "home-pass12", "Office": "office-pass"}, current=current)
        return wifi.WifiService(backend)

    def test_move_up_makes_a_network_preferred(self):
        svc = self.service()
        svc.move("Office", "up")
        self.assertEqual(list(svc.backend.saved), ["Office", "Home-WiFi"])

    def test_move_down_lowers_a_network(self):
        svc = self.service()
        svc.move("Home-WiFi", "down")
        self.assertEqual(list(svc.backend.saved), ["Office", "Home-WiFi"])

    def test_move_at_the_edge_changes_nothing(self):
        svc = self.service()
        svc.move("Home-WiFi", "up")
        self.assertEqual(list(svc.backend.saved), ["Home-WiFi", "Office"])

    def test_move_rejects_bad_direction_and_unknown_network(self):
        svc = self.service()
        with self.assertRaises(ApiError):
            svc.move("Office", "sideways")
        with self.assertRaises(ApiError):
            svc.move("Nope", "up")

    def test_switch_joins_the_chosen_saved_network(self):
        svc = self.service(current="Home-WiFi")
        result = svc.switch("Office")
        self.assertTrue(result["ok"])
        self.assertEqual(svc.backend.current, "Office")

    def test_switch_goes_back_when_the_network_refuses(self):
        svc = self.service(current="Home-WiFi")
        svc.backend.saved["Office"] = "wrong-password"
        result = svc.switch("Office")
        self.assertFalse(result["ok"])
        self.assertEqual(svc.backend.current, "Home-WiFi")

    def test_switch_refuses_unsaved_networks(self):
        svc = self.service()
        with self.assertRaises(ApiError):
            svc.switch("Cafe Free")


class HotspotNameTests(unittest.TestCase):
    def test_name_is_the_device_name_from_the_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config"
            path.write_text('DEVICE_NAME="volodymyr-pi-dac-2"\nCASE="nespi"\n', encoding="utf-8")
            self.assertEqual(wifi.hotspot_name(str(path)), "volodymyr-pi-dac-2")

    def test_falls_back_to_device_when_missing(self):
        self.assertEqual(wifi.hotspot_name("/nonexistent/config"), "device")

    def test_bad_device_name_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config"
            path.write_text('DEVICE_NAME="%s"\n' % ("x" * 40), encoding="utf-8")
            self.assertEqual(wifi.hotspot_name(str(path)), "device")


class ConnectionListTests(unittest.TestCase):
    def test_keeps_only_wifi_connections_with_their_priority(self):
        text = "Home:802-11-wireless:10\nwired:802-3-ethernet:0\nOffice:802-11-wireless:-5\n"
        names = wifi.parse_wifi_names(text)
        self.assertEqual([n["name"] for n in names], ["Home", "Office"])
        self.assertEqual(names[0]["priority"], 10)
        self.assertEqual(names[1]["priority"], -5)

    def test_name_with_a_colon_is_kept(self):
        self.assertEqual(wifi.parse_wifi_names("Cafe\\:Net:802-11-wireless:0\n")[0]["name"], "Cafe:Net")


class ScanModeTests(unittest.TestCase):
    def test_first_load_uses_the_cached_scan_and_scan_again_rescans(self):
        backend = wifi.FakeWifi(nearby=NEARBY)
        service = wifi.WifiService(backend)
        service.nearby(rescan=False)
        self.assertEqual(backend.calls, ["cached"])
        service.nearby()
        self.assertEqual(backend.calls, ["cached", "rescan"])


if __name__ == "__main__":
    unittest.main()
