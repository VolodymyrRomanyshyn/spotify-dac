"""Hardware settings: the audio output and the case and fan GPIO pins.

Saved to /etc/spotify-dac/config and applied by restarting the service that uses them. The
power-enable pin is not editable here: it is written into the boot config by the installer.
"""
import pwd
import re

from .common import SOLOIST_USER, ApiError, read_config, run, write_config

HAT_PINS = {2, 3, 18, 19, 20, 21}
DEFAULT_PINS = {"POWER_PIN": 3, "RESET_PIN": 2, "LED_PIN": 14, "FAN_PIN": 21}
SINK = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
CASES = ("nespi", "none")
POWEROFF = ("hardcut", "graceful")


def _sinks():
    """Playback devices in the soloist session (PipeWire): [{name, label}], without the onboard output."""
    uid = pwd.getpwnam(SOLOIST_USER).pw_uid
    env = ["runuser", "-u", SOLOIST_USER, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}"]
    rc, out, _ = run(env + ["pactl", "list", "sinks"], timeout=10)
    if rc != 0:
        return []
    sinks = []
    name = None
    for line in out.splitlines():
        text = line.strip()
        if text.startswith("Name:"):
            name = text.split(":", 1)[1].strip()
        elif text.startswith("Description:") and name:
            label = text.split(":", 1)[1].strip()
            if "mailbox" not in name:
                sinks.append({"name": name, "label": label})
            name = None
    return sinks


def _selected(sinks, pattern):
    match = next((s["name"] for s in sinks if s["name"].startswith(pattern)), None)
    return match


def _pin(cfg, key):
    try:
        return int(cfg.get(key, DEFAULT_PINS[key]))
    except ValueError:
        return DEFAULT_PINS[key]


def get_hardware(req):
    cfg = read_config()
    sinks = _sinks()
    pattern = cfg.get("DAC_SINK_PATTERN", "alsa_output.usb-")
    return 200, {
        "audio": {"sinks": sinks, "selected": _selected(sinks, pattern), "pattern": pattern},
        "case": cfg.get("CASE", "none"),
        "poweroff": cfg.get("POWEROFF_MODE", "hardcut"),
        "pins": {key: _pin(cfg, key) for key in ("POWER_PIN", "RESET_PIN", "LED_PIN")},
        "power_enable_pin": int(cfg.get("POWER_EN_PIN") or 4),
        "fan": {"enabled": cfg.get("FAN_ENABLED") == "yes", "pin": _pin(cfg, "FAN_PIN")},
        "hat": cfg.get("AUDIO_OUTPUT") == "hat",
        "hat_pins": sorted(HAT_PINS) if cfg.get("AUDIO_OUTPUT") == "hat" else [],
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

    if "sink" in body:
        sink = body["sink"]
        if not isinstance(sink, str) or not SINK.match(sink) or sink not in [s["name"] for s in _sinks()]:
            raise ApiError(400, "pick one of the audio devices listed")
        updates["DAC_SINK_PATTERN"] = sink
    if "case" in body:
        if body["case"] not in CASES:
            raise ApiError(400, "case must be nespi or none")
        updates["CASE"] = body["case"]
    if "poweroff" in body:
        if body["poweroff"] not in POWEROFF:
            raise ApiError(400, "power-off mode must be hardcut or graceful")
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
    if "DAC_SINK_PATTERN" in changed:
        run(["systemctl", "restart", "spotify-dac-volume.service"], timeout=60)
        restarted.append("spotify-dac-volume")
    return 200, {"saved": sorted(updates), "restarted": restarted}
