#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: build-rpm.sh 9|10}
case "$major" in 9|10) ;; *) echo 'Rocky major must be 9 or 10' >&2; exit 2;; esac
out="$root/dist/el$major"
mkdir -p "$out"
stage=$(mktemp -d "$root/build-rpm.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/xenadmin-rocky-1.0.0"
for part in xenadmin_rocky docs packaging README.md LICENSE upstream; do
    cp -a "$root/$part" "$stage/xenadmin-rocky-1.0.0/"
done
find "$stage" -name __pycache__ -type d -exec rm -rf {} +
tar -czf "$out/xenadmin-rocky-1.0.0.tar.gz" -C "$stage" xenadmin-rocky-1.0.0
podman run --rm -v "$out:/out:Z" -v "$root/packaging:/spec:ro,Z" \
    "quay.io/rockylinux/rockylinux:$major" bash -euc '
    dnf install -y rpm-build python3-devel
    mkdir -p /root/rpmbuild/SOURCES
    cp /out/xenadmin-rocky-1.0.0.tar.gz /root/rpmbuild/SOURCES/
    rpmbuild -ba /spec/xenadmin-rocky.spec
    cp /root/rpmbuild/RPMS/noarch/*.rpm /out/
    cp /root/rpmbuild/SRPMS/*.rpm /out/
    '
(cd "$out" && sha256sum ./*.rpm ./*.tar.gz > SHA256SUMS)
