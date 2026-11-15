#!/usr/bin/env bash
# Run on a connected builder. Do not execute downloads on the airgapped target.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
major=${1:?Usage: build-airgap.sh 9|10}
case "$major" in 9|10) ;; *) exit 2;; esac
source "$root/scripts/common.sh"
shopt -s nullglob
app=("$out"/flagship-*.noarch.rpm)
if [[ ${#app[@]} != 1 ]]; then echo 'Build exactly one candidate RPM first' >&2; exit 1; fi
bundle="$out/airgap"
if [[ -e "$bundle" ]]; then echo 'Move the prior airgap directory before rebuilding' >&2; exit 1; fi
mkdir -p "$bundle/rpms" "$bundle/docs"
cp "${app[0]}" "$bundle/rpms/"
cp "$root"/docs/*.md "$bundle/docs/"
cp "$root/LICENSE" "$bundle/LICENSE"
cp "$root/scripts/install-offline.sh" "$bundle/"
podman run --rm -v "$bundle:/bundle:Z" "quay.io/rockylinux/rockylinux:$major" bash -euc '
    dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream install -y dnf-plugins-core createrepo_c
    dnf --disablerepo="*" --enablerepo=baseos --enablerepo=appstream download --resolve --alldeps --destdir=/bundle/rpms /bundle/rpms/flagship-*.rpm
    createrepo_c /bundle/rpms
    rpm -qp --qf "%{NAME}\t%{VERSION}-%{RELEASE}\t%{ARCH}\t%{LICENSE}\n" /bundle/rpms/*.rpm > /bundle/PACKAGES.tsv
    cp /etc/os-release /bundle/BUILD_OS_RELEASE
    '
# Checksums detect corruption, not authenticity; use authenticated release transfer.
(cd "$bundle" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf "$out/flagship-airgap-el$major-x86_64-$app_version.tar.gz" -C "$out" airgap
