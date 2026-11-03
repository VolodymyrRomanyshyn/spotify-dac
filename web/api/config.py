"""Settings API: read the settings, change them, and restart or stop the services they control.

The keys in EDITABLE can be changed here, plus the Spotify API key (stored in the Soloist secret
file, never returned). Hardware (pins and case) is changed through /api/hardware; the sound
card is chosen by the installer.
"""
import grp
import os
import re
from pathlib import Path

from .common import SOLOIST_USER, ApiError, feature_on, read_config, run, write_config

SECRET_FILE = Path(os.environ.get("SPOTIFY_DAC_SECRET", "/etc/spotify-dac/soloist.env"))
NAME = re.compile(r"^[A-Za-z0-9 _+\-]{1,32}$")
KEY = re.compile(r'^[^\s"\\$`]{8,200}$')
# button colours: name -> (light theme, dark theme)
ACCENTS = {
    "blue": ("#2f6fed", "#7aa7ff"),
    "green": ("#1f8f4e", "#3ddc84"),
    "amber": ("#b7791f", "#f5b041"),
    "red": ("#c53030", "#ff7b7b"),
    "violet": ("#6b46c1", "#b98cff"),
    "teal": ("#0f8a86", "#4fd1c5"),
    "grey": ("#5b6270", "#9aa1ad"),
}
APPLY_SERVICES = {"soloist", "spotify-dac-volume"}


def _int_between(low, high):
    def check(value):
        if isinstance(value, bool):
            raise ValueError
        number = int(value)
        if not low <= number <= high:
            raise ValueError
        return str(number)
    return check


def _name(value):
    if not isinstance(value, str) or not NAME.match(value):
        raise ValueError
    return value


def _accent(value):
    if value not in ACCENTS:
        raise ValueError
    return value


def _yesno(value):
    if value not in ("yes", "no"):
        raise ValueError
    return value


EDITABLE = {
    "SPOTIFY_ENABLED": (_yesno, "yes or no"),
    "RADIO_ENABLED": (_yesno, "yes or no"),
    "DEVICE_NAME": (_name, "1-32 characters: letters, digits, space, - _ +"),
    "SOLOIST_UPDATE_AFTER_DAYS": (_int_between(1, 89), "whole number 1-89"),
    "APT_UPGRADE_AFTER_DAYS": (_int_between(0, 365), "whole number 0-365"),
    "DEFAULT_VOLUME": (_int_between(0, 100), "whole number 0-100 (used until a level is set)"),
    "ACCENT_COLOR": (_accent, "blue, green, amber, red, violet, teal or grey"),
}


def api_key_set():
    """True when a key is stored. The key itself is never sent to the browser."""
    try:
        text = SECRET_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        if line.startswith("SOLOIST_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"') != ""
    return False


def _save_api_key(key):
    """Writes the key the way the installer does: readable by root and the soloist group only."""
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_name(SECRET_FILE.name + ".tmp")
    tmp.write_text(f'SOLOIST_API_KEY="{key}"\n', encoding="utf-8")
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, 0, grp.getgrnam(SOLOIST_USER).gr_gid)
    except KeyError:
        os.chown(tmp, 0, 0)
    os.replace(tmp, SECRET_FILE)


def get_config(req):
    return 200, {
        "values": read_config(),
        "editable": {k: hint for k, (_, hint) in EDITABLE.items()},
        "api_key_set": api_key_set(),
    }


def get_device(req):
    """The name shown in the page header and the colours used on every page."""
    cfg = read_config()
    light, dark = ACCENTS.get(cfg.get("ACCENT_COLOR"), ACCENTS["blue"])
    return 200, {"name": cfg.get("DEVICE_NAME") or "DAC", "accent_light": light, "accent_dark": dark}


def _spotify_on(on):
    """Starts Soloist and enables it at boot, or stops it and keeps it off."""
    if on:
        run(["systemctl", "enable", "--now", "soloist.service"], timeout=60)
        return "Spotify on"
    run(["systemctl", "disable", "--now", "soloist.service"], timeout=60)
    run(["systemctl", "disable", "spotify-dac-boot-update.service"], timeout=60)
    return "Spotify off"


def post_config(req):
    body = req.json()
    if not body:
        raise ApiError(400, "nothing to save")
    cfg = read_config()
    updates = {}
    errors = {}
    api_key = None
    for key, value in body.items():
        if key == "SOLOIST_API_KEY":
            if isinstance(value, str) and value.strip() == "":
                continue  # an empty field keeps the stored key
            if isinstance(value, str) and KEY.match(value.strip()):
                api_key = value.strip()
            else:
                errors[key] = "8-200 characters, no spaces or quotes"
            continue
        if key not in EDITABLE:
            raise ApiError(400, f"{key} can't be changed here")
        check, hint = EDITABLE[key]
        try:
            updates[key] = check(value)
        except (ValueError, TypeError):
            errors[key] = hint
    if errors:
        raise ApiError(400, "; ".join(f"{k}: {v}" for k, v in errors.items()))

    spotify = updates.get("SPOTIFY_ENABLED", cfg.get("SPOTIFY_ENABLED", "yes"))
    radio = updates.get("RADIO_ENABLED", cfg.get("RADIO_ENABLED", "yes"))
    if spotify == "no" and radio == "no":
        raise ApiError(400, "Turn on Spotify or internet radio: at least one must stay on")

    if updates:
        write_config(updates)
    applied = []
    if api_key is not None:
        _save_api_key(api_key)
        applied.append("API key saved")
    if "SPOTIFY_ENABLED" in updates:
        if spotify == "no":
            applied.append(_spotify_on(False))
        elif api_key_set():
            applied.append(_spotify_on(True))
        else:
            applied.append("Spotify on: add the API key to start it")
    elif spotify == "yes" and ("DEVICE_NAME" in updates or api_key is not None) and api_key_set():
        run(["systemctl", "restart", "soloist.service"], timeout=60)
        applied.append("Spotify restarted")
    return 200, {"saved": sorted(list(updates) + (["SOLOIST_API_KEY"] if api_key else [])), "applied": applied}


def post_apply(req):
    services = req.json().get("services", [])
    if not isinstance(services, list) or not services:
        raise ApiError(400, "services must be a non-empty list")
    results = {}
    for name in services:
        if name not in APPLY_SERVICES:
            raise ApiError(400, f"{name} can't be restarted from the web UI")
        rc, _, err = run(["systemctl", "restart", name], timeout=60)
        results[name] = "restarted" if rc == 0 else (err.strip() or "failed")
    return 200, {"results": results}


def get_features(req):
    """Which parts of the interface this device has: Spotify and internet radio."""
    return 200, {"spotify": feature_on("spotify"), "radio": feature_on("radio")}
