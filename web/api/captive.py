"""Port 80 for the device hotspot: the Wi-Fi setup page, and a redirect for everything else.

Runs only while the hotspot is on. It serves the Wi-Fi page and its files, and the four Wi-Fi API
routes, without a login (the hotspot password protects the link). Any other address gets a redirect
to the Wi-Fi page, so a phone that joins the hotspot opens the page by itself.
"""
import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import wifi
from .common import MAX_BODY, ApiError, Request

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "static"
HOTSPOT_ADDRESS = "10.42.0.1"
SETUP_PAGE = "/network.html"
SETUP_FILES = {"/network.html", "/network.js", "/style.css", "/common.js"}
API_ROUTES = wifi.ROUTES


def decide(method, path):
    """What to answer on port 80. Returns ("file", path), ("api", None) or ("redirect", url)."""
    if method == "GET" and path in ("/", SETUP_PAGE):
        return ("file", SETUP_PAGE)
    if method == "GET" and path in SETUP_FILES:
        return ("file", path)
    if (method, path) in API_ROUTES:
        return ("api", None)
    return ("redirect", "http://" + HOTSPOT_ADDRESS + SETUP_PAGE)


class CaptiveHandler(BaseHTTPRequestHandler):
    server_version = "dac-captive"

    def log_message(self, fmt, *args):  # keep the journal quiet; errors are printed where they happen
        pass

    def _send(self, code, body, content_type, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _dispatch(self, method):
        path = urlsplit(self.path).path
        kind, target = decide(method, path)
        if kind == "redirect":
            return self._send(302, b"", "text/plain", {"Location": target})
        if kind == "file":
            data = (STATIC / target.lstrip("/")).read_bytes()
            return self._send(200, data, mimetypes.guess_type(target)[0] or "application/octet-stream")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "request body too large")
            body = self.rfile.read(length) if length else b""
            result = API_ROUTES[(method, path)](Request(method, path, self.headers, body))
            self._json(result[0], {"ok": True, "data": result[1]})
        except ApiError as err:
            self._json(err.status, {"ok": False, "error": err.message})
        except Exception:
            traceback.print_exc()
            self._json(500, {"ok": False, "error": "internal error, see the journal"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")


class CaptiveServer:
    """Starts and stops the port-80 server. The watcher calls start() when the hotspot comes on."""

    def __init__(self, port=80, host=HOTSPOT_ADDRESS):
        self.port = port
        self.host = host
        self.httpd = None

    def start(self):
        if self.httpd is not None:
            return
        self.httpd = ThreadingHTTPServer((self.host, self.port), CaptiveHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
