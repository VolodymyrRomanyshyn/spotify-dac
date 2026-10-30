"""Internet radio: station list, playback with mpv on the DAC sink, and what is playing.

mpv runs as the `soloist` user, because the PipeWire session that reaches the DAC belongs to that
user. Only one source plays at a time: starting a station pauses Spotify first.
"""
import json
import os
import pwd
import re
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


def _start_mpv(mpv, url, user):
    env = f"XDG_RUNTIME_DIR=/run/user/{user.pw_uid}"
    argv = ["runuser", "-u", SOLOIST_USER, "--", "env", env, mpv, "--no-video", "--really-quiet",
            "--ao=pipewire", f"--input-ipc-server={MPV_SOCKET}", url]
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def post_play(req):
    station_id = req.json().get("id")
    if not isinstance(station_id, str):
        raise ApiError(400, "id is required")
    station = _station(station_id)
    addresses = [station.get("url", "")] + list(station.get("fallback") or [])
    addresses = [u for u in addresses if isinstance(u, str) and urlsplit(u).scheme in ("http", "https")]
    if not addresses:
        raise ApiError(400, "station has no http:// or https:// address")
    mpv = shutil.which("mpv")
    if not mpv:
        raise ApiError(503, "mpv is not installed; the installer adds it with the radio feature")
    user = _soloist_user()
    with _lock:
        _stop_current()
        run(SOLOIST_CTL + ["pause"])  # ignore the answer: Spotify may already be paused
        played = None
        for url in addresses:
            proc = _start_mpv(mpv, url, user)
            time.sleep(4)  # mpv exits quickly when the address does not answer
            if proc.poll() is None:
                played = (proc, url)
                break
        if played is None:
            raise ApiError(502, "no address of this station answers; try again later")
        proc, url = played
        STATE_FILE.write_text(json.dumps({"pid": proc.pid, "station": station_id, "url": url}), encoding="utf-8")
    from .volume import effective_level
    for _ in range(20):  # mpv opens its socket a moment after it starts
        if _mpv_set_volume(effective_level()):
            break
        time.sleep(0.25)
    return 200, {"playing": station_id, "address": url}


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


CATALOG_DIR = Path(os.environ.get("SPOTIFY_DAC_CATALOG", DEFAULT_STATIONS.parent))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _catalog_items():
    items = []
    for path in sorted(CATALOG_DIR.glob("catalog-*.json")):
        try:
            items.extend(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return items


def get_catalog(req):
    """Search the built-in catalogs (RMF ON, Eska). ?q=text matches name or description."""
    query = (req.query.get("q") or "").strip().lower()
    current = load_stations()
    have_ids = {x.get("id") for x in current}
    have_urls = {x.get("url") for x in current}
    results = []
    for item in _catalog_items():
        text = (item.get("name", "") + " " + item.get("description", "")).lower()
        if query and query not in text:
            continue
        results.append({
            "id": item.get("id"), "name": item.get("name"), "description": item.get("description", ""),
            "url": item.get("url"), "logo": item.get("logo", ""), "fallback": item.get("fallback", []),
            "source": item.get("source", ""), "added": item.get("id") in have_ids or item.get("url") in have_urls,
        })
        if len(results) >= 60:
            break
    return 200, {"results": results}


def _check_station(item):
    """Validates one station record. Returns the cleaned record or raises ApiError."""
    if not isinstance(item, dict):
        raise ApiError(400, "each station must be an object")
    station_id = str(item.get("id", "")).strip()
    name = str(item.get("name", "")).strip()
    url = str(item.get("url", "")).strip()
    if not ID_RE.match(station_id):
        raise ApiError(400, f"bad id '{station_id}': use lowercase letters, digits and dashes")
    if not 1 <= len(name) <= 60:
        raise ApiError(400, f"station '{station_id}': name must be 1-60 characters")
    if urlsplit(url).scheme not in ("http", "https") or len(url) > 500:
        raise ApiError(400, f"station '{station_id}': address must start with http:// or https://")
    logo = str(item.get("logo", "") or "").strip()
    if logo and urlsplit(logo).scheme not in ("http", "https"):
        raise ApiError(400, f"station '{station_id}': logo must be an http:// or https:// address")
    fallback = [str(u).strip() for u in (item.get("fallback") or []) if str(u).strip()]
    if len(fallback) > 5 or any(urlsplit(u).scheme not in ("http", "https") for u in fallback):
        raise ApiError(400, f"station '{station_id}': up to 5 backup addresses, each http:// or https://")
    return {"id": station_id, "name": name, "url": url, "genre": str(item.get("genre", "") or "")[:40],
            "logo": logo, "fallback": fallback}


def put_stations(req):
    """Saves the whole station list. The old file is copied to a backup first."""
    try:
        items = json.loads(req.body.decode("utf-8") or "[]")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(400, "body must be a JSON list of stations")
    if not isinstance(items, list) or len(items) > 200:
        raise ApiError(400, "body must be a JSON list of at most 200 stations")
    cleaned = [_check_station(item) for item in items]
    ids = [x["id"] for x in cleaned]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "station ids must be unique")
    target = STATIONS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy(target, target.with_name(target.name + ".bak-" + time.strftime("%Y%m%d%H%M%S")))
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return 200, {"stations": cleaned}
