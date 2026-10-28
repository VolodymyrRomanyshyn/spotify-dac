# Web UI and internet radio: draft plan

Status: draft for review. No code yet. Branch `feature/web-ui` (from `main`).

## Goals

- A web UI that works on mobile and desktop, with a dark mode option.
- Installation of the web UI from `install.sh` (a question, or `--web`).
- Main page: choose **Spotify** or **Internet radio**.
- Spotify: navigate, see the cover art and the player controls that Soloist exposes.
- Internet radio: pick a station from a list and play it on the same DAC.
- Config page: view and change all settings, including the API key (write-only).
- Status page: check that everything is working.

## Architecture

- **Server:** Python 3 standard library only (`http.server`, `json`, `hashlib`). Trixie already ships
  Python 3, so there are no pip packages to install. The server runs as a systemd service,
  `spotify-dac-web`, on port 8080 by default.
- **Frontend:** plain HTML, CSS and JavaScript in `web/static/`. No build step and no CDN, so it
  works offline on the LAN. Layout is responsive (phone first, then desktop).
- **Dark mode:** CSS variables. Default follows the system (`prefers-color-scheme`), with a toggle
  that is remembered in the browser.
- **Only one source plays at a time.** Spotify (Soloist) and internet radio both write to the same
  PipeWire DAC sink. Starting one pauses the other.

## Backend

The browser needs a backend for four things: reaching Soloist (which only listens on
`127.0.0.1:9090`), reading system state, changing settings, and controlling radio playback.
The backend is a small set of JSON endpoints, one per job.

- **Runtime:** Python 3 standard library only, `http.server` with `ThreadingHTTPServer`, served over
  HTTPS with the certificate from the installer. No framework, no pip packages.
- **Run as:** root. The config and API key files are root-only. Soloist commands use the
  `soloist ctl` tool, which talks to the local websocket, so the backend doesn't touch the
  Soloist user or its session.
- **Static files:** the same server serves `web/static/`, so there is one service and one port.
- **Concurrency:** one lock around playback changes, so two clients can't start radio and Spotify
  at the same time.
- **Errors:** every endpoint returns JSON `{ok, data | error}` with an HTTP status code. A broken
  Soloist or radio stream shows as an error on the page, not a crash.
- **Logging:** requests and actions go to the journal (`journalctl -u spotify-dac-web`). Passwords
  and the API key are never logged.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/login`, `/api/logout` | Session login (only when `WEB_USE_PASSWORD=yes`) |
| GET | `/api/status` | Services, Soloist, DAC rate and format, volume, temperature, throttling, update log |
| GET | `/api/spotify/now` | Track, cover URL, progress, play state (from `soloist ctl now --json`) |
| POST | `/api/spotify/control` | `play`, `pause`, `next`, `prev` (and volume, once checked) |
| GET | `/api/spotify/queue` | Next tracks (`soloist ctl queue`) |
| GET | `/api/radio/stations` | Station list from `radio.json` |
| POST | `/api/radio/play` | Start a station with mpv on the DAC sink; pauses Spotify first |
| POST | `/api/radio/stop` | Stop mpv |
| GET | `/api/config` | Current settings. The API key is replaced with `set` or `not set` |
| POST | `/api/config` | Change settings that need only a service restart |
| POST | `/api/config/apply` | Restart the services that changed |
| GET | `/api/plugins` | Installed plugin types, and each plugin's enabled state and settings (JSON) |
| POST | `/api/plugins` | Add a plugin (starts disabled) |
| PUT | `/api/plugins/{name}` | Change a plugin's settings; validated before saving |
| DELETE | `/api/plugins/{name}` | Disable and remove a plugin |
| POST | `/api/plugins/{name}/enable` | Enable or disable a plugin (`{"enabled": true}`) |
| PUT | `/api/case` | Choose the case from the selector (`none`, `nespi`, ...) |
| GET | `/api/radio/stations` | Station list |
| PUT | `/api/radio/stations` | Add, edit, delete and reorder stations (whole list, validated) |
| PUT | `/api/source` | Switch the active source (`spotify` or `radio`) |

Pin, case and sound-card changes are not in the API. They go through the installer, and the page
shows the command to run.

### Limits and checks

- Request body size is limited (for example 16 KB), and only the listed methods and paths are
  accepted.
- Inputs are checked against the allowed values before they reach a command. Station URLs must be
  `http` or `https`.
- The backend never runs a shell with user text. Commands are built as argument lists.

## Pages

### 1. Home
- A **source switch** (Spotify / Internet radio) at the top. Only enabled sources are shown.
- Switching pauses the other source. The chosen source is kept on the Pi.
- Shows the active source's now-playing card, a short control row, and the DAC status line.

### 2. Spotify
- Now playing: cover art, track, artist, album, progress bar.
- Controls: play, pause, next, previous, shuffle, repeat, volume.
- Queue: next tracks.
- Source for all of this: `soloist ctl -w 127.0.0.1:9090 now --json` returns the status, the track and the
  cover URLs (`decorations.visual_identity.cover`). Controls use `play`, `pause`, `next`, `prev`.
- **Open:** browsing and search. The control list I read earlier did not show them. This needs
  checking on a Pi. Until then the page only controls playback that is already running.

### 3. Internet radio
- Station list with name, logo and genre, stored in `/etc/spotify-dac/radio.json` and editable on the
  config page.
- Play and stop. The stream goes through `mpv --ao=pipewire`, to the same sink as Soloist.
- Shows the station name and the stream's title if the station sends one.
- **Open:** mpv is not installed by the installer yet. It would be added as a package.

### 4. Config
- Sections: **Spotify** (enable, device name, API key), **Internet radio** (enable, link to stations),
  **Plugins** (add, delete, enable, disable, edit JSON), **Case** (one selector: none, nespi, ...),
  **Sound card** (read only), **Updates**, **Web interface**.
- Plugins and the case use the JSON model in [web-ui/plugins.md](web-ui/plugins.md).
- Radio stations are managed on the Radio page, not in Config.
- The API key: a write-only field ("set" / "replace"). It is never shown or sent back.
- Saving:
  - settings that only change a service (device name, volume, update days) are applied and the
    service is restarted;
  - pin, case or sound-card changes need the installer, so the page shows the command to run
    (`sudo bash install.sh --config ...`) instead of changing them directly.

### 5. Status
- Services: `soloist`, `nespi-power`, `nespi-fan`, `spotify-dac-volume`, `spotify-dac-web`.
- Soloist: version, build age, "client expires in N days", login state.
- DAC: card name, sink state, sample rate and format, sink volume.
- Power and heat: throttling flags from `vcgencmd get_throttled`, CPU temperature.
- Recent update log lines from `/var/log/spotify-dac-update.log`.
- System: uptime, disk use, IP address.

## Address

- The main page is `https://<hostname>.local:8443`, for example `https://rpi-2.local:8443`.
- `.local` names come from mDNS. The installer makes sure `avahi-daemon` is installed and running.
- The Pi's hostname is set by the installer question "Hostname (used for the web address)". The
  default is the current hostname. Setting it to `rpi-2` changes `/etc/hostname` and `/etc/hosts`.
- The self-signed certificate is generated for `<hostname>.local` and the Pi's IP address, so it
  is regenerated if the hostname changes.
- Side effect to note: `ssh rpi-2` in `~/.ssh/config` points at `<pi-hostname>.local` today. After a
  rename the SSH alias must use the new name, or the alias must keep the old one.
- The Spotify device name (`DEVICE_NAME`) is separate from the hostname, so it stays as configured.

## Installation

- `install.sh` asks: install the web UI (yes/no), port (8443), hostname, and **use password (yes/no)**.
- Answers file keys: `WEB_UI=yes|no`, `WEB_PORT`, `WEB_HOSTNAME`, `WEB_USE_PASSWORD=yes|no`.
- `WEB_USE_PASSWORD=yes` (default): asks for a password. It is stored as a salted hash
  (`hashlib.scrypt`), not in plain text.
- `WEB_USE_PASSWORD=no`: no login page. Every page is open to anyone on the LAN, and the config page
  can read and change settings. The installer shows a warning and asks for a confirmation.
- The service listens on the LAN address only (configurable). `uninstall.sh` removes it.
- `--web` in an answers file for unattended installs.

## Security

- Authentication (when `WEB_USE_PASSWORD=yes`): a login page with the password from the installer.
  Sessions use a random token in a `Secure`, `HttpOnly` cookie. Config and power actions need a login.
- Without a password, the API key is still never returned, but the config page can change settings.
  Use this only on a home network you trust.
- The API key is never returned by any endpoint.
- No endpoint runs a shell command from user input. Actions are a fixed list (play, pause, next, set
  volume, start or stop radio, restart a service).
- HTTPS is not planned in v1. The UI is for the home LAN only.

## Folder structure (proposed)

```
web/
  server.py            HTTPS server, routing, sessions, static files
  api/
    status.py          /api/status
    spotify.py         /api/spotify/...  (wraps soloist ctl)
    radio.py           /api/radio/...    (mpv, station list)
    config.py          /api/config       (read and write, key masked)
    auth.py            login, logout, password hash check
  static/
    index.html         single page, all screens
    app.js             routing between screens, API calls
    style.css          layout, responsive, dark mode variables
    icons/             SVG icons
files/
  systemd/spotify-dac-web.service
  web/radio.default.json   starter station list
docs/
  web-ui.md            user guide (written when the UI works)
```

## Changes to existing files

- `install.sh`: web questions, `install_web` step, enable the service.
- `uninstall.sh`: remove the web unit and files.
- `lib/common.sh`: a helper to hash the password.
- `config.example`: the new web keys.

## Open questions

1. **Radio player:** `mpv` (recommended, one package, plays most streams) or `ffmpeg`?
2. **Password:** required for every page (recommended), or open on the LAN?
3. **Port:** 8080 is fine, or another one?
4. **Spotify browse and search:** do we need it in v1? It depends on what `soloist ctl` supports.
   I'll check on a Pi once one is reachable.
5. **Config page:** do you want it to apply pin and case changes by re-running the installer,
   or only show the command?

## Phases

| Phase | Scope | Done when |
|---|---|---|
| P0 | This plan, reviewed | You approve the open questions |
| P1 | Folder skeleton, server, login, status page | Status page loads on phone and desktop |
| P2 | Spotify page: now playing, controls, cover art | Controls change Soloist playback |
| P3 | Internet radio: station list, play, stop | A station plays on the DAC |
| P4 | Config page, with the API key write-only | Settings change and services restart |
| P5 | Installer and uninstaller integration | Fresh install gives a working UI |
| P6 | Test on rpi-1 and rpi-2 | Both Pis pass the checklist |

## Test checklist (for P6)

- Phone and desktop layouts, dark and light.
- Login required on every page except the login page.
- Spotify controls change playback; cover art shows during playback.
- Radio plays on the DAC and Soloist pauses; Spotify playback resumes manually.
- Config changes apply, and the API key never appears in the page or the API.
- Status page shows the same values as `dac-status`.
