# Tests

**Unit tests** (no Pi needed):

    python3 -m unittest discover -s tests -p "test_*.py"

**Checks on a Pi** (changes the device name and volume briefly, and puts them back; needs the Pi's sudo password once):

    DAC_HOST=rpi-2 tests/run_on_pi.sh

`DAC_HOST` is the SSH alias or address of the Pi. Other settings for the Pi checks are the
environment variables `DAC_API`, `DAC_CONFIG` and `DAC_OPT` (see the top of `rpi_checks.sh`).
