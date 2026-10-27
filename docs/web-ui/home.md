# Home page

The first page after login. Two large tiles pick the source. A status line shows what is playing.

## Layout

Phone:

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |   top bar: device name, theme, status link
+------------------------------------+
|  +------------------------------+  |
|  |  Spotify                     |  |   tile, full width
|  |  Playing: Old Town Road      |  |   shows only when Spotify is active
|  +------------------------------+  |
|  +------------------------------+  |
|  |  Internet radio              |  |
|  |  Playing: Station name       |  |   shows only when radio is active
|  +------------------------------+  |
|                                    |
|  DAC 44.1 kHz  S32_LE  vol 100%    |   status line
+------------------------------------+
| Home   Spotify   Radio   Config    |   bottom tabs
+------------------------------------+
```

Desktop: the two tiles sit side by side, each about half the width. The status line sits under them.

## Content

| Element | Source |
|---|---|
| Spotify tile subtitle | `GET /api/status` → Soloist state and current track |
| Radio tile subtitle | `GET /api/status` → radio state and station name |
| Status line | `GET /api/status` → DAC rate, format, sink volume |
| Warning badge | Shown when any service is not active or the Pi reports throttling |

## Actions

- Tap **Spotify** → Spotify page. If radio is playing, the radio is stopped first, and the page says so.
- Tap **Internet radio** → Radio page. If Spotify is playing, Soloist is paused first.
- Tap the warning badge → Status page.

## States

| State | What the user sees |
|---|---|
| Nothing playing | Both tiles show "Not playing" |
| Spotify playing | Spotify tile highlighted, track name shown |
| Radio playing | Radio tile highlighted, station name shown |
| Backend unreachable | Banner "Cannot reach the Pi" and the last known values greyed out |
