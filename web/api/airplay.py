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


def set_volume(percent):
    """Sets the volume of the AirPlay stream in the soloist session. True when a stream was found."""
    uid = pwd.getpwnam(SOLOIST_USER).pw_uid
    env = ["runuser", "-u", SOLOIST_USER, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}"]
    rc, out, _ = run(env + ["pactl", "list", "sink-inputs"], timeout=10)
    if rc != 0:
        return False
    changed = False
    for block in out.split("Sink Input #")[1:]:
        index = block.split("\n", 1)[0].strip()
        if index.isdigit() and "shairport" in block.lower():
            rc2, _, _ = run(env + ["pactl", "set-sink-input-volume", index, f"{int(percent)}%"], timeout=10)
            changed = changed or rc2 == 0
    return changed


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
