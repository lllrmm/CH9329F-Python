# Usage notes

## Mouse is asynchronous

`Mouse.move()`, `wheel()` and `button()` accumulate state and return
immediately; a background sender thread drains it at `report_rate` reports per
second (default 200, hard maximum 250 - larger values raise `ValueError`).
`flush()` sends the pending state synchronously, `move_to()` sends an absolute
report immediately, and `close()` stops the thread. Send failures are recorded
in `error_count`/`last_error` and never raise from the sender thread.

## Configuration is read-only

`get_info()`, `get_config()`, `get_usb_string()` and `get_special_config()`
read device state. `DeviceConfig` parses the 50-byte parameter block, but only
protocol mode (CFG0) and work modes 0-2 are accepted; MODE3 values are
rejected. To change the chip configuration, use the WCH configuration tool
(`tools/set_wait_ack.py` shows how to write a special-config flag with raw
protocol commands).

`ch9329f.cfg0.parse_combo("ctrl+alt+delete")` returns the modifier/keycodes
pair accepted by `Keyboard.report()`.
