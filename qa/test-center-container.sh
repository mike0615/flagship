#!/usr/bin/env bash
# Test installed native clients against a separate Xvfb display, with no networking.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: test-center-container.sh 9|10}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
image="localhost/flagship-center-qa:$major"
context=$(mktemp -d)
server=''
cleanup() {
    if [[ -n "$server" ]]; then podman rm -f "$server" >/dev/null; fi
    rm -rf -- "$context"
}
trap cleanup EXIT
packages=openssl
if [[ $major == 9 ]]; then packages='openssl xorg-x11-server-Xvfb'; fi
cat > "$context/Containerfile" <<EOF
FROM quay.io/rockylinux/rockylinux:$major
RUN dnf --disablerepo='*' --enablerepo=baseos --enablerepo=appstream install -y $packages && dnf clean all
EOF
podman build -t "$image" "$context"
# Rocky 10 no longer provides Xvfb in BaseOS/AppStream. A Rocky 9 test-only
# display server serves both clients over a private Unix socket, like a desktop
# Xwayland server. No Rocky 9 libraries/packages enter the Rocky 10 client.
podman image exists localhost/flagship-center-qa:9 || { echo 'Run this script for Rocky 9 first' >&2; exit 1; }
mkdir "$context/sockets"
server=$(podman run -d --rm --network=none -v "$context/sockets:/tmp/.X11-unix:z" localhost/flagship-center-qa:9 Xvfb :99 -screen 0 1280x900x24 -ac -nolisten tcp)
podman run --rm --network=none -v "$context/sockets:/tmp/.X11-unix:ro,z" -v "$out/airgap:/bundle:ro,z" -v "$root/tests:/tests:ro,z" -e DISPLAY=:99 "$image" bash -euc '
cd /bundle
bash install-offline.sh
cd /tmp
export PYTHONPATH=/usr/share/flagship
python3 - <<"PY"
import time, tkinter as tk
for attempt in range(50):
    try:
        root=tk.Tk(); root.destroy(); break
    except tk.TclError: time.sleep(0.1)
else: raise SystemExit("Xvfb did not start")
import flagship
print("INSTALLED", flagship.__version__, flagship.__file__)
assert flagship.__file__.startswith("/usr/share/flagship/")
PY
python3 -m unittest discover -s /tests -v
flagship --smoke-test
flagship --version
rpm -q flagship python3 python3-tkinter
cat /etc/os-release
echo "PASS: installed native GUI and regression suite with network disabled"
'
