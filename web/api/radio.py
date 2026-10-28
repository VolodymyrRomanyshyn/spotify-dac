"""Internet radio: station list, and playback with mpv on the DAC sink.

Only one source plays at a time: starting a station pauses Spotify first.
"""
import json
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .common import SOLOIST_CTL, ApiError, run

STATIONS_FILE = Path(os.environ.get("SPOTIFY_DAC_RADIO", "/etc/spotify-dac/radio.json"))
DEFAULT_STATIONS = Path(__file__).resolve().parents[2] / "radio" / "stations.default.json"
STATE_FILE = Path(os.environ.get("SPOTIFY_DAC_RADIO_STATE", "/run/spotify-dac-radio.json"))
_lock = threading.Lock()


def load_stations():
    path = STATIONS_FILE if STATIONS_FILE.exists() else DEFAULT_STATIONS
    try:
        stations = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ApiError(500, f"station list is unreadable: {path}")
    return stations


def _station(station_id):
    for station in load_stations():
        if station.get("id") == station_id:
            return station
    raise ApiError(404, "no station with that id")


def _current():
    """The playing station and its mpv process, or None. Removes a stale state file."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        os.kill(state["pid"], 0)
        return state
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        STATE_FILE.unlink(missing_ok=True)
        return None


def _stop_current():
    state = _current()
    if state:
        try:
            os.killpg(state["pid"], signal.SIGTERM)
        except OSError:
            pass
    STATE_FILE.unlink(missing_ok=True)


def get_stations(req):
    state = _current()
    return 200, {"stations": load_stations(), "playing": state["station"] if state else None}


def post_play(req):
    station_id = req.json().get("id")
    if not isinstance(station_id, str):
        raise ApiError(400, "id is required")
    station = _station(station_id)
    url = station.get("url", "")
    if urlsplit(url).scheme not in ("http", "https"):
        raise ApiError(400, "station URL must start with http:// or https://")
    mpv = shutil.which("mpv")
    if not mpv:
        raise ApiError(503, "mpv is not installed; the installer adds it with the radio feature")
    with _lock:
        _stop_current()
        run(SOLOIST_CTL + ["pause"])  # ignore the answer: Spotify may already be paused
        proc = subprocess.Popen(
            [mpv, "--no-video", "--really-quiet", "--ao=pipewire", url],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        STATE_FILE.write_text(json.dumps({"pid": proc.pid, "station": station_id}), encoding="utf-8")
    return 200, {"playing": station_id}


def post_stop(req):
    with _lock:
        _stop_current()
    return 200, {"playing": None}
