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

    def move(self, name, delta):
        """Moves a saved network up (delta -1) or down (delta 1) in the priority order."""
        self.calls.append(("move", name, delta))
        items = list(self.saved.items())
        index = [k for k, _ in items].index(name)
        target = index + delta
        if 0 <= target < len(items):
            items[index], items[target] = items[target], items[index]
        self.saved = dict(items)

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


HOTSPOT_CON = "device-hotspot"       # the connection NetworkManager makes for the hotspot
DNS_CAPTIVE_CONF = "/etc/NetworkManager/dnsmasq-shared.d/dac-captive.conf"
HOTSPOT_PASSWORD_FILE = "/etc/spotify-dac/hotspot.env"


def ethernet_connected(text):
    """True when an ethernet device is connected. Input: `nmcli -t -f DEVICE,TYPE,STATE device`."""
    for line in text.splitlines():
        fields = _split_escaped(line)
        if len(fields) >= 3 and fields[1] == "ethernet" and fields[2].startswith("connected"):
            return True
    return False


def active_wifi_name(text):
    """The name of the active Wi-Fi connection, or None. Input: `nmcli -t -f NAME,TYPE,DEVICE connection show --active`."""
    for line in text.splitlines():
        fields = _split_escaped(line)
        if len(fields) >= 3 and fields[1] == "802-11-wireless" and fields[2] not in ("", "--"):
            return fields[0]
    return None


def saved_wifi_names(text):
    """Saved Wi-Fi connection names, without the hotspot. Input: `nmcli -t -f NAME,TYPE connection show`."""
    names = []
    for line in text.splitlines():
        fields = _split_escaped(line)
        if len(fields) >= 2 and fields[1] == "802-11-wireless" and fields[0] != HOTSPOT_CON:
            names.append(fields[0])
    return names


def hotspot_command(password):
    """The nmcli command that starts the device hotspot. NetworkManager runs the DHCP and DNS for it."""
    return ["device", "wifi", "hotspot", "ifname", "wlan0", "con-name", HOTSPOT_CON,
            "ssid", HOTSPOT_NAME, "password", password]


def captive_dns_conf():
    """dnsmasq setting: every name resolves to the hotspot address, so any web address opens the setup page."""
    return "address=/#/10.42.0.1\n"


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
        connection = self._connection_for(name)
        if connection:
            self._run(["connection", "delete", connection])

    def start_hotspot(self):
        password = read_hotspot_password()
        if not password:
            return False
        rc, _ = self._run(hotspot_command(password))
        return rc == 0

    def stop_hotspot(self):
        self._run(["connection", "down", HOTSPOT_CON])

    # state the watcher reads
    @property
    def ethernet(self):
        rc, out = self._run(["-t", "-f", "DEVICE,TYPE,STATE", "device"])
        return rc == 0 and ethernet_connected(out)

    def _ssid(self, connection):
        """The Wi-Fi name (SSID) of a NetworkManager connection; the connection name is only internal."""
        rc, out = self._run(["-s", "-g", "802-11-wireless.ssid", "connection", "show", connection])
        return out.strip() if rc == 0 and out.strip() else connection

    def _connection_for(self, ssid):
        """The NetworkManager connection that holds this Wi-Fi name, or None."""
        rc, out = self._run(["-t", "-f", "NAME,TYPE", "connection", "show"])
        if rc != 0:
            return None
        for connection in saved_wifi_names(out):
            if self._ssid(connection) == ssid:
                return connection
        return None

    @property
    def current(self):
        rc, out = self._run(["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"])
        connection = active_wifi_name(out) if rc == 0 else None
        return self._ssid(connection) if connection else None

    @property
    def hotspot(self):
        rc, out = self._run(["-t", "-f", "NAME", "connection", "show", "--active"])
        return rc == 0 and HOTSPOT_CON in out.splitlines()

    @property
    def saved(self):
        """Saved Wi-Fi networks with their passwords, highest priority first. Read as root."""
        rc, out = self._run(["-t", "-f", "NAME,TYPE", "connection", "show"])
        if rc != 0:
            return {}
        found = []
        for connection in saved_wifi_names(out):
            rc, psk = self._run(["-s", "-g", "802-11-wireless-security.psk", "connection", "show", connection])
            rc2, prio = self._run(["-g", "connection.autoconnect-priority", "connection", "show", connection])
            priority = int(prio) if rc2 == 0 and prio.lstrip("-").isdigit() else 0
            found.append((-priority, self._ssid(connection), psk if rc == 0 and psk else None))
        found.sort(key=lambda item: item[0])
        return {ssid: psk for _, ssid, psk in found}

    def move(self, name, delta):
        """Swaps the priority of a saved network with its neighbour, and writes the new priorities to NetworkManager."""
        order = list(self.saved.keys())
        if name not in order:
            return
        index = order.index(name)
        target = index + delta
        if not 0 <= target < len(order):
            return
        order[index], order[target] = order[target], order[index]
        for position, ssid in enumerate(order):
            connection = self._connection_for(ssid)
            if connection:
                self._run(["connection", "modify", connection, "connection.autoconnect-priority", str(100 - 10 * position)])


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

    def move(self, name, direction):
        """Priority: "up" makes a saved network more preferred, "down" less preferred."""
        if direction not in ("up", "down"):
            raise ApiError(400, "direction must be up or down")
        if name not in self.backend.saved:
            raise ApiError(404, "That network is not saved")
        self.backend.move(name, -1 if direction == "up" else 1)
        return {"saved": list(self.backend.saved)}

    def switch(self, name):
        """Connects now to a saved network. If its password is not accepted, goes back to the previous one."""
        if name not in self.backend.saved:
            raise ApiError(404, "That network is not saved")
        previous = self.backend.current
        if self.backend.connect(name, self.backend.saved[name]):
            if self.backend.hotspot:
                self.backend.stop_hotspot()
            return {"ok": True, "current": name}
        if previous and previous != name:
            self.backend.connect(previous, self.backend.saved.get(previous))
        return {"ok": False, "current": self.backend.current,
                "error": "Could not connect to " + name + ". Still on " + (self.backend.current or "nothing") + "."}

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
        self.forced = False  # True when the reset button asked for the hotspot: it stays on until a network is saved

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
        elif mode in ("ethernet", "wifi") and backend.hotspot and not self.forced:
            backend.stop_hotspot()
            self.last_retry = None
        elif backend.hotspot and self.last_retry is not None and now - self.last_retry >= RETRY_SECONDS:
            self.last_retry = now
            self.retry_saved()
        if not backend.hotspot:
            self.forced = False
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


def post_move(req):
    body = req.json()
    return 200, _service.move(body.get("name", ""), body.get("direction", ""))


def post_switch(req):
    result = _service.switch(req.json().get("name", ""))
    return (200 if result["ok"] else 422), result


def read_hotspot_password(path=HOTSPOT_PASSWORD_FILE):
    """The hotspot password from the root-only file written by the installer, or None."""
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("HOTSPOT_PASSWORD="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return None
    return None


def parse_fallback(value):
    """The installer and Settings use this for HOTSPOT_FALLBACK_SECONDS (60 to 300 seconds)."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Fallback time must be a whole number of seconds")
    if not valid_fallback(seconds):
        raise ApiError(400, "Fallback time must be 60 to 300 seconds")
    return seconds

