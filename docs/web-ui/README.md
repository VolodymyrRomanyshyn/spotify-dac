# Web UI page drafts

Draft layouts for the web UI. Plan: [../web-ui-plan.md](../web-ui-plan.md).

| Page | File | Endpoints used |
|---|---|---|
| Login | [login.md](login.md) | `POST /api/login` |
| Home | [home.md](home.md) | `GET /api/status` |
| Spotify | [spotify.md](spotify.md) | `GET /api/spotify/now`, `POST /api/spotify/control`, `GET /api/spotify/queue` |
| Internet radio | [radio.md](radio.md) | `GET /api/radio/stations`, `POST /api/radio/play`, `POST /api/radio/stop` |
| Config | [config.md](config.md) | `GET /api/config`, `POST /api/config`, `POST /api/config/apply` |
| Plugins (inside Config) | [plugins.md](plugins.md) | `GET /api/plugins`, `POST /api/plugins`, `PUT /api/plugins/{name}`, `DELETE /api/plugins/{name}`, `POST /api/plugins/{name}/enable` |
| Status | [status.md](status.md) | `GET /api/status` |

## Shared rules

- **Layout:** one column on a phone (16 px side margins, no horizontal scroll). Two columns on a
  desktop (from 900 px wide) where a page has a list next to a detail area.
- **Navigation:** a top bar with the app name, four tabs (Home, Spotify, Radio, Config) and a
  Status link. On a phone the tabs move into a bottom bar.
- **Theme:** dark and light colours are CSS variables. Default follows the system setting. A
  toggle in the top bar switches it and remembers the choice in the browser.
- **Errors:** a failed request shows a banner with the message from the API. The page stays usable.
- **Refresh:** Spotify refreshes every 2 s while playing, and Status every 10 s. Other pages refresh
  on action only.
- **Units:** temperatures in °C, times as `m:ss`, volume as a percentage.
- **Names:** the device name from the config is shown in the top bar, so you can see which Pi you
  are on.
