from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from .models import Command, MouseButton
from .protocol import CH9329FError

if TYPE_CHECKING:
    from .device import CH9329FDevice


class Keyboard:
    """Keyboard input helpers for a CH9329F protocol-mode device."""

    def __init__(self, device: "CH9329FDevice"):
        self._device = device

    def report(self, modifier: int = 0, keycodes: list[int] | None = None):
        keycodes = keycodes or []
        if len(keycodes) > 6:
            raise ValueError("at most 6 regular keys are allowed")
        data = bytes((modifier, 0, *keycodes, *([0] * (6 - len(keycodes)))))
        return self._device.transact(Command.KEYBOARD, data)

    def release(self) -> None:
        self.report()


def _clamp_step(value: int) -> int:
    return max(-127, min(127, value))


class Mouse:
    """Mouse input helpers for a CH9329F protocol-mode device.

    ``button()`` updates the button state and ``move()``/``wheel()``
    accumulate relative deltas; all of them return immediately and are
    transmitted by a background sender thread at ``report_rate`` reports per
    second (default 200; setting a rate above ``MAX_REPORT_RATE`` raises
    ``ValueError``). Accumulated deltas are split into <=127-step reports.
    Like a real mouse, the button state is sampled once per report, so
    changes faster than one report period can coalesce. ``move_to()`` sends
    its absolute report immediately and ``flush()`` drains pending state
    synchronously.

    Async send failures are recorded in ``error_count`` and ``last_error``
    and never raise from the sender thread. ``close()`` stops the thread and
    drops pending deltas.
    """

    MAX_REPORT_RATE = 250.0  # Hz; enforced ceiling for report_rate

    def __init__(self, device: "CH9329FDevice", *, report_rate: float = 200.0):
        self._device = device
        self.buttons: int = 0
        self.error_count = 0
        self.last_error: str | None = None
        self._lock = threading.Lock()
        self._dx = 0
        self._dy = 0
        self._dwheel = 0
        self._last_buttons = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._report_rate = 0.0
        self.report_rate = report_rate

    @property
    def report_rate(self) -> float:
        """Reports per second used to drain accumulated movement."""
        return self._report_rate

    @report_rate.setter
    def report_rate(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError("report rate must be positive")
        if rate > self.MAX_REPORT_RATE:
            raise ValueError(
                f"report rate must not exceed {self.MAX_REPORT_RATE:g} Hz"
            )
        self._report_rate = float(rate)

    def _ensure_thread(self) -> None:
        if self._stop.is_set():
            raise RuntimeError("mouse sender is closed")
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="ch9329f-mouse", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        # Pacing uses time.sleep(), which is high-resolution on Windows
        # (threading.Event.wait would be limited to the ~15.6 ms system
        # timer tick). Sleeps are sliced so close() stays responsive.
        next_send = time.monotonic() + 1.0 / self._report_rate
        while not self._stop.is_set():
            period = 1.0 / self._report_rate
            now = time.monotonic()
            if now >= next_send:
                self._send_one()
                next_send += period
                if next_send < now:
                    next_send = now + period
            else:
                time.sleep(min(next_send - now, 0.05))

    def _send_one(self) -> bool:
        """Send one report with the pending state; False when idle."""
        with self._lock:
            if not (
                self._dx
                or self._dy
                or self._dwheel
                or self.buttons != self._last_buttons
            ):
                return False
            step_x = _clamp_step(self._dx)
            step_y = _clamp_step(self._dy)
            step_wheel = _clamp_step(self._dwheel)
            data = bytes(
                (0x01, self.buttons, step_x & 0xFF, step_y & 0xFF, step_wheel & 0xFF)
            )
            try:
                self._device.transact(Command.MOUSE_RELATIVE, data)
            except (CH9329FError, OSError) as exc:
                self.error_count += 1
                self.last_error = str(exc)
                return False
            self._dx -= step_x
            self._dy -= step_y
            self._dwheel -= step_wheel
            self._last_buttons = self.buttons
            return True

    def move(self, dx: int = 0, dy: int = 0) -> None:
        """Accumulate a relative move of any magnitude."""
        if not (dx or dy):
            return
        with self._lock:
            self._dx += dx
            self._dy += dy
        self._ensure_thread()

    def wheel(self, steps: int) -> None:
        """Accumulate wheel steps of any magnitude."""
        if not steps:
            return
        with self._lock:
            self._dwheel += steps
        self._ensure_thread()

    def button(self, button: MouseButton, pressed: bool) -> None:
        """Update the button state; transmitted by the sender thread."""
        mask = int(MouseButton(button))
        with self._lock:
            if pressed:
                self.buttons |= mask
            else:
                self.buttons &= ~mask
        self._ensure_thread()

    def flush(self) -> None:
        """Send all pending movement synchronously."""
        while self._send_one():
            pass

    def close(self) -> None:
        """Stop the sender thread; pending deltas are dropped."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            self._thread = None

    def move_to(self, x: int, y: int) -> None:
        """Send an absolute position report immediately."""
        if not 0 <= x <= 4095 or not 0 <= y <= 4095:
            raise ValueError("absolute coordinates must be in range 0..4095")
        with self._lock:
            step_wheel = _clamp_step(self._dwheel)
            self._dwheel -= step_wheel
            data = bytes((0x02, self.buttons)) + x.to_bytes(2, "little")
            data += y.to_bytes(2, "little") + bytes((step_wheel & 0xFF,))
            self._device.transact(Command.MOUSE_ABSOLUTE, data)
            self._last_buttons = self.buttons
