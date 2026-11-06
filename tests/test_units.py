"""Unit tests for the web API checks and the config file writer. No Pi needed: python3 -m unittest discover -s tests"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# the config and secret files live in a temporary folder during the tests
_TMP = tempfile.mkdtemp(prefix="dac-tests-")
os.environ["SPOTIFY_DAC_CONFIG"] = str(Path(_TMP) / "config")
os.environ["SPOTIFY_DAC_SECRET"] = str(Path(_TMP) / "soloist.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from api import auth, common, config  # noqa: E402
from api import radio  # noqa: E402
from api.common import ApiError  # noqa: E402


class DeviceNameTests(unittest.TestCase):
    def test_accepts_plain_names(self):
        self.assertEqual(config._name("Living Room"), "Living Room")
        self.assertEqual(config._name("RPI-PI-DAC+"), "RPI-PI-DAC+")

    def test_rejects_names_that_break_the_config_file(self):
        for bad in ["Kitchen\n", 'a"b', "a$b", "", "x" * 40, "tab\there"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    config._name(bad)


class ApiKeyTests(unittest.TestCase):
    def test_key_must_match_the_whole_value(self):
        self.assertIsNotNone(config.KEY.fullmatch("abcdefgh12345"))
        self.assertIsNone(config.KEY.fullmatch("abcdefgh\n"))
        self.assertIsNone(config.KEY.fullmatch('abc"defgh'))

    def test_key_file_is_private(self):
        config._save_api_key("abcdefgh12345")
        mode = stat.S_IMODE(os.stat(config.SECRET_FILE).st_mode)
        self.assertEqual(mode, 0o640)
        self.assertIn('SOLOIST_API_KEY="abcdefgh12345"', config.SECRET_FILE.read_text())
        self.assertTrue(config.api_key_set())


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        common.CONFIG_FILE.write_text('DEVICE_NAME="Old"\nCASE="nespi"\n', encoding="utf-8")

    def test_changes_one_key_and_keeps_the_rest(self):
        common.write_config({"DEVICE_NAME": "Kitchen"})
        lines = common.CONFIG_FILE.read_text().splitlines()
        self.assertIn('DEVICE_NAME="Kitchen"', lines)
        self.assertIn('CASE="nespi"', lines)
        self.assertEqual(len(lines), 2)

    def test_adds_a_new_key(self):
        common.write_config({"DEFAULT_VOLUME": "30"})
        self.assertIn('DEFAULT_VOLUME="30"', common.CONFIG_FILE.read_text().splitlines())

    def test_refuses_values_bash_would_misread(self):
        for bad in ['a"b', "a$b", "a`b", "a\nb", "a\\b"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ApiError):
                    common.write_config({"DEVICE_NAME": bad})
        self.assertEqual(common.CONFIG_FILE.read_text(), 'DEVICE_NAME="Old"\nCASE="nespi"\n')

    def test_round_trip_reads_back_the_same_value(self):
        common.write_config({"DEVICE_NAME": "Living Room 2"})
        self.assertEqual(common.read_config()["DEVICE_NAME"], "Living Room 2")


class PasswordTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(__import__("hashlib"), "scrypt"), "needs a Python built with scrypt (the Pi has it)")
    def test_correct_password_passes(self):
        stored = auth.hash_password("correct horse")
        self.assertTrue(auth.check_password("correct horse", stored))
        self.assertFalse(auth.check_password("wrong", stored))

    def test_damaged_salt_fails_cleanly(self):
        self.assertFalse(auth.check_password("pw", "scrypt$zz$00"))
        self.assertFalse(auth.check_password("pw", "garbage"))


class RadioImportTests(unittest.TestCase):
    def test_radio_module_imports_without_the_soloist_user(self):
        self.assertIn("spotify-dac-mpv.sock", str(radio._mpv_socket()))


class WatcherLogTests(unittest.TestCase):
    def test_repeating_error_logs_one_traceback_then_one_line(self):
        import contextlib
        import io
        from api import radio

        class Stop(BaseException):  # not an Exception, so the watcher's own handler cannot catch it
            pass

        sleeps = []

        def fake_sleep(_):
            sleeps.append(1)
            if len(sleeps) > 3:
                raise Stop()

        def failing_check():
            raise RuntimeError("soloist did not answer")

        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.object(radio.time, "sleep", fake_sleep), \
                unittest.mock.patch.object(radio, "feature_on", lambda name: name == "spotify"), \
                unittest.mock.patch.object(radio, "_spotify_playing", failing_check), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(Stop):
                radio.watch_sources(interval=0)
        self.assertEqual(err.getvalue().count("Traceback"), 1)
        self.assertEqual(out.getvalue().count("watcher: same error again"), 2)


class StationCheckTests(unittest.TestCase):
    def good(self, **changes):
        item = {"id": "rmf-on", "name": "RMF ON", "url": "https://example.com/stream", "logo": "", "fallback": []}
        item.update(changes)
        return item

    def test_accepts_a_good_station(self):
        from api import radio
        cleaned = radio._check_station(self.good(genre="News"))
        self.assertEqual(cleaned["id"], "rmf-on")
        self.assertEqual(cleaned["genre"], "News")

    def test_accepts_a_local_logo_and_backup_addresses(self):
        from api import radio
        cleaned = radio._check_station(self.good(logo="/logos/rmf.png", fallback=["http://a.example/s"]))
        self.assertEqual(cleaned["logo"], "/logos/rmf.png")
        self.assertEqual(cleaned["fallback"], ["http://a.example/s"])

    def test_rejects_bad_records(self):
        from api import radio
        bad = [
            "not an object",
            self.good(id="Bad Id"),
            self.good(id="../x"),
            self.good(name=""),
            self.good(name="x" * 61),
            self.good(url="ftp://example.com/s"),
            self.good(url="https://example.com/" + "a" * 500),
            self.good(logo="file:///etc/passwd"),
            self.good(logo="/logos/../secret.png"),
            self.good(fallback=["ftp://example.com/s"]),
            self.good(fallback=["https://example.com/s"] * 11),
        ]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(ApiError):
                    radio._check_station(item)


class StationSaveTests(unittest.TestCase):
    def test_duplicate_ids_are_refused_and_nothing_is_written(self):
        from api import radio

        class Req:
            body = (
                b'[{"id": "a", "name": "A", "url": "https://x.example/a"},'
                b' {"id": "a", "name": "B", "url": "https://x.example/b"}]'
            )

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "radio.json"
            with unittest.mock.patch.object(radio, "STATIONS_FILE", target):
                with self.assertRaises(ApiError):
                    radio.put_stations(Req())
            self.assertFalse(target.exists())

    def test_valid_list_is_saved_and_the_old_file_backed_up(self):
        from api import radio

        class Req:
            body = b'[{"id": "a", "name": "A", "url": "https://x.example/a"}]'

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "radio.json"
            target.write_text("[]", encoding="utf-8")
            with unittest.mock.patch.object(radio, "STATIONS_FILE", target):
                status, _ = radio.put_stations(Req())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))[0]["id"], "a")
            backups = list(Path(tmp).glob("radio.json.bak-*"))
            self.assertEqual(len(backups), 1)


class ConfigValueTests(unittest.TestCase):
    def check(self, key, value):
        validator, _ = config.EDITABLE[key]
        return validator(value)

    def test_whole_number_ranges(self):
        self.assertEqual(self.check("DEFAULT_VOLUME", 30), "30")
        self.assertEqual(self.check("DEFAULT_VOLUME", "0"), "0")
        for bad in [101, -1, "abc", True, 2.5]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.check("DEFAULT_VOLUME", bad)

    def test_yes_no_and_accent(self):
        self.assertEqual(self.check("AIRPLAY_ENABLED", "yes"), "yes")
        with self.assertRaises(ValueError):
            self.check("AIRPLAY_ENABLED", "true")
        self.assertEqual(self.check("ACCENT_COLOR", "teal"), "teal")
        with self.assertRaises(ValueError):
            self.check("ACCENT_COLOR", "pink")


class BootConfigTests(unittest.TestCase):
    """Runs lib/common.sh's bootcfg_set_block in bash on a temporary config.txt.
    Needs GNU sed and sha256sum (the Pi has both; macOS does not), so it is skipped elsewhere."""

    LIB = Path(__file__).resolve().parents[1] / "lib" / "common.sh"

    def setUp(self):
        if not shutil.which("sha256sum") or not shutil.which("bash"):
            self.skipTest("needs sha256sum and bash")
        probe = subprocess.run(["sed", "--version"], capture_output=True, text=True)
        if probe.returncode != 0:
            self.skipTest("needs GNU sed")
        self.tmp = tempfile.mkdtemp(prefix="dac-boot-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = Path(self.tmp) / "config.txt"
        self.cfg.write_text("[pi4]\narm_boost=1\n", encoding="utf-8")

    def run_block(self, block):
        script = (
            f'. "{self.LIB}"\n'
            f'boot_config_path() {{ echo "{self.cfg}"; }}\n'
            f'bootcfg_set_block "{block}"\n'
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.strip()

    def test_adds_replaces_and_removes_one_managed_block(self):
        self.assertEqual(self.run_block("dtparam=audio=off"), "changed")
        text = self.cfg.read_text(encoding="utf-8")
        self.assertEqual(text.count("dtparam=audio=off"), 1)
        self.assertIn("arm_boost=1", text)
        self.assertEqual(self.run_block("dtparam=audio=off"), "")  # same content: no change reported
        self.assertEqual(self.run_block("dtoverlay=gpio-fan"), "changed")
        text = self.cfg.read_text(encoding="utf-8")
        self.assertNotIn("dtparam=audio=off", text)
        self.assertEqual(text.count("dtoverlay=gpio-fan"), 1)
        self.assertEqual(self.run_block(""), "changed")
        text = self.cfg.read_text(encoding="utf-8")
        self.assertNotIn("spotify-dac", text)
        self.assertIn("arm_boost=1", text)
        self.assertTrue(Path(str(self.cfg) + ".spotify-dac.bak").exists())


if __name__ == "__main__":
    unittest.main()
