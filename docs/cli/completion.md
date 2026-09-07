# Shell Completion

[Command-line guide](index.md)

SnapshotFS can print Click's registration script for Bash, Zsh, or Fish.

Enable it for the current shell:

```bash
# Bash
eval "$(snapshotfs completion bash)"

# Zsh
eval "$(snapshotfs completion zsh)"

# Fish
snapshotfs completion fish | source
```

To enable completion permanently, place the command for your shell in its
startup configuration.

Completion includes command names, registered source and parser names,
contextual component options, date formats, common encodings, and input paths.
Encoding values are suggestions rather than a fixed CLI choice; unsupported
encodings still fail when the parser is constructed.
