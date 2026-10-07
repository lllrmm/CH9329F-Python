from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from threading import RLock

from .input import Keyboard, Mouse
from .models import (
    Command,
    DeviceConfig,
    DeviceInfo,
    SpecialConfig,
    USBStringDescriptor,
    USBStringType,
)
from .protocol import CommandError, Packet, ProtocolError, read_packet


class CH9329FDevice:
    def __init__(
        self,
        port,
        *,
        address: int = 0,
        timeout: float = 0.5,
        expect_responses: bool = True,
        trace: Callable[[str, bytes], None] | None = None,
    ):
        self.port = port
        self.address = address
        self.timeout = timeout
        self.expect_responses = expect_responses and address != 0xFF
        self.trace = trace
        self._lock = RLock()
        self.keyboard = Keyboard(self)
        self.mouse = Mouse(self)
        self._pending: deque[Packet] = deque()
        self._owns_port = False

    @classmethod
    def open_serial(
        cls,
        port: str,
        baudrate: int = 9600,
        *,
        address: int = 0,
        timeout: float = 0.5,
        trace: Callable[[str, bytes], None] | None = None,
    ) -> "CH9329FDevice":
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required to open a serial port") from exc
        connection = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=min(timeout, 0.05),
            write_timeout=timeout,
        )
        device = cls(connection, address=address, timeout=timeout, trace=trace)
        device._owns_port = True
        return device

    def transact(
        self, command: int | Command, data: bytes = b"", *, extended: bool = False
    ) -> Packet | None:
        command_value = int(command)
        with self._lock:
            request = Packet(self.address, command_value, bytes(data), extended)
            raw = request.encode()
            if self.trace:
                self.trace("TX", raw)
            written = self.port.write(raw)
            if written is not None and written != len(raw):
                raise ProtocolError(f"short serial write: {written}/{len(raw)} bytes")
            if hasattr(self.port, "flush"):
                self.port.flush()
            if not self.expect_responses:
                return None

            expected = command_value | 0x80
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                response, response_raw = read_packet(
                    self.port, max(0.001, deadline - time.monotonic())
                )
                if self.trace:
                    self.trace("RX", response_raw)
                if response.command == expected:
                    self._raise_for_status(command_value, response)
                    return response
                if response.command == (command_value | 0xC0):
                    status = response.data[0] if response.data else 0xFF
                    raise CommandError(command_value, status)
                self._pending.append(response)
            raise ProtocolError(f"response timeout waiting for command 0x{expected:02X}")

    @staticmethod
    def _raise_for_status(command: int, response: Packet) -> None:
        data_responses = {
            Command.GET_INFO,
            Command.GET_CONFIG,
            Command.GET_USB_STRING,
            Command.GET_SPECIAL_CONFIG,
        }
        if command not in data_responses and response.data and response.data[0] != 0:
            raise CommandError(command, response.data[0])

    def get_info(self) -> DeviceInfo | None:
        response = self.transact(Command.GET_INFO)
        if response is None:
            return None
        if len(response.data) != 8:
            raise ProtocolError(f"GET_INFO returned {len(response.data)} bytes, expected 8")
        version_value, connected, leds, sleep_state = response.data[:4]
        # The manual encodes 0x30 as V1.0 and 0x31 as V1.1.
        version = (
            f"V1.{version_value - 0x30}"
            if 0x30 <= version_value <= 0x39
            else f"0x{version_value:02X}"
        )
        return DeviceInfo(
            version,
            connected == 1,
            bool(leds & 0x01),
            bool(leds & 0x02),
            bool(leds & 0x04),
            sleep_state == 0x03,
            response.data,
        )

    def get_config(self) -> DeviceConfig | None:
        response = self.transact(Command.GET_CONFIG)
        if response is None:
            return None
        if len(response.data) not in (50, 65):
            raise ProtocolError(
                f"GET_CONFIG returned {len(response.data)} bytes, expected 50 or 65"
            )
        data = response.data[:50]
        return DeviceConfig.from_bytes(
            data, compatibility_extra=response.data[DeviceConfig.SIZE :]
        )

    def get_usb_string(
        self, kind: int | USBStringType
    ) -> USBStringDescriptor | None:
        string_type = USBStringType(kind)
        response = self.transact(Command.GET_USB_STRING, bytes((string_type,)))
        if response is None:
            return None
        if len(response.data) < 2:
            raise ProtocolError("USB string response is shorter than 2 bytes")
        returned_type, length = response.data[:2]
        if returned_type != string_type:
            raise ProtocolError(
                f"USB string response type is {returned_type}, expected {string_type}"
            )
        if length > 23 or len(response.data) != length + 2:
            raise ProtocolError("USB string response has an invalid length")
        return USBStringDescriptor(string_type, response.data[2:])

    def get_special_config(self) -> SpecialConfig | None:
        response = self.transact(Command.GET_SPECIAL_CONFIG)
        if response is None:
            return None
        try:
            return SpecialConfig.from_bytes(response.data)
        except ValueError as exc:
            raise ProtocolError(str(exc)) from exc

    def reset(self):
        return self.transact(Command.RESET)

    def receive(self, timeout: float | None = None) -> Packet:
        with self._lock:
            if self._pending:
                return self._pending.popleft()
            packet, raw = read_packet(self.port, self.timeout if timeout is None else timeout)
            if self.trace:
                self.trace("RX", raw)
            return packet

    def _raw_write(self, data: bytes) -> None:
        if self.trace:
            self.trace("TX", data)
        self.port.write(data)
        if hasattr(self.port, "flush"):
            self.port.flush()

    def close(self) -> None:
        self.mouse.close()
        if self._owns_port and self.port is not None:
            self.port.close()
            self.port = None

    def __enter__(self) -> "CH9329FDevice":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
