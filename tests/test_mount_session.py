import sys
import time

import pytest

import snapshotfs.mount_session as session


@pytest.mark.skipif(sys.platform != "linux", reason="Linux mount process lifecycle")
def test_startup_timeout_reaps_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(
        session,
        "cli_executable",
        lambda: [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    processes = []
    original = session.subprocess.Popen

    def tracked(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(session.subprocess, "Popen", tracked)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="did not become ready"):
        session.start_background([], tmp_path, 0.1)
    assert time.monotonic() - started < 8
    assert processes[0].poll() is not None


@pytest.mark.skipif(sys.platform != "linux", reason="Linux mount ownership check")
def test_unmount_refuses_other_filesystems(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "is_snapshot_mount", lambda _: False)

    def forbidden(*args, **kwargs):
        pytest.fail("must not invoke fusermount for an unrelated filesystem")

    monkeypatch.setattr(session.subprocess, "run", forbidden)
    with pytest.raises(RuntimeError, match="not a SnapshotFS mount"):
        session.unmount(tmp_path)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux dynamic loader environment")
@pytest.mark.parametrize("original", [None, "/custom/host-libs"])
def test_external_tools_do_not_inherit_frozen_libraries(monkeypatch, original):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIexample")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    if original is not None:
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", original)
    env = session.external_environment()
    assert env.get("LD_LIBRARY_PATH") == original
    assert "LD_LIBRARY_PATH_ORIG" not in env
    assert session.os.environ["LD_LIBRARY_PATH"] == "/tmp/_MEIexample"
