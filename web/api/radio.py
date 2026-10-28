"""Internet radio: station list, playback with mpv on the DAC sink, and what is playing.

mpv runs as the `soloist` user, because the PipeWire session that reaches the DAC belongs to that
user. Only one source plays at a time: starting a station pauses Spotify first.
"""
import json
import os
import pwd
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .common import SOLOIST_CTL, SOLOIST_USER, ApiError, run

STATIONS_FILE = Path(os.environ.get("SPOTIFY_DAC_RADIO", "/etc/spotify-dac/radio.json"))
DEFAULT_STATIONS = Path(__file__).resolve().parents[2] / "radio" / "stations.default.json"
STATE_FILE = Path(os.environ.get("SPOTIFY_DAC_RADIO_STATE", "/run/spotify-dac-radio.json"))
# mpv runs as the soloist user, so its control socket lives in that user's runtime folder
MPV_SOCKET = Path(f"/run/user/{pwd.getpwnam(SOLOIST_USER).pw_uid}/spotify-dac-mpv.sock")
_lock = threading.Lock()


def load_stations():
    path = STATIONS_FILE if STATIONS_FILE.exists() else DEFAULT_STATIONS
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ApiError(500, f"station list is unreadable: {path}")


def _station(station_id):
    for station in load_stations():
        if station.get("id") == station_id:
            return station
    raise ApiError(404, "no station with that id")


def _current():
    """The playing station and its mpv pid, or None. Removes a stale state file."""
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
    MPV_SOCKET.unlink(missing_ok=True)


def _mpv_property(name):
    """Read one property from the running mpv over its IPC socket. None when not available."""
    if not MPV_SOCKET.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(str(MPV_SOCKET))
            sock.sendall(json.dumps({"command": ["get_property", name]}).encode() + b"\n")
            reply = sock.makefile("rb").readline()
        answer = json.loads(reply)
        return answer.get("data") if answer.get("error") == "success" else None
    except (OSError, ValueError):
        return None


def _mpv_set_volume(percent):
    """Set mpv's volume over its IPC socket. Returns False when mpv is not reachable."""
    if not MPV_SOCKET.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(str(MPV_SOCKET))
            sock.sendall(json.dumps({"command": ["set_property", "volume", percent]}).encode() + b"\n")
            return json.loads(sock.makefile("rb").readline()).get("error") == "success"
    except (OSError, ValueError):
        return False


def _mpv_get_volume():
    value = _mpv_property("volume")
    return int(round(value)) if isinstance(value, (int, float)) else None


def apply_to_radio(percent):
    """Apply the shared level to the playing station, if one is playing."""
    if _current():
        return _mpv_set_volume(percent)
    return False


def _soloist_user():
    try:
        pwd.getpwnam(SOLOIST_USER)
    except KeyError:
        raise ApiError(503, f"user '{SOLOIST_USER}' does not exist; the installer creates it")
    return pwd.getpwnam(SOLOIST_USER)


def get_stations(req):
    state = _current()
    return 200, {"stations": load_stations(), "playing": state["station"] if state else None}


def get_now(req):
    state = _current()
    if not state:
        return 200, {"playing": None, "title": None}
    return 200, {"playing": state["station"], "title": _mpv_property("media-title")}


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
    user = _soloist_user()
    with _lock:
        _stop_current()
        run(SOLOIST_CTL + ["pause"])  # ignore the answer: Spotify may already be paused
        env = f"XDG_RUNTIME_DIR=/run/user/{user.pw_uid}"
        argv = ["runuser", "-u", SOLOIST_USER, "--", "env", env, mpv, "--no-video", "--really-quiet",
                "--ao=pipewire", f"--input-ipc-server={MPV_SOCKET}", url]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        STATE_FILE.write_text(json.dumps({"pid": proc.pid, "station": station_id}), encoding="utf-8")
    from .volume import effective_level
    for _ in range(20):  # mpv opens its socket a moment after it starts
        if _mpv_set_volume(effective_level()):
            break
        time.sleep(0.25)
    return 200, {"playing": station_id}


def post_stop(req):
    with _lock:
        _stop_current()
    return 200, {"playing": None}


def _spotify_playing():
    """True while Soloist reports playback (also when started from the Spotify app on a phone)."""
    rc, out, _ = run(SOLOIST_CTL + ["now", "--json"], timeout=5)
    return rc == 0 and '"status":"playing"' in out.replace(" ", "")


def watch_sources(interval=2):
    """Background loop, every few seconds:
    - Spotify starts playing: the radio stops and the shared volume is applied to Spotify.
    - Volume changed on Spotify (phone or page): the shared level follows it, and the radio gets it.
    - Volume changed on the radio: the shared level follows it, and Spotify gets it.
    The first pass only records the current values, so starting the service doesn't change them."""
    from .volume import apply_to_spotify, effective_level, get_level, set_level, spotify_volume
    was_playing = None
    last_spotify = None
    last_radio = None
    while True:
        time.sleep(interval)
        try:
            now_playing = _spotify_playing()
            spotify_now = spotify_volume()
            radio_now = _mpv_get_volume() if _current() else None
            if was_playing is None:  # first pass: record only
                was_playing, last_spotify, last_radio = now_playing, spotify_now, radio_now
                if get_level() is None:
                    set_level(effective_level())  # no level stored yet: start at the default
                continue
            with _lock:
                if now_playing and not was_playing:
                    if _current():
                        _stop_current()
                        print("radio stopped: Spotify started playing", flush=True)
                    apply_to_spotify(effective_level())
                if spotify_now is not None and spotify_now != last_spotify:
                    set_level(spotify_now)
                    if _current():
                        _mpv_set_volume(spotify_now)
                if radio_now is not None and radio_now != last_radio:
                    set_level(radio_now)
                    if spotify_now is not None and spotify_now != radio_now:
                        apply_to_spotify(radio_now)
            was_playing, last_spotify, last_radio = now_playing, spotify_now, radio_now
        except Exception:  # the watcher must never stop the server
            pass
