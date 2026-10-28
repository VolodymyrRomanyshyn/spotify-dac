# Plugins

Hardware and other add-ons are **plugins**. Each plugin is a small unit with its own settings,
stored as JSON. The Config page lists them and lets you add, delete, enable, disable and edit them.

## Kinds of plugin

| Kind | How many | Examples |
|---|---|---|
| **Case** | Exactly one, chosen from a selector | `none`, `nespi` (RetroFlag NESPi Case+) |
| **Other plugin** | Any number, each can be enabled or disabled | `fan`, later: display, IR remote |

The case selector always has a value. `none` means no case.

## Settings format

Each plugin stores its settings as one JSON object. The Config page shows it as a form, with a
"Show JSON" view for the same data.

### Case: `nespi`

```json
{
  "safeShutdown": true,
  "poweroffMode": "hardcut",
  "updateTrigger": "poweroff",
  "pins": {
    "powerSwitch": 17,
    "reset": 27,
    "led": 14,
    "powerEnable": 4
  },
  "timers": {
    "holdSeconds": 1,
    "syncSeconds": 3,
    "updateTimeoutMinutes": 30
  },
  "enableReset": true
}
```

- `safeShutdown: false` ignores the switch and buttons; the case stays powered. Updates then run at boot.
- `poweroffMode`: `hardcut` (proven) or `graceful` (experimental).
- `updateTrigger`: `poweroff`, `boot` or `none`.

### Plugin: `fan`

```json
{
  "pin": 22,
  "onTemp": 75,
  "offTemp": 55,
  "startupSeconds": 5,
  "pollSeconds": 5
}
```

- Validation: `offTemp` must be lower than `onTemp`, with at least 5 °C between them.
- `pin` must be a free GPIO (not a HAT pin, not used by the case). The check runs on save.

The example from the request (`pin: 21, onTemp: 85, offTemp: 75`) is valid: 85 and 75 leave a
10 °C gap. Pin 21 is only valid with a USB card, because a HAT uses it.

## Plugin lifecycle

| Action | What it does |
|---|---|
| **Add** | Pick a plugin type, fill in its JSON, save. Starts disabled. |
| **Enable** | Starts the plugin's service or sets its pins. |
| **Disable** | Stops the service and releases its pins. Settings are kept. |
| **Edit** | Change the JSON. Applies on save, or on **Apply now** for a running plugin. |
| **Delete** | Disables the plugin and removes its settings. Asks to confirm. |

The case is not added or deleted. It is changed with the case selector.

## Where settings live

- `/etc/spotify-dac/plugins/<name>.json`, one file per plugin, owned by root, mode 640.
- The case selector is `CASE` in `/etc/spotify-dac/config`, plus the case plugin file.
- The installer creates the files from the answers, so `install.sh` and the Config page read the same
  data.

## Rules

- A pin used by one plugin can't be used by another. The check runs on save and lists the conflict.
- A HAT blocks its pins for every plugin.
- A plugin that is enabled but cannot start shows as red on the Status page, with the error.
- Installing a new plugin type needs its files in the repo (`plugins/<name>/`). The Config page only lists
  types that are installed.

## Open items

- How a plugin declares its pins, so conflict checks need no code per plugin.
- Whether pin changes on the case apply live or need the installer (see the Config page).
