# Config page

Shows every setting in `/etc/spotify-dac/config`. Simple settings are saved and applied on the page.
Hardware settings (pins, case, sound card) can't be changed here; the page shows the installer command.

## Layout

Phone (one section per card, collapsed by default except "Device"):

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |
+------------------------------------+
|  ▾ Device                          |
|    Name        [RPI-PI-DAC+      ] |
|    Web password  [Change]          |
|                                    |
|  ▸ Updates                         |
|  ▸ Web interface                   |
|  ▸ Soloist (API key)               |
|  ▸ Hardware (read only)            |
|                                    |
|            [ Save ]                |
+------------------------------------+
| Home   Spotify   Radio   Config    |
+------------------------------------+
```

Desktop: section list on the left, the open section on the right.

## Sections

| Section | Fields | Saved by | Applied by |
|---|---|---|---|
| Device | Name (`DEVICE_NAME`) | `POST /api/config` | restart `soloist` |
| Updates | Update trigger (`UPDATE_TRIGGER`), Soloist days, APT upgrade, APT days | `POST /api/config` | none (next boot or power off) |
| Web interface | Web password (change), port | `POST /api/config` | restart `spotify-dac-web` |
| Soloist (API key) | API key, write-only | `POST /api/config` | restart `soloist` |
| Hardware (read only) | Sound card, case, safe shutdown, pins, fan | shown only | run `sudo bash install.sh --config my.conf` |

## Field rules

- **Name:** 1–32 characters, letters, digits, spaces, `-`, `_`, `+`. Quotes and `$` are refused.
- **Soloist days:** whole number 1–89.
- **APT days:** whole number 0–365 (0 = every update).
- **API key:** shows `set` or `not set`. The field is empty; typing a new key replaces it.
  Leaving it empty keeps the stored key. The key is never sent back to the page.
- **Web password:** enter the current password and the new one twice. Only when the password is
  on.

## Save flow

1. The page sends only the fields that changed.
2. The backend checks every value and returns the list of errors, if any. Nothing is saved on error.
3. On success the page shows "Saved". Services that need a restart are listed, with a button
   **Apply now** (`POST /api/config/apply`).
4. A status note shows the restart result for each service.

## Hardware section

- Shows the current values as text, not as inputs.
- A button **Show installer command** displays:

```bash
cd ~/raspberry_spotify_dac && sudo bash install.sh --config my.conf
```

- A note says the installer re-runs with the same answers, so the page never changes hardware.

## States

| State | What the user sees |
|---|---|
| Loading | Skeleton fields |
| Unsaved changes | "Save" enabled; leaving the page asks to discard |
| Validation error | Red text under the field; no save |
| Saved, restart needed | Green "Saved" with **Apply now** |
| Apply failed | Red note with the service name and the error line from the journal |
