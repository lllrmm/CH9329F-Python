"""Qt demo: forward this computer's mouse and keyboard to another computer.

Wiring
------
- Controlling computer (this script): the CH9329F UART side is attached
  through a USB-serial adapter (e.g. CH343 -> COM6), protocol mode (CFG0).
- Controlled computer: the CH9329F USB plug is attached; it sees a standard
  USB mouse and keyboard.

Controls
--------
- Click the window to capture the mouse and keyboard.
- While captured, movement / buttons / wheel / keystrokes are forwarded; the
  pointer is hidden and locked to the window center.
- Press Ctrl+Alt to release. Pressing a third key while holding Ctrl+Alt
  forwards the full combination instead, so Ctrl+Alt+Del still works.
- Closing the window disconnects.

Run::

    python demo/qt_keyboard_mouse_forward_demo.py --port COM6

The default baudrate is 2 Mbaud and must match the CH9329F configuration.
Relative movement and wheel events are handed to the library's asynchronous
mouse; its sender thread drains the accumulated deltas at ``--report-rate``
reports per second (default 250).
"""

from __future__ import annotations

import argparse
import sys

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # pragma: no cover - PyQt6 fallback
    try:
        from PyQt6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise SystemExit(
            "PySide6 or PyQt6 is required: python -m pip install PySide6"
        ) from exc

from ch9329f.cfg0 import CH9329F, CH9329FError, Mouse, MouseButton, WorkMode


STATUS_INTERVAL_MS = 200

CTRL_MASK = 0x01
ALT_MASK = 0x04


def qt_button(event_button) -> MouseButton | None:
    """Map a Qt mouse button to the CH9329F enum, or None if unsupported."""
    mapping = {
        QtCore.Qt.MouseButton.LeftButton: MouseButton.LEFT,
        QtCore.Qt.MouseButton.RightButton: MouseButton.RIGHT,
        QtCore.Qt.MouseButton.MiddleButton: MouseButton.MIDDLE,
    }
    return mapping.get(event_button)


_QT_MODIFIERS = {
    QtCore.Qt.Key.Key_Shift: 0x02,
    QtCore.Qt.Key.Key_Control: 0x01,
    QtCore.Qt.Key.Key_Alt: 0x04,
    QtCore.Qt.Key.Key_Meta: 0x08,
}


def _add_key(table: dict, name: str, hid: int) -> None:
    key = getattr(QtCore.Qt.Key, name, None)
    if key is not None:
        table[key] = hid


def _build_key_table() -> dict:
    table: dict = {}
    for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        _add_key(table, f"Key_{letter}", 0x04 + index)
    for digit in range(10):
        _add_key(table, f"Key_{digit}", 0x27 if digit == 0 else 0x1D + digit)
    for number in range(1, 13):
        _add_key(table, f"Key_F{number}", 0x39 + number)
    for name, hid in (
        ("Key_Return", 0x28),
        ("Key_Escape", 0x29),
        ("Key_Backspace", 0x2A),
        ("Key_Tab", 0x2B),
        ("Key_Space", 0x2C),
        ("Key_CapsLock", 0x39),
        ("Key_Print", 0x46),
        ("Key_ScrollLock", 0x47),
        ("Key_Pause", 0x48),
        ("Key_Insert", 0x49),
        ("Key_Home", 0x4A),
        ("Key_PageUp", 0x4B),
        ("Key_Delete", 0x4C),
        ("Key_End", 0x4D),
        ("Key_PageDown", 0x4E),
        ("Key_Right", 0x4F),
        ("Key_Left", 0x50),
        ("Key_Down", 0x51),
        ("Key_Up", 0x52),
        ("Key_NumLock", 0x53),
        ("Key_Menu", 0x65),
        ("Key_Minus", 0x2D),
        ("Key_Equal", 0x2E),
        ("Key_BracketLeft", 0x2F),
        ("Key_BracketRight", 0x30),
        ("Key_Backslash", 0x31),
        ("Key_Semicolon", 0x33),
        ("Key_Apostrophe", 0x34),
        ("Key_QuoteLeft", 0x35),
        ("Key_Comma", 0x36),
        ("Key_Period", 0x37),
        ("Key_Slash", 0x38),
        ("Key_Enter", 0x58),
        ("Key_Plus", 0x57),
        ("Key_Asterisk", 0x55),
    ):
        _add_key(table, name, hid)
    return table


_QT_KEY_TABLE = _build_key_table()
_HID_TO_QT = {hid: qt for qt, hid in _QT_KEY_TABLE.items()}
_MODIFIER_ORDER = (0x01, 0x02, 0x04, 0x08)
_MODIFIER_NAMES = {0x01: "Ctrl", 0x02: "Shift", 0x04: "Alt", 0x08: "Win"}


def hid_key_name(code: int) -> str:
    """Human-readable name for a HID keyboard usage code."""
    qt_key = _HID_TO_QT.get(code)
    if qt_key is None:
        return f"0x{code:02X}"
    name = qt_key.name
    return name[4:] if name.startswith("Key_") else name


def map_key(qt_key) -> tuple[int, int]:
    """Map a Qt key to (hid keycode, modifier bit)."""
    modifier = _QT_MODIFIERS.get(qt_key)
    if modifier is not None:
        return 0, modifier
    return _QT_KEY_TABLE.get(qt_key, 0), 0


WORK_MODE_NAMES = {
    0: "keyboard + media + mouse + custom HID",
    1: "keyboard only",
    2: "keyboard + media + mouse",
}


def read_device_mode(device) -> tuple[str, str | None]:
    """Read the CH9329F configuration and describe its mode (GET_CONFIG).

    Read-only. Returns ``(short mode text, warning or None)``.
    """
    try:
        config = device.get_config()
    except (CH9329FError, OSError, ValueError) as exc:
        return "mode read failed", str(exc)
    if config is None:
        return "mode unknown", "no configuration response"
    work_value = config.work_mode & 0x7F
    mode = f"MODE{work_value}/CFG0"
    try:
        work = WorkMode(work_value)
    except ValueError:
        return mode, f"unknown work mode MODE{work_value}"
    if work not in (WorkMode.MODE0, WorkMode.MODE2):
        warning = (
            f"current {work.name} ({WORK_MODE_NAMES.get(work_value, 'unknown')}); "
            "demo needs keyboard + mouse (MODE0 or MODE2)"
        )
        return mode, warning
    return mode, None


def read_wait_ack(device) -> bool | None:
    """Read the special-config wait-for-USB-fetch ACK flag (0x13).

    Read-only. Returns True/False, or None when it cannot be read.
    """
    try:
        config = device.get_special_config()
    except (CH9329FError, OSError):
        return None
    if config is None:
        return None
    return bool(config.wait_for_usb_ack)


class KeyboardSender:
    """Track physical key state and send keyboard reports.

    Holding Ctrl+Alt arms the release hotkey: releasing either modifier
    without pressing another key signals that the capture should end; a third
    key (e.g. Delete) forwards the full combination instead.
    """

    def __init__(self, device) -> None:
        self._device = device
        self.modifiers = 0
        self.held: list[int] = []
        self.error_count = 0
        self.last_error: str | None = None
        self._ctrl_alt_pending = False

    def _send(self) -> None:
        try:
            self._device.keyboard.report(self.modifiers, list(self.held))
        except (CH9329FError, OSError) as exc:
            self.error_count += 1
            self.last_error = str(exc)

    def press(self, keycode: int, modifier: int) -> None:
        if modifier:
            if self.modifiers & modifier:
                return
            self.modifiers |= modifier
            if (self.modifiers & CTRL_MASK) and (self.modifiers & ALT_MASK):
                self._ctrl_alt_pending = True
        elif keycode:
            if keycode in self.held or len(self.held) >= 6:
                return
            self.held.append(keycode)
            self._ctrl_alt_pending = False
        else:
            return
        self._send()

    def release(self, keycode: int, modifier: int) -> bool:
        """Release a key; returns True when the release hotkey fired."""
        if modifier:
            if not self.modifiers & modifier:
                return False
            if self._ctrl_alt_pending and modifier in (CTRL_MASK, ALT_MASK):
                self._ctrl_alt_pending = False
                return True
            self.modifiers &= ~modifier
        elif keycode:
            if keycode not in self.held:
                return False
            self.held.remove(keycode)
        else:
            return False
        self._send()
        return False

    def release_all(self) -> None:
        self._ctrl_alt_pending = False
        if not self.modifiers and not self.held:
            return
        self.modifiers = 0
        self.held.clear()
        self._send()


class CaptureWindow(QtWidgets.QWidget):
    def __init__(
        self,
        device,
        port_label: str,
        warning: str | None = None,
        wait_ack: bool | None = None,
    ) -> None:
        super().__init__()
        self._device = device
        self._keyboard = KeyboardSender(device)
        self.captured = False
        self._saved_pos: QtCore.QPoint | None = None
        self._port_label = port_label
        self._warning = warning
        self._wait_ack = wait_ack
        self._info = None
        self._info_error: str | None = None

        self.setWindowTitle(f"CH9329F mouse/keyboard forward - {port_label}")
        self.resize(720, 480)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)

        self.status_label = QtWidgets.QLabel(self)
        self.status_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.status_label.setStyleSheet("font-size: 14px;")
        self.center_label = QtWidgets.QLabel(self)
        self.center_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.center_label.setStyleSheet("font-size: 15px;")
        # Let mouse events reach the window even when the cursor is over a
        # label; otherwise move events without a pressed button are dropped
        # by the child widget and are never delivered to the window.
        for label in (self.status_label, self.center_label):
            label.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        layout.addWidget(self.center_label)
        layout.addStretch(1)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(STATUS_INTERVAL_MS)

        self._update_labels()

    # -- capture handling -------------------------------------------------

    def _center(self) -> QtCore.QPoint:
        return QtCore.QPoint(self.width() // 2, self.height() // 2)

    def _warp_to_center(self) -> None:
        QtGui.QCursor.setPos(self.mapToGlobal(self._center()))

    def _set_captured(self, captured: bool) -> None:
        if captured == self.captured:
            return
        self.captured = captured
        if captured:
            self._saved_pos = QtGui.QCursor.pos()
            self.setCursor(QtCore.Qt.CursorShape.BlankCursor)
            self._warp_to_center()
            self.setFocus()
        else:
            self.unsetCursor()
            self._release_all_inputs()
            if self._saved_pos is not None:
                QtGui.QCursor.setPos(self._saved_pos)
                self._saved_pos = None
        self._update_labels()

    def _release_all_inputs(self) -> None:
        self._keyboard.release_all()
        if self._device.mouse.buttons:
            for button in (MouseButton.LEFT, MouseButton.RIGHT, MouseButton.MIDDLE):
                self._device.mouse.button(button, False)

    def _update_labels(self) -> None:
        first = self._port_label
        if self._info is not None:
            first += f" | {self._info.version}"
        if self._wait_ack is None:
            first += " | wait_usb_ack: ?"
        else:
            first += f" | wait_usb_ack: {'on' if self._wait_ack else 'off'}"
        status = [first]
        if self._warning:
            status.append(f"⚠ {self._warning}")
        if self._info_error:
            status.append(f"Device status read failed: {self._info_error}")
        elif self._info is not None:
            info = self._info
            status.append(
                f"USB: {'connected' if info.usb_connected else 'disconnected'}"
                f"    Sleep: {'yes' if info.sleeping else 'no'}"
            )
            status.append(
                f"CAPS LOCK: {'on' if info.caps_lock else 'off'}"
                f"    NUM LOCK: {'on' if info.num_lock else 'off'}"
                f"    SCROLL LOCK: {'on' if info.scroll_lock else 'off'}"
            )
        pressed = [
            _MODIFIER_NAMES[bit]
            for bit in _MODIFIER_ORDER
            if self._keyboard.modifiers & bit
        ]
        pressed += [hid_key_name(code) for code in self._keyboard.held]
        keyboard_line = f"Keyboard: {' + '.join(pressed) if pressed else 'idle'}"
        if self._keyboard.error_count:
            keyboard_line += (
                f", {self._keyboard.error_count} send errors"
                f" ({self._keyboard.last_error})"
            )
        status.append(keyboard_line)
        mouse = self._device.mouse
        mouse_line = f"Mouse: report rate {mouse.report_rate:g} Hz"
        if mouse.error_count:
            mouse_line += f", {mouse.error_count} send errors ({mouse.last_error})"
        status.append(mouse_line)
        self.status_label.setText("\n".join(status))

        if self.captured:
            center = (
                "Captured: mouse / keyboard are forwarded to the target\n"
                "Press Ctrl+Alt to release"
            )
        else:
            center = (
                "Not captured: click the window to capture (mouse + keyboard)\n"
                "Release: Ctrl+Alt"
            )
        self.center_label.setText(center)

    # -- status -----------------------------------------------------------

    def _poll_info(self) -> None:
        try:
            self._info = self._device.get_info()
            self._info_error = None
        except (CH9329FError, OSError) as exc:
            self._info = None
            self._info_error = str(exc)

    def _tick(self) -> None:
        # Refresh every tick so pressed-key state stays live; polling info
        # and updating the labels are both cheap.
        self._poll_info()
        self._update_labels()

    # -- Qt events --------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        if not self.captured:
            return
        delta = event.position().toPoint() - self._center()
        if delta.x() or delta.y():
            self._device.mouse.move(delta.x(), delta.y())
            self._warp_to_center()

    def mousePressEvent(self, event) -> None:
        if not self.captured:
            self._set_captured(True)
            return
        button = qt_button(event.button())
        if button is not None:
            self._device.mouse.button(button, True)

    def mouseReleaseEvent(self, event) -> None:
        if not self.captured:
            return
        button = qt_button(event.button())
        if button is not None:
            self._device.mouse.button(button, False)

    def wheelEvent(self, event) -> None:
        if not self.captured:
            return
        steps = int(event.angleDelta().y() / 120)
        if steps:
            self._device.mouse.wheel(steps)

    def keyPressEvent(self, event) -> None:
        if not self.captured:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            return
        keycode, modifier = map_key(event.key())
        if keycode or modifier:
            self._keyboard.press(keycode, modifier)

    def keyReleaseEvent(self, event) -> None:
        if not self.captured or event.isAutoRepeat():
            return
        keycode, modifier = map_key(event.key())
        if keycode or modifier:
            if self._keyboard.release(keycode, modifier):
                self._set_captured(False)

    def focusOutEvent(self, event) -> None:
        self._set_captured(False)
        super().focusOutEvent(event)

    def closeEvent(self, event) -> None:
        self._set_captured(False)
        self.timer.stop()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CH9329F mouse-forward Qt demo")
    parser.add_argument(
        "--port", default="COM6", help="serial port of the CH9329F UART side"
    )
    parser.add_argument(
        "--baudrate",
        "--baud",
        type=int,
        default=2_000_000,
        help="serial baudrate (must match the CH9329F configuration)",
    )
    parser.add_argument("--address", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument(
        "--report-rate",
        type=float,
        default=250.0,
        help="mouse reports per second (max 250, larger values are rejected)",
    )
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication(sys.argv)

    if not 0 < args.report_rate <= Mouse.MAX_REPORT_RATE:
        QtWidgets.QMessageBox.critical(
            None,
            "Invalid argument",
            f"--report-rate must be between 0 and {Mouse.MAX_REPORT_RATE:g} Hz",
        )
        return 2

    try:
        device = CH9329F.uart(
            args.port, args.baudrate, address=args.address, timeout=args.timeout
        )
    except Exception as exc:  # serial errors and similar
        QtWidgets.QMessageBox.critical(None, "Cannot open port", f"{args.port}: {exc}")
        return 1

    device.mouse.report_rate = args.report_rate

    mode_text, mode_warning = read_device_mode(device)
    label = f"Device: {args.port} @ {args.baudrate} | {mode_text}"

    window = CaptureWindow(
        device, label, warning=mode_warning, wait_ack=read_wait_ack(device)
    )
    window.show()
    try:
        return app.exec()
    finally:
        device.close()


if __name__ == "__main__":
    raise SystemExit(main())
