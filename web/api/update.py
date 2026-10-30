"""Code updates: see whether the GitHub branch is ahead, then pull it and reload the web UI.

Light update only: the web and radio files are copied and the web service restarts. Audio, boot
and service changes still need the installer (sudo ./install.sh from the project folder).
"""
import os
import pwd
import shutil
import subprocess
from pathlib import Path

from .common import ApiError, read_config, run

WEB_DIR = Path("/opt/spotify-dac/web")
RADIO_DIR = Path("/opt/spotify-dac/radio")


def _source():
    """The project's git clone, recorded by the installer as SOURCE_DIR."""
    source = read_config().get("SOURCE_DIR")
    if not source or not (Path(source) / ".git").is_dir():
        raise ApiError(409, "the project folder is not known; run the installer from the cloned project once")
    return source


def _git(source, *args, timeout=60):
    """Run git as the owner of the clone, so pulls leave no root-owned files behind."""
    owner = pwd.getpwuid(os.stat(source).st_uid).pw_name
    prefix = ["runuser", "-u", owner, "--"] if os.geteuid() == 0 and owner != "root" else []
    rc, out, err = run(prefix + ["git", "-C", source, *args], timeout=timeout)
    if rc != 0:
        raise ApiError(502, "git: " + (err.strip() or out.strip() or "failed"))
    return out.strip()


def _branch(source):
    return _git(source, "rev-parse", "--abbrev-ref", "HEAD")


def get_update(req):
    source = _source()
    branch = _branch(source)
    current = _git(source, "rev-parse", "HEAD")
    _git(source, "fetch", "-q", "origin", branch, timeout=120)
    latest = _git(source, "rev-parse", f"origin/{branch}")
    commits = []
    if latest != current:
        commits = _git(source, "log", "--format=%s", f"{current}..{latest}").splitlines()[:10]
    return 200, {
        "branch": branch,
        "current": current[:7],
        "latest": latest[:7],
        "update_available": latest != current,
        "commits": commits,
    }


def post_update(req):
    if req.json().get("confirm") is not True:
        raise ApiError(400, "confirm must be true to update")
    source = _source()
    branch = _branch(source)
    _git(source, "pull", "-q", "--ff-only", "origin", branch, timeout=120)
    head = _git(source, "rev-parse", "--short", "HEAD")
    # the same files the installer copies; the station list in /etc is not touched
    shutil.copytree(Path(source) / "web", WEB_DIR, dirs_exist_ok=True)
    shutil.rmtree(RADIO_DIR, ignore_errors=True)
    shutil.copytree(Path(source) / "radio", RADIO_DIR)
    # restart after this answer has been sent, or the request would cut itself off
    subprocess.Popen(
        ["sh", "-c", "sleep 2; systemctl restart spotify-dac-web"],
        start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return 202, {"updated_to": head, "restarting": True}
