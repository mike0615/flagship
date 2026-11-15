#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: build-rpm.sh 9|10}
case "$major" in 9|10) ;; *) echo 'Rocky major must be 9 or 10' >&2; exit 2;; esac
source "$root/scripts/common.sh"
mkdir -p "$out"
stage=$(mktemp -d "$root/build-rpm.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/$archive_name"
for part in flagship xenadmin_rocky docs packaging scripts tests qa README.md LICENSE upstream CONTRIBUTING.md SECURITY.md; do
    cp -a "$root/$part" "$stage/$archive_name/"
done
git -C "$root" rev-parse HEAD > "$stage/$archive_name/SOURCE_COMMIT"
find "$stage" -name __pycache__ -type d -exec rm -rf {} +
tar -czf "$out/$archive_name.tar.gz" -C "$stage" "$archive_name"
podman run --rm -v "$out:/out:Z" -v "$root/packaging:/spec:ro,z" -e RPM_VERSION="$rpm_version" \
    "quay.io/rockylinux/rockylinux:$major" bash -euc '
    dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream install -y rpm-build python3-devel
    mkdir -p /root/rpmbuild/SOURCES
    cp "/out/flagship-$RPM_VERSION.tar.gz" /root/rpmbuild/SOURCES/
    rpmbuild -ba /spec/flagship.spec
    cp /root/rpmbuild/RPMS/noarch/*.rpm /out/
    cp /root/rpmbuild/SRPMS/*.rpm /out/
    '
(cd "$out" && sha256sum ./*.rpm ./*.tar.gz > SHA256SUMS)
