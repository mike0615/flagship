#!/usr/bin/env bash
# Build a disposable X server image, then install/test only from the local bundle.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: test-center-container.sh 9|10}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
image="localhost/flagship-center-qa:$major"
context=$(mktemp -d)
trap 'rm -rf -- "$context"' EXIT
cat > "$context/Containerfile" <<EOF
FROM quay.io/rockylinux/rockylinux:$major
RUN dnf --disablerepo='*' --enablerepo=baseos --enablerepo=appstream install -y xorg-x11-server-Xvfb openssl && dnf clean all
EOF
podman build -t "$image" "$context"
podman run --rm --network=none -v "$out/airgap:/bundle:ro,z" -v "$root/tests:/tests:ro,z" "$image" bash -euc '
cd /bundle
bash install-offline.sh
cd /tmp
Xvfb :99 -screen 0 1280x900x24 -ac &
xpid=$!
trap "kill $xpid 2>/dev/null || true" EXIT
export DISPLAY=:99
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
