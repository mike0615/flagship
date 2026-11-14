#!/usr/bin/env bash
# Fresh disposable container; no network namespace access during installation/testing.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: test-offline.sh 9|10}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
podman run --rm --network=none -v "$out/airgap:/bundle:ro,Z" \
    "quay.io/rockylinux/rockylinux:$major" bash -euc '
    cd /bundle
    bash install-offline.sh
    xenadmin-rocky --version
    python3 -c "import tkinter; print(tkinter.TkVersion)"
    test -s /usr/share/xenadmin-rocky/docs/USER_GUIDE.md
    test -s /usr/share/applications/xenadmin-rocky.desktop
    rpm -q xenadmin-rocky python3-tkinter
    echo "PASS: network-disabled install, imports, help and launcher files"
    '
