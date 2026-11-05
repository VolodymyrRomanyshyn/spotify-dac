"""AirPlay receiver (shairport-sync, a systemd service running as the soloist user).

Settings decides whether AirPlay is allowed (AIRPLAY_ENABLED). The Home page starts and stops the
receiver. The receiver is never started at boot: the user turns it on from Home.
"""
import pwd

from .common import SOLOIST_CTL, SOLOIST_USER, ApiError, installed, read_config, run

UNIT = "spotify-dac-airplay.service"


def _env():
    uid = pwd.getpwnam(SOLOIST_USER).pw_uid
    return ["runuser", "-u", SOLOIST_USER, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}"]


def is_active():
    _, active, _ = run(["systemctl", "is-active", UNIT], timeout=10)
    return active.strip() == "active"


def playing():
    """True while an Apple device streams into the DAC (the stream belongs to shairport-sync and is not corked)."""
    try:
        env = _env()
    except KeyError:
        return False
    rc, out, _ = run(env + ["pactl", "list", "sink-inputs"], timeout=10)
    if rc != 0:
        return False
    return any("shairport" in block.lower() and "Corked: no" in block for block in out.split("Sink Input #")[1:])


def set_volume(percent):
    """Sets the volume of the AirPlay stream in the soloist session. True when a stream was found."""
    try:
        env = _env()
    except KeyError:
        return False
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
    """Settings: AirPlay allowed or not. Not allowed also stops the receiver."""
    if on:
        return "AirPlay allowed: turn it on from Home"
    run(["systemctl", "stop", UNIT], timeout=60)
    return "AirPlay off"


def get_airplay(req):
    cfg = read_config()
    active = is_active()
    return 200, {
        "installed": installed("airplay"),
        "enabled": cfg.get("AIRPLAY_ENABLED") == "yes",
        "active": active,
        "playing": playing() if active else False,
        "name": (cfg.get("DEVICE_NAME") or "DAC") + " AirPlay",
    }


def post_airplay(req):
    """Home: turn the receiver on (radio and Spotify stop) or off."""
    on = req.json().get("on")
    if not isinstance(on, bool):
        raise ApiError(400, "on must be true or false")
    if on:
        if read_config().get("AIRPLAY_ENABLED") != "yes":
            raise ApiError(409, "AirPlay is not allowed: turn it on in Settings first")
        from .radio import stop_playback  # local import: radio imports this module
        stop_playback()
        run(SOLOIST_CTL + ["pause"], timeout=10)  # Spotify pauses; it may already be paused
        run(["systemctl", "start", UNIT], timeout=60)
    else:
        run(["systemctl", "stop", UNIT], timeout=60)
    return 200, {"active": is_active()}
