# Folder structure (target)

Draft layout for the repo once the web UI and plugins are added. Nothing is moved yet; the table at the
end maps today's files to their new places. Moves happen in the implementation phase, with the installer
updated in the same commit.

## Target tree

```
raspberry_spotify_dac/
  install.sh                  installer (wizard, answers file, calls the steps below)
  uninstall.sh
  config.example              answers file template
  README.md

  lib/
    common.sh                 shared helpers (log, ask_*, boot config block, paths)

  core/                       the Spotify side and the OS side, always installed
    bin/
      dac-update              Soloist and OS updates
      dac-status              status on the terminal
      dac-sink-volume         DAC default sink and volume at boot
    systemd/
      soloist.service
      spotify-dac-volume.service
      spotify-dac-boot-update.service
      spotify-dac-boot-apt.service
    pipewire/
      50-spotify-dac.conf
    wireplumber/
      50-spotify-dac.conf
    networkmanager/
      99-spotify-dac-wifi.conf

  plugins/                    add-ons, each in its own folder with a manifest
    README.md                 how a plugin is written and installed
    cases/                    exactly one case is active (selector on the Config page)
      none/
        plugin.json
      nespi/
        plugin.json           name, type, pins, default settings, validation
        bin/nespi-power
        systemd/nespi-power.service
    fans/
      fan/
        plugin.json           pin, onTemp, offTemp, startup and poll seconds
        bin/fan-control       generic fan controller driven by plugin.json
        systemd/fan.service

  web/                        the web UI (Python standard library + static files)
    server.py                 HTTPS server, routing, sessions
    api/
      status.py
      spotify.py
      radio.py
      config.py
      plugins.py
      auth.py
    static/
      index.html
      app.js
      style.css
      icons/
    systemd/
      spotify-dac-web.service

  radio/
    stations.default.json     starter station list, copied to /etc/spotify-dac/radio.json

  docs/
    README.md                 index of the docs
    web-ui-plan.md
    web-ui/                   page drafts and the plugin model
    structure.md              this file
    nespi-wiring.md
```

Changes from today: `bin/` splits between `core/bin/` (Spotify and OS), `plugins/cases/nespi/bin/`
(the case) and `plugins/fans/fan/bin/` (the fan). `files/` becomes `core/`, with the systemd, PipeWire,
WirePlumber and NetworkManager files next to their scripts.

## Plugin manifest (plugin.json)

Every plugin has one manifest. The installer and the web UI read it, so neither needs code per plugin.

```json
{
  "name": "fan",
  "type": "plugin",
  "version": 1,
  "description": "Temperature-controlled fan on a GPIO pin",
  "settings": {
    "pin":            {"type": "gpio", "default": 22},
    "onTemp":         {"type": "int", "min": 30, "max": 95, "default": 75},
    "offTemp":        {"type": "int", "min": 25, "max": 90, "default": 55},
    "startupSeconds": {"type": "int", "min": 0, "max": 60, "default": 5},
    "pollSeconds":    {"type": "int", "min": 1, "max": 60, "default": 5}
  },
  "rules": ["offTemp < onTemp", "offTemp <= onTemp - 5"],
  "service": "fan.service",
  "needs": {"usb_dac_only": false}
}
```

- `type` is `case` or `plugin`.
- `settings` lists each key with its type and limits. The Config page builds the form from this and the
  backend checks the same limits.
- `gpio` type keys are checked for conflicts: no HAT pins, no pin used by another enabled plugin.
- `rules` are checked as written (simple comparisons between settings).
- `needs` lets a plugin say it only works with a USB card, so the installer can warn.

## Installer behaviour with plugins

1. Reads `/etc/spotify-dac/plugins/*.json` (the saved settings).
2. For each enabled plugin, installs its `bin/` files to `/usr/local/sbin`, its units to systemd, and enables
   them.
3. For each disabled plugin, stops and disables its unit and leaves its settings in place.
4. The case selector sets which `cases/*` plugin is enabled. Only one is enabled at a time.

## Rules for the layout

- Nothing under `core/` depends on a plugin. A plugin may depend on `core/`.
- A plugin never writes another plugin's files.
- Generated files (`*.pyc`, `__pycache__`) and secrets (`*.conf` answers, `soloist.env`) are never committed.
- Every folder that holds code has a README with its purpose in two lines.

## Migration from today

| Today | Target |
|---|---|
| `install.sh`, `uninstall.sh`, `config.example` | unchanged |
| `lib/common.sh` | unchanged |
| `bin/dac-update`, `bin/dac-status`, `bin/dac-sink-volume` | `core/bin/` |
| `bin/nespi-power` | `plugins/cases/nespi/bin/` |
| `bin/nespi-fan` | `plugins/fans/fan/bin/fan-control` (rewritten to read `plugin.json`) |
| `files/systemd/soloist.service`, `spotify-dac-volume.service`, `spotify-dac-boot-*.service` | `core/systemd/` |
| `files/systemd/nespi-power.service` | `plugins/cases/nespi/systemd/` |
| `files/systemd/nespi-fan.service` | `plugins/fans/fan/systemd/fan.service` |
| `files/pipewire/`, `files/wireplumber/`, `files/networkmanager/` | `core/pipewire/`, `core/wireplumber/`, `core/networkmanager/` |
| `rpi/` (old librespot scripts) | not moved; kept out of this repo's layout |
| `docs/` | unchanged, plus `structure.md` and `web-ui/` |
| (new) `web/`, `radio/`, `plugins/README.md` | created |

## Open questions

1. Should `none` be a real plugin folder (`cases/none/plugin.json`), or a built-in choice in the code?
2. Keep `rpi/` in the repo, or move it out? It is the old librespot material.
3. Should the fan keep its own name (`nespi-fan`) for the case version, or become one generic fan plugin
   that works with any case?
