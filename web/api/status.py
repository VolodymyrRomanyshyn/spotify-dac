"""Status page: services, Soloist, DAC, power, heat, system and the last update."""
import glob
import os
import re
from pathlib import Path

from .common import run

SERVICES = ["soloist", "nespi-power", "nespi-fan", "spotify-dac-volume", "spotify-dac-web"]
UPDATE_LOG = Path("/var/log/spotify-dac-update.log")
THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def _service(name):
    _, enabled, _ = run(["systemctl", "is-enabled", name])
    _, active, _ = run(["systemctl", "is-active", name])
    return {"name": name, "enabled": enabled.strip(), "active": active.strip()}


def _soloist():
    rc, out, _ = run(["soloist", "--version"])
    version = out.splitlines()[0] if rc == 0 and out.strip() else None
    return {"version": version}


def _dac():
    cards = []
    try:
        for line in Path("/proc/asound/cards").read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*\d+ \[", line):
                cards.append(line.strip())
    except OSError:
        pass
    streams = []
    for path in glob.glob("/proc/asound/card*/pcm*p/sub*/status"):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        state = re.search(r"state: (\w+)", text)
        rate = re.search(r"rate: (\d+)", text)
        streams.append({"path": path.split("/proc/asound/")[1].split("/status")[0],
                        "state": state.group(1) if state else None,
                        "rate": int(rate.group(1)) if rate else None})
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
    services = [_service(name) for name in SERVICES]
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
