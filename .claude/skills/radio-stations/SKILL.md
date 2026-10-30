---
name: radio-stations
description: Find, test, add, fix and update internet radio stations for the Spotify DAC project (predefined list, search catalogs, and the station file on the Pi). Use when a station is missing, silent, moved, or when adding new stations from RMF ON, Eska, moOde or radio-browser.info.
---

# Radio stations for the Spotify DAC

## Where the stations live

| File | Purpose | Who edits it |
|---|---|---|
| `radio/stations.default.json` | Predefined list. The installer copies it to the Pi once. | Repo (commit it) |
| `radio/catalog-rmfon.json` | 129 RMF ON stations with logo and backup hosts (search source) | Regenerate from the RMF API |
| `radio/catalog-eska.json` | 8 Eska rock stations with logo and Icecast fallback | Regenerate from the Eska API |
| `/etc/spotify-dac/radio.json` (on the Pi) | The live list the web UI reads | Pi only; the web Radio page will edit it later |

Station record (same shape everywhere):
```json
{"id": "rmf-rock", "name": "RMF Rock", "url": "https://...", "genre": "Rock", "logo": "https://..."}
```
Catalog entries also carry `"fallback": ["https://...", ...]` (backup addresses to try in order).
`id` must be unique and lowercase with dashes. `url` must start with `http://` or `https://`.

## Known sources

- **RMF ON:** `https://api.rmfon.pl/stations` (list, `mountpoint_mp3` per station, `img` for logo, `short` for description).
  Streams: `https://api.rmfon.pl/stations/<id>/streams` → `playlistMp3.item_mp3` (backup hosts).
  MP3 pattern: `https://rs102-krk.rmfstream.pl/<mountpoint_mp3>`.
- **Eska (Grupa ZPR player):** `https://front-api.grupazprmedia.pl/radios/v1/radio_stations/sc-giFX-r6Hu-5naE/`
  returns the group's stations. Use `stream_url` (HLS playlist) and `stream_ic` (Icecast fallback), `cover`.
  The list endpoint for the whole group is not public; this one is per group.
- **moOde station list:** `https://github.com/moode-player/moode` → `var/local/www/db/moode-sqlite3.db.sql`
  (`INSERT INTO cfg_radio`). Good for international stations; few Polish ones.
- **radio-browser.info:** `https://de1.api.radio-browser.info/json/stations/byname/<name>` (filter `countrycode == "PL"`).
  Has been unavailable at times (HTTP 503); retry later.
- **Station websites / players:** when a site has a player, open it in the browser, press Play, and read
  the `performance` resource list or `<audio>` element for `m3u8`, `aac`, `mp3`. Some players use blobs; then
  look at the player's JSON API calls instead.

## Test a station before saving it

From the Pi (the Mac can be blocked by some hosts):
```bash
ssh rpi-2 'curl -s -o /dev/null -w "%{http_code} %{content_type}\n" --max-time 8 -L -H "Icy-MetaData: 1" "<url>"'
```
- Good: `200` with `audio/mpeg`, `audio/aacp`, or `application/vnd.apple.mpegurl`.
- For HLS (`.m3u8`): fetch the playlist; if it lists a variant (`chunklist.m3u8`), fetch that too, then one segment (`.ts`). Relative segment names must be joined to the playlist's base URL.
- `302` redirects are fine with `-L`. Redirect targets carry tokens that expire: store the base URL, not the redirect.
- A `Connection timed out` on a port (e.g. `:8904`) means the host blocks that port; try another address.

## Add or change a predefined station

1. Edit `radio/stations.default.json` (keep valid JSON: `python3 -m json.tool radio/stations.default.json`).
2. Commit on the feature branch with a message that lists what was added and how it was tested.
3. Do not push unless the user asks.

## Update the station file on the Pi

The installer does not overwrite an existing `/etc/spotify-dac/radio.json`. To merge new predefined stations
without losing stations the user added or changed, use a merge that keeps existing ids and backs up the file
first (see the pattern used in the feature branch: copy to `radio.json.bak-<timestamp>`, add missing ids, write back).
Run it with `sudo`; the web service reads the file on every request, so no restart is needed.

## Fix a station that stopped working

1. Test the URL from the Pi (see above).
2. If it fails, try the `fallback` addresses in order (catalog entries), then the source's API again
   (RMF: `/stations/<id>/streams`; Eska: `stream_url` / `stream_ic`).
3. If all fail, re-check the source site or player: the address may have moved.
4. Update the record (`url`, and `fallback` if useful), test again, commit, and update the Pi file.

## Checks before finishing

- JSON is valid and ids are unique.
- Every new URL was tested from `rpi-2`, with the result noted in the commit message.
- Logos are `https://` URLs (or empty).
- The web API still lists the stations: `curl -sk https://localhost:8443/api/radio/stations` on the Pi.
