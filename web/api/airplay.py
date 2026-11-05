"""AirPlay receiver (shairport-sync, a systemd service running as the soloist user): status and on/off."""
import pwd

from .common import SOLOIST_USER, read_config, run

UNIT = "spotify-dac-airplay.service"


def service_state():
    _, enabled, _ = run(["systemctl", "is-enabled", UNIT], timeout=10)
    _, active, _ = run(["systemctl", "is-active", UNIT], timeout=10)
    return enabled.strip(), active.strip()


def playing():
    """True while an Apple device streams into the DAC (the stream belongs to shairport-sync and is not corked)."""
    try:
        uid = pwd.getpwnam(SOLOIST_USER).pw_uid
    except KeyError:
        return False
    env = ["runuser", "-u", SOLOIST_USER, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}",
           "pactl", "list", "sink-inputs"]
    rc, out, _ = run(env, timeout=10)
    if rc != 0:
        return False
    return any("shairport" in block.lower() and "Corked: no" in block for block in out.split("Sink Input #")[1:])


def set_enabled(on):
    """Starts the receiver and enables it at boot, or stops it and keeps it off."""
    if on:
        run(["systemctl", "enable", "--now", UNIT], timeout=60)
        return "AirPlay on"
    run(["systemctl", "disable", "--now", UNIT], timeout=60)
    return "AirPlay off"


def get_airplay(req):
    cfg = read_config()
    enabled, active = service_state()
    return 200, {
        "enabled": cfg.get("AIRPLAY_ENABLED") == "yes",
        "service_enabled": enabled,
        "active": active == "active",
        "playing": playing() if active == "active" else False,
        "name": (cfg.get("DEVICE_NAME") or "DAC") + " AirPlay",
    }
