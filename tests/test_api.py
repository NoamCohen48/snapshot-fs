from pathlib import Path

import pytest

import snapshotfs
import snapshotfs.api as api


def test_public_library_api_uses_explicit_store_operations() -> None:
    for name in (
        "create_memory_store",
        "create_sqlite_store",
        "open_sqlite_store",
        "mount_store",
        "NodeKind",
        "Observation",
    ):
        assert hasattr(snapshotfs, name)
    removed_names = (
        "import_snapshot",
        "import_snapshot_sqlite",
        "open_snapshot",
        "mount",
        "ParsedPath",
    )
    for removed in removed_names:
        assert not hasattr(snapshotfs, removed)


def test_public_library_api_mounts_explicit_store(
    listing_file: Path, tmp_path: Path, monkeypatch
) -> None:
    pytest.importorskip("pyfuse3")
    import snapshotfs.fuse.adapter as adapter

    mountpoint = tmp_path / "mount"
    mountpoint.mkdir()
    called: dict[str, object] = {}

    def fake_mount(store, path: str, *, simulate_missing_content: bool) -> None:
        called.update(
            store=store,
            path=path,
            simulate_missing_content=simulate_missing_content,
        )

    monkeypatch.setattr(adapter, "mount_snapshot", fake_mount)
    store = snapshotfs.create_memory_store(
        snapshotfs.FileSource(listing_file),
        snapshotfs.WindowsDirParser(),
    )
    snapshotfs.mount_store(
        store,
        mountpoint,
        simulate_missing_content=True,
    )

    assert called["path"] == str(mountpoint)
    assert called["simulate_missing_content"] is True


def test_public_library_api_can_create_store_without_mounting(
    listing_file: Path,
) -> None:
    store = snapshotfs.create_memory_store(
        snapshotfs.FileSource(listing_file),
        snapshotfs.WindowsDirParser(),
    )
    assert list(store.iter_nodes())


@pytest.mark.parametrize("dependency", ["pyfuse3", "trio"])
def test_mount_wraps_only_missing_optional_dependencies(
    listing_file: Path, monkeypatch, dependency: str
) -> None:
    store = snapshotfs.create_memory_store(
        snapshotfs.FileSource(listing_file), snapshotfs.WindowsDirParser()
    )
    missing = ModuleNotFoundError(name=dependency)

    def fail_import(name: str) -> object:
        del name
        raise missing

    monkeypatch.setattr(api, "import_module", fail_import)
    with pytest.raises(snapshotfs.FuseUnavailableError) as caught:
        snapshotfs.mount_store(store, "/unused")
    assert caught.value.__cause__ is missing


@pytest.mark.parametrize(
    "error",
    [
        ImportError("broken adapter implementation"),
        ModuleNotFoundError(name="adapter_internal_dependency"),
    ],
)
def test_mount_propagates_internal_import_errors(
    listing_file: Path, monkeypatch, error: ImportError
) -> None:
    store = snapshotfs.create_memory_store(
        snapshotfs.FileSource(listing_file), snapshotfs.WindowsDirParser()
    )

    def fail_import(name: str) -> object:
        del name
        raise error

    monkeypatch.setattr(api, "import_module", fail_import)
    with pytest.raises(type(error)) as caught:
        snapshotfs.mount_store(store, "/unused")
    assert caught.value is error
