"""Login, sessions and the optional web password.

The password is off unless /etc/spotify-dac/web.json says otherwise:
    {"use_password": true, "password": "scrypt$<salt hex>$<hash hex>"}
"""
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from .common import ApiError

AUTH_FILE = Path("/etc/spotify-dac/web.json")
COOKIE = "spotify_dac_session"
SESSION_SECONDS = 12 * 3600
_lock = threading.Lock()
_sessions = {}  # token -> expiry (monotonic seconds)


def settings():
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"use_password": False}


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), digest_hex)


def _new_session():
    token = secrets.token_urlsafe(32)
    with _lock:
        now = time.monotonic()
        for key in [k for k, exp in _sessions.items() if exp < now]:
            del _sessions[key]
        _sessions[token] = now + SESSION_SECONDS
    return token


def _session_valid(token):
    if not token:
        return False
    with _lock:
        expiry = _sessions.get(token)
        return expiry is not None and expiry >= time.monotonic()


def is_authorized(req):
    """True when no password is set, or the request carries a valid session cookie."""
    if not settings().get("use_password"):
        return True
    return _session_valid(req.cookie(COOKIE))


def login(req):
    current = settings()
    if not current.get("use_password"):
        return 200, {"password": False}
    password = req.json().get("password", "")
    if not isinstance(password, str) or not check_password(password, current.get("password", "")):
        time.sleep(1)  # slows down guessing
        raise ApiError(401, "Wrong password")
    token = _new_session()
    cookie = f"{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_SECONDS}"
    return 200, {"password": True}, {"Set-Cookie": cookie}


def logout(req):
    token = req.cookie(COOKIE)
    with _lock:
        _sessions.pop(token, None)
    expired = f"{COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"
    return 200, {}, {"Set-Cookie": expired}
