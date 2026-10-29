"""Status page: services, Soloist, DAC, power, heat, system and the last update."""
import glob
import os
import pwd
import re
from pathlib import Path

from .common import SOLOIST_CTL, SOLOIST_USER, run

SERVICES = ["soloist", "nespi-power", "nespi-fan", "spotify-dac-volume", "spotify-dac-web"]
UPDATE_LOG = Path("/var/log/spotify-dac-update.log")
THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


# PipeWire and WirePlumber run in the soloist user's session, not as system services
SESSION_SERVICES = ["pipewire", "pipewire-pulse", "wireplumber"]


def _session_service(name):
    """A user service of the soloist session (PipeWire, WirePlumber)."""
    try:
        uid = pwd.getpwnam(SOLOIST_USER).pw_uid
    except KeyError:
        return {"name": name, "enabled": "unknown", "active": "unknown"}
    env = ["sudo", "-n", "runuser", "-u", SOLOIST_USER, "--", "env", f"XDG_RUNTIME_DIR=/run/user/{uid}",
           "systemctl", "--user"]
    _, enabled, _ = run(env + ["is-enabled", name])
    _, active, _ = run(env + ["is-active", name])
    return {"name": name, "enabled": enabled.strip() or "unknown", "active": active.strip() or "unknown"}


def _service(name):
    _, enabled, _ = run(["systemctl", "is-enabled", name])
    _, active, _ = run(["systemctl", "is-active", name])
    return {"name": name, "enabled": enabled.strip(), "active": active.strip()}


def _soloist():
    rc, out, _ = run(["soloist", "--version"])
    version = out.splitlines()[0] if rc == 0 and out.strip() else None
    # `soloist ctl status` reports the local websocket API that the web UI uses
    rc, out, _ = run(SOLOIST_CTL + ["status"], timeout=5)
    api = {"reachable": False, "websocket": None, "logged_in": None, "active_device": None}
    if rc == 0:
        for line in out.splitlines():
            key, _, value = line.strip().partition(":")
            value = value.strip()
            if key == "soloist":
                api["reachable"] = value == "reachable"
            elif key == "ws":
                api["websocket"] = value.replace("listening on ", "") if value else None
            elif key == "logged in":
                api["logged_in"] = value == "yes"
            elif key == "active device":
                api["active_device"] = value == "yes"
    return {"version": version, "api": api}


def _dac():
    """Sound cards (index, name, driver) and the playback streams that are open."""
    cards = []
    try:
        for line in Path("/proc/asound/cards").read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*(\d+) \[(.*?)\s*\]: (\S+)", line)
            if match:
                cards.append({"index": int(match.group(1)), "name": match.group(2), "driver": match.group(3)})
    except OSError:
        pass
    names = {card["index"]: card["name"] for card in cards}
    streams = []
    for path in glob.glob("/proc/asound/card*/pcm*p/sub*/status"):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        card_index = int(re.search(r"card(\d+)", path).group(1))
        state = re.search(r"state: (\w+)", text)
        if state is None and text.strip().startswith("closed"):
            state_name = "closed"
        else:
            state_name = state.group(1) if state else None
        rate = None
        try:
            hw = Path(path).with_name("hw_params").read_text(encoding="utf-8")
            match = re.search(r"rate: (\d+)", hw)
            rate = int(match.group(1)) if match else None
        except OSError:
            pass
        streams.append({"card": names.get(card_index, "card %d" % card_index), "state": state_name, "rate": rate})
    return {"cards": cards, "streams": streams}


def _power():
    rc, out, _ = run(["vcgencmd", "get_throttled"])
    flags = None
    if rc == 0 and "=" in out:
        value = int(out.split("=")[1].strip(), 16)
        flags = {
            "undervoltage_now": bool(value & 0x1),
            "throttled_now": bool(value & 0x4),
            "undervoltage_seen": bool(value & 0x10000),
            "throttled_seen": bool(value & 0x40000),
        }
    temp = None
    try:
        temp = round(int(THERMAL.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    return {"flags": flags, "temperature_c": temp}


def _system():
    st = os.statvfs("/")
    used = round(100 * (1 - st.f_bavail / st.f_blocks), 1) if st.f_blocks else None
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        uptime = None
    _, ips, _ = run(["hostname", "-I"])
    return {"uptime_seconds": uptime, "disk_used_percent": used, "addresses": ips.split()}


def _last_update():
    try:
        lines = UPDATE_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-3:]


def get_status(req):
    services = [_service(name) for name in SERVICES] + [_session_service(n) for n in SESSION_SERVICES]
    problems = [s["name"] for s in services if s["enabled"] == "enabled" and s["active"] != "active"]
    power = _power()
    warnings = []
    if power["flags"] and power["flags"]["undervoltage_now"]:
        warnings.append("undervoltage now")
    if power["temperature_c"] is not None and power["temperature_c"] >= 80:
        warnings.append("temperature above 80 C")
    if problems:
        mark = "error"
    elif warnings:
        mark = "warning"
    else:
        mark = "ok"
    return 200, {
        "overall": mark,
        "problems": problems,
        "warnings": warnings,
        "services": services,
        "soloist": _soloist(),
        "dac": _dac(),
        "power": power,
        "system": _system(),
        "last_update": _last_update(),
    }
