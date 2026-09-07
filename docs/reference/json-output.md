# JSON Output

[Documentation](../index.md)

`snapshotfs sqlite show SNAPSHOT --json` writes UTF-8 JSON with this top-level
shape:

```json
{
  "snapshot": {},
  "nodes": [],
  "diagnostics": [],
  "diagnostic_count": 0
}
```

## Snapshot

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Snapshot identifier. Current imports use a UUID string. |
| `source_uri` | string | Source provenance; files use an absolute `file:` URI. |
| `source_format` | string | Parser format, currently `windows-dir`. |
| `imported_at` | string | ISO 8601 import timestamp. |
| `source_metadata` | object | JSON-compatible source metadata. |

## Nodes

Every node, including the virtual root, has these fields:

| Field | Type |
| --- | --- |
| `id` | integer |
| `parent_id` | integer or null |
| `mounted_name` | string |
| `original_path` | string or null |
| `kind` | `directory`, `file`, `symlink`, `special`, or `unknown` |
| `size` | non-negative integer or null |
| `modified_at` | ISO 8601 string or null |
| `content` | Base64 string or null |
| `content_encoding` | `base64` or null |
| `content_status` | content-status string |
| `content_ref` | string or null |
| `source_line` | positive integer or null |
| `source_metadata` | object |

Inline content is Base64 encoded. Empty present content is represented by an
empty string with `content_encoding` set to `base64`.

## Diagnostics

Each retained diagnostic contains `severity`, `line_number`, `code`, and
`message`. `diagnostic_count` includes all observed diagnostics even when the
retained array reached its limit.
