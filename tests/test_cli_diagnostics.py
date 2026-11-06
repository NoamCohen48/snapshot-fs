from pathlib import Path

import pytest

import snapshotfs.doctor as doctor
from snapshotfs.cli import main
from snapshotfs.logging_setup import logger, package_version


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "snapshotfs.logging_setup.default_log_path", lambda: tmp_path / "default.log"
    )


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"snapshotfs, version {package_version()}"


def test_doctor_checks_missing_dependencies_without_mounting(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")

    def missing(name):
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(doctor.importlib, "import_module", missing)
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    real_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists", lambda p: False if p == Path("/dev/fuse") else real_exists(p)
    )
    assert main(["doctor", "--mountpoint", str(tmp_path / "absent")]) == 1
    output = capsys.readouterr()
    for label in (
        "platform",
        "pyfuse3",
        "trio",
        "fusermount3",
        "FUSE device",
        "device access",
        "mountpoint",
    ):
        assert f"FAIL {label}:" in output.out
    assert "Diagnostic log:" in output.err


def test_doctor_ready_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.importlib, "import_module", lambda _: object())
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/bin/fusermount3")
    monkeypatch.setattr(doctor.os, "access", lambda *args: True)
    real_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists", lambda p: True if p == Path("/dev/fuse") else real_exists(p)
    )
    mountpoint = tmp_path / "mount"
    mountpoint.mkdir()
    assert main(["doctor", "--mountpoint", str(mountpoint)]) == 0
    assert "FAIL" not in capsys.readouterr().out
    (mountpoint / "entry").touch()
    assert main(["doctor", "--mountpoint", str(mountpoint)]) == 1
    assert "choose an empty directory" in capsys.readouterr().out


def test_failure_logs_traceback_and_does_not_pollute_stdout(tmp_path, capsys):
    log = tmp_path / "logs" / "snapshotfs.log"
    original_handlers = tuple(logger.handlers)
    original_level = logger.level
    assert (
        main(
            [
                "--log-file",
                str(log),
                "sqlite",
                "show",
                str(tmp_path / "absent.db"),
                "--json",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert "Traceback" not in output.err
    assert str(log) in output.err
    text = log.read_text()
    assert "Traceback" in text and "absent.db" in text
    assert tuple(logger.handlers) == original_handlers
    assert logger.level == original_level


def test_verbose_includes_traceback_on_stderr(tmp_path, capsys):
    assert main(["-v", "sqlite", "show", str(tmp_path / "absent.db")]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Traceback" in output.err


def test_unwritable_explicit_log_path_is_actionable(tmp_path, capsys):
    blocked = tmp_path / "file"
    blocked.touch()
    assert main(["--log-file", str(blocked / "log"), "doctor"]) == 1
    assert "cannot open log file" in capsys.readouterr().err


def test_default_log_failure_does_not_block_command(tmp_path, monkeypatch, capsys):
    blocked = tmp_path / "file"
    blocked.touch()
    monkeypatch.setattr(
        "snapshotfs.logging_setup.default_log_path", lambda: blocked / "log"
    )
    assert main(["sqlite", "show", str(tmp_path / "absent.db")]) == 1
    assert "cannot open default log file" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\xff\n", "--encoding"),
        (b"localized header\n", "English Windows dir /s"),
        (b" Directory of C:\\\n01/31/2024 10:00 0 empty.txt\n", "complete dir /s"),
    ],
)
def test_import_hints_preserve_atomic_rejection(tmp_path, capsys, content, expected):
    source = tmp_path / "listing.txt"
    source.write_bytes(content)
    destination = tmp_path / "snapshot.db"
    assert (
        main(
            [
                "sqlite",
                "create",
                str(destination),
                "--source",
                "file",
                str(source),
                "--parser",
                "windows-dir",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert expected in output.err
    assert not destination.exists()


def test_date_failure_has_excerpt_and_format_hint(tmp_path, capsys):
    source = tmp_path / "listing.txt"
    source.write_text(
        " Directory of C:\\\n31/01/2024 10:00 0 empty.txt\n", encoding="utf-8"
    )
    assert (
        main(
            [
                "sqlite",
                "create",
                str(tmp_path / "out.db"),
                "--source",
                "file",
                str(source),
                "--parser",
                "windows-dir",
            ]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert "line 2" in error
    assert "31/01/2024 10:00 0 empty.txt" in error
    assert "--date-format" in error


def test_bad_line_excerpt_is_bounded_and_escaped(tmp_path, capsys):
    source = tmp_path / "listing.txt"
    source.write_text("\x1b[31m" + "x" * 10000 + "\n", encoding="utf-8")
    assert (
        main(
            [
                "sqlite",
                "create",
                str(tmp_path / "out.db"),
                "--source",
                "file",
                str(source),
                "--parser",
                "windows-dir",
            ]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert "\\x1b" in error and "\x1b" not in error
    assert len(error) < 2500


def test_success_keeps_json_clean_and_records_import(tmp_path, listing_file, capsys):
    artifact = tmp_path / "out.db"
    assert (
        main(
            [
                "sqlite",
                "create",
                str(artifact),
                "--source",
                "file",
                str(listing_file),
                "--parser",
                "windows-dir",
            ]
        )
        == 0
    )
    assert capsys.readouterr().err == ""
    assert "Import completed" in (tmp_path / "default.log").read_text()
    assert main(["sqlite", "show", str(artifact), "--json"]) == 0
    import json

    assert json.loads(capsys.readouterr().out)["nodes"]
