# lib/common.sh - shared helpers for install.sh / uninstall.sh (sourced, not executed)

CONF_DIR="/etc/spotify-dac"
CONFIG_FILE="$CONF_DIR/config"
SECRET_FILE="$CONF_DIR/soloist.env"
STATE_DIR="/var/lib/spotify-dac"
SOLOIST_USER="soloist"
SOLOIST_BIN="/usr/local/bin/soloist"
SBIN_DIR="/usr/local/sbin"
UNIT_DIR="/etc/systemd/system"

BOOTCFG_BEGIN="# >>> spotify-dac (managed block, edit via install.sh) >>>"
BOOTCFG_END="# <<< spotify-dac <<<"

log()  { printf '\033[1;32m[spotify-dac]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[spotify-dac] WARNING:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[spotify-dac] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "Run with sudo: sudo $0 $*"
}

boot_config_path() {
  if [ -f /boot/firmware/config.txt ]; then echo /boot/firmware/config.txt
  elif [ -f /boot/config.txt ]; then echo /boot/config.txt
  else die "config.txt not found in /boot/firmware or /boot"
  fi
}

# Replace (or remove, when $1 is empty) our managed block at the end of config.txt.
# Prints "changed" when the file content changed.
bootcfg_set_block() {
  local block="$1" cfg tmp before after
  cfg="$(boot_config_path)"
  [ -f "$cfg.spotify-dac.bak" ] || cp -p "$cfg" "$cfg.spotify-dac.bak"
  before="$(sha256sum "$cfg" | cut -d' ' -f1)"
  tmp="$(mktemp)"
  awk -v b="$BOOTCFG_BEGIN" -v e="$BOOTCFG_END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip   { print }
  ' "$cfg" > "$tmp"
  # trim trailing blank lines left behind by a removed block
  sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$tmp"
  if [ -n "$block" ]; then
    printf '\n%s\n[all]\n%s\n%s\n' "$BOOTCFG_BEGIN" "$block" "$BOOTCFG_END" >> "$tmp"
  fi
  cat "$tmp" > "$cfg"
  rm -f "$tmp"
  after="$(sha256sum "$cfg" | cut -d' ' -f1)"
  [ "$before" != "$after" ] && echo changed || true
}

# --- whiptail wrappers (all return the answer on stdout) ---
WT_TITLE="Spotify DAC installer"

ask_input() {   # ask_input "question" "default"
  whiptail --title "$WT_TITLE" --inputbox "$1" 10 70 "$2" 3>&1 1>&2 2>&3
}

ask_password() {   # ask_password "question"
  whiptail --title "$WT_TITLE" --passwordbox "$1" 11 70 3>&1 1>&2 2>&3
}

ask_menu() {   # ask_menu "question" default tag1 "desc1" tag2 "desc2" ...
  local q="$1" def="$2"; shift 2
  local n=$(( $# / 2 ))
  whiptail --title "$WT_TITLE" --default-item "$def" --menu "$q" $(( n + 10 )) 76 "$n" "$@" 3>&1 1>&2 2>&3
}

ask_yesno() {   # ask_yesno "question" yes|no  -> prints yes/no
  local def_flag=()
  [ "$2" = "no" ] && def_flag=(--defaultno)
  # same stream swap as the other helpers: the dialog draws on the terminal, and
  # only the answer reaches the caller's $(...) - without it the escape codes end up in the value
  if whiptail --title "$WT_TITLE" "${def_flag[@]}" --yesno "$1" 12 70 3>&1 1>&2 2>&3; then echo yes; else echo no; fi
}

msg() { whiptail --title "$WT_TITLE" --msgbox "$1" 14 72; }
