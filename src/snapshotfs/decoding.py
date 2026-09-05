"""Strict, byte-bounded line decoding for supported Windows text encodings."""

import codecs
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

MAX_LINE_BYTES = 1024 * 1024
READ_SIZE = 64 * 1024
_SINGLE_BYTE_ENCODINGS = {"ascii", "iso8859-1", *(f"cp125{i}" for i in range(9))}
_UTF16_ENCODINGS = {"utf-16", "utf-16-le", "utf-16-be"}


@dataclass(frozen=True, slots=True)
class DecodedLine:
    number: int
    text: str


class DecodeError(ValueError):
    def __init__(
        self, message: str, *, encoding: str, byte_offset: int, line_number: int
    ) -> None:
        super().__init__(
            f"{message} at byte offset {byte_offset} using {encoding} "
            f"(line {line_number})"
        )
        self.encoding = encoding
        self.byte_offset = byte_offset
        self.line_number = line_number


def iter_decoded_lines(
    stream: BinaryIO, encoding: str = "utf-8", max_line_bytes: int = MAX_LINE_BYTES
) -> Iterator[DecodedLine]:
    """Yield strict lines while bounding content bytes excluding LF or CRLF."""
    try:
        canonical = codecs.lookup(encoding).name
    except LookupError as exc:
        raise DecodeError(
            "unknown encoding", encoding=encoding, byte_offset=0, line_number=1
        ) from exc
    if canonical in {"utf-8", "utf-8-sig"} | _SINGLE_BYTE_ENCODINGS:
        yield from _iter_byte_lines(stream, encoding, canonical, max_line_bytes)
    elif canonical in _UTF16_ENCODINGS:
        yield from _iter_utf16_lines(stream, encoding, canonical, max_line_bytes)
    else:
        raise DecodeError(
            "unsupported potentially buffering encoding; use UTF-8, UTF-16, "
            "ASCII, Latin-1, or a Windows-125x code page",
            encoding=encoding,
            byte_offset=0,
            line_number=1,
        )


def _iter_byte_lines(
    stream: BinaryIO, encoding: str, canonical: str, max_line_bytes: int
) -> Iterator[DecodedLine]:
    pending = bytearray()
    line_start = 0
    line_number = 1
    first = True
    search_from = 0
    while chunk := stream.read(READ_SIZE):
        pending.extend(chunk)
        while (newline := pending.find(b"\n", search_from)) >= 0:
            raw = bytes(pending[:newline])
            del pending[: newline + 1]
            content = raw[:-1] if raw.endswith(b"\r") else raw
            _check_limit(content, encoding, line_start, line_number, max_line_bytes)
            yield DecodedLine(
                line_number,
                _decode(content, encoding, canonical, line_start, line_number, first),
            )
            line_start += len(raw) + 1
            line_number += 1
            first = False
            search_from = 0
        search_from = len(pending)
        possible_cr = 1 if pending.endswith(b"\r") else 0
        if len(pending) - possible_cr > max_line_bytes:
            _raise_limit(encoding, line_start, line_number, max_line_bytes)
    if pending:
        content = bytes(pending)
        _check_limit(content, encoding, line_start, line_number, max_line_bytes)
        yield DecodedLine(
            line_number,
            _decode(content, encoding, canonical, line_start, line_number, first),
        )


def _iter_utf16_lines(
    stream: BinaryIO, encoding: str, canonical: str, max_line_bytes: int
) -> Iterator[DecodedLine]:
    pending = bytearray()
    line_start = 0
    line_number = 1
    byte_order: str | None = {
        "utf-16-le": "little",
        "utf-16-be": "big",
    }.get(canonical)
    search_from = 0
    while chunk := stream.read(READ_SIZE):
        pending.extend(chunk)
        if byte_order is None and len(pending) >= 2:
            byte_order = _utf16_byte_order(pending, encoding, canonical, line_number)
        if byte_order is None:
            continue
        newline = b"\n\x00" if byte_order == "little" else b"\x00\n"
        carriage_return = b"\r\x00" if byte_order == "little" else b"\x00\r"
        while True:
            newline_at = _find_aligned(pending, newline, search_from)
            if newline_at < 0:
                break
            raw = bytes(pending[:newline_at])
            del pending[: newline_at + 2]
            content = raw[:-2] if raw.endswith(carriage_return) else raw
            _check_limit(content, encoding, line_start, line_number, max_line_bytes)
            yield DecodedLine(
                line_number,
                _decode_utf16(
                    content,
                    encoding,
                    canonical,
                    byte_order,
                    line_start,
                    line_number,
                ),
            )
            line_start += len(raw) + 2
            line_number += 1
            search_from = 0
        complete_length = len(pending) - len(pending) % 2
        search_from = complete_length
        possible_cr = 2 if pending[:complete_length].endswith(carriage_return) else 0
        if complete_length - possible_cr > max_line_bytes:
            _raise_limit(encoding, line_start, line_number, max_line_bytes)
    if pending:
        _check_limit(pending, encoding, line_start, line_number, max_line_bytes)
        yield DecodedLine(
            line_number,
            _decode_utf16(
                bytes(pending),
                encoding,
                canonical,
                byte_order or "little",
                line_start,
                line_number,
            ),
        )


def _utf16_byte_order(
    pending: bytearray, encoding: str, canonical: str, line_number: int
) -> str:
    if canonical == "utf-16-le":
        return "little"
    if canonical == "utf-16-be":
        return "big"
    if pending.startswith(codecs.BOM_UTF16_LE):
        return "little"
    if pending.startswith(codecs.BOM_UTF16_BE):
        return "big"
    raise DecodeError(
        "UTF-16 input requires a byte-order mark",
        encoding=encoding,
        byte_offset=0,
        line_number=line_number,
    )


def _find_aligned(data: bytearray, needle: bytes, start: int) -> int:
    index = data.find(needle, start)
    while index >= 0 and index % 2:
        index = data.find(needle, index + 1)
    return index


def _decode(
    content: bytes,
    encoding: str,
    canonical: str,
    line_start: int,
    line_number: int,
    first: bool,
) -> str:
    if canonical in {"utf-8", "utf-8-sig"}:
        decoder_encoding = "utf-8-sig" if first else "utf-8"
    else:
        decoder_encoding = encoding
    return _strict_decode(content, decoder_encoding, encoding, line_start, line_number)


def _decode_utf16(
    content: bytes,
    encoding: str,
    canonical: str,
    byte_order: str,
    line_start: int,
    line_number: int,
) -> str:
    decoder_encoding = encoding
    if canonical == "utf-16" and line_start > 0:
        suffix = "le" if byte_order == "little" else "be"
        decoder_encoding = f"utf-16-{suffix}"
    return _strict_decode(content, decoder_encoding, encoding, line_start, line_number)


def _strict_decode(
    content: bytes,
    decoder_encoding: str,
    requested_encoding: str,
    line_start: int,
    line_number: int,
) -> str:
    try:
        return content.decode(decoder_encoding, errors="strict")
    except UnicodeDecodeError as exc:
        message = (
            "incomplete byte sequence"
            if "unexpected end" in exc.reason or "truncated" in exc.reason
            else "invalid byte sequence"
        )
        raise DecodeError(
            message,
            encoding=requested_encoding,
            byte_offset=line_start + exc.start,
            line_number=line_number,
        ) from exc


def _check_limit(
    content: bytes | bytearray,
    encoding: str,
    line_start: int,
    line_number: int,
    max_line_bytes: int,
) -> None:
    if len(content) > max_line_bytes:
        _raise_limit(encoding, line_start, line_number, max_line_bytes)


def _raise_limit(
    encoding: str, line_start: int, line_number: int, max_line_bytes: int
) -> None:
    raise DecodeError(
        f"physical line exceeds {max_line_bytes} bytes",
        encoding=encoding,
        byte_offset=line_start + max_line_bytes,
        line_number=line_number,
    )
