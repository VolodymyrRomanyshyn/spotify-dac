"""Wi-Fi settings: the current network, saved networks, nearby networks, and the hotspot fallback.

The network work is done by a backend object. Two backends exist:
- NmcliWifi: runs NetworkManager's nmcli on the Pi (used on the device).
- FakeWifi: keeps everything in memory (used by the tests and the mocked prototype).

The decisions (which mode to be in, whether a password is valid, what to do when a connection
fails) live here, so they are tested with FakeWifi and do not need a Pi.
"""
import re
import subprocess
import time

from .common import ApiError

HOTSPOT_NAME = "device"
CONNECT_TIMEOUT = 30          # seconds to wait for a network to accept the password
FALLBACK_MIN, FALLBACK_MAX, FALLBACK_DEFAULT = 60, 300, 60
SSID_MAX = 32
PASSWORD_MIN, PASSWORD_MAX = 8, 63


# ---------- pure rules (no system calls) ----------

def valid_name(name):
    return isinstance(name, str) and 1 <= len(name.strip()) <= SSID_MAX and "\x00" not in name


def valid_password(password):
    return isinstance(password, str) and PASSWORD_MIN <= len(password) <= PASSWORD_MAX


def valid_fallback(seconds):
    return isinstance(seconds, int) and not isinstance(seconds, bool) and FALLBACK_MIN <= seconds <= FALLBACK_MAX


def next_mode(ethernet_up, wifi_up, offline_seconds, fallback_seconds):
    """Which mode the Pi should be in. Ethernet wins; then Wi-Fi; then the hotspot after the fallback time."""
    if ethernet_up:
        return "ethernet"
    if wifi_up:
        return "wifi"
    if offline_seconds >= fallback_seconds:
        return "hotspot"
    return "none"


# ---------- backends ----------

class FakeWifi:
    """In-memory backend. A password is accepted unless it is "wrong-password" (test rule)."""

    def __init__(self, current=None, saved=None, nearby=None, ethernet=False):
        self.current = current                       # name of the joined Wi-Fi, or None
        self.saved = dict(saved or {})               # name -> password (None for open networks)
        self.nearby = list(nearby or [])             # dicts: name, signal, secure
        self.ethernet = ethernet
        self.hotspot = False
        self.calls = []

    def scan(self):
        self.calls.append("scan")
        return list(self.nearby)

    def connect(self, name, password):
        self.calls.append(("connect", name))
        known = {n["name"]: n for n in self.nearby}
        if name not in known:
            return False
        if password == "wrong-password":
            return False
        self.current = name
        self.saved.setdefault(name, password)
        return True

    def disconnect(self):
        self.calls.append("disconnect")
        self.current = None

    def forget(self, name):
        self.calls.append(("forget", name))
        self.saved.pop(name, None)
        if self.current == name:
            self.current = None

    def start_hotspot(self):
        self.calls.append("start_hotspot")
        self.hotspot = True

    def stop_hotspot(self):
        self.calls.append("stop_hotspot")
        self.hotspot = False


_SIGNAL = re.compile(r"^\d{1,3}$")


def parse_scan(text):
    """Parses `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list` output into network dicts."""
    networks = {}
    for line in text.splitlines():
        parts = _split_escaped(line)
        if len(parts) < 3 or not parts[0]:
            continue
        name, signal, security = parts[0], parts[1], parts[2]
        if not _SIGNAL.match(signal):
            continue
        strength = int(signal)
        if name not in networks or strength > networks[name]["signal"]:
            networks[name] = {"name": name, "signal": strength, "secure": security.strip() not in ("", "--")}
    return sorted(networks.values(), key=lambda n: -n["signal"])


def _split_escaped(line):
    """nmcli -t separates fields with ':' and escapes a ':' inside a field as '\\:'."""
    fields, current, escaped = [], "", False
    for ch in line:
        if escaped:
            current += ch
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append(current)
            current = ""
        else:
            current += ch
    fields.append(current)
    return fields


class NmcliWifi:
    """The real backend on the Pi, through NetworkManager's nmcli. Not tested on a Pi yet."""

    def _run(self, args, timeout=60):
        try:
            done = subprocess.run(["nmcli"] + args, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return 1, "timed out"
        return done.returncode, (done.stdout + done.stderr).strip()

    def scan(self):
        rc, out = self._run(["-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"])
        return parse_scan(out) if rc == 0 else []

    def connect(self, name, password):
        args = ["device", "wifi", "connect", name]
        if password:
            args += ["password", password]
        rc, _ = self._run(args, timeout=CONNECT_TIMEOUT)
        return rc == 0

    def disconnect(self):
        self._run(["device", "disconnect", "wlan0"])

    def forget(self, name):
        self._run(["connection", "delete", name])

    def start_hotspot(self):
        self._run(["device", "wifi", "hotspot", "ifname", "wlan0", "ssid", HOTSPOT_NAME])

    def stop_hotspot(self):
        self._run(["connection", "down", "Hotspot"])


# ---------- the service: what the web API does ----------

class WifiService:
    def __init__(self, backend, fallback_seconds=FALLBACK_DEFAULT):
        self.backend = backend
        self.fallback_seconds = fallback_seconds

    def state(self):
        if self.backend.ethernet:
            mode = "ethernet"
        elif self.backend.current is not None:
            mode = "wifi"
        elif self.backend.hotspot:
            mode = "hotspot"
        else:
            mode = "none"
        return {
            "mode": mode,
            "current": self.backend.current,
            "ethernet": self.backend.ethernet,
            "hotspot": {"on": self.backend.hotspot, "name": HOTSPOT_NAME},
            "saved": sorted(self.backend.saved),
        }

    def nearby(self):
        saved = set(self.backend.saved)
        return [dict(n, saved=n["name"] in saved) for n in self.backend.scan()]

    def save(self, name, password):
        """Test the password by connecting. Success: keep the network and stop the hotspot.
        Failure: go back to the previous network, or to the hotspot if there was none."""
        if not valid_name(name):
            raise ApiError(400, "Network name must be 1 to 32 characters")
        nearby = {n["name"]: n for n in self.backend.scan()}
        secure = nearby[name]["secure"] if name in nearby else None
        if secure is None:
            raise ApiError(404, "That network is not in the list. Scan again.")
        if secure and not valid_password(password):
            raise ApiError(400, "Password must be 8 to 63 characters")
        if not secure:
            password = None
        previous = self.backend.current
        if self.backend.connect(name, password):
            if self.backend.hotspot:
                self.backend.stop_hotspot()
            return {"ok": True, "current": name, "mode": "wifi", "hotspot": self.backend.hotspot}
        # the password was not accepted: go back to where we were
        if previous and previous != name:
            self.backend.connect(previous, None)
        if self.backend.current is None:
            self.backend.start_hotspot()
        return {
            "ok": False,
            "error": "Password not accepted. Still on " + (self.backend.current or "the hotspot") + ".",
            "current": self.backend.current,
            "hotspot": self.backend.hotspot,
        }

    def forget(self, name):
        if not valid_name(name):
            raise ApiError(400, "Network name must be 1 to 32 characters")
        if name not in self.backend.saved:
            raise ApiError(404, "That network is not saved")
        self.backend.forget(name)
        return {"forgotten": name}


RETRY_SECONDS = 300  # while in hotspot mode, try the saved networks this often


class Watcher:
    """Called every few seconds: starts the hotspot after the fallback time without a network,
    stops it when a network or cable comes back, and retries the saved networks while it runs."""

    def __init__(self, service, fallback_seconds=FALLBACK_DEFAULT, clock=time.monotonic):
        self.service = service
        self.fallback_seconds = fallback_seconds
        self.clock = clock
        self.offline_since = None
        self.last_retry = None

    def tick(self):
        backend = self.service.backend
        now = self.clock()
        online = backend.ethernet or backend.current is not None
        if online:
            self.offline_since = None
        elif self.offline_since is None:
            self.offline_since = now
        offline = 0 if online else now - self.offline_since
        mode = next_mode(backend.ethernet, backend.current is not None, offline, self.fallback_seconds)
        if mode == "hotspot" and not backend.hotspot:
            backend.start_hotspot()
            self.last_retry = now
        elif mode in ("ethernet", "wifi") and backend.hotspot:
            backend.stop_hotspot()
            self.last_retry = None
        elif backend.hotspot and self.last_retry is not None and now - self.last_retry >= RETRY_SECONDS:
            self.last_retry = now
            self.retry_saved()
        return mode

    def retry_saved(self):
        """Tries each saved network once. The first one that accepts its password ends the hotspot."""
        backend = self.service.backend
        for name, password in list(backend.saved.items()):
            if backend.connect(name, password):
                backend.stop_hotspot()
                return name
        return None


# the service used by the web server; tests create their own with FakeWifi
_service = WifiService(NmcliWifi())


def get_network(req):
    return 200, dict(_service.state(), nearby=_service.nearby())


def post_scan(req):
    return 200, {"nearby": _service.nearby()}


def post_save(req):
    body = req.json()
    result = _service.save(body.get("name", ""), body.get("password"))
    return (200 if result["ok"] else 422), result


def post_forget(req):
    return 200, _service.forget(req.json().get("name", ""))


def parse_fallback(value):
    """The installer and Settings use this for HOTSPOT_FALLBACK_SECONDS (60 to 300 seconds)."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Fallback time must be a whole number of seconds")
    if not valid_fallback(seconds):
        raise ApiError(400, "Fallback time must be 60 to 300 seconds")
    return seconds

