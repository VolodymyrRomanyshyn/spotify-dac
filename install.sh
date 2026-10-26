#!/usr/bin/env bash
# install.sh - Spotify Soloist streamer for Raspberry Pi OS Lite (Trixie, 64-bit)
#
#   sudo ./install.sh                     interactive (whiptail dialogs)
#   sudo ./install.sh --config my.conf    unattended, answers from file (see config.example)
#
# Safe to re-run: current answers in /etc/spotify-dac/config become the defaults.
if [ -z "${BASH_VERSION:-}" ]; then exec /usr/bin/env bash "$0" "$@"; fi
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
. "$REPO_DIR/lib/common.sh"

ANSWERS_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --config) ANSWERS_FILE="$2"; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done
INTERACTIVE=yes
[ -n "$ANSWERS_FILE" ] && INTERACTIVE=no

require_root "$@"

# --- preflight ----------------------------------------------------------------

# shellcheck disable=SC1091
. /etc/os-release
if [ "${VERSION_CODENAME:-}" != "trixie" ]; then
  warn "Detected '${PRETTY_NAME:-unknown}'. Soloist is tested on Raspberry Pi OS based on Debian Trixie."
fi
[ "$(uname -m)" = "aarch64" ] || warn "Not a 64-bit OS ($(uname -m)). Use Raspberry Pi OS Lite (64-bit)."
if [ "$INTERACTIVE" = yes ] && ! command -v whiptail >/dev/null; then
  apt-get install -y -q whiptail
fi

# --- defaults: built-in < existing install < answers file ---------------------

DEVICE_NAME="$(hostname)"
AUDIO_OUTPUT="usb"                 # usb | hat
AUDIO_HAT_OVERLAY=""               # e.g. iqaudio-dacplus (only for AUDIO_OUTPUT=hat)
CASE="none"                        # nespi | none
FAN_ENABLED="yes"
POWEROFF_MODE="hardcut"            # hardcut | graceful
UPDATE_TRIGGER=""                  # poweroff | boot | none   (default depends on CASE)
SOLOIST_UPDATE_AFTER_DAYS="45"
APT_UPGRADE="yes"
APT_UPGRADE_AFTER_DAYS=""          # default depends on UPDATE_TRIGGER
UPDATE_TIMEOUT_MINUTES="30"
SOLOIST_WS_PORT="9090"
WIFI_POWERSAVE_OFF="yes"
GPIO_CHIP="/dev/gpiochip0"
POWER_PIN="3"; RESET_PIN="2"; LED_PIN="14"; POWER_EN_PIN="4"
SAFE_SHUTDOWN="yes"                # yes: power switch and buttons work | no: case stays powered, switch ignored
IDLE_SHUTDOWN_MINUTES="30"         # power off after N minutes with no audio playing (0 = never)
HOLD_SECONDS="1"; SYNC_SECONDS="3"; ENABLE_RESET="yes"
FAN_PIN="21"; FAN_TEMP_ON="75"; FAN_TEMP_OFF="55"; FAN_STARTUP_SECONDS="5"; FAN_POLL_SECONDS="5"
SOLOIST_API_KEY=""

# shellcheck disable=SC1090
[ -f "$CONFIG_FILE" ] && . "$CONFIG_FILE"
# shellcheck disable=SC1090
[ -f "$SECRET_FILE" ] && . "$SECRET_FILE"
STORED_API_KEY="$SOLOIST_API_KEY"
if [ -n "$ANSWERS_FILE" ]; then
  [ -f "$ANSWERS_FILE" ] || die "Answers file not found: $ANSWERS_FILE"
  # shellcheck disable=SC1090
  . "$ANSWERS_FILE"
  # an empty key in the answers file means "keep the one already installed"
  [ -n "$SOLOIST_API_KEY" ] || SOLOIST_API_KEY="$STORED_API_KEY"
fi

# --- questions ----------------------------------------------------------------

usb_cards_desc() {   # "Topping E30, ..." for USB cards ALSA sees right now
  local c names=()
  for c in /proc/asound/card[0-9]*; do
    [ -f "$c/usbid" ] && names+=("$(cat "$c/id")")
  done
  local IFS=', '; echo "${names[*]:-}"
}

# GPIO used by the HAT (I2C 2 and 3, I2S 18-21). Only a HAT takes these pins.
is_hat_pin() {
  [ "$AUDIO_OUTPUT" = hat ] || return 1
  case "$1" in 2|3|18|19|20|21) return 0 ;; *) return 1 ;; esac
}

# Move the USB defaults that a HAT takes to free pins
hat_pin_defaults() {
  [ "$AUDIO_OUTPUT" = hat ] || return 0
  [ "$POWER_PIN" = 3 ] && POWER_PIN=17
  [ "$RESET_PIN" = 2 ] && RESET_PIN=27
  [ "$FAN_PIN" = 21 ] && FAN_PIN=22
  return 0
}

# ask_pin "label" current -> a BCM number that is usable with this sound card
ask_pin() {
  local label="$1" val
  while :; do
    val="$(ask_input "$label\n\nBCM GPIO number (0-27).$( [ "$AUDIO_OUTPUT" = hat ] && echo ' With this HAT, GPIO 2, 3 and 18-21 are taken.')" "$2")" || die "Cancelled"
    if [[ "$val" =~ ^[0-9]+$ ]] && [ "$val" -le 27 ] && ! is_hat_pin "$val"; then
      echo "$val"; return 0
    fi
    msg "GPIO '$val' can't be used here."
  done
}

ask_questions() {
  local usb hw

  DEVICE_NAME="$(ask_input "Name shown in the Spotify app (Spotify Connect device):" "$DEVICE_NAME")"

  usb="$(usb_cards_desc)"
  local cur="usb"
  [ "$AUDIO_OUTPUT" = hat ] && cur="$AUDIO_HAT_OVERLAY"
  hw="$(ask_menu "Sound card. Onboard jack and HDMI audio will be disabled." "$cur" \
        usb                "USB DAC (Topping E30 etc.)${usb:+ - detected: $usb}" \
        iqaudio-dacplus    "IQaudIO DAC+ / Raspberry Pi DAC+ (I2S HAT)" \
        hifiberry-dacplus  "HiFiBerry DAC+ / DAC2 Pro, PiFi DAC+ (I2S HAT)" \
        hifiberry-dac      "HiFiBerry DAC / MiniAmp (I2S HAT)" \
        hifiberry-digi     "HiFiBerry Digi+ / PiFi Digi+ (S/PDIF HAT)")"
  if [ "$hw" = usb ]; then AUDIO_OUTPUT=usb; AUDIO_HAT_OVERLAY=""
  else AUDIO_OUTPUT=hat; AUDIO_HAT_OVERLAY="$hw"; fi

  # a HAT takes GPIO 2, 3 and 18-21, so the case and fan must use other pins
  if [ "$AUDIO_OUTPUT" = hat ]; then
    msg "This HAT uses GPIO 2, 3 and 18-21.\n\nThe NESPi Case+ and fan can use other pins. The next screens offer free defaults; change them if your wiring is different."
  fi
  CASE="$(ask_menu "Case / GPIO control:" "$CASE" \
        nespi "RetroFlag NESPi Case+ (power/reset buttons, LED, GPIO fan)" \
        none  "No GPIO control")"

  if [ "$CASE" = nespi ]; then
    hat_pin_defaults
    SAFE_SHUTDOWN="$(ask_yesno "Use the NESPi power switch and buttons for safe shutdown?\n(no: the case stays powered, switch and buttons are ignored, updates run at boot)" "$SAFE_SHUTDOWN")"
    if [ "$SAFE_SHUTDOWN" = yes ]; then
      POWEROFF_MODE="$(ask_menu "What happens when the power switch is turned OFF (after updates):" "$POWEROFF_MODE" \
            hardcut  "Stop, sync, read-only remount, cut power via GPIO $POWER_EN_PIN (proven)" \
            graceful "Full systemctl poweroff, kernel cuts power (EXPERIMENTAL)")"
      POWER_PIN="$(ask_pin "GPIO for the power switch" "$POWER_PIN")"
      RESET_PIN="$(ask_pin "GPIO for the reset button" "$RESET_PIN")"
      LED_PIN="$(ask_pin "GPIO for the case LED" "$LED_PIN")"
    fi
    POWER_EN_PIN="$(ask_pin "GPIO that keeps the case powered (power enable)" "$POWER_EN_PIN")"
    FAN_ENABLED="$(ask_yesno "Control a fan with the case?\n(on at ${FAN_TEMP_ON}C, off at ${FAN_TEMP_OFF}C, ${FAN_STARTUP_SECONDS}s spin at boot)" "$FAN_ENABLED")"
    if [ "$FAN_ENABLED" = yes ]; then
      FAN_PIN="$(ask_pin "GPIO for the fan" "$FAN_PIN")"
    fi
  fi

  if [ "$CASE" = nespi ] && [ "$SAFE_SHUTDOWN" = yes ]; then
    UPDATE_TRIGGER="$(ask_menu "When should updates run?" "${UPDATE_TRIGGER:-poweroff}" \
          poweroff "When the power switch is turned off (zero maintenance)" \
          boot     "At power on, before Soloist starts" \
          none     "Only when the Soloist build has expired")"
  else
    # Without the case there is no power-switch hook, so boot is the only
    # trigger that keeps the box zero-maintenance.
    UPDATE_TRIGGER=boot
  fi

  if [ "$UPDATE_TRIGGER" != none ]; then
    SOLOIST_UPDATE_AFTER_DAYS="$(ask_input "Update Soloist once its build is at least N days old.\nBuilds expire after 90 days. Allowed: 1-89." "$SOLOIST_UPDATE_AFTER_DAYS")"
    APT_UPGRADE="$(ask_yesno "Also run 'apt full-upgrade' for the OS during updates?" "$APT_UPGRADE")"
    if [ "$APT_UPGRADE" = yes ]; then
      local def_apt="${APT_UPGRADE_AFTER_DAYS:-}"
      [ -n "$def_apt" ] || { [ "$UPDATE_TRIGGER" = poweroff ] && def_apt=0 || def_apt=7; }
      APT_UPGRADE_AFTER_DAYS="$(ask_input "Run the OS upgrade at most every N days (0 = every time):" "$def_apt")"
    fi
  fi

  IDLE_SHUTDOWN_MINUTES="$(ask_input "Power off after how many minutes with no audio playing?\n(0 = never). Playing means the DAC is streaming; paused or stopped music counts as idle." "$IDLE_SHUTDOWN_MINUTES")"

  local key
  if [ -n "$SOLOIST_API_KEY" ]; then
    key="$(ask_password "Soloist API key (from developer.spotify.com > Soloist).\n\nA key is already stored - leave empty to keep it.")"
  else
    key="$(ask_password "Soloist API key (from developer.spotify.com > Soloist).\n\nLeave empty to add it later (re-run the installer).")"
  fi
  if [ -n "$key" ]; then SOLOIST_API_KEY="$key"; fi
}

validate() {
  DEVICE_NAME="$(printf '%s' "$DEVICE_NAME" | tr -d '"\\$`')"
  [ -n "$DEVICE_NAME" ] || die "Device name is empty"
  case "$AUDIO_OUTPUT" in usb|hat) ;; *) die "AUDIO_OUTPUT must be usb or hat" ;; esac
  [ "$AUDIO_OUTPUT" = hat ] && [ -z "$AUDIO_HAT_OVERLAY" ] && die "AUDIO_HAT_OVERLAY is required for a HAT"
  # PipeWire sink name prefix of the DAC, used by dac-sink-volume to make it the default
  if [ "$AUDIO_OUTPUT" = hat ]; then DAC_SINK_PATTERN="alsa_output.platform-soc_sound"
  else DAC_SINK_PATTERN="alsa_output.usb-"; fi
  case "$CASE" in nespi|none) ;; *) die "CASE must be nespi or none" ;; esac
  case "$FAN_ENABLED" in yes|no) ;; *) die "FAN_ENABLED must be yes or no (got: $(printf '%q' "$FAN_ENABLED"))" ;; esac
  case "$APT_UPGRADE" in yes|no) ;; *) die "APT_UPGRADE must be yes or no (got: $(printf '%q' "$APT_UPGRADE"))" ;; esac
  case "$POWEROFF_MODE" in hardcut|graceful) ;; *) die "POWEROFF_MODE must be hardcut or graceful" ;; esac
  case "$SAFE_SHUTDOWN" in yes|no) ;; *) die "SAFE_SHUTDOWN must be yes or no" ;; esac
  # no power switch to hook: updates can only run at boot
  [ "$SAFE_SHUTDOWN" = no ] && UPDATE_TRIGGER=boot
  [[ "$IDLE_SHUTDOWN_MINUTES" =~ ^[0-9]+$ ]] && [ "$IDLE_SHUTDOWN_MINUTES" -le 1440 ] \
    || die "IDLE_SHUTDOWN_MINUTES must be 0-1440"
  if [ "$CASE" = nespi ] && [ "$SAFE_SHUTDOWN" = no ] && [ "$IDLE_SHUTDOWN_MINUTES" -gt 0 ]; then
    warn "Idle power-off needs the case's power switch path; disabled with SAFE_SHUTDOWN=no"
    IDLE_SHUTDOWN_MINUTES=0
  fi
  if [ "$CASE" = nespi ]; then
    local used=("$POWER_EN_PIN") pin i j
    [ "$SAFE_SHUTDOWN" = yes ] && used+=("$POWER_PIN" "$RESET_PIN" "$LED_PIN")
    [ "$FAN_ENABLED" = yes ] && used+=("$FAN_PIN")
    for pin in "${used[@]}"; do
      [[ "$pin" =~ ^[0-9]+$ ]] && [ "$pin" -le 27 ] || die "GPIO '$pin' is not a valid BCM number (0-27)"
      is_hat_pin "$pin" && die "GPIO $pin is used by the HAT (I2C/I2S). Choose another pin for the case or fan."
    done
    for ((i = 0; i < ${#used[@]}; i++)); do
      for ((j = i + 1; j < ${#used[@]}; j++)); do
        [ "${used[i]}" = "${used[j]}" ] && die "GPIO ${used[i]} is assigned twice"
      done
    done
  fi
  [ -n "$UPDATE_TRIGGER" ] || { [ "$CASE" = nespi ] && UPDATE_TRIGGER=poweroff || UPDATE_TRIGGER=boot; }
  case "$UPDATE_TRIGGER" in poweroff|boot|none) ;; *) die "UPDATE_TRIGGER must be poweroff, boot or none" ;; esac
  if [ "$CASE" != nespi ] && [ "$UPDATE_TRIGGER" != boot ]; then
    warn "UPDATE_TRIGGER=$UPDATE_TRIGGER needs CASE=nespi; without the case updates run at boot"
    UPDATE_TRIGGER=boot
  fi
  [ -n "$APT_UPGRADE_AFTER_DAYS" ] || { [ "$UPDATE_TRIGGER" = poweroff ] && APT_UPGRADE_AFTER_DAYS=0 || APT_UPGRADE_AFTER_DAYS=7; }
  [[ "$SOLOIST_UPDATE_AFTER_DAYS" =~ ^[0-9]+$ ]] && [ "$SOLOIST_UPDATE_AFTER_DAYS" -ge 1 ] && [ "$SOLOIST_UPDATE_AFTER_DAYS" -le 89 ] \
    || die "SOLOIST_UPDATE_AFTER_DAYS must be 1-89"
  [[ "$APT_UPGRADE_AFTER_DAYS" =~ ^[0-9]+$ ]] || die "APT_UPGRADE_AFTER_DAYS must be a number"
  SOLOIST_API_KEY="$(printf '%s' "$SOLOIST_API_KEY" | tr -d '[:space:]"\\$`')"
}

confirm() {
  local hw="USB DAC"; [ "$AUDIO_OUTPUT" = hat ] && hw="HAT ($AUDIO_HAT_OVERLAY)"
  local cs="none"; [ "$CASE" = nespi ] && cs="NESPi Case+ (fan: $FAN_ENABLED, power-off: $POWEROFF_MODE)"
  whiptail --title "$WT_TITLE" --yesno "Install with these settings?

  Device name : $DEVICE_NAME
  Sound card  : $hw
  Case        : $cs
  Updates     : $UPDATE_TRIGGER (Soloist after ${SOLOIST_UPDATE_AFTER_DAYS}d, apt: $APT_UPGRADE every ${APT_UPGRADE_AFTER_DAYS}d)
  API key     : $([ -n "$SOLOIST_API_KEY" ] && echo set || echo 'NOT SET')" 16 78 || die "Cancelled"
}

# --- install steps ------------------------------------------------------------

install_packages() {
  log "Installing packages"
  local pkgs=(curl ca-certificates alsa-utils pipewire pipewire-pulse wireplumber dbus-user-session pulseaudio-utils libpulse0)
  [ "$CASE" = nespi ] && pkgs+=(python3 python3-libgpiod)
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${pkgs[@]}"
}

write_config() {
  log "Writing $CONFIG_FILE"
  install -d -m 755 "$CONF_DIR"
  cat > "$CONFIG_FILE" <<EOF
# /etc/spotify-dac/config - written by install.sh, re-run the installer to change.
# Read by bash scripts and by systemd (EnvironmentFile).
DEVICE_NAME="$DEVICE_NAME"
AUDIO_OUTPUT="$AUDIO_OUTPUT"
AUDIO_HAT_OVERLAY="$AUDIO_HAT_OVERLAY"
DAC_SINK_PATTERN="$DAC_SINK_PATTERN"
CASE="$CASE"
FAN_ENABLED="$FAN_ENABLED"
POWEROFF_MODE="$POWEROFF_MODE"
UPDATE_TRIGGER="$UPDATE_TRIGGER"
SOLOIST_UPDATE_AFTER_DAYS="$SOLOIST_UPDATE_AFTER_DAYS"
APT_UPGRADE="$APT_UPGRADE"
APT_UPGRADE_AFTER_DAYS="$APT_UPGRADE_AFTER_DAYS"
UPDATE_TIMEOUT_MINUTES="$UPDATE_TIMEOUT_MINUTES"
SOLOIST_WS_PORT="$SOLOIST_WS_PORT"
WIFI_POWERSAVE_OFF="$WIFI_POWERSAVE_OFF"
GPIO_CHIP="$GPIO_CHIP"
SAFE_SHUTDOWN="$SAFE_SHUTDOWN"
IDLE_SHUTDOWN_MINUTES="$IDLE_SHUTDOWN_MINUTES"
POWER_PIN="$POWER_PIN"
RESET_PIN="$RESET_PIN"
LED_PIN="$LED_PIN"
POWER_EN_PIN="$POWER_EN_PIN"
HOLD_SECONDS="$HOLD_SECONDS"
SYNC_SECONDS="$SYNC_SECONDS"
ENABLE_RESET="$ENABLE_RESET"
FAN_PIN="$FAN_PIN"
FAN_TEMP_ON="$FAN_TEMP_ON"
FAN_TEMP_OFF="$FAN_TEMP_OFF"
FAN_STARTUP_SECONDS="$FAN_STARTUP_SECONDS"
FAN_POLL_SECONDS="$FAN_POLL_SECONDS"
EOF
  chmod 644 "$CONFIG_FILE"
}

setup_user() {
  if ! id "$SOLOIST_USER" >/dev/null 2>&1; then
    log "Creating system user '$SOLOIST_USER'"
    useradd --system --create-home --home-dir "/home/$SOLOIST_USER" --shell /usr/sbin/nologin \
            --groups audio "$SOLOIST_USER"
  else
    usermod -aG audio "$SOLOIST_USER"
  fi
  SOLOIST_UID="$(id -u "$SOLOIST_USER")"

  # API key: readable by root and the soloist group only, never in the repo
  umask 077
  printf 'SOLOIST_API_KEY="%s"\n' "$SOLOIST_API_KEY" > "$SECRET_FILE"
  umask 022
  chown root:"$SOLOIST_USER" "$SECRET_FILE"
  chmod 640 "$SECRET_FILE"

  # lingering user session = PipeWire runs headless, without anyone logged in
  loginctl enable-linger "$SOLOIST_USER"
  systemctl start "user@$SOLOIST_UID.service"
}

as_soloist() {
  runuser -u "$SOLOIST_USER" -- env XDG_RUNTIME_DIR="/run/user/$SOLOIST_UID" "$@"
}

install_files() {
  log "Installing scripts and units"
  install -d -m 755 "$STATE_DIR"
  install -m 755 "$REPO_DIR/bin/dac-update" "$REPO_DIR/bin/dac-status" "$REPO_DIR/bin/dac-sink-volume" "$REPO_DIR/bin/dac-idle" "$SBIN_DIR/"
  if [ "$CASE" = nespi ]; then
    install -m 755 "$REPO_DIR/bin/nespi-power" "$REPO_DIR/bin/nespi-fan" "$SBIN_DIR/"
  fi
  sed "s/@UID@/$SOLOIST_UID/g" "$REPO_DIR/files/systemd/soloist.service" > "$UNIT_DIR/soloist.service"
  sed "s/@UID@/$SOLOIST_UID/g" "$REPO_DIR/files/systemd/spotify-dac-volume.service" > "$UNIT_DIR/spotify-dac-volume.service"
  local u
  for u in spotify-dac-boot-update spotify-dac-boot-apt spotify-dac-idle nespi-power nespi-fan; do
    install -m 644 "$REPO_DIR/files/systemd/$u.service" "$UNIT_DIR/"
  done

  install -D -m 644 "$REPO_DIR/files/pipewire/50-spotify-dac.conf" /etc/pipewire/pipewire.conf.d/50-spotify-dac.conf
  install -D -m 644 "$REPO_DIR/files/wireplumber/50-spotify-dac.conf" /etc/wireplumber/wireplumber.conf.d/50-spotify-dac.conf
  if [ "$WIFI_POWERSAVE_OFF" = yes ] && [ -d /etc/NetworkManager/conf.d ]; then
    install -m 644 "$REPO_DIR/files/networkmanager/99-spotify-dac-wifi.conf" /etc/NetworkManager/conf.d/
  fi
}

configure_boot() {
  local block="" changed
  block+="# onboard headphone audio off - the DAC is the only output"$'\n'
  block+="dtparam=audio=off"
  if [ "$AUDIO_OUTPUT" = hat ]; then
    block+=$'\n'"dtoverlay=$AUDIO_HAT_OVERLAY"
  fi
  if [ "$CASE" = nespi ] && [ "$POWEROFF_MODE" = graceful ]; then
    block+=$'\n'"# NESPi Case+: hold GPIO$POWER_EN_PIN high while running, pull it low at the end of poweroff"
    block+=$'\n'"dtoverlay=gpio-poweroff,gpiopin=$POWER_EN_PIN,active_low=1"
  fi
  changed="$(bootcfg_set_block "$block")"
  if [ "$changed" = changed ]; then
    REBOOT_NEEDED=yes
    log "Updated $(boot_config_path) (reboot required)"
  fi
}

disable_legacy() {
  local u
  for u in librespot-native raspotify raspotify-docker-start gpio-safe-shutdown gpio-fan-control; do
    if systemctl list-unit-files "$u.service" >/dev/null 2>&1 && systemctl is-enabled --quiet "$u.service" 2>/dev/null; then
      log "Disabling old service $u"
      systemctl disable --now "$u.service" || true
    fi
  done
  if [ -f /etc/asound.conf ] && grep -q 'type hw card' /etc/asound.conf; then
    log "Moving old /etc/asound.conf (forced hw device) aside - PipeWire owns the DAC now"
    mv /etc/asound.conf /etc/asound.conf.spotify-dac.old
  fi
}

configure_units() {
  log "Enabling services"
  systemctl daemon-reload
  as_soloist systemctl --user enable pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1 || true
  as_soloist systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service >/dev/null 2>&1 || true

  systemctl enable soloist.service
  if [ "$UPDATE_TRIGGER" = boot ]; then
    systemctl enable spotify-dac-boot-update.service
    if [ "$APT_UPGRADE" = yes ]; then systemctl enable spotify-dac-boot-apt.service
    else systemctl disable spotify-dac-boot-apt.service 2>/dev/null || true; fi
  else
    systemctl disable spotify-dac-boot-update.service spotify-dac-boot-apt.service 2>/dev/null || true
  fi

  if [ "$CASE" = nespi ]; then
    systemctl enable nespi-power.service
    systemctl restart nespi-power.service
    if [ "$FAN_ENABLED" = yes ]; then systemctl enable nespi-fan.service; systemctl restart nespi-fan.service
    else systemctl disable --now nespi-fan.service 2>/dev/null || true; fi
  else
    systemctl disable --now nespi-power.service nespi-fan.service 2>/dev/null || true
  fi

  # PipeWire resets the DAC sink to 0.40 on every start; make it the default at 100% (bit-perfect)
  systemctl enable spotify-dac-volume.service

  # idle power-off without the case (with the case, nespi-power does it)
  if [ "$CASE" != nespi ] && [ "$IDLE_SHUTDOWN_MINUTES" -gt 0 ]; then
    systemctl enable spotify-dac-idle.service && systemctl restart spotify-dac-idle.service
  else
    systemctl disable --now spotify-dac-idle.service 2>/dev/null || true
  fi
}

install_soloist() {
  log "Installing Spotify Soloist (downloaded from Spotify's CDN)"
  "$SBIN_DIR/dac-update" --trigger install --only soloist || true
  [ -x "$SOLOIST_BIN" ] || die "Soloist download failed - check network and re-run"
  local missing
  missing="$(ldd "$SOLOIST_BIN" 2>/dev/null | grep 'not found' || true)"
  [ -z "$missing" ] || warn "Soloist is missing libraries:\n$missing"
  log "$("$SOLOIST_BIN" --version 2>&1 | head -n1)"
}

# --- main ---------------------------------------------------------------------

REBOOT_NEEDED=no
[ "$INTERACTIVE" = yes ] && ask_questions
validate
[ "$INTERACTIVE" = yes ] && confirm

install_packages
write_config
setup_user
install_files
disable_legacy
configure_boot
configure_units
install_soloist

if [ -n "$SOLOIST_API_KEY" ]; then
  [ "$REBOOT_NEEDED" = yes ] || systemctl restart soloist.service
else
  systemctl stop soloist.service 2>/dev/null || true
  warn "No Soloist API key set: soloist will not work until you re-run: sudo $0"
fi

if [ "$REBOOT_NEEDED" = no ]; then
  systemctl restart spotify-dac-volume.service || warn "DAC volume service did not set 100%: journalctl -u spotify-dac-volume"
fi

echo
log "Done."
log "Pair: open the Spotify app on the same network -> devices -> '$DEVICE_NAME'."
log "Check: sudo dac-status    Logs: journalctl -u soloist -f"
if [ "$REBOOT_NEEDED" = yes ]; then
  if [ "$INTERACTIVE" = yes ] && [ "$(ask_yesno "Boot configuration changed. Reboot now?" yes)" = yes ]; then
    systemctl reboot
  fi
  warn "Reboot required to apply boot configuration: sudo reboot"
fi
