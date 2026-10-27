# NESPi Case+ wiring

How the RetroFlag NESPi Case+ harness connects to the Pi header, which GPIO
each wire carries, and what to move when a HAT (IQaudIO DAC+) is installed.

The colours and pin numbers below come from photos of the harness on a
Pi with an IQaudIO DAC+ board. Check each wire with a continuity test
before you move it (see [Verify a wire](#verify-a-wire)).

## Header pins used by the harness

Pin numbers are the Pi's 40-pin header, counted from pin 1 at the top left.
Odd pins are on one row, even pins on the other.

| Header pin | Signal | GPIO | Harness colour | Used by |
|---|---|---|---|---|
| 1 | 3.3 V | - | none | - |
| 2 | 5 V | - | red | case power |
| 3 | SDA (I2C) | 2 | orange | reset button |
| 4 | 5 V | - | none | - |
| 5 | SCL (I2C) | 3 | yellow | power switch |
| 6 | GND | - | black-red | case ground |
| 7 | GPIO 4 | 4 | green | power enable |
| 8 | TXD | 14 | white | LED |

The harness has no fan wire, so GPIO 21 (header pin 40) is not used.

## Conflict with the IQaudIO DAC+

The DAC+ takes GPIO 2 and 3 for I2C, and GPIO 18-21 for I2S. Its board
sits on the header, so the orange (GPIO 2) and yellow (GPIO 3) wires
can't stay there.

| Cable | Move from | Move to | Result |
|---|---|---|---|
| Orange (reset) | header pin 3 (GPIO 2) | header pin 13 (GPIO 27) | free pin, same odd row |
| Yellow (power switch) | header pin 5 (GPIO 3) | header pin 11 (GPIO 17) | free pin, same odd row |
| Red, black-red, green, white | no change | no change | GPIO 4 and 14 are not used by the DAC+ |

If the case runs with `SAFE_SHUTDOWN=no`, the installer only holds GPIO 4
high. The reset, switch and LED wires are then unused. Orange and yellow can
stay disconnected, and no move is needed.

## Installer answers for a HAT with the case

| Question | Answer |
|---|---|
| Sound card | HAT, `iqaudio-dacplus` |
| Case | NESPi Case+ |
| Safe shutdown | yes (switch, reset and LED work) or no (switch ignored) |
| Power switch GPIO | 17 |
| Reset GPIO | 27 |
| LED GPIO | 14 |
| Power enable GPIO | 4 |
| Fan | no (the harness has no fan wire) |

## Verify a wire

With the Pi powered off, touch one probe on the wire's end at the case side
and the other on the header pin you expect, and check for a beep. Do this for
each wire before moving it. Don't connect a wire to 5 V or ground by mistake.

## Open items

- The GPIO 17 and 27 pins are not yet checked against the IQaudIO DAC+
  overlay. Run `dtc -I dtb -O dts /boot/firmware/overlays/iqaudio-dacplus.dtbo | grep -i gpio`
  on the Pi to confirm.
- GPIO 4 is GPCLK0 by default, and the case uses it as a plain output. Check
  with `pinctrl get 4` after install.
