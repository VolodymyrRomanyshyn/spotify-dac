"""Reset button rules for the NESPi case: a quick press reboots, a 5-second hold starts the hotspot.

Pure timing rules, tested without a button. The power script (bin/nespi-power) uses them when the
reset button is pressed and released.
"""

HOTSPOT_HOLD_SECONDS = 5.0


def reset_action(held_seconds, still_held):
    """What to do for a press that has lasted held_seconds.
    While still held: "hotspot" once the hold reaches 5 seconds, otherwise "wait".
    After release: "reboot" for a press shorter than 5 seconds, otherwise nothing more ("none")."""
    if still_held:
        return "hotspot" if held_seconds >= HOTSPOT_HOLD_SECONDS else "wait"
    return "reboot" if held_seconds < HOTSPOT_HOLD_SECONDS else "none"


# LED patterns: a list of (on seconds, off seconds), repeated
LED_REBOOT = [(0.2, 0.2)]                  # fast blink while the reboot is prepared
LED_HOLDING = [(0.2, 0.2)]                 # steady blink while the button is held, before 5 s
LED_HOTSPOT_STARTING = [(1.0, 0.0)]        # solid for 1 second at the 5-second mark
LED_HOTSPOT_ON = [(0.1, 0.1), (0.1, 0.7)]  # two short flashes and a pause, until a network connects
