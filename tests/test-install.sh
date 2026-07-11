#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

DEVBOX_INSTALLER_SOURCE_ONLY=1 . "$root/install.sh"

python_is_compatible python3
! python_is_compatible false

HOME="$tmp/home"
mkdir -p "$HOME"
SHELL=/bin/sh
PATH=/usr/bin:/bin
export HOME SHELL PATH
persist_home_bin_path
grep -F '# >>> devbox installer >>>' "$HOME/.profile"
persist_home_bin_path
[ "$(grep -c '# >>> devbox installer >>>' "$HOME/.profile")" -eq 1 ]

printf 'POSIX installer tests passed\n'
