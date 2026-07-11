#!/bin/sh
# Devbox installer. Intended to be run with `sh`.
set -eu

DEVBOX_REF=${DEVBOX_REF:-main}
DEVBOX_SOURCE_URL=${DEVBOX_SOURCE_URL:-https://raw.githubusercontent.com/alexandru/devbox/${DEVBOX_REF}/bin/devbox}
DEVBOX_FORCE=${DEVBOX_FORCE:-0}

log() { printf '%s\n' "devbox installer: $*"; }
warn() { printf '%s\n' "devbox installer: warning: $*" >&2; }
die() { printf '%s\n' "devbox installer: error: $*" >&2; exit 1; }

python_is_compatible() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

find_compatible_python() {
  DEVBOX_PYTHON=
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_compatible "$(command -v "$candidate")"; then
      DEVBOX_PYTHON=$(command -v "$candidate")
      export DEVBOX_PYTHON
      return 0
    fi
  done
  return 1
}

select_package_manager() {
  DEVBOX_PACKAGE_MANAGER=
  case "$(uname -s)" in
    Darwin) command -v brew >/dev/null 2>&1 && DEVBOX_PACKAGE_MANAGER=brew ;;
    *) for manager in apt-get dnf yum pacman apk zypper brew; do
         if command -v "$manager" >/dev/null 2>&1; then DEVBOX_PACKAGE_MANAGER=$manager; break; fi
       done ;;
  esac
  [ -n "$DEVBOX_PACKAGE_MANAGER" ]
}

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; return; fi
  command -v sudo >/dev/null 2>&1 || die "sudo is required to install Python; install it or run the package-manager command as root."
  log "requesting sudo permission for: $*"
  sudo "$@"
}

install_python() {
  select_package_manager || die "No supported package manager found. Install Python 3.9 or newer manually."
  log "installing Python with $DEVBOX_PACKAGE_MANAGER"
  case "$DEVBOX_PACKAGE_MANAGER" in
    brew) brew install python ;;
    apt-get) run_as_root apt-get update && run_as_root apt-get install -y python3 ;;
    dnf) run_as_root dnf install -y python3 ;;
    yum) run_as_root yum install -y python3 ;;
    pacman) run_as_root pacman -S --needed --noconfirm python ;;
    apk) run_as_root apk add --no-cache python3 ;;
    zypper) run_as_root zypper --non-interactive install python3 ;;
  esac
  hash -r 2>/dev/null || :
  find_compatible_python || die "The installed Python is still older than Python 3.9. Install a compatible Python manually."
}

download_devbox() {
  target=$1
  if [ -n "${DEVBOX_SOURCE_FILE:-}" ]; then
    [ -r "$DEVBOX_SOURCE_FILE" ] || die "DEVBOX_SOURCE_FILE is not readable: $DEVBOX_SOURCE_FILE"
    cp "$DEVBOX_SOURCE_FILE" "$target"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "$DEVBOX_SOURCE_URL" -o "$target"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$target" "$DEVBOX_SOURCE_URL"
  else
    die "curl or wget is required to download devbox."
  fi
}

path_contains_home_bin() {
  case ":${PATH:-}:" in *":$HOME/bin:"*) return 0;; *) return 1;; esac
}

select_shell_startup_file() {
  case "${SHELL:-}" in
    */zsh) printf '%s\n' "$HOME/.zshrc" ;;
    */bash) case "$(uname -s)" in Darwin) printf '%s\n' "$HOME/.bash_profile";; *) printf '%s\n' "$HOME/.bashrc";; esac ;;
    *) printf '%s\n' "$HOME/.profile" ;;
  esac
}

persist_home_bin_path() {
  case "${SHELL:-}" in
    */fish)
      command -v fish_add_path >/dev/null 2>&1 || die "fish_add_path is required to update Fish PATH."
      fish_add_path --universal "$HOME/bin"
      log "updated Fish universal PATH"
      return
      ;;
  esac
  path_contains_home_bin && return
  startup_file=$(select_shell_startup_file)
  mkdir -p "$(dirname "$startup_file")"
  touch "$startup_file"
  if ! grep -Fx 'export PATH="$HOME/bin:$PATH"' "$startup_file" >/dev/null 2>&1; then
    [ -s "$startup_file" ] && printf '\n' >> "$startup_file"
    printf '%s\n' 'export PATH="$HOME/bin:$PATH"' >> "$startup_file"
    log "updated $startup_file"
  fi
}

install_devbox() {
  [ -n "${HOME:-}" ] && [ -d "$HOME" ] && [ -w "$HOME" ] || die "HOME must name a writable directory."
  find_compatible_python || install_python
  install_dir="$HOME/bin"
  destination="$install_dir/devbox"
  marker="$install_dir/.devbox-installed"
  mkdir -p "$install_dir"
  existing=$(command -v devbox 2>/dev/null || :)
  if [ -n "$existing" ] && [ "$existing" != "$destination" ] && [ "$DEVBOX_FORCE" != 1 ]; then
    die "existing devbox command at $existing would be shadowed; set DEVBOX_FORCE=1 to proceed."
  fi
  if [ -e "$destination" ] && [ ! -f "$marker" ] && [ "$DEVBOX_FORCE" != 1 ]; then
    die "$destination is not managed by this installer; set DEVBOX_FORCE=1 to replace it."
  fi
  temporary=$(mktemp "$install_dir/.devbox.XXXXXX") || die "cannot create temporary download file"
  trap 'rm -f "$temporary"' EXIT HUP INT TERM
  download_devbox "$temporary"
  "$DEVBOX_PYTHON" "$temporary" --help >/dev/null || die "downloaded devbox script did not validate"
  chmod 0755 "$temporary"
  mv -f "$temporary" "$destination"
  trap - EXIT HUP INT TERM
  printf '%s\n' "$DEVBOX_SOURCE_URL" > "$marker"
  persist_home_bin_path
  log "installed $destination using $DEVBOX_PYTHON"
  if ! path_contains_home_bin; then warn "restart your shell or source its startup file before running devbox."; fi
}

main() { install_devbox; }

if [ "${DEVBOX_INSTALLER_SOURCE_ONLY:-0}" != 1 ]; then main "$@"; fi
