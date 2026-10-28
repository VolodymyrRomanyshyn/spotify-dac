"""Spotify page: now playing, controls and queue, through `soloist ctl` (local websocket)."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .common import SOLOIST_CTL, ApiError, run

CONTROLS = {"play", "pause", "next", "prev"}
_URI = re.compile(r"^spotify:(track|album|playlist|episode):[A-Za-z0-9]{1,64}$")


def _soloist_now():
    rc, out, err = run(SOLOIST_CTL + ["now", "--json"])
    if rc != 0:
        raise ApiError(502, "Soloist is not reachable: " + (err.strip() or "no response"))
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise ApiError(502, "Soloist sent an unexpected answer")


def get_now(req):
    data = _soloist_now()
    item = data.get("item") or {}
    decorations = item.get("decorations") or {}
    name = (decorations.get("identity") or {}).get("name")
    covers = (decorations.get("visual_identity") or {}).get("cover") or []
    small = next((c.get("url") for c in covers if c.get("size") == "small"), None)
    cover = small or (covers[0].get("url") if covers else None)
    return 200, {"status": data.get("status"), "name": name, "uri": item.get("uri"), "cover": cover}


def get_queue(req):
    rc, out, err = run(SOLOIST_CTL + ["queue", "10"])
    if rc != 0:
        raise ApiError(502, "Soloist is not reachable: " + (err.strip() or "no response"))
    return 200, {"lines": [line for line in out.splitlines() if line.strip()]}


def post_control(req):
    body = req.json()
    action = body.get("action")
    if action not in CONTROLS:
        raise ApiError(400, "action must be one of: " + ", ".join(sorted(CONTROLS)))
    args = SOLOIST_CTL + [action]
    if action == "play" and body.get("uri"):
        uri = body["uri"]
        if not isinstance(uri, str) or not _URI.match(uri):
            raise ApiError(400, "uri must look like spotify:track:<id>")
        args.append(uri)
    rc, out, err = run(args)
    if rc != 0:
        raise ApiError(502, f"Soloist did not accept '{action}': " + (err.strip() or out.strip()))
    return 200, {"action": action}


SOLOIST_URL = "https://soloist-builds.spotifycdn.com/soloist_release_arm64.tar.gz"
SOLOIST_UPDATER = "/usr/local/sbin/dac-update"
INSTALLED_SHA = Path("/var/lib/spotify-dac/soloist.sha256")


def _sha256_of_download(url):
    """Download the Soloist archive to a temp file and return its SHA-256 (chunked)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "soloist.tar.gz")
        rc, _, err = run(["curl", "--fail", "--silent", "--show-error", "--location",
                          "--connect-timeout", "15", "--max-time", "240", "-o", path, url], timeout=260)
        if rc != 0:
            raise ApiError(502, "cannot reach Spotify's Soloist server: " + (err.strip() or "no answer"))
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()


def _installed_version():
    rc, out, _ = run(["soloist", "--version"])
    return out.splitlines()[0] if rc == 0 and out.strip() else None


def get_update(req):
    latest = _sha256_of_download(SOLOIST_URL)
    try:
        current = INSTALLED_SHA.read_text(encoding="utf-8").strip()
    except OSError:
        current = None
    return 200, {"installed": _installed_version(), "update_available": current != latest}


def post_update(req):
    if req.json().get("confirm") is not True:
        raise ApiError(400, "confirm must be true to update Soloist")
    # --force: a manual update installs the newest build now, whatever its age
    rc, out, err = run([SOLOIST_UPDATER, "--trigger", "manual", "--only", "soloist", "--force"], timeout=400)
    if rc != 0:
        raise ApiError(502, "update failed: " + (err or out).strip()[-300:])
    return 200, {"installed": _installed_version(), "restarted": True}
