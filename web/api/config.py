"""Settings API: read the settings, change them, and restart or stop the services they control.

The keys in EDITABLE can be changed here, plus the Spotify API key (stored in the Soloist secret
file, never returned). Hardware (pins and case) is changed through /api/hardware; the sound
card is chosen by the installer.
"""
import grp
import os
import re
from pathlib import Path

from . import airplay
from .common import systemctl, SOLOIST_USER, ApiError, feature_on, installed, read_config, run, write_config

SECRET_FILE = Path(os.environ.get("SPOTIFY_DAC_SECRET", "/etc/spotify-dac/soloist.env"))
NAME = re.compile(r"[A-Za-z0-9 _+\-]{1,32}")
KEY = re.compile(r'[^\s"\\$`]{8,200}')
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
        if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError  # only whole numbers: 2.5 is not stored as 2
        number = int(value)
        if not low <= number <= high:
            raise ValueError
        return str(number)
    return check


def _name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
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
    "AIRPLAY_ENABLED": (_yesno, "yes or no"),
    "DEVICE_NAME": (_name, "1-32 characters: letters, digits, space, - _ +"),
    "SOLOIST_UPDATE_AFTER_DAYS": (_int_between(1, 89), "whole number 1-89"),
    "APT_UPGRADE_AFTER_DAYS": (_int_between(0, 365), "0 = every time updates run; 1-365 = at most once every N days"),
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
    """Writes the key the way the installer does: readable by root and the soloist group only.
    The owner and mode are set before the key is written, so it is never readable by others."""
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_name(SECRET_FILE.name + ".tmp")
    tmp.unlink(missing_ok=True)  # a leftover file would keep its old permissions
    try:
        gid = grp.getgrnam(SOLOIST_USER).gr_gid
    except KeyError:
        gid = 0
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        if os.geteuid() == 0:  # only root can change the owner; the service runs as root
            os.fchown(handle.fileno(), 0, gid)
        handle.write(f'SOLOIST_API_KEY="{key}"\n')
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
    """Starts Soloist and enables it at boot, or stops it and keeps it off. Failures are returned as text."""
    if on:
        ok, detail = systemctl("enable", "--now", "soloist.service")
        return "Spotify on" if ok else f"Spotify did not start: {detail}"
    ok, detail = systemctl("disable", "--now", "soloist.service")
    systemctl("disable", "spotify-dac-boot-update.service")
    return "Spotify off" if ok else f"Spotify did not stop: {detail}"


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
            if isinstance(value, str) and KEY.fullmatch(value.strip()):
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
    for key, source in (("SPOTIFY_ENABLED", "spotify"), ("RADIO_ENABLED", "radio"), ("AIRPLAY_ENABLED", "airplay")):
        if updates.get(key) == "yes" and not installed(source):
            raise ApiError(409, f"{source} is not installed on this device: run sudo bash install.sh to add it")

    spotify = updates.get("SPOTIFY_ENABLED", cfg.get("SPOTIFY_ENABLED", "yes"))
    radio = updates.get("RADIO_ENABLED", cfg.get("RADIO_ENABLED", "yes"))
    air = updates.get("AIRPLAY_ENABLED", cfg.get("AIRPLAY_ENABLED", "no"))
    if spotify == "no" and radio == "no" and air == "no":
        raise ApiError(400, "Turn on Spotify, internet radio or AirPlay: at least one must stay on")

    if updates:
        write_config(updates)
    applied = []
    if updates.get("RADIO_ENABLED") == "no":
        from .radio import stop_playback  # local import: radio is not needed for the other settings
        if stop_playback():
            applied.append("radio stopped")
    if api_key is not None:
        _save_api_key(api_key)
        applied.append("API key saved")
    if "AIRPLAY_ENABLED" in updates:
        applied.append(airplay.set_enabled(air == "yes"))
    if "SPOTIFY_ENABLED" in updates:
        if spotify == "no":
            applied.append(_spotify_on(False))
        elif api_key_set():
            applied.append(_spotify_on(True))
        else:
            applied.append("Spotify on: add the API key to start it")
    elif spotify == "yes" and ("DEVICE_NAME" in updates or api_key is not None) and api_key_set():
        ok, detail = systemctl("restart", "soloist.service")
        applied.append("Spotify restarted" if ok else f"Spotify restart failed: {detail}")
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
    """Which sources this device has: Spotify, internet radio and AirPlay (on and installed), and what is installed."""
    return 200, {
        "spotify": feature_on("spotify"), "radio": feature_on("radio"), "airplay": feature_on("airplay"),
        "installed": {name: installed(name) for name in ("spotify", "radio", "airplay")},
    }
