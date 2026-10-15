#!/usr/bin/env bash
# uninstall.sh - remove everything install.sh set up.
#   sudo ./uninstall.sh           keep config, API key and Soloist pairing
#   sudo ./uninstall.sh --purge   remove those too
if [ -z "${BASH_VERSION:-}" ]; then exec /usr/bin/env bash "$0" "$@"; fi
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$REPO_DIR/lib/common.sh"

PURGE=no
[ "${1:-}" = "--purge" ] && PURGE=yes
require_root "$@"

UNITS=(soloist spotify-dac-boot-update spotify-dac-boot-apt nespi-power nespi-fan)
for u in "${UNITS[@]}"; do
  systemctl disable --now "$u.service" 2>/dev/null || true
  rm -f "$UNIT_DIR/$u.service"
done
systemctl daemon-reload

rm -f "$SOLOIST_BIN" "$SOLOIST_BIN.prev" \
      "$SBIN_DIR/dac-update" "$SBIN_DIR/dac-status" "$SBIN_DIR/nespi-power" "$SBIN_DIR/nespi-fan" \
      /etc/pipewire/pipewire.conf.d/50-spotify-dac.conf \
      /etc/wireplumber/wireplumber.conf.d/50-spotify-dac.conf \
      /etc/NetworkManager/conf.d/99-spotify-dac-wifi.conf

if [ "$(bootcfg_set_block "")" = changed ]; then
  log "Removed managed block from $(boot_config_path) (reboot to apply)"
fi

if [ "$PURGE" = yes ]; then
  log "Purging config, API key, state and the '$SOLOIST_USER' user"
  loginctl disable-linger "$SOLOIST_USER" 2>/dev/null || true
  userdel -r "$SOLOIST_USER" 2>/dev/null || true
  rm -rf "$CONF_DIR" "$STATE_DIR" /var/lib/soloist /var/cache/soloist /var/log/spotify-dac-update.log
else
  log "Kept $CONF_DIR, /var/lib/soloist (pairing) and user '$SOLOIST_USER'. Use --purge to remove."
fi
log "Uninstalled. Packages (pipewire, wireplumber, ...) were left installed."
