"""Config page: read the settings, change the simple ones, restart services.

Only the keys in EDITABLE can be changed here. Hardware (pins, case, sound card) is not editable;
those go through the installer. The API key is not in the config file and is never returned.
"""
import re

from .common import ApiError, feature_on, read_config, run, write_config

NAME = re.compile(r"^[A-Za-z0-9 _+\-]{1,32}$")
# button colours: name -> (light theme, dark theme)
ACCENTS = {
    "blue": ("#2f6fed", "#7aa7ff"),
    "green": ("#1f8f4e", "#3ddc84"),
    "amber": ("#b7791f", "#f5b041"),
    "red": ("#c53030", "#ff7b7b"),
    "violet": ("#6b46c1", "#b98cff"),
    "teal": ("#0f8a86", "#4fd1c5"),
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


EDITABLE = {
    "DEVICE_NAME": (_name, "1-32 characters: letters, digits, space, - _ +"),
    "SOLOIST_UPDATE_AFTER_DAYS": (_int_between(1, 89), "whole number 1-89"),
    "APT_UPGRADE_AFTER_DAYS": (_int_between(0, 365), "whole number 0-365"),
    "DEFAULT_VOLUME": (_int_between(0, 100), "whole number 0-100 (used until a level is set)"),
    "ACCENT_COLOR": (_accent, "blue, green, amber, red, violet or teal"),
}


def get_config(req):
    return 200, {"values": read_config(), "editable": {k: hint for k, (_, hint) in EDITABLE.items()}}


def get_device(req):
    """The name shown in the page header (the Spotify Connect device name)."""
    cfg = read_config()
    light, dark = ACCENTS.get(cfg.get("ACCENT_COLOR"), ACCENTS["blue"])
    return 200, {"name": cfg.get("DEVICE_NAME") or "DAC", "accent_light": light, "accent_dark": dark}


def post_config(req):
    body = req.json()
    if not body:
        raise ApiError(400, "nothing to save")
    updates = {}
    errors = {}
    for key, value in body.items():
        if key not in EDITABLE:
            raise ApiError(400, f"{key} can't be changed here")
        check, hint = EDITABLE[key]
        try:
            updates[key] = check(value)
        except (ValueError, TypeError):
            errors[key] = hint
    if errors:
        raise ApiError(400, "; ".join(f"{k}: {v}" for k, v in errors.items()))
    write_config(updates)
    restart = ["soloist"] if "DEVICE_NAME" in updates else []
    return 200, {"saved": sorted(updates), "restart": restart}


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
