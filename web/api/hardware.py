"""Hardware settings: the case and fan GPIO pins.

Saved to /etc/spotify-dac/config and applied by restarting the service that uses them. The
power-enable pin is not editable here: it is written into the boot config by the installer.
"""
from .common import ApiError, read_config, run, write_config

HAT_PINS = {2, 3, 18, 19, 20, 21}
DEFAULT_PINS = {"POWER_PIN": 3, "RESET_PIN": 2, "LED_PIN": 14, "FAN_PIN": 21}
CASES = ("nespi", "none")
POWEROFF = ("hardcut",)


def _pin(cfg, key):
    try:
        return int(cfg.get(key, DEFAULT_PINS[key]))
    except ValueError:
        return DEFAULT_PINS[key]


def get_hardware(req):
    cfg = read_config()
    hat = cfg.get("AUDIO_OUTPUT") == "hat"
    return 200, {
        "case": cfg.get("CASE", "none"),
        "poweroff": cfg.get("POWEROFF_MODE", "hardcut"),
        "pins": {key: _pin(cfg, key) for key in ("POWER_PIN", "RESET_PIN", "LED_PIN")},
        "power_enable_pin": int(cfg.get("POWER_EN_PIN") or 4),
        "fan": {"enabled": cfg.get("FAN_ENABLED") == "yes", "pin": _pin(cfg, "FAN_PIN")},
        "hat": hat,
        "hat_pins": sorted(HAT_PINS) if hat else [],
    }


def _pin_value(value, label):
    if isinstance(value, bool):
        raise ApiError(400, f"{label}: whole GPIO number 0-27")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{label}: whole GPIO number 0-27")
    if not 0 <= number <= 27:
        raise ApiError(400, f"{label}: whole GPIO number 0-27")
    return number


def post_hardware(req):
    body = req.json()
    if not body:
        raise ApiError(400, "nothing to save")
    cfg = read_config()
    updates = {}

    if "case" in body:
        if body["case"] not in CASES:
            raise ApiError(400, "case must be nespi or none")
        updates["CASE"] = body["case"]
    if "poweroff" in body:
        if body["poweroff"] not in POWEROFF:
            raise ApiError(400, "power-off mode must be hardcut")
        updates["POWEROFF_MODE"] = body["poweroff"]
    if "fan_enabled" in body:
        if not isinstance(body["fan_enabled"], bool):
            raise ApiError(400, "fan_enabled must be true or false")
        updates["FAN_ENABLED"] = "yes" if body["fan_enabled"] else "no"
    labels = {"POWER_PIN": "power switch", "RESET_PIN": "reset button", "LED_PIN": "case LED", "FAN_PIN": "fan"}
    for key, label in labels.items():
        if key.lower() in body:
            updates[key] = str(_pin_value(body[key.lower()], label))

    # the pins that are in use after this change must be different and must not be HAT pins
    merged = dict(cfg, **updates)
    used = []
    if merged.get("CASE") == "nespi":
        used += [("power switch", _pin(merged, "POWER_PIN")), ("reset button", _pin(merged, "RESET_PIN")),
                 ("case LED", _pin(merged, "LED_PIN")), ("power enable", int(merged.get("POWER_EN_PIN", "4")))]
    if merged.get("FAN_ENABLED") == "yes":
        used.append(("fan", _pin(merged, "FAN_PIN")))
    seen = {}
    for label, pin in used:
        if merged.get("AUDIO_OUTPUT") == "hat" and pin in HAT_PINS:
            raise ApiError(400, f"GPIO {pin} is used by the HAT (the {label}); pick another pin")
        if pin in seen:
            raise ApiError(400, f"GPIO {pin} is used for both the {seen[pin]} and the {label}")
        seen[pin] = label

    if not updates:
        return 200, {"saved": [], "restarted": []}
    write_config(updates)
    changed = {key for key in updates if cfg.get(key) != updates[key]}
    restarted = []
    if changed & {"FAN_ENABLED", "FAN_PIN"}:
        if merged.get("FAN_ENABLED") == "yes":
            run(["systemctl", "enable", "nespi-fan.service"], timeout=30)
            run(["systemctl", "restart", "nespi-fan.service"], timeout=30)
            restarted.append("nespi-fan")
        else:
            run(["systemctl", "disable", "--now", "nespi-fan.service"], timeout=30)
            restarted.append("nespi-fan stopped")
    if changed & {"CASE", "POWER_PIN", "RESET_PIN", "LED_PIN", "POWEROFF_MODE"}:
        if merged.get("CASE") == "nespi":
            run(["systemctl", "enable", "nespi-power.service"], timeout=30)
            run(["systemctl", "restart", "nespi-power.service"], timeout=30)
            restarted.append("nespi-power")
        else:
            run(["systemctl", "disable", "--now", "nespi-power.service"], timeout=30)
            restarted.append("nespi-power stopped")
    return 200, {"saved": sorted(updates), "restarted": restarted}
