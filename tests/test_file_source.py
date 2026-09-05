import codecs
import io
from pathlib import Path

import pytest

from snapshotfs.decoding import DecodeError, iter_decoded_lines
from snapshotfs.sources.file import FileSource, SourceError


class ChunkedBytesIO(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        chunk_size = 2 if size is None or size < 0 else min(size, 2)
        return super().read(chunk_size)


def test_file_source_streams_binary_data(tmp_path: Path) -> None:
    path = tmp_path / "input.bin"
    path.write_bytes(b"abc")
    source = FileSource(path)

    assert source.size == 3
    assert source.uri == path.absolute().as_uri()
    with source.open() as stream:
        assert stream.read(2) == b"ab"
        assert stream.read() == b"c"


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_file_source_errors_include_path(tmp_path: Path, kind: str) -> None:
    path = tmp_path / kind
    if kind == "directory":
        path.mkdir()
    source = FileSource(path)

    with pytest.raises(SourceError, match=str(path)), source.open():
        pass


def test_file_source_wraps_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "private.txt"
    path.write_bytes(b"private")

    def denied(*args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "open", denied)
    with (
        pytest.raises(SourceError, match=r"private\.txt.*Permission denied"),
        FileSource(path).open(),
    ):
        pass


def test_decoder_handles_chunks_bom_crlf_and_cp1252() -> None:
    utf8 = ChunkedBytesIO(b"\xef\xbb\xbfone\r\ntwo\n")
    assert [line.text for line in iter_decoded_lines(utf8)] == ["one", "two"]

    western = io.BytesIO("caf\N{LATIN SMALL LETTER E WITH ACUTE}\n".encode("cp1252"))
    assert [line.text for line in iter_decoded_lines(western, "cp1252")] == [
        "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
    ]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_utf8_bom_is_stripped_only_at_stream_start(encoding: str) -> None:
    stream = ChunkedBytesIO(
        codecs.BOM_UTF8 + b"first\n" + codecs.BOM_UTF8 + b"second\n"
    )
    assert [line.text for line in iter_decoded_lines(stream, encoding)] == [
        "first",
        "\ufeffsecond",
    ]


def test_decoder_supports_explicit_utf16() -> None:
    stream = ChunkedBytesIO("one\r\ntwo\n".encode("utf-16"))
    assert [line.text for line in iter_decoded_lines(stream, "utf-16")] == [
        "one",
        "two",
    ]


def test_decoder_reports_invalid_bytes_and_offset() -> None:
    with pytest.raises(DecodeError, match=r"byte offset 2.*utf-8"):
        list(iter_decoded_lines(io.BytesIO(b"ok\xff\n")))


def test_decoder_rejects_oversized_physical_line() -> None:
    with pytest.raises(DecodeError, match="physical line exceeds"):
        list(iter_decoded_lines(io.BytesIO(b"x" * 9), max_line_bytes=8))


@pytest.mark.parametrize("terminator", ["\n", "\r\n"])
def test_multibyte_limit_excludes_newline_bytes(terminator: str) -> None:
    accepted = ("ab" + terminator).encode("utf-16-le")
    assert [
        line.text
        for line in iter_decoded_lines(
            io.BytesIO(accepted), "utf-16-le", max_line_bytes=4
        )
    ] == ["ab"]

    rejected = ("abc" + terminator).encode("utf-16-le")
    with pytest.raises(DecodeError) as caught:
        list(iter_decoded_lines(io.BytesIO(rejected), "utf-16-le", 4))
    assert caught.value.byte_offset == 4


@pytest.mark.parametrize(
    ("data", "encoding", "offset"),
    [
        (b"a\xe2x", "utf-8", 1),
        (b"a\xe2", "utf-8", 1),
        (b"a\x00x", "utf-16-le", 2),
    ],
)
def test_decoder_reports_start_of_malformed_or_incomplete_sequence(
    data: bytes, encoding: str, offset: int
) -> None:
    with pytest.raises(DecodeError) as caught:
        list(iter_decoded_lines(io.BytesIO(data), encoding))
    assert caught.value.byte_offset == offset


def test_decoder_rejects_stateful_encoding_before_reading() -> None:
    class TrackingStream(io.BytesIO):
        reads = 0

        def read(self, size: int | None = -1) -> bytes:
            self.reads += 1
            return super().read(size)

    stream = TrackingStream(b"+" + b"A" * (1024 * 1024))
    with pytest.raises(DecodeError, match="unsupported potentially buffering encoding"):
        list(iter_decoded_lines(stream, "utf-7"))
    assert stream.reads == 0
