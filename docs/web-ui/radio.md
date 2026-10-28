# Internet radio page

Pick a station from a list and play it on the same DAC as Spotify.

## Layout

Phone:

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |
+------------------------------------+
|  Now playing                       |
|  [logo]  Station name  ■ Stop      |   shown only while playing
|          Stream title, if any      |
+------------------------------------+
|  Stations                  [+ Add] |
|  +------------------------------+  |
|  | [logo] Jazz FM        ▶      |  |   row: logo, name, genre, play
|  |        Jazz                  |  |
|  +------------------------------+  |
|  | [logo] Classic 100    ▶      |  |
|  |        Classical             |  |
|  +------------------------------+  |
+------------------------------------+
| Home   Spotify   Radio   Config    |
+------------------------------------+
```

Desktop: station list on the left, the "Now playing" card and the add form on the right.

## Content

| Element | Source |
|---|---|
| Station list | `GET /api/radio/stations` (from `/etc/spotify-dac/radio.json`) |
| Logo | Station's `logo` URL; a letter badge when missing |
| Now playing | Local state after `POST /api/radio/play` |
| Stream title | Not in v1; shown only if mpv reports it |

## Actions

| Control | Request |
|---|---|
| ▶ on a station | `POST /api/radio/play` with the station id. Spotify is paused first. |
| ■ Stop | `POST /api/radio/stop` |
| + Add | Opens the add form (below). Saves to the station list. |
| Edit / delete a station | Long-press or ⋮ menu. Not in v1 if time is short. |

## Managing stations

Stations are added and changed on this page. The Config page only turns the radio on or off.

- **Manage stations** opens the station editor: a list with **Edit** and **Delete** for each row.
- **Edit** opens the same form as **Add**, filled in. Changes are saved to `radio.json` at once.
- **Delete** asks to confirm. Deleting the station that is playing stops playback first.
- **Reorder:** drag a row (desktop) or use the ↑ ↓ buttons (phone). The order shows on Home.
- **Import / export:** the station list as a JSON file, so it can be backed up.

Station record:

```json
{
  "id": "jazz-fm",
  "name": "Jazz FM",
  "url": "https://example.com/jazz.mp3",
  "genre": "Jazz",
  "logo": ""
}
```

## Add-station form

- Fields: name (required), stream URL (required, must start with `http://` or `https://`),
  genre (optional), logo URL (optional).
- The URL is checked by the backend before it is saved. A bad URL shows an error under the field.
- Save writes to `radio.json`. The new station appears at the end of the list.

## States

| State | What the user sees |
|---|---|
| No stations | "No stations yet. Add one." |
| Starting | Play button spins; the row is marked "Connecting..." |
| Playing | Station row highlighted; Now playing card shows the name |
| Stream failed | Row shows "Could not play this station"; Spotify stays paused |
| Spotify is playing | Banner "Spotify is playing. Starting radio will pause it." with a confirm button |

## Notes

- The stream plays through `mpv` to the PipeWire DAC sink. The installer must add `mpv` as a
  package (open question 1 in the plan).
- Only one station plays at a time. Starting a new one stops the old one.
