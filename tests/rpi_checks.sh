#!/usr/bin/env bash
# Checks on a running Spotify DAC. Runs on the Pi as root: sudo bash rpi_checks.sh
# Parameters (environment variables, all optional):
#   DAC_API     web address on the Pi      (default https://127.0.0.1:8443)
#   DAC_CONFIG  config file                (default /etc/spotify-dac/config)
#   DAC_OPT     installed web folder       (default /opt/spotify-dac)
# Changes the device name and the default volume only briefly, and puts them back.
set -u
API="${DAC_API:-https://127.0.0.1:8443}"
CFG="${DAC_CONFIG:-/etc/spotify-dac/config}"
OPT="${DAC_OPT:-/opt/spotify-dac}"
UNIT=/etc/systemd/system/soloist.service
pass=0; fail=0
ok()  { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }
post() { curl -sk -X POST -H "Content-Type: application/json" -d "$1" "$API$2"; }
setting() { grep "^$1=" "$CFG" | cut -d'"' -f2; }

name=$(setting DEVICE_NAME)
volume=$(setting DEFAULT_VOLUME)

echo "== 1. a failed Soloist restart is reported, not shown as success"
if [ -e "$UNIT" ]; then
  boot_setting=$(systemctl is-enabled soloist.service 2>/dev/null)   # masking clears it: put it back afterwards
  mv "$UNIT" "$UNIT.keep"             # systemd only masks a unit when no unit file of that name is in the way
  systemctl mask soloist.service >/dev/null 2>&1
  out=$(post "{\"DEVICE_NAME\":\"$name\"}" /api/config)
  echo "   answer: $out"
  echo "$out" | grep -q "Spotify restart failed" && ok "failure text shown" || bad "failure text not shown"
  systemctl unmask soloist.service >/dev/null 2>&1
  mv "$UNIT.keep" "$UNIT"
  systemctl daemon-reload
  [ "$boot_setting" = enabled ] && systemctl enable soloist.service >/dev/null 2>&1
  systemctl restart soloist.service; sleep 3
  systemctl is-active soloist.service | grep -q "^active$" && ok "Soloist running again" || bad "Soloist not running after restore"
  [ "$(systemctl is-enabled soloist.service 2>/dev/null)" = "$boot_setting" ] \
    && ok "Soloist start at boot restored ($boot_setting)" || bad "Soloist start at boot not restored"
else
  bad "unit file $UNIT not found: test 1 skipped"
fi

echo "== 2. catalog update keeps the radio catalogs"
before=$(ls "$OPT/radio" | wc -l)
out=$(post '{"confirm":true}' /api/code/update)
echo "   answer: $out"
echo "$out" | grep -q '"ok": true' && ok "update accepted" || bad "update refused"
sleep 10
[ -d "$OPT/radio" ] && [ "$(ls "$OPT/radio" | wc -l)" = "$before" ] \
  && ok "radio catalogs present ($before files)" || bad "radio catalogs missing or changed"
[ ! -e "$OPT/radio.new" ] && [ ! -e "$OPT/radio.old" ] \
  && ok "no leftover .new or .old folder" || bad "leftover .new or .old folder"
systemctl is-active spotify-dac-web | grep -q "^active$" && ok "web service back after update" || bad "web service not back"

echo "== 3. overlapping saves do not lose other settings"
keys_before=$(cut -d= -f1 "$CFG" | sort)
for i in $(seq 1 20); do
  post "{\"DEFAULT_VOLUME\":\"$((25 + i % 2))\"}" /api/config >/dev/null &
done
wait
keys_after=$(cut -d= -f1 "$CFG" | sort)
[ "$keys_before" = "$keys_after" ] && ok "every setting still in the config file" || bad "a setting was lost"
[ "$(grep -c '^DEFAULT_VOLUME=' "$CFG")" = 1 ] && ok "one DEFAULT_VOLUME line" || bad "DEFAULT_VOLUME written twice"
[ -e "$CFG.lock" ] && ok "lock file used" || bad "lock file missing"
post "{\"DEFAULT_VOLUME\":\"$volume\"}" /api/config >/dev/null

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" = 0 ]
