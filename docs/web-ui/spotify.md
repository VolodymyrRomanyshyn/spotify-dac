# Spotify page

Shows what Soloist is playing and the controls it exposes. Browsing and search are not in v1 until
`soloist ctl` support is checked on a Pi.

## Layout

Phone:

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |
+------------------------------------+
|        +---------------------+     |
|        |                     |     |
|        |    cover art        |     |   square, about 70% of width
|        |                     |     |
|        +---------------------+     |
|                                    |
|   Old Town Road                    |   track name
|   Lil Nas X, Billy Ray Cyrus       |   artists
|   Remix                            |   album or release
|                                    |
|   1:21 [=========o-----] 2:37      |   progress
|                                    |
|    shuffle   prev   ▶   next  rep  |   controls
|                                    |
|   Volume  [-----o------]  26%      |   slider
|                                    |
|   Next up                          |
|   1. Track name - Artist           |
|   2. Track name - Artist           |
+------------------------------------+
| Home   Spotify   Radio   Config    |
+------------------------------------+
```

Desktop: cover art on the left (about 320 px), track details and controls on the right, queue
below the controls.

## Content

| Element | Source |
|---|---|
| Cover art | `cover` URL in `GET /api/spotify/now` (small size) |
| Track, artists, album | `GET /api/spotify/now` |
| Progress | `GET /api/spotify/now`, refreshed every 2 s while playing |
| Shuffle, repeat state | `GET /api/spotify/now` |
| Queue | `GET /api/spotify/queue` |
| Volume | `GET /api/spotify/now` (Soloist volume) |

## Actions

| Control | Request |
|---|---|
| Play / pause | `POST /api/spotify/control` with `play` or `pause` |
| Next / previous | `POST /api/spotify/control` with `next` or `prev` |
| Volume slider | `POST /api/spotify/control` with `volume` (only after the Soloist command is checked) |
| Shuffle, repeat | Not in v1 unless `soloist ctl` supports them |

## States

| State | What the user sees |
|---|---|
| Playing | Full controls, progress moving |
| Paused | Play button shown, progress stopped |
| Nothing loaded | Placeholder cover, "Start playback in the Spotify app" |
| Soloist not running | Banner with the status from `GET /api/status`, controls disabled |
| Radio playing | Banner "Radio is playing. Play Spotify to switch." |

## Notes

- The cover image is loaded from Spotify's image host through the browser, so the Pi doesn't need
  internet for the page itself. If the image can't load, the placeholder stays.
- Progress updates locally between refreshes so the bar doesn't jump.
