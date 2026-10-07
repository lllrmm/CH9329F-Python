"""CH9329F protocol-mode (CFG0) command-line demo.

Small interactive/one-shot controller built on the ``ch9329f.cfg0``
subpackage: keyboard combos, text typing, relative/absolute mouse moves,
raw frames, and read-only status/configuration display.

Run from the project root::

    python demo/cli_demo.py --port COM6            # interactive shell
    python demo/cli_demo.py --port COM6 info
    python demo/cli_demo.py --port COM6 key ctrl+alt+delete
    python demo/cli_demo.py --dry-run key shift+a  # print frames, no port

The default port is COM6 at 2,000,000 baud, matching the hardware setup used
by the other demos; use --baudrate/--address to match a different one.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import time
from dataclasses import asdict

import serial
from serial.tools import list_ports

from ch9329f.cfg0 import CH9329F, CH9329FDevice, CH9329FError, MouseButton
from ch9329f.cfg0.keymap import CHAR_KEYS, parse_combo

WORK_MODE_NAMES = {
    0: "keyboard + media + mouse + custom HID",
    1: "keyboard only",
    2: "keyboard + media + mouse",
}

CLICK_BUTTONS = {
    "left": MouseButton.LEFT,
    "right": MouseButton.RIGHT,
    "middle": MouseButton.MIDDLE,
}

HELP = """Commands:
  info                             show chip and USB state
  config                           show the read-only 50-byte configuration
  key <combo> [hold_ms]            press and release, e.g. ctrl+alt+delete
  release                          release all keyboard keys
  text <text>                      type US-layout ASCII text
  mouse move <dx> <dy>             relative move (async, then flushed)
  mouse wheel <steps>              scroll
  mouse click <left|right|middle> [hold_ms]
  mouse abs <x> <y>                absolute move, 0..4095
  raw <hex bytes>                  write exact serial bytes
  receive                          read and decode one incoming protocol frame
  help                             show this help
  quit                             close the port

Numbers accept decimal or 0x-prefixed notation. Text can be quoted.
"""


class DryRunPort:
    """Write-only stand-in for a serial port (--dry-run)."""

    def write(self, data: bytes) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def number(value: str) -> int:
    return int(value, 0)


def parse_hex(parts: list[str]) -> bytes:
    cleaned = re.sub(r"0[xX]", "", " ".join(parts).replace(",", " "))
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError(
            "expected hexadecimal bytes such as '57 AB 00 01 00 03'"
        ) from exc


def print_trace(direction: str, data: bytes) -> None:
    print(f"{direction}  {data.hex(' ').upper()}")


def print_ports() -> None:
    ports = sorted(list_ports.comports(), key=lambda item: item.device)
    if not ports:
        print("No serial ports found.")
        return
    for item in ports:
        details = " - ".join(
            value for value in (item.description, item.hwid) if value
        )
        print(f"{item.device:10} {details}")


def format_config(config) -> str:
    work = config.work_mode & 0x7F
    return "\n".join(
        (
            f"work mode    : 0x{config.work_mode:02X} "
            f"({WORK_MODE_NAMES.get(work, 'unknown')}, {config.work_mode_source})",
            f"serial mode  : 0x{config.serial_mode:02X} (protocol/CFG0)",
            f"address      : 0x{config.address:02X}",
            f"baudrate     : {config.baudrate}",
            f"packet gap   : {config.packet_interval_ms} ms",
            f"USB VID:PID  : {config.vid:04X}:{config.pid:04X}",
            f"raw          : {config.raw.hex(' ').upper()}",
        )
    )


def type_text(device, text: str) -> None:
    for character in text:
        entry = CHAR_KEYS.get(character)
        if entry is None:
            raise ValueError(
                f"unsupported character {character!r}; "
                "US-layout printable ASCII only"
            )
        modifier, keycode = entry
        device.keyboard.report(modifier, [keycode])
        time.sleep(0.01)
        device.keyboard.release()
        time.sleep(0.01)


def execute_mouse(device, args: list[str]) -> None:
    if not args:
        raise ValueError("usage: mouse <move|wheel|click|abs> ...")
    operation = args[0].lower()
    mouse = device.mouse
    if operation == "move" and len(args) == 3:
        mouse.move(number(args[1]), number(args[2]))
        mouse.flush()
    elif operation == "wheel" and len(args) == 2:
        mouse.wheel(number(args[1]))
        mouse.flush()
    elif operation == "click" and len(args) in (2, 3):
        button = CLICK_BUTTONS.get(args[1].lower())
        if button is None:
            raise ValueError("click button must be left, right, or middle")
        hold_ms = number(args[2]) if len(args) == 3 else 30
        mouse.button(button, True)
        mouse.flush()
        time.sleep(hold_ms / 1000)
        mouse.button(button, False)
        mouse.flush()
    elif operation == "abs" and len(args) == 3:
        mouse.move_to(number(args[1]), number(args[2]))
    else:
        raise ValueError("invalid mouse command; type 'help' for syntax")


def execute(device, words: list[str], *, dry_run: bool) -> bool:
    if not words:
        return True
    command, args = words[0].lower(), words[1:]
    if command in ("quit", "exit"):
        return False
    if command == "help":
        print(HELP)
        return True
    if command == "raw":
        # Exact serial bytes; _raw_write is the library's semi-private hook.
        device._raw_write(parse_hex(args))
        return True
    if command == "receive":
        if dry_run:
            raise ValueError("receive is not available in dry-run mode")
        packet = device.receive()
        print(
            f"address=0x{packet.address:02X} command=0x{packet.command:02X} "
            f"data={packet.data.hex(' ').upper()}"
        )
        return True
    if command == "info":
        info = device.get_info()
        if info is None:
            print("(no response)")
            return True
        for key, value in asdict(info).items():
            if key != "raw":
                print(f"{key:14}: {value}")
        return True
    if command == "config":
        config = device.get_config()
        if config is None:
            print("(no response)")
            return True
        print(format_config(config))
        return True
    if command == "key":
        if not args:
            raise ValueError("usage: key <combo> [hold_ms]")
        modifier, keycodes = parse_combo(args[0])
        device.keyboard.report(modifier, keycodes)
        time.sleep(number(args[1]) / 1000 if len(args) > 1 else 0.02)
        device.keyboard.release()
        return True
    if command == "release":
        device.keyboard.release()
        return True
    if command == "text":
        if not args:
            raise ValueError("usage: text <text>")
        type_text(device, " ".join(args))
        return True
    if command == "mouse":
        execute_mouse(device, args)
        return True
    raise ValueError(f"unknown command: {command}; type 'help' for commands")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CH9329F (CFG0) command-line demo")
    parser.add_argument("--port", default="COM6", help="serial port (default: COM6)")
    parser.add_argument(
        "--baudrate", "--baud", type=int, default=2_000_000,
        help="serial baudrate (default: 2000000)",
    )
    parser.add_argument("--address", type=number, default=0)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--trace", action="store_true", help="print TX/RX frames")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print frames without opening a port",
    )
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument(
        "command", nargs=argparse.REMAINDER,
        help="one command; omit for an interactive shell",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_ports:
        print_ports()
        return 0
    if not 0 <= args.address <= 0xFF:
        print("error: --address must be in range 0..255", file=sys.stderr)
        return 2

    trace = print_trace if (args.trace or args.dry_run) else None

    if args.dry_run:
        device = CH9329FDevice(
            DryRunPort(),
            address=args.address,
            timeout=args.timeout,
            expect_responses=False,
            trace=trace,
        )
    else:
        try:
            device = CH9329F.uart(
                args.port,
                args.baudrate,
                address=args.address,
                timeout=args.timeout,
                trace=trace,
            )
        except serial.SerialException as exc:
            print(f"error: cannot open {args.port}: {exc}", file=sys.stderr)
            return 1

    try:
        if args.command:
            execute(device, args.command, dry_run=args.dry_run)
            return 0
        label = (
            f"dry-run @ {args.baudrate}"
            if args.dry_run
            else f"{args.port} @ {args.baudrate}"
        )
        print(f"CH9329F ready: {label}")
        print("Type 'help' for commands, 'quit' to exit.")
        while True:
            try:
                line = input("ch9329f> ")
            except EOFError:
                break
            try:
                if not execute(device, shlex.split(line), dry_run=args.dry_run):
                    break
            except (CH9329FError, ValueError) as exc:
                print(f"error: {exc}")
        return 0
    except (CH9329FError, ValueError, serial.SerialException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    finally:
        device.close()


if __name__ == "__main__":
    raise SystemExit(main())
