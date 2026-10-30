#!/usr/bin/env bash
# bootstrap.sh - install git, fetch spotify-dac from GitHub and run the installer.
#   curl -fsSL https://raw.githubusercontent.com/VolodymyrRomanyshyn/spotify-dac/main/bootstrap.sh | sudo bash
#   sudo bash bootstrap.sh     # run again to update: pulls the newest code, then reinstalls
# Optional: SPOTIFY_DAC_BRANCH, SPOTIFY_DAC_DIR. Your settings are kept (see install.sh).
if [ -z "${BASH_VERSION:-}" ]; then exec /usr/bin/env bash "$0" "$@"; fi
set -euo pipefail

REPO_URL="https://github.com/VolodymyrRomanyshyn/spotify-dac.git"
BRANCH="${SPOTIFY_DAC_BRANCH:-main}"
OWNER_HOME="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
DEST="${SPOTIFY_DAC_DIR:-$OWNER_HOME/spotify-dac}"

log() { printf '\033[1;32m[spotify-dac]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[spotify-dac] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo bash bootstrap.sh"

if ! command -v git >/dev/null 2>&1; then
  log "Installing git"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git
fi

if [ -d "$DEST/.git" ]; then
  log "Updating $DEST ($BRANCH)"
  git -C "$DEST" fetch -q origin "$BRANCH"
  git -C "$DEST" checkout -q "$BRANCH"
  git -C "$DEST" pull -q --ff-only origin "$BRANCH"
else
  log "Cloning $REPO_URL ($BRANCH) into $DEST"
  git clone -q --branch "$BRANCH" "$REPO_URL" "$DEST"
fi

# the clone belongs to the user who ran sudo, so later git pulls work without root
if [ -n "${SUDO_USER:-}" ]; then chown -R "$SUDO_USER:$SUDO_USER" "$DEST"; fi

log "Running the installer"
cd "$DEST"
# when run as `curl ... | sudo bash`, stdin is the script itself: give the installer the terminal
if [ -r /dev/tty ]; then exec bash install.sh "$@" </dev/tty; fi
exec bash install.sh "$@"
