# Wi-Fi and hotspot: technical requirements

Status: the web page, backend (tested with a fake Wi-Fi), watcher, port-80 setup page, reset button rules and installer questions are written. Not yet tested on rpi-2 with the hotspot running. Branches: `network-settings` (web page and backend) and `installer-hotspot` (installer, watcher, reset button, and the rest).

## Modes

- **Ethernet:** a cable is connected. Ethernet wins; the hotspot is off.
- **Wi-Fi:** joined to a saved network. The hotspot is off.
- **Hotspot:** the Pi runs the `device` access point and the setup page on port 80.
- **None:** no network yet; the hotspot starts after the fallback time.

The hotspot starts in two ways:
- **Automatic:** no Wi-Fi and no Ethernet for `HOTSPOT_FALLBACK_SECONDS` (default 60, 60 to 300).
- **Reset button:** press and hold for 5 seconds.

It stops when Ethernet or Wi-Fi comes back. While it runs, saved networks are retried every 5 minutes.

## Saved networks, priority and switching

- Saved networks are kept in priority order, highest first. The top one is marked "first".
- **Up / Down:** moves a saved network in the order. NetworkManager's `autoconnect-priority` is rewritten to match.
- **Connect:** joins a saved network now. If its password is refused, the Pi goes back to the network it was on (or stays on the hotspot).
- **Forget:** deletes a saved network.
- The Pi joins the highest-priority saved network it can see (NetworkManager's autoconnect).
- Names are shown as Wi-Fi names (SSID), not NetworkManager connection names.

## Wi-Fi page (web UI)

- Visible in every mode, from the menu on every page.
- **Connection:** the current network, Ethernet, hotspot, or nothing.
- **Saved networks:** priority order, Up, Down, Connect, Forget.
- **Nearby networks:** signal bars, secured or open, and a Save button. Save asks for the password on secured networks, checks it by connecting, and keeps the network if it is accepted. A refused password leaves the Pi where it was.
- Passwords are 8 to 63 characters (WPA2 minimum is 8). Open networks need no password.

## Setup page on port 80 (hotspot only)

- Serves the Wi-Fi page and its four API routes (`/api/network`, `/api/network/scan`, `/api/network/save`, `/api/network/forget`), plus `move` and `switch`, without a login. The hotspot password protects the link.
- Every other address redirects to `http://10.42.0.1/network.html`, so a phone that joins the hotspot opens the page by itself.
- The port-80 server runs only while the hotspot is on.

## Reset button

- **Quick press (released before 5 s):** reboot.
- **Hold for 5 s:** start the hotspot. The LED goes solid for a moment, then the hotspot is requested.
- LED patterns: reboot blinks fast; holding blinks steadily; hotspot on shows two short flashes and a pause.

## Installer

- Asks whether to start the hotspot (default no).
- If yes: the fallback time (60 to 300 seconds) and the hotspot password (8 to 63 characters, no quotes, backslashes, `$` or backticks).
- The password is stored in `/etc/spotify-dac/hotspot.env`, readable by root only.
- The watcher service (`spotify-dac-netwatch`) is enabled only when the hotspot is on.
- The uninstaller removes the watcher, the password file and the `device-hotspot` connection.

## Safety

- The Pi must never be left unreachable. A failed connect always goes back to the previous network, or to the hotspot if there was none.
- Test on rpi-2 with an Ethernet cable plugged in, so SSH survives a Wi-Fi change.
- rpi-2 has one Wi-Fi radio. Scanning while the hotspot runs is still to be verified on the hardware.

## Tests

- Unit tests (`tests/test_wifi.py`, fake Wi-Fi and fake clock): mode rules, input checks, saving with revert, forgetting, priorities, switching, the watcher, nmcli output parsing, the reset button timing, port-80 routing, and the hotspot command.
- On the Pi (to do): scan while the hotspot runs; start and stop the hotspot; a wrong password reverts; Ethernet takes priority; a 5-second reset hold starts the hotspot; the iPhone hotspot test (join it, turn it off, the device hotspot starts, add a network again).

## Open decisions

- Confirm the hotspot name `device`.
- Power script wiring for the reset button and the LED patterns: tested only on hardware.
