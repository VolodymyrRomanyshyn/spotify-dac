"""One shared volume level for both sources.

The level is the last value set by either source: the Spotify volume (phone slider or the page) or
the radio volume (radio page or mpv). The watcher in radio.py keeps the stored level in step with
both. Starting a source applies the stored level to it.
"""
import json
import os
import tempfile
from pathlib import Path

from .common import SOLOIST_CTL, ApiError, feature_on, read_config, run

VOLUME_FILE = Path(os.environ.get("SPOTIFY_DAC_VOLUME", "/var/lib/spotify-dac/volume.json"))
FALLBACK_DEFAULT = 25  # used when DEFAULT_VOLUME is not set in the config


def default_level():
    """DEFAULT_VOLUME from the config page (0-100), or 25 when it is not set."""
    try:
        value = int(read_config().get("DEFAULT_VOLUME", FALLBACK_DEFAULT))
    except ValueError:
        return FALLBACK_DEFAULT
    return min(100, max(0, value))


def get_level():
    """The stored level, or None before the first sync (the watcher sets it at start)."""
    try:
        value = int(json.loads(VOLUME_FILE.read_text(encoding="utf-8"))["percent"])
        return min(100, max(0, value))
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return None


def set_level(percent):
    VOLUME_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(VOLUME_FILE.parent), prefix=".volume-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"percent": int(percent)}, handle)
    os.chmod(tmp, 0o644)
    os.replace(tmp, VOLUME_FILE)


def spotify_volume():
    """Soloist's current volume (what the phone slider sets), or None when Soloist doesn't answer."""
    rc, out, _ = run(SOLOIST_CTL + ["now", "--json"], timeout=5)
    if rc != 0:
        return None
    try:
        value = json.loads(out).get("volume")
    except json.JSONDecodeError:
        return None
    return int(round(value)) if isinstance(value, (int, float)) else None


def apply_to_spotify(percent):
    """Set Soloist's volume. Returns False when Soloist does not answer."""
    rc, _, _ = run(SOLOIST_CTL + ["volume", str(int(percent))], timeout=5)
    return rc == 0


def effective_level():
    """The stored shared level, or the default from the config page before any level is stored."""
    level = get_level()
    return level if level is not None else default_level()


def get_volume(req):
    return 200, {"percent": effective_level()}


def post_volume(req):
    value = req.json().get("percent")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ApiError(400, "percent must be a whole number from 0 to 100")
    set_level(value)
    applied = apply_to_spotify(value) if feature_on("spotify") else False
    from .radio import apply_to_radio  # local import: radio imports this module
    apply_to_radio(value)
    return 200, {"percent": value, "spotify_applied": applied}
