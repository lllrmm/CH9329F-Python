"""CH9329F protocol-mode (CFG0) support for keyboard/mouse work modes.

This is the ``ch9329f.cfg0`` subpackage: the chip's UART runs in protocol
mode (serial mode 0) and exposes its standard USB HID keyboard and mouse.

- work modes are limited to MODE0..2 (keyboard/mouse functions); MODE3 values
  are rejected when reading the configuration;
- the configuration is read-only: the 50-byte parameter block can be fetched
  but not written, and the serial mode cannot be switched;
- only the UART connection is available; the USB custom-HID data channel is
  not part of this subpackage.

Keyboard and mouse input live in dedicated helpers::

    from ch9329f.cfg0 import CH9329F, MouseButton

    with CH9329F.uart("COM6") as device:
        device.keyboard.report(0, [0x04])
        device.keyboard.release()
        device.mouse.move(20, -10)
        device.mouse.button(MouseButton.LEFT, True)
        device.mouse.button(MouseButton.LEFT, False)
"""

from .connections import CH9329F, UARTConnection
from .device import CH9329FDevice
from .input import Keyboard, Mouse
from .keymap import parse_combo
from .models import (
    Command,
    DeviceConfig,
    DeviceInfo,
    KeyboardModifier,
    MouseButton,
    SpecialConfig,
    USBStringDescriptor,
    USBStringType,
    WorkMode,
)
from .protocol import CH9329FError, CommandError, Packet, ProtocolError

__all__ = [
    "CH9329FDevice",
    "CH9329F",
    "CH9329FError",
    "CommandError",
    "Command",
    "DeviceConfig",
    "DeviceInfo",
    "Keyboard",
    "KeyboardModifier",
    "Mouse",
    "MouseButton",
    "Packet",
    "ProtocolError",
    "SpecialConfig",
    "USBStringDescriptor",
    "USBStringType",
    "UARTConnection",
    "WorkMode",
    "parse_combo",
]
