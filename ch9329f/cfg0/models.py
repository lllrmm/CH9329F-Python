from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag


class Command(IntEnum):
    GET_INFO = 0x01
    KEYBOARD = 0x02
    MOUSE_ABSOLUTE = 0x04
    MOUSE_RELATIVE = 0x05
    GET_CONFIG = 0x08
    GET_USB_STRING = 0x0A
    RESET = 0x0F
    GET_SPECIAL_CONFIG = 0x13


class WorkMode(IntEnum):
    # USB functions: 0 = keyboard + media + mouse + custom HID,
    # 1 = keyboard only (no media keys), 2 = keyboard + media + mouse.
    MODE0 = 0
    MODE1 = 1
    MODE2 = 2


class ConfigSource(IntEnum):
    SOFTWARE = 0
    PINS = 1


class USBStringType(IntEnum):
    MANUFACTURER = 0
    PRODUCT = 1
    SERIAL_NUMBER = 2


class KeyboardModifier(IntFlag):
    LEFT_CTRL = 0x01
    LEFT_SHIFT = 0x02
    LEFT_ALT = 0x04
    LEFT_GUI = 0x08
    RIGHT_CTRL = 0x10
    RIGHT_SHIFT = 0x20
    RIGHT_ALT = 0x40
    RIGHT_GUI = 0x80


class MouseButton(IntFlag):
    LEFT = 0x01
    RIGHT = 0x02
    MIDDLE = 0x04


@dataclass(frozen=True)
class DeviceInfo:
    version: str
    usb_connected: bool
    num_lock: bool
    caps_lock: bool
    scroll_lock: bool
    sleeping: bool
    raw: bytes


@dataclass(frozen=True)
class DeviceConfig:
    """CH9329F 50-byte parameter configuration.

    Configuration writes are not exposed by this library; this model parses
    and displays device configuration. Work mode is restricted to MODE0..2
    (keyboard/mouse functions) and the serial mode field to protocol mode
    (CFG0, either 0x00 or 0x80); other values are rejected.
    """

    work_mode: int
    serial_mode: int
    address: int
    baudrate: int
    uart_reserved: bytes
    packet_interval_ms: int
    vid: int
    pid: int
    keyboard_upload_interval_ms: int
    keyboard_release_delay_ms: int
    keyboard_auto_enter: int
    enter_character_1: bytes
    enter_character_2: bytes
    filter_prefix: bytes
    filter_suffix: bytes
    usb_string_flags: int
    keyboard_fast_upload: int
    sleep_control: int
    usb_speed_control: int
    touch_control: int
    polling_enable: int
    keyboard_polling: int
    mouse_polling: int
    media_polling: int
    custom_hid_polling: int
    reserved: bytes
    compatibility_extra: bytes = b""

    SIZE = 50

    @classmethod
    def from_bytes(
        cls, data: bytes, *, compatibility_extra: bytes = b""
    ) -> "DeviceConfig":
        if len(data) != cls.SIZE:
            raise ValueError(f"device configuration must be {cls.SIZE} bytes")
        if data[0] not in (*range(3), *range(0x80, 0x83)):
            raise ValueError(
                "device work mode is not MODE0..2; "
                "this library does not support MODE3 (custom HID)"
            )
        if data[1] not in (0x00, 0x80):
            raise ValueError(
                "device serial mode is not protocol (CFG0); "
                "this library supports CFG0 devices only"
            )
        return cls(
            work_mode=data[0],
            serial_mode=data[1],
            address=data[2],
            baudrate=int.from_bytes(data[3:7], "big"),
            uart_reserved=data[7:9],
            packet_interval_ms=int.from_bytes(data[9:11], "big"),
            vid=int.from_bytes(data[11:13], "little"),
            pid=int.from_bytes(data[13:15], "little"),
            keyboard_upload_interval_ms=int.from_bytes(data[15:17], "big"),
            keyboard_release_delay_ms=int.from_bytes(data[17:19], "big"),
            keyboard_auto_enter=data[19],
            enter_character_1=data[20:24],
            enter_character_2=data[24:28],
            filter_prefix=data[28:32],
            filter_suffix=data[32:36],
            usb_string_flags=data[36],
            keyboard_fast_upload=data[37],
            sleep_control=data[38],
            usb_speed_control=data[39],
            touch_control=data[40],
            polling_enable=data[41],
            keyboard_polling=data[42],
            mouse_polling=data[43],
            media_polling=data[44],
            custom_hid_polling=data[45],
            reserved=data[46:50],
            compatibility_extra=compatibility_extra,
        )

    def to_bytes(self) -> bytes:
        if self.work_mode not in (*range(3), *range(0x80, 0x83)):
            raise ValueError("work_mode must be 0..2 or 0x80..0x82")
        if self.serial_mode not in (0x00, 0x80):
            raise ValueError(
                "serial_mode must stay in protocol mode (0x00 or 0x80)"
            )
        _require_range("address", self.address, 0, 0xFF)
        _require_range("baudrate", self.baudrate, 0, 0xFFFFFFFF)
        _require_range("packet_interval_ms", self.packet_interval_ms, 0, 0xFFFF)
        _require_range("vid", self.vid, 0, 0xFFFF)
        _require_range("pid", self.pid, 0, 0xFFFF)
        _require_range(
            "keyboard_upload_interval_ms", self.keyboard_upload_interval_ms, 0, 0xFFFF
        )
        _require_range(
            "keyboard_release_delay_ms", self.keyboard_release_delay_ms, 0, 0xFFFF
        )
        byte_fields = (
            "keyboard_auto_enter",
            "usb_string_flags",
            "keyboard_fast_upload",
            "sleep_control",
            "usb_speed_control",
            "touch_control",
            "polling_enable",
            "keyboard_polling",
            "mouse_polling",
            "media_polling",
            "custom_hid_polling",
        )
        for name in byte_fields:
            _require_range(name, getattr(self, name), 0, 0xFF)
        for name, size in (
            ("uart_reserved", 2),
            ("enter_character_1", 4),
            ("enter_character_2", 4),
            ("filter_prefix", 4),
            ("filter_suffix", 4),
            ("reserved", 4),
        ):
            if len(getattr(self, name)) != size:
                raise ValueError(f"{name} must contain exactly {size} bytes")

        data = bytearray()
        data.extend((self.work_mode, self.serial_mode, self.address))
        data.extend(self.baudrate.to_bytes(4, "big"))
        data.extend(self.uart_reserved)
        data.extend(self.packet_interval_ms.to_bytes(2, "big"))
        data.extend(self.vid.to_bytes(2, "little"))
        data.extend(self.pid.to_bytes(2, "little"))
        data.extend(self.keyboard_upload_interval_ms.to_bytes(2, "big"))
        data.extend(self.keyboard_release_delay_ms.to_bytes(2, "big"))
        data.append(self.keyboard_auto_enter)
        data.extend(self.enter_character_1)
        data.extend(self.enter_character_2)
        data.extend(self.filter_prefix)
        data.extend(self.filter_suffix)
        data.extend(
            (
                self.usb_string_flags,
                self.keyboard_fast_upload,
                self.sleep_control,
                self.usb_speed_control,
                self.touch_control,
                self.polling_enable,
                self.keyboard_polling,
                self.mouse_polling,
                self.media_polling,
                self.custom_hid_polling,
            )
        )
        data.extend(self.reserved)
        if len(data) != self.SIZE:
            raise AssertionError(f"encoded configuration has unexpected size {len(data)}")
        return bytes(data)

    @property
    def raw(self) -> bytes:
        return self.to_bytes()

    @property
    def effective_work_mode(self) -> WorkMode:
        return WorkMode(self.work_mode & 0x7F)

    @property
    def work_mode_source(self) -> str:
        return "pins" if self.work_mode & 0x80 else "software"


@dataclass(frozen=True)
class SpecialConfig:
    disable_sleep: int
    high_speed_usb: int
    touch_enabled: int
    hid_command_enabled: int
    wait_for_usb_ack: int
    reserved: bytes = b"\x00" * 5

    SIZE = 10

    @classmethod
    def from_bytes(cls, data: bytes) -> "SpecialConfig":
        if len(data) != cls.SIZE:
            raise ValueError(f"special configuration must be {cls.SIZE} bytes")
        return cls(*data[:5], data[5:])

@dataclass(frozen=True)
class USBStringDescriptor:
    kind: USBStringType
    data: bytes

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


def _require_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in range {minimum}..{maximum}")
