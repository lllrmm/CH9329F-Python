from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Protocol


HEADER = b"\x57\xAB"


class CH9329FError(Exception):
    """Base error for CH9329F operations."""


class ProtocolError(CH9329FError):
    """A received frame is malformed or timed out."""


STATUS_TEXT = {
    0x00: "success",
    0xE1: "serial byte timeout",
    0xE2: "invalid frame header",
    0xE3: "invalid command",
    0xE4: "checksum mismatch",
    0xE5: "invalid parameter",
    0xE6: "operation failed",
}


class CommandError(CH9329FError):
    def __init__(self, command: int, status: int):
        self.command = command
        self.status = status
        message = STATUS_TEXT.get(status, f"unknown status 0x{status:02X}")
        super().__init__(f"command 0x{command:02X} failed: {message}")


@dataclass(frozen=True)
class Packet:
    address: int
    command: int
    data: bytes = b""
    extended: bool = False

    def encode(self) -> bytes:
        if not 0 <= self.address <= 0xFF:
            raise ValueError("address must be in range 0..255")
        max_length = 510 if self.extended else 255
        if len(self.data) > max_length:
            raise ValueError(f"payload exceeds {max_length} bytes")
        length = len(self.data).to_bytes(2 if self.extended else 1, "big")
        frame = HEADER + bytes((self.address, self.command)) + length + self.data
        return frame + bytes((sum(frame) & 0xFF,))

    @classmethod
    def decode(cls, frame: bytes, *, extended: bool | None = None) -> "Packet":
        if len(frame) < 6 or frame[:2] != HEADER:
            raise ProtocolError("invalid frame header or length")
        if extended is None:
            extended = frame[3] in (0x10, 0x91)
        length_size = 2 if extended else 1
        header_size = 4 + length_size
        if len(frame) < header_size + 1:
            raise ProtocolError("truncated frame")
        data_length = int.from_bytes(frame[4:header_size], "big")
        expected_length = header_size + data_length + 1
        if len(frame) != expected_length:
            raise ProtocolError(
                f"frame length is {len(frame)}, expected {expected_length}"
            )
        if (sum(frame[:-1]) & 0xFF) != frame[-1]:
            raise ProtocolError("checksum mismatch")
        return cls(frame[2], frame[3], frame[header_size:-1], extended)


class SerialLike(Protocol):
    timeout: float | None

    def read(self, size: int = 1) -> bytes: ...


def read_packet(port: SerialLike, timeout: float = 0.5) -> tuple[Packet, bytes]:
    """Read one frame, discarding bytes before the 57 AB header."""
    deadline = monotonic() + timeout
    matched = 0
    while monotonic() < deadline:
        chunk = port.read(1)
        if not chunk:
            continue
        value = chunk[0]
        if matched == 0:
            matched = 1 if value == HEADER[0] else 0
        elif value == HEADER[1]:
            break
        else:
            matched = 1 if value == HEADER[0] else 0
    else:
        raise ProtocolError("response timeout waiting for frame header")

    fixed = _read_exact(port, 3, deadline)
    command = fixed[1]
    extended = command == 0x91
    length_bytes = fixed[2:] + (_read_exact(port, 1, deadline) if extended else b"")
    data_length = int.from_bytes(length_bytes, "big")
    tail = _read_exact(port, data_length + 1, deadline)
    raw = HEADER + fixed[:2] + length_bytes + tail
    try:
        return Packet.decode(raw, extended=extended), raw
    except ProtocolError as exc:
        # CH9329F V1.0 has been observed returning 65 config bytes while the
        # GET_CONFIG length field remains 0x32. Its checksum covers all 65.
        if command != 0x88 or data_length != 50 or str(exc) != "checksum mismatch":
            raise
        raw += _read_exact(port, 15, deadline)
        if (sum(raw[:-1]) & 0xFF) != raw[-1]:
            raise ProtocolError("checksum mismatch") from exc
        return Packet(raw[2], raw[3], raw[5:-1]), raw


def _read_exact(port: SerialLike, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size and monotonic() < deadline:
        chunk = port.read(size - len(data))
        if chunk:
            data.extend(chunk)
    if len(data) != size:
        raise ProtocolError(f"response timeout after {len(data)}/{size} bytes")
    return bytes(data)
