#!/usr/bin/env bash
# Run the GTK suite or a supplied command in a private Wayland session.
set -euo pipefail
if [[ ${1:-} != --session ]]; then
    exec dbus-run-session -- "$0" --session "$@"
fi
shift
private=$(mktemp -d)
export XDG_RUNTIME_DIR="$private" XDG_CONFIG_HOME="$private/config" XDG_CACHE_HOME="$private/cache" XDG_DATA_HOME="$private/data"
export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman XDG_CURRENT_DESKTOP=sway
export GDK_BACKEND=wayland GSK_RENDERER=cairo GTK_A11Y=none GTK_IM_MODULE=gtk-im-context-simple GIO_USE_VFS=local
unset DISPLAY WAYLAND_DISPLAY SWAYSOCK
printf '%s\n' 'output * resolution 1280x960' 'xwayland disable' 'default_border none' 'seat seat0 fallback true' > "$private/sway.conf"
sway -c "$private/sway.conf" > "$private/sway.log" 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; rm -rf -- "$private"' EXIT
for _ in {1..65}; do
    socket=$(find "$private" -maxdepth 1 -type s -name 'wayland-*' -print -quit)
    [[ -n "$socket" ]] && break
    sleep .1
done
[[ -n "$socket" ]] || { cat "$private/sway.log"; exit 1; }
export WAYLAND_DISPLAY="${socket##*/}"
SWAYSOCK=$(find "$private" -maxdepth 1 -type s -name 'sway-ipc*' -print -quit)
export SWAYSOCK
dbus-update-activation-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR GDK_BACKEND GSK_RENDERER XDG_CURRENT_DESKTOP GTK_IM_MODULE GTK_A11Y
if [[ $# == 0 ]]; then set -- /usr/bin/python3 -m unittest discover -s prototypes/gtk; fi
"$@"
