# Adapter

[Development](../README.md) / Adapter

An adapter exposes a `SnapshotStore` through another interface. The current
adapter presents a store as a read-only Linux filesystem, but the store boundary
allows other consumers without coupling them to input formats.

## Responsibilities

The filesystem adapter translates its operations into store lookups, node reads,
and child iteration. It uses store inode identifiers directly and must preserve
the store's immutable, read-only semantics.

The adapter may define interface-specific behavior such as attributes, handles,
pagination, and error translation. It must not parse input, normalize source
paths, mutate a store, or access storage-backend internals.

## Optional Dependencies

Filesystem support is optional and imported lazily through `mount_store`. Keep
optional adapter imports isolated so source parsing and store use continue to
work where adapter dependencies are not installed.

## Content Policy

Snapshots commonly contain metadata without file bytes. The adapter reports the
declared metadata and returns `ENODATA` for unavailable file content. Callers may
explicitly request bounded zero-filled stand-ins for eligible missing content;
this behavior must never imply that the original bytes are present.

## Testing

Test adapter operations directly with a store fixture. Kernel-level integration
tests should be separate and may skip when the host lacks the required kernel
support, permissions, or optional dependencies.
