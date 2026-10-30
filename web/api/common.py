"""Shared helpers for the web API: errors, requests, commands and the config file."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("SPOTIFY_DAC_CONFIG", "/etc/spotify-dac/config"))
SOLOIST_CTL = ["soloist", "ctl", "-w", "127.0.0.1:9090"]
SOLOIST_USER = "soloist"
MAX_BODY = 16 * 1024

_CONFIG_LINE = re.compile(r'^([A-Z_][A-Z0-9_]*)="(.*)"$')


class ApiError(Exception):
    """An error with an HTTP status code. The message is shown to the user."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Request:
    """The parts of a request the handlers need."""

    def __init__(self, method, path, headers, body):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body

    def json(self):
        """The request body as a JSON object, or an ApiError(400)."""
        if not self.body:
            return {}
        try:
            value = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "body must be JSON")
        if not isinstance(value, dict):
            raise ApiError(400, "body must be a JSON object")
        return value

    def cookie(self, name):
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return None


def run(args, timeout=10):
    """Run a command with an argument list (never a shell). Returns (returncode, stdout, stderr)."""
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise ApiError(503, f"{args[0]} is not installed")
    except subprocess.TimeoutExpired:
        raise ApiError(504, f"{args[0]} did not answer in {timeout} s")
    return done.returncode, done.stdout, done.stderr


def read_config():
    """All KEY="value" lines of the config file as a dict. Other lines are ignored."""
    values = {}
    try:
        lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        match = _CONFIG_LINE.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    return values


def write_config(updates):
    """Set the given keys in the config file, keeping every other line. Written atomically."""
    try:
        lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    seen = set()
    out = []
    for line in lines:
        match = _CONFIG_LINE.match(line.strip())
        if match and match.group(1) in updates:
            out.append(f'{match.group(1)}="{updates[match.group(1)]}"')
            seen.add(match.group(1))
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f'{key}="{value}"')
    fd, tmp = tempfile.mkstemp(dir=str(CONFIG_FILE.parent), prefix=".config-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, CONFIG_FILE)


FEATURE_KEYS = {"spotify": "SPOTIFY_ENABLED", "radio": "RADIO_ENABLED"}


def feature_on(name):
    """Whether Spotify or radio is turned on in the installer's choices (on when the key is missing)."""
    return read_config().get(FEATURE_KEYS[name], "yes") != "no"
