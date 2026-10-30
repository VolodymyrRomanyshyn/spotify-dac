#!/usr/bin/env python3
"""Spotify DAC web UI: HTTPS server, JSON API and static pages (standard library only).

Usage:
    sudo python3 server.py --cert /etc/spotify-dac/web/cert.pem --key /etc/spotify-dac/web/key.pem
    python3 server.py --http --port 8080        (development only, no TLS)

Every API answer is JSON: {"ok": true, "data": ...} or {"ok": false, "error": "..."}.
Requests are logged to the journal without their bodies.
"""
import argparse
import json
import mimetypes
import ssl
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from api import auth, config, hardware, radio, spotify, status, update, volume  # noqa: E402
from api.common import MAX_BODY, ApiError, Request, feature_on  # noqa: E402

STATIC = HERE / "static"

ROUTES = {
    ("POST", "/api/login"): auth.login,
    ("POST", "/api/logout"): auth.logout,
    ("GET", "/api/status"): status.get_status,
    ("GET", "/api/spotify/now"): spotify.get_now,
    ("GET", "/api/spotify/queue"): spotify.get_queue,
    ("POST", "/api/spotify/control"): spotify.post_control,
    ("GET", "/api/spotify/update"): spotify.get_update,
    ("POST", "/api/spotify/update"): spotify.post_update,
    ("GET", "/api/radio/stations"): radio.get_stations,
    ("PUT", "/api/radio/stations"): radio.put_stations,
    ("GET", "/api/radio/catalog"): radio.get_catalog,
    ("GET", "/api/radio/now"): radio.get_now,
    ("POST", "/api/radio/play"): radio.post_play,
    ("POST", "/api/radio/stop"): radio.post_stop,
    ("GET", "/api/volume"): volume.get_volume,
    ("POST", "/api/volume"): volume.post_volume,
    ("GET", "/api/device"): config.get_device,
    ("GET", "/api/features"): config.get_features,
    ("GET", "/api/hardware"): hardware.get_hardware,
    ("POST", "/api/hardware"): hardware.post_hardware,
    ("GET", "/api/code/update"): update.get_update,
    ("POST", "/api/code/update"): update.post_update,
    ("GET", "/api/config"): config.get_config,
    ("POST", "/api/config"): config.post_config,
    ("POST", "/api/config/apply"): config.post_apply,
}
PUBLIC = {("POST", "/api/login")}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https:; style-src 'self'; script-src 'self'",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "spotify-dac-web"
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write(f"web {self.client_address[0]} {fmt % args}\n")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def _dispatch(self, method):
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            if method != "GET":
                return self._json(405, {"ok": False, "error": "method not allowed"})
            return self._static(path)
        handler = ROUTES.get((method, path))
        if handler is None:
            return self._json(404, {"ok": False, "error": "no such endpoint"})
        try:
            body = self._body()
            req = Request(method, path, self.headers, body)
            req.query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            if (method, path) not in PUBLIC and not auth.is_authorized(req):
                raise ApiError(401, "sign in first")
            for prefix, feature, label in (("/api/spotify/", "spotify", "Spotify"), ("/api/radio/", "radio", "Radio")):
                if path.startswith(prefix) and not feature_on(feature):
                    raise ApiError(404, f"{label} is turned off on this device")
            result = handler(req)
            status_code, data = result[0], result[1]
            extra = result[2] if len(result) > 2 else {}
            self._json(status_code, {"ok": True, "data": data}, extra)
        except ApiError as err:
            self._json(err.status, {"ok": False, "error": err.message})
        except Exception:  # keep the server up; details go to the journal only
            traceback.print_exc()
            self._json(500, {"ok": False, "error": "internal error, see the journal"})

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        return self.rfile.read(length) if length else b""

    def _json(self, code, payload, extra_headers=None):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def _static(self, url_path):
        rel = url_path.lstrip("/") or "index.html"
        target = (STATIC / rel).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            return self._json(404, {"ok": False, "error": "not found"})
        if not target.is_file():
            return self._json(404, {"ok": False, "error": "not found"})
        data = target.read_bytes()
        self.send_response(200)
        self._common_headers()
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _common_headers(self):
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--cert", default="/etc/spotify-dac/web/cert.pem")
    parser.add_argument("--key", default="/etc/spotify-dac/web/key.pem")
    parser.add_argument("--http", action="store_true", help="development only: serve plain HTTP")
    args = parser.parse_args()

    threading.Thread(target=radio.watch_sources, daemon=True).start()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    if not args.http:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.load_cert_chain(args.cert, args.key)
        except OSError as err:
            sys.exit(f"cannot load the certificate ({err}); run the installer or use --http for development")
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    scheme = "http" if args.http else "https"
    print(f"spotify-dac web on {scheme}://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
