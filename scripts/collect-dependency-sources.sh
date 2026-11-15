#!/usr/bin/env bash
# Retain matching source RPMs alongside the redistributed dependency bundle.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: collect-dependency-sources.sh 9|10}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
mkdir -p "$out/dependency-sources"
rpm -qp --qf '%{NAME}\t%{SOURCERPM}\n' "$out"/airgap/rpms/*.rpm > "$out/dependency-sources/BINARY_TO_SOURCE.tsv"
test -s "$out/dependency-sources/BINARY_TO_SOURCE.tsv"
podman run --rm -v "$out/dependency-sources:/sources:Z" \
    "quay.io/rockylinux/rockylinux:$major" bash -euc '
    dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream install -y dnf-plugins-core
    mapfile -t specs < <(cut -f2 /sources/BINARY_TO_SOURCE.tsv | grep -v "^flagship-" | sed "s/\.src\.rpm$//" | sort -u)
    test "${#specs[@]}" -gt 0
    dnf --disablerepo="*" --enablerepo=baseos-source --enablerepo=appstream-source \
        download --source --destdir=/sources "${specs[@]}"
    '
cp "$out"/*.src.rpm "$out/dependency-sources/"
(cd "$out/dependency-sources" && sha256sum ./*.rpm BINARY_TO_SOURCE.tsv > SHA256SUMS)
tar -czf "$out/flagship-dependency-sources-el$major-$app_version.tar.gz" -C "$out" dependency-sources
