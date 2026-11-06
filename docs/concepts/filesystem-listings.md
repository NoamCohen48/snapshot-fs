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

## Source Timestamps

Windows `dir /s` records wall-clock times without a timezone. Set the timezone
of the machine that produced the listing explicitly when importing:

```bash
snapshotfs sqlite create backup.snapshot \
  --source file listing.txt --parser windows-dir \
  --date-format mdy --source-timezone Asia/Jerusalem
```

Use an IANA name such as `Asia/Jerusalem`, `America/New_York`, or `Europe/London`.
The documented default is `UTC`, preserving the previous mount interpretation;
it is an assumption, not timezone detection. The mounting host's timezone never
determines the source timezone. New imports store offset-aware timestamps and
record the source timezone and ambiguity policy in snapshot metadata. The
mounted Unix timestamp represents that instant; file managers display it in
their own local timezone. Zone rules are applied for the date in the listing,
including historical daylight-saving offsets. Timezone data is bundled with
the wheel and standalone executable for hosts without an IANA database.

A repeated local time during a daylight-saving transition is rejected by
default. If you know which occurrence the listing means, select
`--ambiguous-time earlier` or `--ambiguous-time later`. A nonexistent local time
in a daylight-saving gap is always rejected; correct the source timestamp or
source-timezone setting. SnapshotFS does not silently normalize such times.

Existing artifacts with naive timestamps retain their legacy UTC interpretation
when mounted. Reimport the original listing with `--source-timezone` to correct
one. Synthesized ancestors without source timestamps use the import time;
mounted access/change/birth times are projected from the modification time, not
independently recovered source metadata. Ownership and read-only modes are also
synthetic.
