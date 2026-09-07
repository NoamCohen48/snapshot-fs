# SQLite Artifacts

[Documentation](../index.md)

SnapshotFS SQLite files are persistent, read-only snapshot artifacts. They are
not an extension API and should be opened through `open_sqlite_store()` or
`snapshotfs sqlite show` rather than queried as an application database.

The current artifact schema version is 4. Opening an artifact validates the
SnapshotFS application ID and requires an exact supported schema version;
automatic migration is not performed.

Validation also covers SQLite integrity and foreign keys, required schema
objects and storage classes, exactly one snapshot and root, tree reachability,
parent types, names, enum values, metadata, and content invariants. Treat
artifacts from untrusted sources as untrusted input despite these checks.

## Publication

Creation builds a temporary database in the destination directory. SnapshotFS
commits, closes, syncs, validates, and only then publishes it. Without
`overwrite=True`, an existing destination is preserved.

Overwrite publication is atomic, but concurrent successful writers use
last-finisher-wins behavior. `SQLiteDurabilityError` and
`SQLitePublicationError` describe failures after publication may already have
changed the destination.
