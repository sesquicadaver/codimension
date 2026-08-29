# -*- coding: utf-8 -*-
#
# codimension - LSP stdio Content-Length framing (R202)
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Encode / decode LSP JSON-RPC messages with ``Content-Length`` headers."""

from __future__ import annotations

import json
from typing import Any, BinaryIO, Mapping, MutableMapping


class LspFramingError(ValueError):
    """Malformed or oversized LSP framing on stdio."""


#: Default maximum JSON body size (16 MiB).
DEFAULT_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


def encode_message(payload: Mapping[str, Any]) -> bytes:
    """Serialize ``payload`` as one LSP stdio frame (UTF-8 JSON)."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_message(
    stream: BinaryIO,
    *,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
) -> dict[str, Any]:
    """Read one framed LSP message from ``stream``.

    Raises:
        EOFError: when the stream ends cleanly before a full message.
        LspFramingError: on invalid headers or oversized bodies.
    """
    headers: MutableMapping[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            if not headers:
                raise EOFError("LSP stdio closed")
            raise LspFramingError("unexpected EOF while reading LSP headers")
        if line in (b"\r\n", b"\n"):
            break
        try:
            text = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise LspFramingError("LSP header is not ASCII") from exc
        if ":" not in text:
            raise LspFramingError(f"invalid LSP header line: {text!r}")
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    if "content-length" not in headers:
        raise LspFramingError("missing Content-Length header")
    try:
        length = int(headers["content-length"])
    except ValueError as exc:
        raise LspFramingError(f"invalid Content-Length: {headers['content-length']!r}") from exc
    if length < 0:
        raise LspFramingError(f"negative Content-Length: {length}")
    if length > max_message_bytes:
        raise LspFramingError(f"LSP message {length} bytes exceeds max_message_bytes={max_message_bytes}")

    body = stream.read(length)
    if len(body) < length:
        raise EOFError("LSP stdio closed mid-message")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LspFramingError("LSP body is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise LspFramingError("LSP payload must be a JSON object")
    return payload


__all__ = [
    "DEFAULT_MAX_MESSAGE_BYTES",
    "LspFramingError",
    "encode_message",
    "read_message",
]
