"""Unit tests for the web API checks and the config file writer. No Pi needed: python3 -m unittest discover -s tests"""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

# the config and secret files live in a temporary folder during the tests
_TMP = tempfile.mkdtemp(prefix="dac-tests-")
os.environ["SPOTIFY_DAC_CONFIG"] = str(Path(_TMP) / "config")
os.environ["SPOTIFY_DAC_SECRET"] = str(Path(_TMP) / "soloist.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from api import auth, common, config  # noqa: E402
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
        from api import radio
        self.assertIn("spotify-dac-mpv.sock", str(radio._mpv_socket()))


if __name__ == "__main__":
    unittest.main()
