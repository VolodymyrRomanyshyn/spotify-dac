# Home page

The first page after login. A **source switch** chooses Spotify or Internet radio. The switch shows
what is playing and changes the source; the rest of the page follows the chosen source.

## Layout

Phone:

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |   top bar: device name, theme, status link
+------------------------------------+
|  +------------------+------------+ |
|  |  ● Spotify       | Internet   | |   source switch (segmented control)
|  |                  |  radio     | |   the selected part is filled
|  +------------------+------------+ |
|                                    |
|  Now playing                       |
|  Old Town Road - Lil Nas X         |   content of the chosen source
|  ▶  ⏸  ⏭                           |   short controls
|  Open Spotify page →               |   link to the full page
|                                    |
|  DAC 44.1 kHz  S32_LE  vol 100%    |   status line
+------------------------------------+
| Home   Spotify   Radio   Config    |   bottom tabs
+------------------------------------+
```

- The switch shows only the sources **enabled** in Config. If only one is enabled, the switch is
  hidden and the page shows that source.
- Desktop: the switch sits at the top; the now-playing card and controls are side by side.

## Switching sources

- Choosing a source makes it the active source and pauses the other one.
- If the other source is playing, the switch asks: "Pause Spotify and play radio?" (or the reverse).
- The chosen source is remembered on the Pi, so every browser shows the same source.

## Content for each source

| Source | Shows on Home |
|---|---|
| Spotify | Track, artists, play state, previous, play/pause, next. "Open Spotify page" link. |
| Internet radio | Station name, logo, play/stop. "Open Radio page" link. "Choose station" shows the station list. |

## Shared status line

| Element | Source |
|---|---|
| DAC rate, format, sink volume | `GET /api/status` |
| Warning badge | Shown when any enabled service is not active, or the Pi reports throttling. Tap to open Status. |

## States

| State | What the user sees |
|---|---|
| Nothing playing | Selected source shown with "Not playing" |
| Playing | Controls active, track or station name shown |
| Source disabled in Config | Hidden from the switch |
| No source enabled | "No source enabled. Turn one on in Config." |
| Backend unreachable | Banner "Cannot reach the Pi"; last values greyed out |
