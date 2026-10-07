# CH9329F-Python

Python driver for the WCH **CH9329F** UART-to-USB HID chip. One package,
isolated subpackages per serial mode:

| Subpackage | Serial mode | Scope |
|---|---|---|
| `ch9329f.cfg0` | protocol (CFG0) | Keyboard/mouse reports for work modes 0-2, read-only configuration access |
| `ch9329f.cfg2` | transparent (CFG2) | Raw byte pipe for work mode 3 (custom HID) - planned, not implemented yet |

Subpackages never import each other; import exactly the one you need.

## Requirements

- Python 3.10+
- `pyserial` (library), `PySide6` (Qt demo only)

## Installation

```powershell
python -m pip install -e .
# or, to also install the Qt demo dependency:
python -m pip install -e ".[demo]"
```

## Quick start

```python
from ch9329f.cfg0 import CH9329F, MouseButton

with CH9329F.uart("COM6", baudrate=2_000_000) as device:
    device.keyboard.report(0, [0x04])       # hold 'a' (HID usage 0x04)
    device.keyboard.release()

    device.mouse.move(20, -10)              # relative move, sent by the thread
    device.mouse.button(MouseButton.LEFT, True)
    device.mouse.button(MouseButton.LEFT, False)
    device.mouse.flush()                    # drain pending state synchronously
```

## Documentation

- [Usage notes](docs/usage.md) - asynchronous mouse semantics, read-only
  configuration, and key-combo parsing

## Demos

The demos import the `ch9329f` package, so install it first (an editable
install keeps them pointed at this checkout).

Qt forwarder (this computer's keyboard/mouse to a second computer):

```powershell
python demo/qt_keyboard_mouse_forward_demo.py --port COM6
```

Click the window to capture, press **Ctrl+Alt** to release (a third key while
Ctrl+Alt is held is forwarded instead, so Ctrl+Alt+Del works). Defaults:
COM6 @ 2,000,000 baud, 250 Hz mouse reports.

Command line:

```powershell
python demo/cli_demo.py --port COM6            # interactive shell
python demo/cli_demo.py --port COM6 info
python demo/cli_demo.py --port COM6 key ctrl+alt+delete
python demo/cli_demo.py --port COM6 mouse move 20 -10
python demo/cli_demo.py --dry-run key shift+a  # print frames without a port
```

## Tools

- `tools/set_wait_ack.py` - set the special-config `wait_for_usb_ack` flag
  (special-config writes are intentionally not part of the library API).

## Repository layout

```text
ch9329f/        import package
├── cfg0/       protocol mode: keyboard/mouse
└── cfg2/       transparent mode: raw transport (planned)
demo/           example applications
tools/          one-off maintenance scripts
```

## Hardware notes

- Tested chip: CH9329F V1.0. Frames follow the vendor's "CH9329 chip serial
  protocol" V1.3 manual.
- The chip's UART side connects through a USB-serial adapter (CH343 in the
  test setup); the USB side enumerates as a standard keyboard/mouse on the
  target computer.
- Configure the chip with the vendor tool first: protocol mode (CFG0) and a
  matching baudrate (2,000,000 in the demos).

## TODO

- [ ] Refactor keyboard API
- [ ] Improve documentation
- [ ] Custom HID driver (host side)
- [ ] Device configuration writes
- [ ] Custom HID driver (slave side)
- [ ] Media key driver
- [ ] Touch-screen driver
- [ ] GPIO driver
