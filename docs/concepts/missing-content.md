# Missing File Content

[Documentation](../index.md)

Directory listings usually declare file sizes without containing file bytes.
SnapshotFS records this distinction rather than representing every listed file
as empty.

| Node | Stored content | Content status |
| --- | --- | --- |
| Directory | `None` | `not_applicable` |
| Non-empty listed file | `None` | `missing` |
| Zero-length listed file | `b""` | `present` |

Inspect statuses in Python with:

```python
from snapshotfs.model import ContentStatus

for node in store.iter_nodes():
    if node.content_status is ContentStatus.MISSING:
        print(node.original_path, node.size)
```

`ContentStatus` is exported from `snapshotfs.model`, not from the top-level
package.

## Mounted Reads

By default, reading unavailable non-empty content returns Linux `ENODATA`.
Returning empty bytes would incorrectly claim that the file is empty.

With `simulate_missing_content=True`, a missing file with a known size reads as
bounded NUL bytes up to its declared end. Simulation does not apply to unknown
sizes or `remote`, `failed`, or `redacted` content. It is stand-in data, never
recovered original content, and must not be used for hashing, recovery, or other
byte-accurate work.
