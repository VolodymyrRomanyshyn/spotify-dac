# Pi Spotify DAC

Turns a Raspberry Pi into a zero-maintenance Spotify Connect streamer using
Spotify's official headless client, [Spotify Soloist](https://developer.spotify.com/documentation/soloist).

- USB DAC (Topping E30, ...) or a HAT: IQaudIO DAC+, HiFiBerry DAC/DAC+/Digi+, PiFi DAC+/Digi+
- Optional RetroFlag NESPi Case+ support (USB DAC only): power switch, reset button, LED, GPIO fan
- Self-updating: Soloist builds expire after 90 days, so updates run when you
  switch the box off or on, once the build is old enough

## Requirements

- Raspberry Pi 3/4/5 with **Raspberry Pi OS Lite (64-bit)**, Debian Trixie based
- Wi-Fi/SSH set in Raspberry Pi Imager
- A Spotify Premium account and a **Soloist API key** from the
  [Spotify for Developers dashboard](https://developer.spotify.com/dashboard)

## Install

On a fresh Pi OS Lite, one command installs git, downloads the project and runs the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/VolodymyrRomanyshyn/spotify-dac/main/bootstrap.sh | sudo bash
```

To update later, run the same script from the project folder: `sudo bash bootstrap.sh`.
It pulls the newest code and runs the installer again, keeping your settings.

Or do it by hand:

```bash
sudo apt-get install -y git
git clone https://github.com/VolodymyrRomanyshyn/spotify-dac.git
cd spotify-dac
sudo bash install.sh
```

The installer asks for the device name, sound card, case, update policy and API key,
then downloads Soloist straight from Spotify. It reboots if the boot config changed.
Then open Spotify on your phone, tap the devices icon and pick your device.

Unattended or repeat installs: copy `config.example` to `my.conf`, fill it in, then run
`sudo bash install.sh --config my.conf`. Running the installer again keeps your
current settings as defaults.

## How it works

| Box | Updates | Power off |
|---|---|---|
| NESPi Case+ + USB DAC | when the power switch is turned **off** | update, then hard cut via GPIO4 |
| DAC HAT, no case control | at **power on**, before Soloist starts | - |

Without the NESPi case there is no power switch to hook, so updates always run at
boot. That keeps a bare Pi zero-maintenance too: the `none` trigger (update only
when the build has expired) is available for the NESPi case only.

- **Soloist** is updated only when the installed build is at least
  `SOLOIST_UPDATE_AFTER_DAYS` old (default 45). If Soloist ever exits with
  code 10 (build expired), it fetches a new build and restarts automatically.
- **OS** `apt full-upgrade` runs at most every `APT_UPGRADE_AFTER_DAYS` (0 = every time).
  At boot it runs in the background after Soloist is up.
- **Audio** goes Soloist -> PipeWire -> DAC. PipeWire is locked to Spotify's 44.1 kHz,
  so there is no resampling. Onboard and HDMI audio are disabled, so the DAC is the
  only output.

### NESPi Case+ power switch

The case keeps the Pi powered until GPIO4 goes low. RetroFlag's own script is unreliable:
after a normal shutdown the case's buttons end up in the wrong state, and their fix
(`shutdown -r`) reboots and loses power during boot. Instead, `nespi-power` does:

1. Switch **off** -> LED blinks slowly -> `dac-update` runs
2. Soloist is stopped, `sync`, then all filesystems are remounted **read-only** (sysrq `u`)
3. GPIO4 is pulled low -> the case cuts power. The SD card is read-only by then, so it can't be corrupted.

`POWEROFF_MODE=graceful` (experimental) instead runs a full `systemctl poweroff` and
lets the kernel `gpio-poweroff` overlay pull GPIO4 low at the very end.

Reset button: the LED blinks fast for 5 s, then the Pi reboots.

### GPIO pins (BCM)

| Function | USB DAC default | HAT default (IQaudIO DAC+) |
|---|---|---|
| Power switch | 3 | 17 (header pin 11) |
| Reset button | 2 | 27 (header pin 13) |
| LED | 14 | 14 |
| Power enable (case) | 4 | 4 |
| Fan | 21 | 22 (if the fan is wired to GPIO 22) |

A HAT takes GPIO 2, 3 and 18-21 (I2C and I2S), so with a HAT the installer
asks for each case and fan pin, offers the free defaults above, and rejects
any HAT pin. Without a case, `CASE=none` and the fan is off.

The wiring for the NESPi with a HAT, and which cables to move, is in
[docs/nespi-wiring.md](docs/nespi-wiring.md).

Supported HAT overlays: `iqaudio-dacplus`, `hifiberry-dacplus` (also PiFi DAC+),
`hifiberry-dac`, `hifiberry-digi` (HiFiBerry Digi+ and PiFi Digi+, S/PDIF out).

## Everyday commands

```bash
sudo dac-status                     # services, Soloist build age, what the DAC receives
journalctl -u soloist -f            # Soloist log
journalctl -u nespi-power -b -1     # what happened at the last power off
sudo dac-update --force             # update Soloist + OS now
soloist ctl -w 127.0.0.1:9090 now   # now playing
```

Settings live in `/etc/spotify-dac/config`. The API key is in
`/etc/spotify-dac/soloist.env`, mode 640. To change anything, re-run the installer.

## Uninstall

```bash
sudo bash uninstall.sh            # keeps config, API key and pairing
sudo bash uninstall.sh --purge    # removes everything
```

## Notes

- Soloist binaries are never stored in this repo; Spotify's terms forbid redistribution.
  The installer always downloads them from `soloist-builds.spotifycdn.com`.
- Keep your API key private. Don't commit `my.conf`; it is gitignored.
