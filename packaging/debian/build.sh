#!/usr/bin/env bash
set -euo pipefail
# Run from the repository root after building the Linux FUSE executable.
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
install -Dm755 dist/snapshotfs "$stage/usr/bin/snapshotfs"
install -Dm644 examples/windows-dir.txt "$stage/usr/share/doc/snapshotfs/examples/windows-dir.txt"
mkdir -p "$stage/DEBIAN" release
cat > "$stage/DEBIAN/control" <<CONTROL
Package: snapshotfs
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: SnapshotFS contributors <92931230+NoamCohen48@users.noreply.github.com>
Depends: fuse3, libc6 (>= 2.35)
Description: Mount validated filesystem inventories as read-only FUSE filesystems
 Includes the Python runtime and FUSE Python bindings. File contents are not
 recovered from listings; unavailable reads return ENODATA by default.
CONTROL
dpkg-deb --root-owner-group --build "$stage" "release/snapshotfs_${version}_amd64.deb"
