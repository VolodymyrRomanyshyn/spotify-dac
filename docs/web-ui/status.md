# Status page

One page that answers "is everything OK?". It shows the same values as `sudo dac-status`, in
groups, with a green, amber or red mark per group.

## Layout

Phone:

```
+------------------------------------+
| RPI-PI-DAC+            [Dark] [⚙]  |
+------------------------------------+
|  Overall: OK                 ●     |   green / amber / red
+------------------------------------+
|  Services                    ●     |
|   soloist ............ active      |
|   nespi-power ........ active      |
|   nespi-fan .......... disabled    |
|   spotify-dac-volume . active      |
|   spotify-dac-web .... active      |
+------------------------------------+
|  Soloist                     ●     |
|   Version   1.3.10.4               |
|   Build age 6 days (update at 45)  |
|   Logged in        yes             |
|   Playing          Old Town Road   |
+------------------------------------+
|  DAC (IQaudIO)               ●     |
|   Stream   44.1 kHz  S32_LE  idle  |
|   Volume   100%                    |
+------------------------------------+
|  Power and heat              ●     |
|   Undervoltage     none            |
|   Throttling       earlier         |
|   CPU temperature  55 °C           |
+------------------------------------+
|  System                      ●     |
|   Uptime       2 days              |
|   Disk         12 % used           |
|   IP           192.168.18.111      |
+------------------------------------+
|  Last update                       |
|   2026-10-27 20:25 APT finished    |
+------------------------------------+
| Home   Spotify   Radio   Config    |
+------------------------------------+
```

Desktop: groups in two columns.

## Checks and marks

| Group | Green | Amber | Red |
|---|---|---|---|
| Services | all enabled services active | a service disabled on purpose | an enabled service not active |
| Soloist | logged in, build age below the update days | build age over the update days | not running, or not logged in |
| DAC | sink present and RUNNING or idle, rate 44.1 or 48 kHz | a rate other than 44.1 or 48 kHz | DAC missing from ALSA |
| Power and heat | no undervoltage now, temperature below 70 °C | throttling seen earlier, or 70–80 °C | undervoltage now, or above 80 °C |
| System | disk below 80 % used | disk 80–90 % | disk above 90 % |

Overall = the worst mark of the groups.

## Data

| Element | Source |
|---|---|
| Services | `GET /api/status` (`systemctl is-enabled` and `is-active`) |
| Soloist | `GET /api/status` (`soloist ctl status`, `soloist ctl now --json`) |
| DAC | `GET /api/status` (ALSA `hw_params` and `status`, PipeWire sink list) |
| Power and heat | `GET /api/status` (`vcgencmd get_throttled`, `measure_temp`) |
| System | `GET /api/status` (`uptime`, `df`, IP address) |
| Last update | `GET /api/status` (last lines of `/var/log/spotify-dac-update.log`) |

## Actions

- Tap a group to expand the details (for example the full service list).
- **Refresh** button, and an automatic refresh every 10 s.
- Each failing item links to its fix: for example "Soloist not logged in" points to the Spotify page.

## States

| State | What the user sees |
|---|---|
| Loading | Skeleton groups |
| All OK | Green overall mark |
| Some amber | Amber overall mark, amber groups listed first |
| Red | Red overall mark with the failing group at the top |
| Backend unreachable | "Cannot reach the Pi", last values greyed out with their time |
