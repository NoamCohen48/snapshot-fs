"""Actionable preflight errors should occur before touching the FUSE kernel API."""

import pytest

pytest.importorskip("pyfuse3")
from snapshotfs.fuse.adapter import mount as adapter


@pytest.mark.parametrize("state", ["missing", "file", "nonempty", "mounted"])
def test_invalid_mountpoint_fails_before_fuse_init(tmp_path, monkeypatch, state):
    path = tmp_path / "mount"
    if state == "file":
        path.write_text("file")
    elif state != "missing":
        path.mkdir()
        if state == "nonempty":
            (path / "entry").touch()
    monkeypatch.setattr(adapter.os.path, "ismount", lambda _: state == "mounted")

    def unexpected_init(*args):
        pytest.fail("FUSE init must not be called for an invalid mountpoint")

    monkeypatch.setattr(adapter.pyfuse3, "init", unexpected_init)
    with pytest.raises(RuntimeError, match="mountpoint"):
        adapter.mount_snapshot(None, str(path))
