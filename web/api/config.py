"""Config page: read the settings, change the simple ones, restart services.

Only the keys in EDITABLE can be changed here. Hardware (pins, case, sound card) is not editable;
those go through the installer. The API key is not in the config file and is never returned.
"""
import re

from .common import ApiError, read_config, run, write_config

NAME = re.compile(r"^[A-Za-z0-9 _+\-]{1,32}$")
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


EDITABLE = {
    "DEVICE_NAME": (_name, "1-32 characters: letters, digits, space, - _ +"),
    "SOLOIST_UPDATE_AFTER_DAYS": (_int_between(1, 89), "whole number 1-89"),
    "APT_UPGRADE_AFTER_DAYS": (_int_between(0, 365), "whole number 0-365"),
    "DEFAULT_VOLUME": (_int_between(0, 100), "whole number 0-100 (used until a level is set)"),
}


def get_config(req):
    return 200, {"values": read_config(), "editable": {k: hint for k, (_, hint) in EDITABLE.items()}}


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
