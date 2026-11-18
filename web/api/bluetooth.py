"""Bluetooth speaker: the phone streams music to the DAC (A2DP sink), and the box can control it (AVRCP).

Pairing uses a PIN the user sets in the installer or on the Settings page. The pairing window is
open for a short time, started by the Pair button. The PIN is kept in a root-only file, read by
the bt-agent service (spotify-dac-bluetooth-agent).
"""
import json
import re
import subprocess

from .common import ApiError, read_config, run

PENDING_FILE = "/run/spotify-dac-bt-pairing.json"  # the code the phone shows, written by the agent
DECISION_FILE = "/run/spotify-dac-bt-decision"    # the user's answer: "yes" or "no"
AGENT_UNIT = "spotify-dac-bluetooth-agent.service"
PAIRING_SECONDS = 120
PAIRING_TIMER = "spotify-dac-bluetooth-pairing-off"
TRANSPORT = {"play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous"}
PLAYER_IFACE = "org.bluez.MediaPlayer1"


# ---------- pure parsing (tested without a Bluetooth adapter) ----------

def parse_show(text):
    """The adapter state from `bluetoothctl show`: powered, discoverable, pairable, name."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if ": " in line:
            key, _, value = line.partition(": ")
            values.setdefault(key, value)
    return {
        "powered": values.get("Powered") == "yes",
        "discoverable": values.get("Discoverable") == "yes",
        "pairable": values.get("Pairable") == "yes",
        "name": values.get("Alias", ""),
    }


def parse_devices(text):
    """Paired devices from `bluetoothctl devices Paired`: [{"address", "name"}]."""
    devices = []
    for line in text.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) == 3 and parts[0] == "Device":
            devices.append({"address": parts[1], "name": parts[2]})
    return devices


def find_player(managed_objects):
    """The phone's media player (org.bluez.MediaPlayer1) in the D-Bus object list, with its track.

    managed_objects: the result of GetManagedObjects, as read from `busctl --json=short`."""
    for path, interfaces in managed_objects.items():
        if PLAYER_IFACE not in interfaces:
            continue
        props = interfaces[PLAYER_IFACE]
        track = _variant(props.get("Track")) or {}
        title = _variant(track.get("Title"))
        artist = _variant(track.get("Artist"))
        return {
            "path": path,
            "status": _variant(props.get("Status")) or "",
            "title": title or "",
            "artist": artist or "",
        }
    return None


def _variant(value):
    """A D-Bus value as busctl --json=short prints it: {"type": "s", "data": "..."} or the plain value."""
    if isinstance(value, dict):
        return value.get("data")
    return value


MAC = re.compile(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}")


def valid_address(address):
    return isinstance(address, str) and MAC.fullmatch(address.upper()) is not None


def forget(address):
    """Removes a paired phone (its pairing is deleted, so it must pair again to play)."""
    if not valid_address(address):
        raise ApiError(400, "address must be a Bluetooth address like 11:22:33:44:55:66")
    rc, out, err = _bt(["remove", address.upper()])
    if rc != 0:
        raise ApiError(502, "Could not forget the device: " + (err or out).strip())
    return adapter_state()


def transport_method(action):
    if action not in TRANSPORT:
        raise ApiError(400, "action must be play, pause, next or previous")
    return TRANSPORT[action]


# ---------- the system (bluetoothctl, busctl, systemctl) ----------

def _bt(args, timeout=15):
    return run(["bluetoothctl"] + args, timeout=timeout)


def adapter_state():
    rc, out, _ = _bt(["show"])
    state = parse_show(out) if rc == 0 else {"powered": False, "discoverable": False, "pairable": False, "name": ""}
    rc, out, _ = _bt(["devices", "Paired"])
    state["devices"] = parse_devices(out) if rc == 0 else []
    return state


def stop_other_sources():
    """Bluetooth takes the DAC: Spotify pauses, radio and AirPlay stop."""
    run(["soloist", "ctl", "-w", "127.0.0.1:9090", "pause"], timeout=5)
    from .radio import stop_playback  # local import: radio imports nothing from here
    stop_playback()
    run(["systemctl", "stop", "spotify-dac-airplay.service"], timeout=20)


def set_power(on):
    if on:
        stop_other_sources()
    _bt(["power", "on" if on else "off"])
    if on:
        run(["rfkill", "unblock", "bluetooth"], timeout=10)  # a soft block keeps the adapter off
    return adapter_state()


def start_pairing():
    """Makes the box pairable and discoverable for PAIRING_SECONDS, then closes the window again."""
    _bt(["pairable", "on"])
    _bt(["discoverable", "on"])
    run(["systemctl", "stop", PAIRING_TIMER + ".timer"], timeout=10)
    run(["systemd-run", "--on-active=%d" % PAIRING_SECONDS, "--unit=" + PAIRING_TIMER,
         "bluetoothctl", "pairable", "off"], timeout=10)
    return adapter_state()


def player_state():
    """The phone's track and play state, or None when no phone is playing through the box."""
    rc, out, _ = run(["busctl", "--json=short", "call", "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
                      "GetManagedObjects"], timeout=10)
    if rc != 0:
        return None
    try:
        managed = json.loads(out)["data"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return find_player(managed)


def transport(action):
    method = transport_method(action)
    player = player_state()
    if not player:
        raise ApiError(409, "No phone is connected for playback control")
    rc, _, err = run(["busctl", "call", "org.bluez", player["path"], PLAYER_IFACE, method], timeout=10)
    if rc != 0:
        raise ApiError(502, "The phone did not answer: " + err.strip())
    return player_state()


def pending_pairing():
    """The code a phone is waiting to be confirmed with, or None."""
    try:
        with open(PENDING_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        return {"code": data["code"], "device": data.get("device", "")}
    except (OSError, ValueError, KeyError):
        return None


def decide(match):
    """The user's answer on the Settings page: the codes match (yes) or do not (no)."""
    if pending_pairing() is None:
        raise ApiError(409, "No phone is waiting to be confirmed")
    with open(DECISION_FILE, "w", encoding="utf-8") as handle:
        handle.write("yes" if match else "no")
    return pending_pairing()


def configured():
    return read_config().get("BLUETOOTH_ENABLED") == "yes"
