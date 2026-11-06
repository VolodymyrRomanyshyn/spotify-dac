#!/usr/bin/env bash
# Runs tests/rpi_checks.sh on a Pi over SSH.
#   DAC_HOST=rpi-2 tests/run_on_pi.sh          (DAC_HOST: an SSH alias or address; default rpi-2)
# You are asked for the Pi's sudo password once, in the terminal.
set -eu
HOST="${DAC_HOST:-rpi-2}"
HERE="$(cd "$(dirname "$0")" && pwd)"
scp -q "$HERE/rpi_checks.sh" "$HOST:/tmp/dac_rpi_checks.sh"
ssh -t "$HOST" 'sudo bash /tmp/dac_rpi_checks.sh; status=$?; rm -f /tmp/dac_rpi_checks.sh; exit $status'
