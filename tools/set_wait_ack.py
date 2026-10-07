"""Temporary: set the CH9329F special-config wait-for-USB-fetch ACK flag.

Reads the special config (0x13), sets byte 5 (1-based) to 0x01 -- the
"USB keyboard/mouse packet must wait until the USB host has fetched it
before replying" flag -- writes it back (0x14), then reads and prints again.

ch9329f.cfg0 does not expose special-config writes, so this script uses
the raw protocol commands.

Run from the project root::

    python tools/set_wait_ack.py
"""

from __future__ import annotations

import argparse

from ch9329f.cfg0 import CH9329F, SpecialConfig

CMD_GET_SPECIAL = 0x13
CMD_SET_SPECIAL = 0x14

# 5th byte (1-based) of the special config: USB keyboard/mouse ACK timing.
# 0x01 = only reply after the USB host has successfully fetched the packet.
ACK_FLAG_INDEX = 4


def describe(raw: bytes) -> None:
    print(f"raw ({len(raw)} bytes): {raw.hex(' ').upper()}")
    try:
        config = SpecialConfig.from_bytes(raw)
    except ValueError as exc:
        print(f"parse error: {exc}")
        return
    print(f"  disable_sleep       : {config.disable_sleep}")
    print(f"  high_speed_usb      : {config.high_speed_usb}")
    print(f"  touch_enabled       : {config.touch_enabled}")
    print(f"  hid_command_enabled : {config.hid_command_enabled}")
    print(f"  wait_for_usb_ack    : {config.wait_for_usb_ack}")
    print(f"  reserved            : {config.reserved.hex(' ').upper()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baudrate", "--baud", type=int, default=2_000_000)
    args = parser.parse_args()

    with CH9329F.uart(args.port, args.baudrate, timeout=0.5) as device:
        print("== before ==")
        response = device.transact(CMD_GET_SPECIAL)
        if response is None or len(response.data) < ACK_FLAG_INDEX + 1:
            print("no/short special-config response:", response)
            return 1
        raw = response.data
        describe(raw)

        updated = bytearray(raw)
        if updated[ACK_FLAG_INDEX] == 0x01:
            print("\nbyte 5 is already 0x01; writing the unchanged value anyway")
        updated[ACK_FLAG_INDEX] = 0x01
        device.transact(CMD_SET_SPECIAL, bytes(updated))
        print("\nspecial config written")

        print("\n== after ==")
        response = device.transact(CMD_GET_SPECIAL)
        if response is None:
            print("no response")
            return 1
        describe(response.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
