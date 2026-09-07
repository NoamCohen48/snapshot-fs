# Snapshots And Nodes

[Documentation](../index.md)

A `Snapshot` identifies one successful import. It records a UUID string, source
URI, parser format, aware UTC import time, and immutable source metadata.

Each built-in store contains one snapshot and a virtual root node with inode
`1`. Every other node is connected through `parent_id`. A node ID is also its
inode when mounted through FUSE.

`mounted_name` contains the exact UTF-8 bytes used for lookup and mounting.
`original_path` contains a slash-joined parser-defined relative path; it is not
necessarily the literal source path. Paths are exact and case-sensitive, so
`Foo` and `foo` can coexist even if the listing came from a case-insensitive
filesystem.

`Snapshot`, `Node`, and `ParsedEntry` are frozen dataclasses. Metadata is copied
and recursively frozen into JSON-compatible immutable values. A snapshot does
not track later changes to its source listing or the filesystem that produced
the listing.
