#!/usr/bin/env bash
# Preserve exact sources for changed dependency RPMs without duplicating a prior source archive.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: collect-source-delta.sh 9|10 baseline-source-directory}
baseline=${2:?Specify the extracted, authenticated prior dependency source directory}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
delta="$out/source-delta"
mkdir -p "$delta"
cp "$out"/*.src.rpm "$delta/"
rpm -qp --qf '%{SOURCERPM}\n' "$out"/airgap/rpms/*.rpm | sort -u > "$delta/REQUIRED_SOURCES"
: > "$delta/NEEDED_SPECS"
while IFS= read -r name; do
    if [[ ! -f "$baseline/$name" && ! -f "$delta/$name" ]]; then
        printf '%s\n' "${name%.src.rpm}" >> "$delta/NEEDED_SPECS"
    fi
done < "$delta/REQUIRED_SOURCES"
if [[ -s "$delta/NEEDED_SPECS" ]]; then
    podman run --rm -v "$delta:/sources:Z" "quay.io/rockylinux/rockylinux:$major" bash -euc '
    dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream install -y dnf-plugins-core
    mapfile -t specs < /sources/NEEDED_SPECS
    dnf --disablerepo="*" --enablerepo=baseos-source --enablerepo=appstream-source \
        download --source --destdir=/sources "${specs[@]}"
    '
fi
: > "$delta/SOURCE-COVERAGE.tsv"
while IFS= read -r name; do
    if [[ -f "$delta/$name" ]]; then
        digest=$(sha256sum "$delta/$name")
        printf '%s\tdelta\t%s\n' "$name" "${digest%% *}" >> "$delta/SOURCE-COVERAGE.tsv"
    elif [[ -f "$baseline/$name" ]]; then
        digest=$(sha256sum "$baseline/$name")
        printf '%s\tbaseline\t%s\n' "$name" "${digest%% *}" >> "$delta/SOURCE-COVERAGE.tsv"
    else
        echo "Missing exact source RPM: $name" >&2
        exit 1
    fi
done < "$delta/REQUIRED_SOURCES"
(cd "$delta" && sha256sum ./*.rpm REQUIRED_SOURCES NEEDED_SPECS SOURCE-COVERAGE.tsv > SHA256SUMS)
tar -czf "$out/xenadmin-rocky-source-delta-el$major-$app_version.tar.gz" -C "$out" source-delta
