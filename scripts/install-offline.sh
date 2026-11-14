#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ $EUID != 0 ]]; then echo 'Run with sudo from the transferred bundle' >&2; exit 1; fi
sha256sum -c SHA256SUMS
. /etc/os-release
if [[ $ID != rocky || ( $VERSION_ID != 9* && $VERSION_ID != 10* ) ]]; then
    echo 'Rocky Linux 9 or 10 required' >&2; exit 1
fi
. ./BUILD_OS_RELEASE
bundle_major=${VERSION_ID%%.*}
. /etc/os-release
if [[ ${VERSION_ID%%.*} != "$bundle_major" || $(uname -m) != x86_64 ]]; then
    echo 'Bundle must match the target Rocky major and x86_64 architecture' >&2; exit 1
fi
# The app candidate is unsigned; authenticate the bundle before this local transaction.
# Upstream dependency signatures may be verified separately with Rocky trusted keys.
dnf --disablerepo='*' --setopt=localpkg_gpgcheck=0 install -y ./rpms/*.rpm
