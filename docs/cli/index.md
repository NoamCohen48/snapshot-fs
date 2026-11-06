# Command-Line Guide

[Documentation](../index.md)

Use `snapshotfs doctor` to check FUSE setup and `snapshotfs --version` to identify
the build. Global `-v` / `--verbose` and `--log-file PATH` options go before the
command. Import and mount commands are organized by storage backend:

```text
snapshotfs
├── sqlite
│   ├── create
│   ├── mount
│   └── show
├── memory
│   └── mount
├── doctor
├── unmount
├── run
└── completion
```

Commands that import a listing require an explicit source and parser. Selecting
those components adds their arguments and options to the command.

```bash
snapshotfs sqlite create --source file --parser windows-dir --help
```

The built-in `file` source contributes an `INPUT` argument. The built-in
`windows-dir` parser contributes `--encoding`, `--date-format`,
`--source-timezone`, and `--ambiguous-time`.

## Common Workflows

- [Create, inspect, and mount SQLite artifacts](sqlite.md)
- [Import and mount without persistence](memory.md)
- [Enable shell completion](completion.md)
- [Diagnose errors](troubleshooting.md)
- [Read the complete generated command reference](../reference/cli.md)

Successful create and mount commands normally produce no output. Diagnostics and
errors are written to standard error. `sqlite show` writes its tree or JSON
document to standard output.
