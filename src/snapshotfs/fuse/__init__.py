"""Dependency-free policies shared with the optional FUSE adapter."""

from snapshotfs.fuse.policy import ContentReadError, read_node

__all__ = ["ContentReadError", "read_node"]
