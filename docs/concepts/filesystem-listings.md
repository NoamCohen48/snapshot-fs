# Filesystem Listings

[Documentation](../index.md)

A filesystem listing is an inventory, not a backup. It usually records names,
sizes, and timestamps but not file bytes, ownership, permissions, link targets,
or complete timezone information.

SnapshotFS treats listings as untrusted structured input. It does not execute
their contents or resolve listed paths against the host filesystem.

For the built-in Windows parser, a section such as:

```text
Directory of C:\Users\Alice
```

becomes this mounted hierarchy:

```text
/
└── C/
    └── Users/
        └── Alice/
```

The drive is an ordinary first-level component. Missing ancestors are
synthesized.

The parser validates complete section summaries and the aggregate `Total Files
Listed:` footer. Counts and byte totals must match parsed entries, unknown
meaningful lines are errors, and malformed ordering fails the import. Generate
listings consistently and configure their encoding and date order explicitly.
